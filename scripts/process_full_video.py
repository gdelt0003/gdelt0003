"""Transcribe, translate, and burn bilingual captions into a full video."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from importlib.metadata import version as package_version
from pathlib import Path

if __package__:
    from .operation_audit import (
        OperationAudit,
        current_pipeline_version,
        current_task_id,
    )
else:
    from operation_audit import (
        OperationAudit,
        current_pipeline_version,
        current_task_id,
    )


ASR_MODEL = "large-v3-turbo"
TRANSLATION_MODEL = "facebook/m2m100_1.2B"
MAX_RELEASE_ASSET_BYTES = 1_950_000_000
MIN_SUBTITLE_CUE_SECONDS = 0.83
MAX_FRAGMENT_GAP_SECONDS = 1.25
CAPTION_LOWER_MARGIN_PERCENT = 18


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    english: str
    chinese: str


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode:
        details = result.stderr.strip() if capture and result.stderr else ""
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}"
            + (f"\n{details}" if details else "")
        )
    return result.stdout if capture else ""


def timestamp(seconds: float, *, decimal: str) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole, milliseconds = divmod(milliseconds, 1000)
    return (
        f"{hours:02}:{minutes:02}:{whole:02}"
        f"{decimal}{milliseconds:03}"
    )


def srt_text(cues: list[Cue], language: str) -> str:
    rows = []
    for index, cue in enumerate(cues, start=1):
        text = cue.english if language == "en" else cue.chinese
        rows.append(
            f"{index}\n{timestamp(cue.start, decimal=',')} --> "
            f"{timestamp(cue.end, decimal=',')}\n{text}"
        )
    return "\n\n".join(rows) + "\n"


def bilingual_srt_text(cues: list[Cue]) -> str:
    rows = []
    for index, cue in enumerate(cues, start=1):
        rows.append(
            f"{index}\n{timestamp(cue.start, decimal=',')} --> "
            f"{timestamp(cue.end, decimal=',')}\n"
            f"{cue.chinese}\n{cue.english}"
        )
    return "\n\n".join(rows) + "\n"


def ass_escape(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r", "")
        .replace("\n", " ")
    )


def ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    whole, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{whole:02}.{fraction:02}"


def _split_aligned_clauses(english: str, chinese: str) -> list[tuple[str, str]]:
    english_sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", english.strip())
        if part.strip()
    ]
    chinese_sentences = [
        part.strip()
        for part in re.split(r"(?<=[。！？])", chinese.strip())
        if part.strip()
    ]
    if len(english_sentences) == len(chinese_sentences) > 1:
        return list(zip(english_sentences, chinese_sentences, strict=True))

    english_comma_parts = [
        part.strip()
        for part in re.split(r"(?<=,)\s*", english.strip())
        if part.strip()
    ]
    chinese_comma_parts = [
        part.strip()
        for part in re.split(r"(?<=[，,])", chinese.strip())
        if part.strip()
    ]
    if len(english_comma_parts) == len(chinese_comma_parts) > 1:
        english_total = max(1, len(english.split()))
        chinese_total = max(
            1,
            sum("\u3400" <= char <= "\u9fff" for char in chinese),
        )
        aligned = True
        english_seen = 0
        chinese_seen = 0
        for english_part, chinese_part in zip(
            english_comma_parts[:-1],
            chinese_comma_parts[:-1],
            strict=True,
        ):
            english_seen += len(english_part.split())
            chinese_seen += sum(
                "\u3400" <= char <= "\u9fff" for char in chinese_part
            )
            if (
                not english_seen
                or not chinese_seen
                or abs(
                    english_seen / english_total
                    - chinese_seen / chinese_total
                ) > 0.25
            ):
                aligned = False
                break
        if aligned:
            return list(
                zip(
                    english_comma_parts,
                    chinese_comma_parts,
                    strict=True,
                )
            )

    chinese_connectors = {
        "and": ("以及", "并且", "而且", "和"),
        "but": ("但是", "不过", "但"),
        "because": ("因为", "由于"),
        "so": ("因此", "所以"),
        "or": ("或者", "或"),
    }
    english_words = list(re.finditer(r"\b(?:and|but|because|so|or)\b", english, re.I))
    chinese_chars = sum("\u3400" <= char <= "\u9fff" for char in chinese)
    candidates: list[tuple[float, int, int]] = []
    for english_match in english_words:
        word = english_match.group().lower()
        english_prefix_words = len(english[:english_match.start()].split())
        english_total_words = max(1, len(english.split()))
        if english_prefix_words < 4 or english_total_words - english_prefix_words < 4:
            continue
        for connector in chinese_connectors[word]:
            position = chinese.find(connector)
            if position < 0:
                continue
            chinese_prefix_chars = sum(
                "\u3400" <= char <= "\u9fff"
                for char in chinese[:position]
            )
            chinese_suffix_chars = chinese_chars - chinese_prefix_chars
            if chinese_prefix_chars < 4 or chinese_suffix_chars < 4:
                continue
            english_ratio = english_prefix_words / english_total_words
            chinese_ratio = chinese_prefix_chars / max(1, chinese_chars)
            difference = abs(english_ratio - chinese_ratio)
            if difference <= 0.20:
                candidates.append(
                    (difference, english_match.start(), position)
                )
    if not candidates:
        return [(english.strip(), chinese.strip())]

    _difference, english_cut, chinese_cut = min(candidates)
    return [
        (english[:english_cut].strip(), chinese[:chinese_cut].strip()),
        (english[english_cut:].strip(), chinese[chinese_cut:].strip()),
    ]


def _ends_sentence(text: str) -> bool:
    trimmed = text.rstrip("\"'”’)]} ")
    if not re.search(r"[.!?…]+$", trimmed):
        return False
    if re.search(
        r"\b(?:mr|mrs|ms|dr|prof|sr|jr|u\.s|u\.k|inc|etc|vs)\.$",
        trimmed,
        re.I,
    ):
        return False
    return True


def _join_english_fragments(parts: list[str]) -> str:
    result = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if result and not re.match(r"^[,.;:!?%)\]}”’]", part):
            result += " "
        result += part
    return result


def _join_chinese_fragments(parts: list[str]) -> str:
    result = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if result and result[-1:].isascii() and part[:1].isascii():
            result += " "
        result += part
    return result


def merge_sentence_fragments(cues: list[Cue]) -> list[Cue]:
    """Join ASR-sized fragments so translations stay with their full sentence."""
    if not cues:
        return []

    merged: list[Cue] = []
    group = [cues[0]]

    def flush() -> None:
        if not group:
            return
        merged.append(
            Cue(
                group[0].start,
                group[-1].end,
                _join_english_fragments([cue.english for cue in group]),
                _join_chinese_fragments([cue.chinese for cue in group]),
            )
        )

    for cue in cues[1:]:
        previous = group[-1]
        gap = cue.start - previous.end
        if _ends_sentence(previous.english) or gap > MAX_FRAGMENT_GAP_SECONDS:
            flush()
            group = []
        group.append(cue)
    flush()
    return merged


def reflow_cues(cues: list[Cue]) -> list[Cue]:
    reflowed = []

    for cue in cues:
        duration = cue.end - cue.start
        if duration <= 0:
            continue
        aligned_clauses = _split_aligned_clauses(cue.english, cue.chinese)
        clause_weights = [
            max(1, len(english.split()))
            for english, _ in aligned_clauses
        ]
        if (
            len(aligned_clauses) > 1
            and duration * min(clause_weights) / sum(clause_weights)
            < MIN_SUBTITLE_CUE_SECONDS
        ):
            aligned_clauses = [(cue.english, cue.chinese)]
            clause_weights = [max(1, len(cue.english.split()))]
        total_weight = sum(clause_weights)
        elapsed_weight = 0
        start = cue.start
        for index, (english, chinese) in enumerate(aligned_clauses):
            elapsed_weight += clause_weights[index]
            end = cue.end if index == len(aligned_clauses) - 1 else (
                cue.start + duration * elapsed_weight / total_weight
            )
            reflowed.append(Cue(start, end, english, chinese))
            start = end
    return reflowed


def _wrap_english(text: str, max_chars: int, max_lines: int = 2) -> list[str]:
    lines = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        midpoint = (len(lines) + max_lines - 1) // max_lines
        lines = [
            " ".join(lines[index:index + midpoint])
            for index in range(0, len(lines), midpoint)
        ]
    return lines[:max_lines]


def _wrap_chinese(text: str, max_chars: int, max_lines: int = 2) -> list[str]:
    characters = list(text.strip())
    if not characters:
        return []
    lines = []
    start = 0
    while start < len(characters):
        end = min(start + max_chars, len(characters))
        if end < len(characters):
            punctuation = next(
                (
                    index + 1
                    for index in range(start, min(end + 1, len(characters)))
                    if characters[index] in "，。！？；：、,.!?;"
                ),
                None,
            )
            if punctuation is not None and punctuation > start:
                end = punctuation
        lines.append("".join(characters[start:end]))
        start = end
    if len(lines) > max_lines:
        midpoint = (len(lines) + max_lines - 1) // max_lines
        lines = [
            "".join(lines[index:index + midpoint])
            for index in range(0, len(lines), midpoint)
        ]
    return lines[:max_lines]


def write_ass(path: Path, cues: list[Cue], width: int, height: int) -> None:
    chinese_font = max(32, round(height * 0.052))
    english_font = max(34, round(chinese_font * 1.22))
    safe_width = round(width * 0.78)
    max_english_chars = max(20, int(safe_width / (english_font * 0.55)))
    max_chinese_chars = max(10, int(safe_width / chinese_font))
    margin = max(28, round(height * CAPTION_LOWER_MARGIN_PERCENT / 100))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Chinese,Noto Sans CJK SC,{chinese_font},&H004DD8FF,&H000000FF,&H00101010,&H70000000,1,0,0,0,100,100,0,0,3,6,0,2,{round(width * 0.11)},{round(width * 0.11)},{margin},1
Style: English,Noto Sans CJK SC,{english_font},&H00FFFFFF,&H000000FF,&H00101010,&H70000000,1,0,0,0,100,100,0,0,3,6,0,2,{round(width * 0.11)},{round(width * 0.11)},{margin},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header]
    for cue in cues:
        chinese_lines = _wrap_chinese(cue.chinese, max_chinese_chars)
        english_lines = _wrap_english(cue.english, max_english_chars)
        dialogue_lines = [
            *(f"{{\\rChinese}}{ass_escape(line)}" for line in chinese_lines),
            *(f"{{\\rEnglish}}{ass_escape(line)}" for line in english_lines),
        ]
        if not dialogue_lines:
            continue
        dialogue_text = r"\N".join(dialogue_lines)
        lines.append(
            f"Dialogue: 0,{ass_time(cue.start)},{ass_time(cue.end)},"
            f"Chinese,,0,0,0,,{dialogue_text}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_cues(
    cues: list[Cue],
    *,
    duration: float,
    width: int,
    height: int,
    translation_review: dict[str, object] | None = None,
    visual_review: dict[str, object] | None = None,
) -> dict[str, object]:
    if not cues:
        raise RuntimeError("Caption verification failed: there are no cues.")
    if width <= 0 or height <= 0:
        raise RuntimeError("Caption verification failed: invalid video dimensions.")
    previous_end = 0.0
    english_rate_flags = []
    chinese_rate_flags = []
    for index, cue in enumerate(cues, start=1):
        if not cue.english.strip() or not cue.chinese.strip():
            raise RuntimeError(
                f"Caption verification failed: cue {index} is missing a language."
            )
        if cue.start < 0 or cue.end <= cue.start or cue.end > duration + 0.01:
            raise RuntimeError(
                f"Caption verification failed: cue {index} has invalid timing."
            )
        if index > 1 and cue.start < previous_end - 0.02:
            raise RuntimeError(
                f"Caption verification failed: cue {index} overlaps its predecessor."
            )
        cue_duration = cue.end - cue.start
        if len(cue.english) / cue_duration > 20:
            english_rate_flags.append(index)
        chinese_characters = sum(
            "\u3400" <= char <= "\u9fff" for char in cue.chinese
        )
        if chinese_characters / cue_duration > 10:
            chinese_rate_flags.append(index)
        previous_end = cue.end

    chinese_font = max(32, round(height * 0.052))
    english_font = max(34, round(chinese_font * 1.22))
    if english_font / chinese_font < 1.20:
        raise RuntimeError(
            "Caption verification failed: English text is not at least 20% larger."
        )
    review = translation_review or {}
    visual = visual_review or {}

    def review_count(field: str) -> int:
        value = review.get(field, 0)
        return value if type(value) is int and value >= 0 else 0

    return {
        "structural_checks": "passed",
        "bilingual_cue_sync": {
            "status": "passed",
            "scope": "both languages share the same phrase-level cue timing",
            "audio_level_alignment": (
                "passed"
                if review.get("audio_level_alignment") is True
                else "not_verified"
            ),
        },
        "cue_timing": "passed",
        "source_resolution": "passed",
        "subtitle_readability": {
            "status": (
                "style_contract_passed"
                if not english_rate_flags and not chinese_rate_flags
                else "manual_review_required"
            ),
            "english_font_px": english_font,
            "chinese_font_px": chinese_font,
            "english_to_chinese_size_ratio": round(
                english_font / chinese_font, 3
            ),
            "horizontal_safe_width_percent": 78,
            "lower_margin_percent": CAPTION_LOWER_MARGIN_PERCENT,
            "max_lines_per_language": 2,
            "english_reading_speed_over_20_cps_cues": english_rate_flags,
            "chinese_reading_speed_over_10_cps_cues": chinese_rate_flags,
            "visual_frame_review": (
                "passed" if visual.get("status") == "passed" else "required"
            ),
        },
        "translation_accuracy": {
            "status": (
                review.get("status")
                if review.get("status") in {"verified", "not_verified"}
                else "not_verified"
            ),
            "audio_level_alignment": (
                "passed" if review.get("audio_level_alignment") is True
                else "not_verified"
            ),
            "source_audio_review": (
                "passed" if review.get("source_audio_review") is True
                else "required"
            ),
            "independent_translation_review": (
                "passed"
                if review.get("independent_translation_review") is True
                else "required"
            ),
            "translation_models_compared": review_count(
                "translation_models_compared"
            ),
            "llm_judges": review_count("llm_judges"),
            "source_cross_check_passes": review_count(
                "source_cross_check_passes"
            ),
        },
    }


def vtt_from_bilingual_srt(content: str) -> str:
    timing = re.compile(
        r"(\d{2}:\d{2}:\d{2}),(\d{3})( --> "
        r"\d{2}:\d{2}:\d{2}),(\d{3})"
    )
    return "WEBVTT\n\n" + timing.sub(r"\1.\2\3.\4", content)


def translate_batches(
    texts: list[str],
    *,
    batch_size: int = 8,
    audit: OperationAudit | None = None,
    asset_id: str = "unassigned",
    parent_operation_id: str | None = None,
) -> list[str]:
    import torch
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

    model_id = TRANSLATION_MODEL

    def load_model():
        tokenizer = M2M100Tokenizer.from_pretrained(model_id, src_lang="en")
        model = M2M100ForConditionalGeneration.from_pretrained(model_id)
        model.eval()
        return tokenizer, model

    transformers_version = "unrecorded"
    if audit is None:
        tokenizer, model = load_model()
    else:
        with audit.record(
            "translation_model_load",
            asset_id=asset_id,
            tool="Hugging Face Transformers",
            version=f"model={model_id}",
            details={"parent_operation_id": parent_operation_id},
        ) as operation:
            transformers_version = package_version("transformers")
            operation["version"] = (
                f"model={model_id}; transformers={transformers_version}"
            )
            tokenizer, model = load_model()
    target_language = tokenizer.get_lang_id("zh")
    translated: list[str] = []

    with torch.inference_mode():
        for batch_index, offset in enumerate(
            range(0, len(texts), batch_size),
            start=1,
        ):
            batch = texts[offset:offset + batch_size]
            def translate_batch() -> list[str]:
                encoded = tokenizer(
                    batch,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=512,
                )
                generated = model.generate(
                    **encoded,
                    forced_bos_token_id=target_language,
                    num_beams=4,
                    max_new_tokens=256,
                )
                return [
                    value.strip()
                    for value in tokenizer.batch_decode(
                        generated,
                        skip_special_tokens=True,
                    )
                ]

            if audit is None:
                batch_translations = translate_batch()
            else:
                with audit.record(
                    "translation_batch",
                    asset_id=asset_id,
                    tool="Hugging Face Transformers",
                    version=(
                        f"model={model_id}; transformers="
                        f"{transformers_version}"
                    ),
                    details={
                        "parent_operation_id": parent_operation_id,
                        "batch_index": batch_index,
                        "first_cue_index": offset,
                        "cue_count": len(batch),
                    },
                ):
                    batch_translations = translate_batch()
            translated.extend(batch_translations)
            print(
                f"Translated {min(offset + len(batch), len(texts))}"
                f"/{len(texts)} subtitle cues",
                flush=True,
            )
    return translated


def probe_video(path: Path) -> tuple[float, int, int]:
    details = json.loads(run([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-show_entries",
        "stream=codec_type,width,height",
        "-of",
        "json",
        str(path),
    ], capture=True))
    video = next(
        (stream for stream in details.get("streams", [])
         if stream.get("codec_type") == "video"),
        None,
    )
    if video is None:
        raise RuntimeError(f"No video stream found in {path.name}")
    return (
        float(details["format"]["duration"]),
        int(video["width"]),
        int(video["height"]),
    )


def validate_output_prefix(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", value):
        raise ValueError(
            "Output prefix must be 1-100 letters, digits, dots, underscores, or hyphens."
        )
    return value


def _parse_timestamp(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def read_srt(path: Path) -> list[tuple[float, float, str]]:
    content = path.read_text(encoding="utf-8-sig")
    rows = []
    timing = re.compile(
        r"(?m)^(\d{2}:\d{2}:\d{2}),(\d{3}) --> "
        r"(\d{2}:\d{2}:\d{2}),(\d{3})$"
    )
    for block in re.split(r"\r?\n\s*\r?\n", content.strip()):
        match = timing.search(block)
        if not match:
            continue
        lines = block.splitlines()
        text = "\n".join(
            line.strip()
            for line in lines
            if line.strip() and not line.strip().isdigit()
            and "-->" not in line
        )
        start = _parse_timestamp(f"{match.group(1)}.{match.group(2)}")
        end = _parse_timestamp(f"{match.group(3)}.{match.group(4)}")
        if text and end > start:
            rows.append((start, end, text))
    return rows


def copy_review_evidence(
    source_dir: Path,
    output_dir: Path,
    translation_review: dict[str, object],
    visual_review: dict[str, object],
) -> None:
    evidence_records = []
    for field in (
        "models",
        "judges",
        "source_cross_checks",
        "source_audio_passes",
    ):
        records = translation_review.get(field, [])
        if isinstance(records, list):
            evidence_records.extend(
                record for record in records if isinstance(record, dict)
            )
    frames = visual_review.get("frames", [])
    if isinstance(frames, list):
        evidence_records.extend(
            record for record in frames if isinstance(record, dict)
        )

    source_root = source_dir.resolve()
    output_root = output_dir.resolve()
    for record in evidence_records:
        relative_path = record.get("evidence_file")
        if not isinstance(relative_path, str) or not relative_path.strip():
            continue
        source_path = (source_root / relative_path).resolve()
        output_path = (output_root / relative_path).resolve()
        try:
            source_path.relative_to(source_root)
            output_path.relative_to(output_root)
        except ValueError as error:
            raise RuntimeError(
                "Review evidence path must stay within its manifest directory."
            ) from error
        if not source_path.is_file():
            raise FileNotFoundError(
                f"Review evidence file is missing: {source_path}"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--output-prefix",
        type=validate_output_prefix,
        default="whitehouse-oW-PQlgw1wo",
        help="Filename prefix for generated video, subtitles, and manifest.",
    )
    parser.add_argument("--event-id", help="Verified event key to record in the manifest.")
    parser.add_argument(
        "--reuse-subtitles",
        type=Path,
        help="Reuse existing English and Chinese SRT files instead of rerunning ASR and translation.",
    )
    args = parser.parse_args()

    source = args.input.resolve()
    output_dir = args.output_dir.resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise FileNotFoundError(f"Input video is missing or empty: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = OperationAudit(
        output_dir / "operation-audit.json",
        task_id=current_task_id(),
        pipeline_version=current_pipeline_version(),
    )

    duration, width, height = probe_video(source)
    language_probability = None
    translation_models_used = (
        [] if args.reuse_subtitles else [TRANSLATION_MODEL]
    )
    translation_review: dict[str, object] = {}
    visual_review: dict[str, object] = {}
    if args.reuse_subtitles:
        prefix = "whitehouse-oW-PQlgw1wo"
        prior_manifest_path = args.reuse_subtitles / "manifest.json"
        if prior_manifest_path.is_file():
            prior_manifest = json.loads(
                prior_manifest_path.read_text(encoding="utf-8")
            )
            prior_review = prior_manifest.get("translation_review")
            if isinstance(prior_review, dict):
                translation_review = prior_review
            prior_visual_review = prior_manifest.get("visual_review")
            if isinstance(prior_visual_review, dict):
                visual_review = prior_visual_review
            copy_review_evidence(
                args.reuse_subtitles,
                output_dir,
                translation_review,
                visual_review,
            )
            prior_models = prior_manifest.get("translation_models_used")
            translation_models_used = (
                [model for model in prior_models if isinstance(model, str)]
                if isinstance(prior_models, list)
                else []
            )
            if not translation_models_used:
                prior_translation_model = prior_manifest.get(
                    "translation_model"
                )
                translation_models_used = (
                    [prior_translation_model]
                    if isinstance(prior_translation_model, str)
                    and prior_translation_model
                    else []
                )
        english_cues = read_srt(
            args.reuse_subtitles / f"{prefix}.en.srt"
        )
        chinese_cues = read_srt(
            args.reuse_subtitles / f"{prefix}.zh-Hans.srt"
        )
        if len(english_cues) != len(chinese_cues):
            raise RuntimeError(
                "English and Chinese subtitle files have different cue counts."
            )
        cues = [
            Cue(
                en_start,
                min(duration, en_end),
                english,
                chinese,
            )
            for (en_start, en_end, english), (
                zh_start,
                zh_end,
                chinese,
            ) in zip(english_cues, chinese_cues, strict=True)
            if abs(en_start - zh_start) <= 0.01
            and abs(en_end - zh_end) <= 0.01
            and en_start < duration
        ]
        if len(cues) != len(english_cues):
            raise RuntimeError(
                "English and Chinese SRT timings do not match, or a cue "
                "extends beyond the source video."
            )
        cues = merge_sentence_fragments(cues)
    else:
        with audit.record(
            "asr",
            asset_id=source.name,
            tool="faster-whisper",
            version=f"model={ASR_MODEL}",
        ) as operation:
            operation["version"] = (
                f"model={ASR_MODEL}; "
                f"faster-whisper={package_version('faster-whisper')}"
            )
            from faster_whisper import WhisperModel

            model = WhisperModel(
                ASR_MODEL,
                device="cpu",
                compute_type="int8",
                cpu_threads=max(1, os.cpu_count() or 1),
                num_workers=1,
            )
            segments, info = model.transcribe(
                str(source),
                language="en",
                task="transcribe",
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            english_cues = [
                (max(0.0, float(segment.start)), min(duration, float(segment.end)),
                 " ".join(segment.text.split()))
                for segment in segments
                if segment.end > segment.start and segment.text.strip()
            ]
            del model
            if not english_cues:
                raise RuntimeError("Whisper produced no English transcript cues.")

        translation_units = merge_sentence_fragments(
            [Cue(start, end, english, "") for start, end, english in english_cues]
        )
        with audit.record(
            "translation_pipeline",
            asset_id=source.name,
            tool="Hugging Face Transformers",
            version=f"model={TRANSLATION_MODEL}",
            details={
                "input_cues": len(translation_units),
                "includes_child_timings": True,
            },
        ) as operation:
            operation["version"] = (
                f"model={TRANSLATION_MODEL}; "
                f"transformers={package_version('transformers')}"
            )
            chinese_texts = translate_batches(
                [cue.english for cue in translation_units],
                audit=audit,
                asset_id=source.name,
                parent_operation_id=str(operation["operation_id"]),
            )
            if len(chinese_texts) != len(translation_units):
                raise RuntimeError(
                    "Translation output count did not match transcript cues."
                )
        cues = [
            Cue(cue.start, cue.end, cue.english, chinese)
            for cue, chinese in zip(
                translation_units,
                chinese_texts,
                strict=True,
            )
            if chinese
        ]
        language_probability = float(info.language_probability)
    if not cues:
        raise RuntimeError("Translation produced no Chinese subtitle cues.")
    cues = reflow_cues(cues)

    prefix = args.output_prefix
    english_srt = output_dir / f"{prefix}.en.srt"
    chinese_srt = output_dir / f"{prefix}.zh-Hans.srt"
    bilingual_srt = output_dir / f"{prefix}.en-zh.srt"
    bilingual_vtt = output_dir / f"{prefix}.en-zh.vtt"
    ass_path = output_dir / f"{prefix}.en-zh.ass"
    with audit.record(
        "subtitle_export",
        asset_id=source.name,
        tool="Python",
        version=platform.python_version(),
        details={"cue_count": len(cues)},
    ):
        english_srt.write_text(srt_text(cues, "en"), encoding="utf-8")
        chinese_srt.write_text(srt_text(cues, "zh"), encoding="utf-8")
        combined_srt = bilingual_srt_text(cues)
        bilingual_srt.write_text(combined_srt, encoding="utf-8")
        bilingual_vtt.write_text(
            vtt_from_bilingual_srt(combined_srt),
            encoding="utf-8",
        )
        write_ass(ass_path, cues, width, height)

    output_video = output_dir / f"{prefix}-bilingual.mp4"
    ffmpeg_version = run(["ffmpeg", "-version"], capture=True).splitlines()[0]
    with audit.record(
        "subtitle_burn",
        asset_id=output_video.name,
        tool="ffmpeg",
        version=ffmpeg_version,
        details={"source_asset": source.name, "resolution": f"{width}x{height}"},
    ):
        run([
            "ffmpeg", "-y", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0?",
            "-vf", f"subtitles={ass_path}",
            "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "22", "-maxrate", "4000k", "-bufsize", "8000k",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_video),
        ])
        output_duration, output_width, output_height = probe_video(output_video)
        if abs(output_duration - duration) > 3:
            raise RuntimeError(
                f"Output duration changed unexpectedly: {duration:.2f}s -> "
                f"{output_duration:.2f}s"
            )
        if (output_width, output_height) != (width, height):
            raise RuntimeError(
                f"Output resolution changed unexpectedly: "
                f"{width}x{height} -> {output_width}x{output_height}"
            )
        if output_video.stat().st_size > MAX_RELEASE_ASSET_BYTES:
            raise RuntimeError(
                f"Encoded MP4 is too large for a GitHub Release asset: "
                f"{output_video.stat().st_size} bytes"
            )
    quality_checks = verify_cues(
        cues,
        duration=duration,
        width=width,
        height=height,
        translation_review=translation_review,
        visual_review=visual_review,
    )

    manifest = {
        "event_id": args.event_id,
        "source_video": source.name,
        "output_prefix": prefix,
        "duration_seconds": round(duration, 3),
        "resolution": f"{width}x{height}",
        "asr_model": None if args.reuse_subtitles else ASR_MODEL,
        "translation_model": (
            translation_models_used[0]
            if len(translation_models_used) == 1
            else None
        ),
        "translation_models_used": translation_models_used,
        "translation_review": translation_review or {
            "status": "not_verified",
            "source_audio_review": False,
            "independent_translation_review": False,
            "translation_models_compared": 0,
            "llm_judges": 0,
            "source_cross_check_passes": 0,
        },
        "visual_review": visual_review or {"status": "not_verified"},
        "reused_existing_subtitles": args.reuse_subtitles is not None,
        "subtitle_cues": len(cues),
        "languages": ["en", "zh-Hans"],
        "video_file": output_video.name,
        "subtitle_files": [
            english_srt.name,
            chinese_srt.name,
            bilingual_srt.name,
        ],
        "subtitle_style": "gold Chinese above white English; responsive phrase-level timing",
        "quality_checks": quality_checks,
        "source_resolution_preserved": True,
        "operation_audit_file": "operation-audit.json",
        "processing_operations": audit.records,
        "whisper_detected_language_probability": (
            round(language_probability, 4)
            if language_probability is not None
            else None
        ),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ass_path.unlink(missing_ok=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
