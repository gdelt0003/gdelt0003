"""Compare ten bilingual translation models and blindly judge a video sample."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import random
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

if __package__:
    from .process_full_video import (
        Cue,
        bilingual_srt_text,
        read_srt,
        srt_text,
    )
else:
    from process_full_video import (
        Cue,
        bilingual_srt_text,
        read_srt,
        srt_text,
    )


API_BASE = "https://openrouter.ai/api/v1"
SOURCE_PREFIX = "whitehouse-oW-PQlgw1wo"
TRANSLATION_MODELS = (
    "anthropic/claude-sonnet-4.6",
    "openai/gpt-4.1",
    "google/gemini-2.5-pro",
    "deepseek/deepseek-chat-v3.1",
    "qwen/qwen3.8-max-prime",
    "mistralai/mistral-medium-3-5",
    "moonshotai/kimi-k2.6",
    "x-ai/grok-4.7",
    "meta-llama/llama-4-maverick",
    "cohere/command-a",
)
JUDGE_MODELS = (
    "anthropic/claude-opus-5.5",
    "openai/gpt-5.6-luna-pro",
    "google/gemini-3.8-flash",
)
CONTEXT_SOURCES = (
    {
        "name": "White House official event video",
        "url": "https://www.whitehouse.gov/videos/president-trump-delivers-remarks-oct-6-2026/",
        "role": "official_event_metadata",
    },
    {
        "name": "Official White House YouTube recording",
        "url": "https://www.youtube.com/watch?v=oW-PQlgw1wo",
        "role": "primary_audio_video_source",
    },
    {
        "name": "The Singju Post transcript",
        "url": "https://singjupost.com/transcript-trump-delivers-remarks-at-anduril-industries-in-baltimore-md/",
        "role": "unverified_third_party_transcript",
    },
    {
        "name": "Reuters event reporting",
        "url": "https://www.reuters.com/business/aerospace-defense/anduril-us-navy-invest-66-bln-boost-submarine-parts-production-2026-10-06/",
        "role": "news_context_not_transcript",
    },
    {
        "name": "Associated Press event reporting",
        "url": "https://apnews.com/article/trump-baltimore-moore-submarines-midterms-1cacc864be999e71ef8bcf9b15e21cda",
        "role": "news_context_not_transcript",
    },
    {
        "name": "The Baltimore Sun event live coverage",
        "url": "https://www.baltimoresun.com/2026/10/06/trump-visits-sparrows-point-live-updates/",
        "role": "news_context_not_transcript",
    },
    {
        "name": "WUSA9 shipyard reporting",
        "url": "https://www.wusa9.com/video/news/politics/trump-announces-investment-at-baltimore-shipyard/65-badd42c3-9995-492a-b2fb-4df9f4953c33",
        "role": "news_context_not_transcript",
    },
)
TRANSLATION_BATCH_SIZE = 24
JUDGE_BATCH_SIZE = 6
MAX_TRANSLATION_TOKENS = 4096
MAX_JUDGE_TOKENS = 8192
@dataclass(frozen=True)
class CatalogModel:
    model_id: str
    prompt_price: float
    completion_price: float
    context_length: int


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.meta_description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self._hidden_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta" and attributes.get("name", "").lower() == "description":
            self.meta_description = attributes.get("content") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._hidden_depth:
            self._hidden_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        elif not self._hidden_depth:
            self.text_parts.append(value)


def fetch_json(url: str, *, timeout: int = 60) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "gdelt0003-subtitle-translation-review/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_context_sources() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for source in CONTEXT_SOURCES:
        record: dict[str, Any] = dict(source, fetch_status="not_fetched")
        request = urllib.request.Request(
            source["url"],
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; "
                    "gdelt0003-subtitle-review/1.0)"
                )
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                parser = VisibleTextParser()
                parser.feed(response.read(1_000_000).decode("utf-8", errors="replace"))
                visible = " ".join(parser.text_parts)
                record.update(
                    fetch_status="fetched",
                    http_status=response.status,
                    page_title=" ".join(parser.title_parts)[:300],
                    description=parser.meta_description[:1000],
                    excerpt=visible[:4000],
                )
        except urllib.error.HTTPError as error:
            record.update(
                fetch_status="blocked_or_unavailable",
                http_status=error.code,
                excerpt="",
            )
        except (TimeoutError, urllib.error.URLError) as error:
            record.update(
                fetch_status="unavailable",
                fetch_error=str(error)[:500],
                excerpt="",
            )
        results.append(record)
    return results


def load_catalog() -> dict[str, CatalogModel]:
    catalog = fetch_json(f"{API_BASE}/models")
    return {
        row["id"]: CatalogModel(
            model_id=row["id"],
            prompt_price=float(row["pricing"]["prompt"]),
            completion_price=float(row["pricing"]["completion"]),
            context_length=int(row.get("context_length") or 0),
        )
        for row in catalog.get("data", [])
        if row.get("id")
        and isinstance(row.get("pricing"), dict)
        and row["pricing"].get("prompt") is not None
        and row["pricing"].get("completion") is not None
    }


def resolve_required_models(
    catalog: dict[str, CatalogModel],
) -> tuple[list[CatalogModel], list[CatalogModel]]:
    required = (*TRANSLATION_MODELS, *JUDGE_MODELS)
    missing = [model_id for model_id in required if model_id not in catalog]
    if missing:
        raise RuntimeError(
            "These configured model IDs are not available in the live "
            "provider catalog: " + ", ".join(missing)
        )
    return (
        [catalog[model_id] for model_id in TRANSLATION_MODELS],
        [catalog[model_id] for model_id in JUDGE_MODELS],
    )


def _message_json(messages: list[dict[str, str]]) -> str:
    return json.dumps(messages, ensure_ascii=False, separators=(",", ":"))


def estimate_cost(
    translation_cues: list[tuple[int, float, float, str]],
    candidate_models: list[CatalogModel],
    judge_models: list[CatalogModel],
    sample_indices: list[int],
    *,
    batch_size: int = TRANSLATION_BATCH_SIZE,
    judge_batch_size: int = JUDGE_BATCH_SIZE,
) -> float:
    total = 0.0
    for model in candidate_models:
        for offset in range(0, len(translation_cues), batch_size):
            rows = translation_cues[offset:offset + batch_size]
            prompt = _translation_messages(rows)
            input_tokens = math.ceil(len(_message_json(prompt)) / 2.5)
            output_tokens = MAX_TRANSLATION_TOKENS
            total += (
                input_tokens * model.prompt_price
                + output_tokens * model.completion_price
            )
    by_index = {row[0]: row for row in translation_cues}
    for judge in judge_models:
        for offset in range(0, len(sample_indices), judge_batch_size):
            rows = [by_index[index] for index in sample_indices[offset:offset + judge_batch_size]]
            english_characters = sum(len(row[3]) for row in rows)
            estimated_review_characters = (
                english_characters
                * (1 + len(candidate_models) * 1.5)
                + 8000
            )
            input_tokens = math.ceil(estimated_review_characters * 1.1)
            output_tokens = MAX_JUDGE_TOKENS
            total += (
                input_tokens * judge.prompt_price
                + output_tokens * judge.completion_price
            )
    return total * 1.35


def _translation_messages(
    rows: list[tuple[int, float, float, str]],
) -> list[dict[str, str]]:
    source_rows = [{"index": row[0], "english": row[3]} for row in rows]
    return [
        {
            "role": "system",
            "content": (
                "Translate spoken English into faithful, natural Simplified "
                "Chinese subtitles. Preserve the speaker's meaning, register, "
                "negation, uncertainty, names, numbers, and claims; do not "
                "add information from outside the source. Keep each line "
                "aligned to its input index and concise for subtitles. Return "
                "only a JSON object of the form "
                '{"translations":[{"index":0,"text":"..."}]}. '
                "Translate all entries exactly once; do not combine lines."
            ),
        },
        {"role": "user", "content": json.dumps(source_rows, ensure_ascii=False)},
    ]


def _parse_json_content(content: str) -> Any:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        left = cleaned.find("{")
        right = cleaned.rfind("}")
        if left >= 0 and right > left:
            return json.loads(cleaned[left:right + 1])
        raise


def _request_model(
    model: CatalogModel,
    messages: list[dict[str, str]],
    token: str,
    *,
    max_tokens: int,
) -> tuple[str, float]:
    body = json.dumps(
        {
            "model": model.model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0,
            "usage": {"include": True},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/gdelt0003/gdelt0003",
            "X-Title": "White House bilingual subtitle review",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(
            f"Request to {model.model_id} failed with HTTP "
            f"{error.code}: {details}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Request to {model.model_id} failed without retry to avoid "
            f"potential duplicate charges: {error}"
        ) from error
    choices = payload.get("choices", [])
    if not choices:
        raise RuntimeError(
            f"{model.model_id} returned no completion choices."
        )
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(
            f"{model.model_id} returned an empty or non-text completion."
        )
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError(
            f"{model.model_id} response omitted billing usage; refusing "
            "to continue with an unverifiable spend total."
        )
    actual_cost = usage.get("cost")
    if actual_cost is None:
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if (
            type(prompt_tokens) is not int
            or prompt_tokens < 0
            or type(completion_tokens) is not int
            or completion_tokens < 0
        ):
            raise RuntimeError(
                f"{model.model_id} response omitted valid billing usage; "
                "refusing to continue with an unverifiable spend total."
            )
        actual_cost = (
            prompt_tokens * model.prompt_price
            + completion_tokens * model.completion_price
        )
    try:
        actual_cost = float(actual_cost)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            f"{model.model_id} returned an invalid billing cost."
        ) from error
    if not math.isfinite(actual_cost) or actual_cost < 0:
        raise RuntimeError(
            f"{model.model_id} returned an invalid billing cost."
        )
    return content, actual_cost


def translate_all(
    cues: list[tuple[int, float, float, str]],
    models: list[CatalogModel],
    token: str,
    cost_limit: float,
    already_spent: float,
) -> tuple[dict[str, list[str]], float]:
    translations: dict[str, list[str]] = {}
    spent = already_spent
    for model in models:
        values: list[str | None] = [None] * len(cues)
        for offset in range(0, len(cues), TRANSLATION_BATCH_SIZE):
            rows = cues[offset:offset + TRANSLATION_BATCH_SIZE]
            messages = _translation_messages(rows)
            request_reserve = (
                math.ceil(len(_message_json(messages)) * 1.1)
                * model.prompt_price
                + MAX_TRANSLATION_TOKENS * model.completion_price
            )
            if spent + request_reserve > cost_limit:
                raise RuntimeError(
                    f"Remaining authorized budget cannot cover the next "
                    f"{model.model_id} request (reserved ${request_reserve:.4f}; "
                    f"spent ${spent:.4f}; limit ${cost_limit:.2f})."
                )
            content, cost = _request_model(
                model,
                messages,
                token,
                max_tokens=MAX_TRANSLATION_TOKENS,
            )
            spent += cost
            if spent > cost_limit:
                raise RuntimeError(
                    f"Provider-reported spend ${spent:.4f} exceeds the "
                    f"authorized ${cost_limit:.2f} limit. Stop before further "
                    "requests; inspect partial artifacts."
                )
            result = _parse_json_content(content)
            records = result.get("translations") if isinstance(result, dict) else None
            if not isinstance(records, list):
                raise RuntimeError(
                    f"{model.model_id} batch {offset} returned no translations array."
                )
            batch_indices = {row[0] for row in rows}
            seen: set[int] = set()
            for record in records:
                if not isinstance(record, dict):
                    raise RuntimeError(
                        f"{model.model_id} returned a malformed translation record."
                    )
                index = record.get("index")
                text = record.get("text")
                if (
                    not isinstance(index, int)
                    or index not in batch_indices
                    or index in seen
                    or not isinstance(text, str)
                    or not text.strip()
                ):
                    raise RuntimeError(
                        f"{model.model_id} returned an invalid cue translation."
                    )
                seen.add(index)
                values[index] = text.strip()
            if seen != batch_indices:
                missing = sorted(batch_indices - seen)
                raise RuntimeError(
                    f"{model.model_id} omitted cue indices {missing[:10]}."
                )
            print(
                f"{model.model_id}: translated "
                f"{min(offset + len(rows), len(cues))}/{len(cues)} cues "
                f"(estimated/provider cost so far ${spent:.4f})",
                flush=True,
            )
        if any(value is None for value in values):
            raise RuntimeError(f"{model.model_id} did not translate every cue.")
        translations[model.model_id] = [str(value) for value in values]
    return translations, spent


def stratified_sample_indices(
    cues: list[tuple[int, float, float, str]],
    sample_size: int,
    seed: int,
) -> list[int]:
    if sample_size < 1:
        raise ValueError("The LLM review sample must include at least one cue.")
    count = len(cues)
    if count <= sample_size:
        return list(range(count))
    rng = random.Random(seed)
    high_risk = [
        index for index, cue in enumerate(cues)
        if re.search(r"\d|[A-Z][a-z]{2,}", cue[3])
    ]
    rng.shuffle(high_risk)
    chosen = set(high_risk[:sample_size // 3])
    remaining = sample_size - len(chosen)
    for offset in range(remaining):
        chosen.add(round(offset * (count - 1) / max(1, remaining - 1)))
    if len(chosen) > sample_size:
        removable = sorted(chosen - set(high_risk[:sample_size // 3]))
        while len(chosen) > sample_size and removable:
            chosen.remove(removable.pop())
    while len(chosen) < sample_size:
        for index in range(count):
            if index not in chosen:
                chosen.add(index)
                if len(chosen) == sample_size:
                    break
    return sorted(chosen)


def _source_context_for_judges(
    sources: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "name": source["name"],
            "url": source["url"],
            "role": source["role"],
            "status": source["fetch_status"],
            "title": source.get("page_title", ""),
            "context": (
                source.get("excerpt", "")
                or source.get("description", "")
            )[:2000],
        }
        for source in sources
    ]


def _judge_messages(
    rows: list[tuple[int, float, float, str]],
    translations: dict[str, list[str]],
    source_context: list[dict[str, str]],
    seed: int,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    rng = random.Random(seed)
    blind_maps: dict[str, dict[str, str]] = {}
    review_rows = []
    for cue_index, _start, _end, english in rows:
        model_ids = list(translations)
        rng.shuffle(model_ids)
        labels = [f"Candidate {chr(ord('A') + i)}" for i in range(len(model_ids))]
        blind_maps[str(cue_index)] = dict(zip(labels, model_ids, strict=True))
        review_rows.append(
            {
                "cue_index": cue_index,
                "source_english": english,
                "candidates": [
                    {
                        "candidate_id": label,
                        "simplified_chinese": translations[model_id][cue_index],
                    }
                    for label, model_id in zip(labels, model_ids, strict=True)
                ],
            }
        )
    messages = [
        {
            "role": "system",
            "content": (
                "You are an independent English-to-Simplified-Chinese subtitle "
                "quality judge. Score every anonymous candidate against its "
                "English source, not against the other candidates. Rate "
                "faithfulness, completeness, fluency, and terminology from 0 "
                "to 5 (5 best; use integers). Flag changed names/numbers, "
                "omissions, additions, wrong negation, or unsupported claims. "
                "News coverage is context only, never evidence of exact speech; "
                "an unverified transcript is not authoritative. Do not reward "
                "a candidate for agreeing with a report over the English "
                "source. Return only JSON: {\"scores\":[{\"cue_index\":0,"
                "\"candidate_id\":\"Candidate A\",\"faithfulness\":5,"
                "\"completeness\":5,\"fluency\":5,\"terminology\":5,"
                "\"flags\":[],\"reason\":\"short source-grounded reason\"}]}."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "source_context_not_transcript_evidence": source_context,
                    "items": review_rows,
                },
                ensure_ascii=False,
            ),
        },
    ]
    return messages, blind_maps


def judge_sample(
    cues: list[tuple[int, float, float, str]],
    translations: dict[str, list[str]],
    sample_indices: list[int],
    models: list[CatalogModel],
    sources: list[dict[str, Any]],
    token: str,
    cost_limit: float,
    already_spent: float,
    seed: int,
) -> tuple[list[dict[str, Any]], float]:
    by_index = {cue[0]: cue for cue in cues}
    context = _source_context_for_judges(sources)
    raw_scores: list[dict[str, Any]] = []
    spent = already_spent
    for judge_number, model in enumerate(models):
        for offset in range(0, len(sample_indices), JUDGE_BATCH_SIZE):
            batch_indices = sample_indices[offset:offset + JUDGE_BATCH_SIZE]
            rows = [by_index[index] for index in batch_indices]
            messages, blind_maps = _judge_messages(
                rows,
                translations,
                context,
                seed + judge_number * 10000 + offset,
            )
            request_reserve = (
                math.ceil(len(_message_json(messages)) * 1.1)
                * model.prompt_price
                + MAX_JUDGE_TOKENS * model.completion_price
            )
            if spent + request_reserve > cost_limit:
                raise RuntimeError(
                    f"Remaining authorized budget cannot cover the next "
                    f"{model.model_id} review request (reserved "
                    f"${request_reserve:.4f}; spent ${spent:.4f}; "
                    f"limit ${cost_limit:.2f})."
                )
            content, cost = _request_model(
                model,
                messages,
                token,
                max_tokens=MAX_JUDGE_TOKENS,
            )
            spent += cost
            if spent > cost_limit:
                raise RuntimeError(
                    f"Provider-reported spend ${spent:.4f} exceeds the "
                    f"authorized ${cost_limit:.2f} limit. Stop before further "
                    "requests; inspect partial artifacts."
                )
            result = _parse_json_content(content)
            records = result.get("scores") if isinstance(result, dict) else None
            if not isinstance(records, list):
                raise RuntimeError(
                    f"{model.model_id} review batch {offset} returned no scores array."
                )
            allowed = {
                (index, label)
                for index, mapping in blind_maps.items()
                for label in mapping
            }
            seen: set[tuple[int, str]] = set()
            for record in records:
                if not isinstance(record, dict):
                    raise RuntimeError(
                        f"{model.model_id} returned a malformed score."
                    )
                cue_index = record.get("cue_index")
                candidate_id = record.get("candidate_id")
                if type(cue_index) is not int or not isinstance(candidate_id, str):
                    raise RuntimeError(
                        f"{model.model_id} returned an invalid cue/candidate ID."
                    )
                key = (cue_index, candidate_id)
                if key not in allowed or key in seen:
                    raise RuntimeError(
                        f"{model.model_id} returned a duplicate or unknown "
                        "cue/candidate score."
                    )
                criteria = ("faithfulness", "completeness", "fluency", "terminology")
                if any(
                    type(record.get(name)) is not int
                    or not 0 <= record[name] <= 5
                    for name in criteria
                ):
                    raise RuntimeError(
                        f"{model.model_id} returned out-of-range review scores."
                    )
                flags = record.get("flags", [])
                reason = record.get("reason", "")
                if (
                    not isinstance(flags, list)
                    or any(not isinstance(flag, str) for flag in flags)
                    or not isinstance(reason, str)
                ):
                    raise RuntimeError(
                        f"{model.model_id} returned malformed review notes."
                    )
                seen.add(key)
                raw_scores.append(
                    {
                        "judge_model": model.model_id,
                        "cue_index": cue_index,
                        "candidate_id": candidate_id,
                        "translation_model": blind_maps[str(cue_index)][candidate_id],
                        **{name: record[name] for name in criteria},
                        "flags": flags,
                        "reason": reason[:1000],
                    }
                )
            if seen != allowed:
                missing = len(allowed - seen)
                raise RuntimeError(
                    f"{model.model_id} omitted {missing} cue/candidate scores."
                )
        print(
            f"{model.model_id}: blindly scored {len(sample_indices)} cues "
            f"(spend so far ${spent:.4f})",
            flush=True,
        )
    return raw_scores, spent


def aggregate_scores(scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for score in scores:
        by_model.setdefault(score["translation_model"], []).append(score)
    rankings = []
    for model_id, rows in by_model.items():
        score_100 = sum(
            row["faithfulness"] * 0.40
            + row["completeness"] * 0.25
            + row["fluency"] * 0.25
            + row["terminology"] * 0.10
            for row in rows
        ) / len(rows) * 20
        flagged = sum(bool(row["flags"]) for row in rows)
        rankings.append(
            {
                "model": model_id,
                "mean_score_100": round(score_100, 2),
                "reviewed_cues": len({row["cue_index"] for row in rows}),
                "judgments": len(rows),
                "flagged_judgments": flagged,
            }
        )
    return sorted(
        rankings,
        key=lambda row: (
            row["mean_score_100"],
            -row["flagged_judgments"],
            row["model"],
        ),
        reverse=True,
    )


def _write_outputs(
    output_dir: Path,
    cues: list[tuple[int, float, float, str]],
    translations: dict[str, list[str]],
    rankings: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    spent: float,
    estimated_cost: float,
    sample_indices: list[int],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for model_id, translated in translations.items():
        safe_name = re.sub(r"[^a-zA-Z0-9.-]+", "-", model_id).strip("-")
        model_cues = [
            Cue(start, end, english, translated[index])
            for index, start, end, english in cues
        ]
        (output_dir / f"{SOURCE_PREFIX}.{safe_name}.zh-Hans.srt").write_text(
            srt_text(model_cues, "zh"),
            encoding="utf-8",
        )
        (output_dir / f"{SOURCE_PREFIX}.{safe_name}.en-zh.srt").write_text(
            bilingual_srt_text(model_cues),
            encoding="utf-8",
        )
    winner = rankings[0]["model"]
    winner_cues = [
        Cue(start, end, english, translations[winner][index])
        for index, start, end, english in cues
    ]
    (output_dir / f"{SOURCE_PREFIX}.winner.zh-Hans.srt").write_text(
        srt_text(winner_cues, "zh"),
        encoding="utf-8",
    )
    (output_dir / f"{SOURCE_PREFIX}.winner.en-zh.srt").write_text(
        bilingual_srt_text(winner_cues),
        encoding="utf-8",
    )
    report = {
        "source_video_id": "oW-PQlgw1wo",
        "source_video_title": "President Trump Delivers Remarks, Oct. 6, 2026",
        "english_cues": len(cues),
        "translation_models": list(translations),
        "llm_judges": list(JUDGE_MODELS),
        "blind_review_sample_indices_zero_based": sample_indices,
        "reviewed_cue_count": len(sample_indices),
        "ranking_scope": (
            "Blind LLM review of a stratified sample only; not human-certified "
            "and not proof that exact spoken wording was verified."
        ),
        "context_sources": sources,
        "transcript_note": (
            "The official recording is the authority for words spoken. "
            "YouTube captions are ASR; the third-party transcript, if fetched, "
            "is unverified. News reports corroborate event context only."
        ),
        "estimated_max_cost_usd": round(estimated_cost, 4),
        "billing_cost_usd": round(spent, 6),
        "billing_cost_note": (
            "Provider-reported where supplied by the inference API; otherwise "
            "calculated from returned token usage and the live model catalog."
        ),
        "ranking": rankings,
        "scores": scores,
    }
    (output_dir / "translation-review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Translate all English SRT cues with ten OpenRouter models, "
            "retrieve web context, and blind-score a stratified sample."
        )
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        required=True,
        help="Required hard spending ceiling in USD; requests stop above it.",
    )
    parser.add_argument("--sample-size", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20261006)
    args = parser.parse_args()
    if not math.isfinite(args.max_cost_usd) or args.max_cost_usd <= 0:
        parser.error("--max-cost-usd must be a finite number greater than zero.")
    if args.sample_size < 1:
        parser.error("--sample-size must be at least one.")
    api_token = os.environ.get("OPENROUTER_API_KEY")
    if not api_token:
        raise RuntimeError(
            "OPENROUTER_API_KEY is missing; no billable requests were made."
        )

    prefix = SOURCE_PREFIX
    english = read_srt(args.input_dir / f"{prefix}.en.srt")
    chinese = read_srt(args.input_dir / f"{prefix}.zh-Hans.srt")
    if not english or len(english) != len(chinese):
        raise RuntimeError(
            "Expected non-empty, cue-aligned English and Chinese source SRTs."
        )
    for index, (en, zh) in enumerate(zip(english, chinese, strict=True)):
        if abs(en[0] - zh[0]) > 0.01 or abs(en[1] - zh[1]) > 0.01:
            raise RuntimeError(f"Existing SRT timing mismatch at cue {index}.")
    cues = [
        (index, start, end, text.replace("\n", " "))
        for index, (start, end, text) in enumerate(english)
    ]
    sample_indices = stratified_sample_indices(
        cues,
        min(args.sample_size, len(cues)),
        args.seed,
    )
    catalog = load_catalog()
    candidate_models, judge_models = resolve_required_models(catalog)
    estimated_cost = estimate_cost(
        cues,
        candidate_models,
        judge_models,
        sample_indices,
    )
    if estimated_cost > args.max_cost_usd:
        raise RuntimeError(
            f"Preflight estimated cost ${estimated_cost:.2f}, above the "
            f"authorized ${args.max_cost_usd:.2f} ceiling; no model requests "
            "were made. Raise the explicit ceiling or reduce the judge sample."
        )
    print(
        f"Cost preflight: estimated worst-case ${estimated_cost:.4f}; "
        f"authorized ceiling ${args.max_cost_usd:.2f}; "
        f"{len(candidate_models)} translation models; "
        f"{len(judge_models)} blind judges; "
        f"{len(cues)} cues; {len(sample_indices)} judged cues.",
        flush=True,
    )
    sources = fetch_context_sources()
    for source in sources:
        print(
            f"Reference: {source['name']} — {source['fetch_status']}"
            + (
                f" (HTTP {source['http_status']})"
                if source.get("http_status")
                else ""
            ),
            flush=True,
        )
    translations, spent = translate_all(
        cues,
        candidate_models,
        api_token,
        args.max_cost_usd,
        0.0,
    )
    scores, spent = judge_sample(
        cues,
        translations,
        sample_indices,
        judge_models,
        sources,
        api_token,
        args.max_cost_usd,
        spent,
        args.seed,
    )
    rankings = aggregate_scores(scores)
    _write_outputs(
        args.output_dir,
        cues,
        translations,
        rankings,
        scores,
        sources,
        spent,
        estimated_cost,
        sample_indices,
    )
    print(
        json.dumps(
            {
                "provisional_winner": rankings[0],
                "next_best": rankings[1:3],
                "estimated_cost_usd": round(estimated_cost, 4),
                "billing_cost_usd": round(spent, 6),
                "artifacts": str(args.output_dir.resolve()),
                "publish_warning": (
                    "Winner is based on blind LLM review of a sample only. "
                    "Do not publish as verified until the full transcript is "
                    "checked against the official recording and a human "
                    "reviewer resolves flagged cues."
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
