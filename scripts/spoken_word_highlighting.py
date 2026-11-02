"""Validate reviewed audio-derived word timings for subtitle rendering."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class CueLike(Protocol):
    start: float
    end: float
    english: str


@dataclass(frozen=True)
class TimedWord:
    text: str
    start: float
    end: float


WORD_HIGHLIGHT_SCALE_PERCENT = 108


def ass_highlighted_english_line(
    line: str,
    words: tuple[TimedWord, ...],
    cue_start: float,
    font_size: int,
    escape_text: Callable[[str], str],
    *,
    reset_style: bool = True,
) -> str | None:
    line_words = re.findall(r"\S+", line)
    if len(line_words) != len(words) or any(
        text != timing.text for text, timing in zip(line_words, words, strict=True)
    ):
        return None

    rendered_words = []
    style_prefix = (
        f"\\rEnglish\\fs{font_size}\\1c&H00FFFFFF&" if reset_style
        else f"\\fs{font_size}"
    )
    for text, timing in zip(line_words, words, strict=True):
        start_cs = round((timing.start - cue_start) * 100)
        end_cs = round((timing.end - cue_start) * 100)
        if start_cs < 0 or end_cs - start_cs < 3:
            return None
        rendered_words.append(
            f"{{{style_prefix}\\fscy100"
            f"\\t({start_cs},{start_cs + 1},"
            f"\\fscy{WORD_HIGHLIGHT_SCALE_PERCENT})"
            f"\\t({end_cs - 1},{end_cs},\\fscy100)}}"
            f"{escape_text(text)}"
        )
    return " ".join(rendered_words)


def _not_verified(reason: str) -> tuple[None, dict[str, object]]:
    return None, {"status": "not_verified", "reason": reason}


def disabled_word_highlighting_status() -> dict[str, object]:
    return {"status": "disabled", "reason": "disabled_by_operator"}


def load_reviewed_word_timings(
    path: Path | None,
    cues: list[CueLike],
) -> tuple[tuple[tuple[TimedWord, ...], ...] | None, dict[str, object]]:
    if path is None:
        return _not_verified("word_timing_input_not_provided")
    if not path.is_file():
        return _not_verified("word_timing_input_missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _not_verified("word_timing_input_malformed_json")
    return validate_reviewed_word_timings(data, cues)


def validate_reviewed_word_timings(
    data: object,
    cues: list[CueLike],
) -> tuple[tuple[tuple[TimedWord, ...], ...] | None, dict[str, object]]:
    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
    ):
        return _not_verified("word_timing_schema_invalid")

    timing_source = data.get("timing_source")
    if not isinstance(timing_source, str) or timing_source not in {
        "forced_alignment",
        "asr_word_timestamps",
    }:
        return _not_verified("word_timing_source_not_audio_derived")

    review = data.get("review")
    if (
        not isinstance(review, dict)
        or review.get("status") != "verified"
        or review.get("checked_against_soundtrack") is not True
        or not isinstance(review.get("evidence"), str)
        or not review["evidence"].strip()
    ):
        return _not_verified("soundtrack_review_evidence_not_verified")

    entries = data.get("cues")
    if not isinstance(entries, list) or len(entries) != len(cues):
        return _not_verified("word_timings_incomplete_cue_coverage")

    validated: list[tuple[TimedWord, ...]] = []
    for cue_index, (entry, cue) in enumerate(zip(entries, cues, strict=True), 1):
        if not isinstance(entry, dict):
            return _not_verified("word_timing_cue_entry_invalid")
        cue_start = _finite_float(cue.start)
        cue_end = _finite_float(cue.end)
        if (
            cue_start is None
            or cue_end is None
            or cue_end <= cue_start
        ):
            return _not_verified("word_timing_cue_text_or_alignment_mismatch")
        if type(entry.get("cue_index")) is not int or entry["cue_index"] != cue_index:
            return _not_verified("word_timing_cue_order_invalid")
        recorded_start = _finite_float(entry.get("start"))
        recorded_end = _finite_float(entry.get("end"))
        if (
            recorded_start is None
            or recorded_end is None
            or abs(recorded_start - cue_start) > 0.01
            or abs(recorded_end - cue_end) > 0.01
            or entry.get("english") != cue.english
        ):
            return _not_verified("word_timing_cue_text_or_alignment_mismatch")

        words = entry.get("words")
        expected_words = cue.english.split()
        if not isinstance(words, list) or len(words) != len(expected_words):
            return _not_verified("word_timings_incomplete_word_coverage")

        validated_words: list[TimedWord] = []
        previous_end = cue_start
        for word_entry, expected_text in zip(words, expected_words, strict=True):
            if not isinstance(word_entry, dict) or word_entry.get("text") != expected_text:
                return _not_verified("word_timing_text_alignment_mismatch")
            start = _finite_float(word_entry.get("start"))
            end = _finite_float(word_entry.get("end"))
            if (
                start is None
                or end is None
                or start < cue_start
                or end > cue_end
                or end <= start
            ):
                return _not_verified("word_timing_outside_cue_or_invalid")
            if start < previous_end:
                return _not_verified("word_timings_out_of_order_or_overlapping")
            if (
                round((start - cue_start) * 100)
                + 3
                > round((end - cue_start) * 100)
            ):
                return _not_verified("word_timing_below_ass_precision")
            validated_words.append(
                TimedWord(expected_text, start, end)
            )
            previous_end = end
        validated.append(tuple(validated_words))

    return tuple(validated), {
        "status": "enabled",
        "reason": "reviewed_audio_word_timings_validated",
        "timing_source": timing_source,
        "cue_count": len(cues),
        "review_evidence": review["evidence"].strip(),
    }


def _finite_float(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        converted = float(value)
    except OverflowError:
        return None
    return converted if math.isfinite(converted) else None
