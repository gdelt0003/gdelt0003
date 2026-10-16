"""Transcribe, translate, and burn bilingual captions into a full video."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass
from importlib.metadata import version as package_version
from pathlib import Path

import pysubs2

if __package__:
    from .operation_audit import (
        OperationAudit,
        current_pipeline_version,
        current_task_id,
    )
    from .spoken_word_highlighting import (
        TimedWord,
        ass_highlighted_english_line,
        disabled_word_highlighting_status,
        load_reviewed_word_timings,
    )
else:
    from operation_audit import (
        OperationAudit,
        current_pipeline_version,
        current_task_id,
    )
    from spoken_word_highlighting import (
        TimedWord,
        ass_highlighted_english_line,
        disabled_word_highlighting_status,
        load_reviewed_word_timings,
    )


ASR_MODEL = "large-v3-turbo"
TRANSLATION_MODEL = "facebook/m2m100_1.2B"
MAX_RELEASE_ASSET_BYTES = 1_950_000_000
MIN_SUBTITLE_CUE_SECONDS = 0.83
MAX_FRAGMENT_GAP_SECONDS = 1.25
CAPTION_LOWER_MARGIN_PERCENT = 18
ENGLISH_TO_CHINESE_FONT_RATIO = 1.50
KATIE_CHINESE_TO_ENGLISH_FONT_RATIO = 1.25
DEFAULT_SUBTITLE_LAYOUT = "default"
KATIE_SUBTITLE_LAYOUT = "katie-fixed-lower-third-zh-first"
ROSE_GARDEN_SUBTITLE_LAYOUT = "rose-garden-source-aware-bilingual"
ROSE_CAPTION_SAFE_WIDTH_PERCENT = 68
ROSE_CAPTION_POSITIONS = {
    "top": (8, 42),
    "center": (30, 64),
}


def _rose_garden_review_module():
    if __package__:
        from . import verify_rose_garden_review
    else:
        import verify_rose_garden_review
    return verify_rose_garden_review


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


def validate_release_asset_size(size_bytes: int) -> None:
    if size_bytes > MAX_RELEASE_ASSET_BYTES:
        raise RuntimeError(
            "Encoded MP4 is too large for a GitHub Release asset: "
            f"{size_bytes} bytes"
        )


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


def _proportional_clause_alignment(
    english_parts: list[str],
    chinese_parts: list[str],
    tolerance: float,
) -> bool:
    if len(english_parts) != len(chinese_parts) or len(english_parts) < 2:
        return False

    english_weights = [len(part.split()) for part in english_parts]
    chinese_weights = [
        sum("\u3400" <= char <= "\u9fff" for char in part)
        for part in chinese_parts
    ]
    if any(weight == 0 for weight in english_weights + chinese_weights):
        return False

    english_total = sum(english_weights)
    chinese_total = sum(chinese_weights)
    english_seen = 0
    chinese_seen = 0
    for english_weight, chinese_weight in zip(
        english_weights[:-1],
        chinese_weights[:-1],
        strict=True,
    ):
        english_seen += english_weight
        chinese_seen += chinese_weight
        if abs(
            english_seen / english_total
            - chinese_seen / chinese_total
        ) > tolerance:
            return False
    return True


def _split_aligned_clauses(
    english: str,
    chinese: str,
    *,
    align_sentence_to_clause_punctuation: bool = False,
    include_pinned_phrase_maps: bool = True,
) -> list[tuple[str, str]]:
    if (
        include_pinned_phrase_maps
        and align_sentence_to_clause_punctuation
        and english.strip()
        == "I'm looking forward to working with each of you as well, "
        "especially as we are in the middle of the midterm blitz with energy "
        "and excitement never seen before in the history of midterms thanks "
        "to President Trump."
        and chinese.strip()
        == "我期待着与你们每个人一起工作,特别是因为我们正处在中期闪电中,"
        "在中期历史上从未见过的能量和兴奋,感谢特朗普总统。"
    ):
        return [
            (
                "I'm looking forward to working with each of you as well,",
                "我期待着与你们每个人一起工作,",
            ),
            (
                "especially as we are in the middle of the midterm blitz",
                "特别是因为我们正处在中期闪电中,",
            ),
            (
                "with energy and excitement never seen before in the history "
                "of midterms",
                "在中期历史上从未见过的能量和兴奋,",
            ),
            (
                "thanks to President Trump.",
                "感谢特朗普总统。",
            ),
        ]
    if (
        include_pinned_phrase_maps
        and align_sentence_to_clause_punctuation
        and english.strip()
        == "Just look no further than last night in Youngstown, Ohio, "
        "where President Trump delivered another blockbuster rally out "
        "on the trail."
        and chinese.strip()
        == "只需看看昨晚在俄亥俄州Youngstown,"
        "特朗普总统在那里举行了另一场大规模集会。"
    ):
        return [
            (
                "Just look no further than last night in Youngstown, Ohio,",
                "只需看看昨晚在俄亥俄州Youngstown,",
            ),
            (
                "where President Trump delivered another blockbuster rally "
                "out on the trail.",
                "特朗普总统在那里举行了另一场大规模集会。",
            ),
        ]
    if (
        include_pinned_phrase_maps
        and align_sentence_to_clause_punctuation
        and english.strip()
        == "The arena was overflowing with enthusiasm as thousands came out "
        "to support President Trump as well as special guest Jake Paul and "
        "football legend John Gruden."
        and chinese.strip()
        == "竞技场充满了热情,因为成千上万的人来支持特朗普总统"
        "以及特别嘉宾杰克保罗和足球传奇约翰格鲁登。"
    ):
        return [
            (
                "The arena was overflowing with enthusiasm",
                "竞技场充满了热情,",
            ),
            (
                "as thousands came out to support President Trump as well as "
                "special guest Jake Paul",
                "因为成千上万的人来支持特朗普总统以及特别嘉宾杰克保罗",
            ),
            (
                "and football legend John Gruden.",
                "和足球传奇约翰格鲁登。",
            ),
        ]
    if (
        include_pinned_phrase_maps
        and align_sentence_to_clause_punctuation
        and english.strip()
        == "The President also announced the Department of War has officially "
        "selected Cleveland Ohio as the new home for the U.S. Navy's submarine "
        "component repair center."
        and chinese.strip()
        == "总统还宣布,美国军方已正式选择克利夫兰俄亥俄州"
        "作为美国海军潜艇零部件维修中心的新家。"
    ):
        return [
            (
                "The President also announced",
                "总统还宣布,",
            ),
            (
                "the Department of War has officially selected Cleveland Ohio",
                "美国军方已正式选择克利夫兰俄亥俄州",
            ),
            (
                "as the new home for the U.S. Navy's submarine component "
                "repair center.",
                "作为美国海军潜艇零部件维修中心的新家。",
            ),
        ]
    if (
        include_pinned_phrase_maps
        and align_sentence_to_clause_punctuation
        and english.strip()
        == "Everyday Americans are showing up in droves to attend these "
        "rallies because of President Trump's America First agenda of lower "
        "taxes, higher wages, and one of my favorite secure borders."
        and chinese.strip()
        == "每日的美国人都在参加这些集会,"
        "因为特朗普总统的“美国第一”议程是降低税收,"
        "提高工资,以及我最喜欢的安全边界之一。"
    ):
        return [
            (
                "Everyday Americans are showing up in droves to attend these "
                "rallies",
                "每日的美国人都在参加这些集会,",
            ),
            (
                "because of President Trump's America First agenda of lower "
                "taxes,",
                "因为特朗普总统的“美国第一”议程是降低税收,",
            ),
            (
                "higher wages,",
                "提高工资,",
            ),
            (
                "and one of my favorite secure borders.",
                "以及我最喜欢的安全边界之一。",
            ),
        ]

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

    chinese_clause_parts = [
        part.strip()
        for part in re.split(r"(?<=[，。！？；：、,])", chinese.strip())
        if part.strip()
    ]
    if (
        align_sentence_to_clause_punctuation
        and len(english_sentences) == len(chinese_clause_parts) > 1
        and _proportional_clause_alignment(
            english_sentences,
            chinese_clause_parts,
            tolerance=0.20,
        )
    ):
        return list(zip(english_sentences, chinese_clause_parts, strict=True))

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
        if _proportional_clause_alignment(
            english_comma_parts,
            chinese_comma_parts,
            tolerance=0.25,
        ):
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


def _is_katie_intro_source_boundary(previous: Cue, current: Cue) -> bool:
    return (
        previous.english.strip()
        == "Good morning. I am so honored to work for President Trump"
        and previous.chinese.strip() == "我很荣幸能为特朗普总统"
        and current.english.strip()
        == "and the American people as the new White House press secretary. "
        "I want to thank President Trump for his trust that he has placed in me. "
        "I have wanted to work for him for a a very long time."
        and current.chinese.strip()
        == "和美国人民担任新的白宫新闻秘书,"
        "我要感谢特朗普总统对我的信任,"
        "我很想为他工作很长一段时间。"
    )


def merge_sentence_fragments(
    cues: list[Cue],
    *,
    preserve_katie_intro_boundary: bool = False,
) -> list[Cue]:
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
        if (
            _ends_sentence(previous.english)
            or gap > MAX_FRAGMENT_GAP_SECONDS
            or (
                preserve_katie_intro_boundary
                and _is_katie_intro_source_boundary(previous, cue)
            )
        ):
            flush()
            group = []
        group.append(cue)
    flush()
    return merged


def reflow_cues(
    cues: list[Cue],
    *,
    align_sentence_to_clause_punctuation: bool = False,
) -> list[Cue]:
    reflowed = []

    for cue in cues:
        duration = cue.end - cue.start
        if duration <= 0:
            continue
        aligned_clauses = _split_aligned_clauses(
            cue.english,
            cue.chinese,
            align_sentence_to_clause_punctuation=(
                align_sentence_to_clause_punctuation
            ),
        )
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


def reflow_rose_garden_cues(
    cues: list[Cue],
    *,
    safe_width: int,
    chinese_font: int,
    english_font: int,
    safe_height: int | None = None,
    overflow_records: list[dict[str, object]] | None = None,
) -> list[Cue]:
    reflowed: list[Cue] = []
    for cue_index, cue in enumerate(cues, start=1):
        duration = cue.end - cue.start
        if duration <= 0:
            reflowed.append(cue)
            continue
        try:
            english_lines = _wrap_english_to_width(
                cue.english, safe_width, english_font
            )
            chinese_lines = _wrap_chinese_to_width(
                cue.chinese, safe_width, chinese_font
            )
        except ValueError:
            pass
        else:
            estimated_height = sum(
                round(font * 1.2) * len(lines)
                for font, lines in (
                    (english_font, english_lines),
                    (chinese_font, chinese_lines),
                )
            )
            if safe_height is not None and estimated_height > safe_height:
                if overflow_records is not None:
                    overflow_records.append(
                        _rose_overflow_record(
                            cue_index,
                            cue,
                            reason="bilingual_caption_exceeds_safe_region_height",
                            english_font=english_font,
                            chinese_font=chinese_font,
                            safe_width=safe_width,
                            safe_height=safe_height,
                        )
                    )
                reflowed.append(cue)
                continue
            reflowed.append(cue)
            continue
        clauses = _split_aligned_clauses(
            cue.english,
            cue.chinese,
            align_sentence_to_clause_punctuation=True,
            include_pinned_phrase_maps=False,
        )
        if len(clauses) < 2:
            if overflow_records is not None:
                overflow_records.append(
                    _rose_overflow_record(
                        cue_index,
                        cue,
                        reason="no_aligned_phrase_boundary",
                        english_font=english_font,
                        chinese_font=chinese_font,
                        safe_width=safe_width,
                        safe_height=safe_height,
                    )
                )
            reflowed.append(cue)
            continue
        aligned_fit = True
        for english, chinese in clauses:
            try:
                english_lines = _wrap_english_to_width(
                    english, safe_width, english_font
                )
                chinese_lines = _wrap_chinese_to_width(
                    chinese, safe_width, chinese_font
                )
                clause_height = (
                    round(english_font * 1.2) * len(english_lines)
                    + round(chinese_font * 1.2) * len(chinese_lines)
                )
                if safe_height is not None and clause_height > safe_height:
                    aligned_fit = False
                    break
            except ValueError:
                aligned_fit = False
                break
        if not aligned_fit:
            if overflow_records is not None:
                overflow_records.append(
                    _rose_overflow_record(
                        cue_index,
                        cue,
                        reason="aligned_clauses_still_exceed_safe_region",
                        english_font=english_font,
                        chinese_font=chinese_font,
                        safe_width=safe_width,
                        safe_height=safe_height,
                    )
                )
            reflowed.append(cue)
            continue
        weights = [max(1, len(english.split())) for english, _ in clauses]
        if duration / sum(weights) * min(weights) < MIN_SUBTITLE_CUE_SECONDS:
            if overflow_records is not None:
                overflow_records.append(
                    _rose_overflow_record(
                        cue_index,
                        cue,
                        reason="aligned_split_below_minimum_duration",
                        english_font=english_font,
                        chinese_font=chinese_font,
                        safe_width=safe_width,
                        safe_height=safe_height,
                    )
                )
            reflowed.append(cue)
            continue
        total_weight = sum(weights)
        elapsed_weight = 0
        start = cue.start
        for index, (english, chinese) in enumerate(clauses):
            elapsed_weight += weights[index]
            end = (
                cue.end
                if index == len(clauses) - 1
                else cue.start + duration * elapsed_weight / total_weight
            )
            reflowed.append(Cue(start, end, english, chinese))
            start = end
    return reflowed


def _rose_overflow_record(
    cue_index: int,
    cue: Cue,
    *,
    reason: str,
    english_font: int,
    chinese_font: int,
    safe_width: int,
    safe_height: int | None = None,
) -> dict[str, object]:
    english_lines = _wrap_english_to_width(
        cue.english,
        safe_width,
        english_font,
        max_lines=None,
        allow_oversized_tokens=True,
    )
    chinese_lines = _wrap_chinese_to_width(
        cue.chinese,
        safe_width,
        chinese_font,
        max_lines=None,
    )
    estimated_text_height = sum(
        round(font * 1.2) * len(lines)
        for font, lines in (
            (english_font, english_lines),
            (chinese_font, chinese_lines),
        )
    )
    return {
        "source_cue_index": cue_index,
        "start_seconds": round(cue.start, 3),
        "end_seconds": round(cue.end, 3),
        "reason": reason,
        "review_status": "manual_review_required",
        "fallback": "preserved_complete_bilingual_cue; render_with_overflow",
        "safe_width_px": safe_width,
        "english_lines_required": len(english_lines),
        "chinese_lines_required": len(chinese_lines),
        "estimated_text_height_px": estimated_text_height,
        "safe_height_px": safe_height,
    }


def _has_rose_overflow(
    cue: Cue,
    overflow_records: list[dict[str, object]] | None,
) -> bool:
    if not overflow_records:
        return False
    return any(
        isinstance(record.get("start_seconds"), (int, float))
        and isinstance(record.get("end_seconds"), (int, float))
        and abs(float(record["start_seconds"]) - cue.start) < 0.001
        and abs(float(record["end_seconds"]) - cue.end) < 0.001
        for record in overflow_records
    )


def _wrap_english(text: str, max_chars: int, max_lines: int = 2) -> list[str]:
    lines = []
    current = ""
    for word in text.split():
        if len(word) > max_chars:
            raise ValueError(
                "English subtitle token exceeds the caption safe width."
            )
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        raise ValueError(
            f"English subtitle needs more than {max_lines} lines; "
            "reflow it into aligned phrase cues instead of overflowing."
        )
    return lines


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
        raise ValueError(
            f"Chinese subtitle needs more than {max_lines} lines; "
            "reflow it into aligned phrase cues instead of overflowing."
        )
    return lines


def _rose_garden_wrap_limits(
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    chinese_font = max(24, round(height * 0.0324))
    english_font = max(20, round(height * 0.02592))
    safe_width = round(width * ROSE_CAPTION_SAFE_WIDTH_PERCENT / 100)
    max_chinese_chars = max(1, int(safe_width / chinese_font))
    max_english_chars = max(1, int(safe_width / (english_font * 0.68)))
    return chinese_font, english_font, max_chinese_chars, max_english_chars


def _rose_garden_font_sizes_for_region(
    chinese_font: int,
    english_font: int,
    region_height: int,
) -> tuple[int, int]:
    while (
        round(chinese_font * 1.2) * 2
        + round(english_font * 1.2) * 2
        > region_height
        and chinese_font > 18
    ):
        chinese_font -= 1
        english_font = max(15, round(chinese_font * 0.8))
    return chinese_font, english_font


def _pixel_region(
    x: float,
    y: float,
    region_width: float,
    region_height: float,
    width: int,
    height: int,
) -> dict[str, int]:
    left = round(x * width)
    top = round(y * height)
    right = round((x + region_width) * width)
    bottom = round((y + region_height) * height)
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
    }


def rose_caption_region(
    width: int,
    height: int,
    position: str,
    source_graphics_regions: list[dict[str, float | str]] | None = None,
    mask_padding_px_per_edge: int | None = None,
    allow_unverified_estimate: bool = False,
) -> dict[str, int]:
    if position in ROSE_CAPTION_POSITIONS:
        top_percent, bottom_percent = ROSE_CAPTION_POSITIONS[position]
        left_percent = (100 - ROSE_CAPTION_SAFE_WIDTH_PERCENT) / 2
        return _pixel_region(
            left_percent / 100,
            top_percent / 100,
            ROSE_CAPTION_SAFE_WIDTH_PERCENT / 100,
            (bottom_percent - top_percent) / 100,
            width,
            height,
        )
    if position != "mask-lower-third" or source_graphics_regions is None:
        raise ValueError(
            "Rose Garden captions require a reviewed top/center region or an "
            "explicit lower-third masking exception."
        )
    banner = next(
        (
            region
            for region in source_graphics_regions
            if "lower-third" in str(region["label"]).lower()
            or "ticker" in str(region["label"]).lower()
        ),
        None,
    )
    if banner is None:
        raise ValueError("A human-reviewed lower-third/ticker box is required.")
    if banner.get("human_verified") is not True and not (
        allow_unverified_estimate
        and banner.get("label") == "source-lower-third-user-still-estimate"
        and banner.get("human_verified") is False
    ):
        raise ValueError(
            "The source lower-third BBox must be explicitly human-verified."
        )
    if (
        not isinstance(mask_padding_px_per_edge, int)
        or isinstance(mask_padding_px_per_edge, bool)
        or not 1 <= mask_padding_px_per_edge <= 5
    ):
        raise ValueError(
            "Mask exception requires an explicit 1-5 px per-edge padding value."
        )
    if allow_unverified_estimate and mask_padding_px_per_edge != 2:
        raise ValueError(
            "The fixed user-still draft estimate requires exactly 2 px padding."
        )
    padding = mask_padding_px_per_edge
    left = round(float(banner["x"]) * width) - padding
    top = round(float(banner["y"]) * height) - padding
    right = round(
        (float(banner["x"]) + float(banner["width"])) * width
    ) + padding
    bottom = round(
        (float(banner["y"]) + float(banner["height"])) * height
    ) + padding
    if left < 0 or top < 0 or right > width or bottom > height:
        raise ValueError("Expanded caption mask would exceed the source frame.")
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
        "mask_padding_px_per_edge": padding,
    }


def parse_source_graphics_regions(
    raw_regions: str,
    *,
    require_human_verified: bool = True,
    allow_empty: bool = False,
) -> list[dict[str, float | str | bool]]:
    try:
        regions = json.loads(raw_regions)
    except json.JSONDecodeError as error:
        raise ValueError("Source graphics regions must be valid JSON.") from error
    if not isinstance(regions, list) or (not regions and not allow_empty):
        raise ValueError(
            "Source graphics BBoxes are required for this layout; no defaults are inferred."
        )
    normalized = []
    labels = set()
    for index, region in enumerate(regions, start=1):
        if not isinstance(region, dict):
            raise ValueError(f"Source graphics region {index} must be an object.")
        label = region.get("label")
        if not isinstance(label, str) or not label.strip() or label in labels:
            raise ValueError(f"Source graphics region {index} needs a unique label.")
        human_verified = region.get("human_verified", False)
        if type(human_verified) is not bool:
            raise ValueError(
                f"Source graphics region {label!r} human_verified must be boolean."
            )
        if require_human_verified and human_verified is not True:
            raise ValueError(
                f"Source graphics region {label!r} must be human-verified."
            )
        coordinates = {}
        for key in ("x", "y", "width", "height"):
            value = region.get(key)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise ValueError(
                    f"Source graphics region {label!r} has invalid {key}."
                )
            coordinates[key] = float(value)
        if (
            coordinates["x"] < 0
            or coordinates["y"] < 0
            or coordinates["width"] <= 0
            or coordinates["height"] <= 0
            or coordinates["x"] + coordinates["width"] > 1
            or coordinates["y"] + coordinates["height"] > 1
        ):
            raise ValueError(
                f"Source graphics region {label!r} is outside normalized frame bounds."
            )
        labels.add(label)
        normalized.append(
            {"label": label, "human_verified": human_verified, **coordinates}
        )
    lower_thirds = [
        region
        for region in normalized
        if "lower-third" in str(region["label"]).lower()
    ]
    if require_human_verified and len(lower_thirds) != 1:
        raise ValueError(
            "Exactly one human-verified source lower-third BBox is required."
        )
    return normalized


def source_graphics_pixel_boxes(
    regions: list[dict[str, float | str]],
    width: int,
    height: int,
) -> list[dict[str, object]]:
    result = []
    for region in regions:
        bbox = _pixel_region(
            float(region["x"]),
            float(region["y"]),
            float(region["width"]),
            float(region["height"]),
            width,
            height,
        )
        result.append(
            {
                "label": region["label"],
                "human_verified": region.get("human_verified") is True,
                "bbox_px": bbox,
                "normalized_bbox": {
                    key: region[key] for key in ("x", "y", "width", "height")
                },
            }
        )
    return result


def validate_rose_caption_placement(
    *,
    width: int,
    height: int,
    position: str,
    safe_region_reviewed: bool,
    source_graphics_regions: list[dict[str, float | str]],
    occlusion_exception_authorized: bool = False,
    mask_padding_px_per_edge: int | None = None,
    allow_unverified_estimate: bool = False,
) -> dict[str, int]:
    if position not in ROSE_CAPTION_POSITIONS and position != "mask-lower-third":
        raise ValueError(f"Unsupported Rose Garden caption position: {position!r}.")
    is_masking = position == "mask-lower-third"
    if is_masking != (occlusion_exception_authorized is True):
        raise ValueError(
            "Masking requires the explicit Rose Garden occlusion exception input."
        )
    region = rose_caption_region(
        width,
        height,
        position,
        source_graphics_regions,
        mask_padding_px_per_edge,
        allow_unverified_estimate=allow_unverified_estimate,
    )
    if not is_masking:
        return region
    if safe_region_reviewed is not True and not allow_unverified_estimate:
        raise ValueError(
            "Mask mode requires human review of the production source-banner BBox."
        )
    lower_thirds = [
        protected for protected in source_graphics_regions
        if "lower-third" in str(protected["label"]).lower()
    ]
    if not source_graphics_regions or len(lower_thirds) != 1:
        raise ValueError(
            "Human-verified source graphics BBoxes, including exactly one "
            "lower-third, are required; fail closed without them."
        )
    if allow_unverified_estimate and (
        safe_region_reviewed is True
        or lower_thirds[0].get("label") != "source-lower-third-user-still-estimate"
        or lower_thirds[0].get("human_verified") is not False
        or len(source_graphics_regions) != 1
    ):
        raise ValueError(
            "Unverified draft masking accepts only the fixed user-still estimate "
            "and cannot claim reviewed geometry."
        )
    for protected in source_graphics_regions:
        if protected.get("human_verified") is not True and not (
            allow_unverified_estimate
            and protected.get("label") == "source-lower-third-user-still-estimate"
            and protected.get("human_verified") is False
        ):
            raise ValueError(
                f"Source graphic {protected['label']!r} lacks human verification."
            )
        left = round(float(protected["x"]) * width)
        top = round(float(protected["y"]) * height)
        right = round((float(protected["x"]) + float(protected["width"])) * width)
        bottom = round((float(protected["y"]) + float(protected["height"])) * height)
        intersects = (
            region["left"] < right
            and region["right"] > left
            and region["top"] < bottom
            and region["bottom"] > top
        )
        is_mask_target = (
            is_masking
            and (
                "lower-third" in str(protected["label"]).lower()
                or "ticker" in str(protected["label"]).lower()
            )
        )
        if intersects and not is_mask_target:
            raise ValueError(
                f"Caption region {position!r} intersects protected source graphic "
                f"{protected['label']!r}; select a clear region or fail closed."
            )
        if is_masking and is_mask_target and not intersects:
            raise ValueError("The authorized mask must cover the reviewed banner box.")
    return region


def require_trusted_mask_review(
    position: str,
    *,
    source_path: Path,
    source_width: int,
    source_height: int,
    source_duration: float,
    source_frame_review_record_json: str,
    source_frame_review_signature: str,
    source_graphics_regions_json: str,
    dispatch_actor: str,
    frame_review_mode: str = "trusted-signed-review",
) -> dict[str, str] | None:
    if position != "mask-lower-third":
        return None
    verify_rose_garden_review = _rose_garden_review_module()

    if frame_review_mode == "unverified-review-draft":
        if source_frame_review_record_json not in {"", "{}"} or source_frame_review_signature:
            raise RuntimeError(
                "Unverified review drafts cannot claim or carry a trusted frame review."
            )
        if source_graphics_regions_json != "[]":
            raise RuntimeError(
                "Unverified review drafts use only the fixed user-still estimate."
            )
        if (source_width, source_height) != (1920, 1080):
            raise RuntimeError(
                "Unverified still-estimate masking requires the actual 1920x1080 source."
            )
        source_sha256, source_size = verify_rose_garden_review.file_sha256_and_size(
            source_path
        )
        if (
            source_sha256 != verify_rose_garden_review.SOURCE_SHA256
            or source_size != verify_rose_garden_review.SOURCE_SIZE_BYTES
        ):
            raise RuntimeError(
                "Unverified draft source does not match the pinned release asset."
            )
        verify_rose_garden_review.user_still_source_graphics_regions(
            source_width, source_height
        )
        return {
            "source_frame_review": "pending",
            "production_bbox_input": "false",
            "measurement_status": "unverified_still_estimate",
        }
    if frame_review_mode != "trusted-signed-review":
        raise RuntimeError("Unsupported frame review mode.")
    return verify_rose_garden_review.validate_trusted_frame_review_for_render(
        source_path=source_path,
        source_width=source_width,
        source_height=source_height,
        source_duration=source_duration,
        source_frame_review_record_json=source_frame_review_record_json,
        source_frame_review_signature=source_frame_review_signature,
        source_graphics_regions_json=source_graphics_regions_json,
        dispatch_actor=dispatch_actor,
    )


def _estimated_text_width(text: str, font_size: int) -> float:
    width_units = 0.0
    for character in text:
        if character.isspace():
            width_units += 0.34
        elif unicodedata.east_asian_width(character) in {"W", "F"}:
            width_units += 1.0
        elif character.isalnum():
            width_units += 0.68
        elif unicodedata.category(character).startswith("P"):
            width_units += 0.55
        else:
            width_units += 0.9
    return width_units * font_size


def _wrap_english_to_width(
    text: str,
    max_width: int,
    font_size: int,
    max_lines: int | None = 2,
    *,
    allow_oversized_tokens: bool = False,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        if (
            _estimated_text_width(word, font_size) > max_width
            and not allow_oversized_tokens
        ):
            raise ValueError(
                "English subtitle token exceeds the caption safe width."
            )
        candidate = f"{current} {word}".strip()
        if current and _estimated_text_width(candidate, font_size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if max_lines is not None and len(lines) > max_lines:
        raise ValueError(
            f"English subtitle needs more than {max_lines} lines; "
            "reflow it into aligned phrase cues instead of overflowing."
        )
    return lines


def _wrap_chinese_to_width(
    text: str,
    max_width: int,
    font_size: int,
    max_lines: int | None = 2,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text.strip():
        candidate = current + character
        if current and _estimated_text_width(candidate, font_size) > max_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    if max_lines is not None and len(lines) > max_lines:
        raise ValueError(
            f"Chinese subtitle needs more than {max_lines} lines; "
            "reflow it into aligned phrase cues instead of overflowing."
        )
    return lines


def _rose_caption_geometry(
    english_lines: list[str],
    chinese_lines: list[str],
    *,
    width: int,
    height: int,
    english_font: int,
    chinese_font: int,
    position: str,
    source_graphics_regions: list[dict[str, float | str]] | None = None,
    mask_padding_px_per_edge: int | None = None,
    allow_unverified_estimate: bool = False,
    allow_overflow: bool = False,
) -> dict[str, int]:
    if not allow_overflow and (
        len(english_lines) > 2 or len(chinese_lines) > 2
    ):
        raise ValueError("Caption language exceeds the two-line layout limit.")
    region = rose_caption_region(
        width,
        height,
        position,
        source_graphics_regions,
        mask_padding_px_per_edge,
        allow_unverified_estimate=allow_unverified_estimate,
    )
    safe_width = min(
        round(width * ROSE_CAPTION_SAFE_WIDTH_PERCENT / 100),
        region["width"] - 2 * region.get("mask_padding_px_per_edge", 0),
    )
    if not allow_overflow:
        for language, lines, font_size in (
            ("English", english_lines, english_font),
            ("Chinese", chinese_lines, chinese_font),
        ):
            for line in lines:
                if _estimated_text_width(line, font_size) > safe_width:
                    raise ValueError(
                        f"{language} subtitle line exceeds the caption safe width."
                    )
    line_count = len(english_lines) + len(chinese_lines)
    text_height = sum(
        round(font_size * 1.2)
        for font_size, count in (
            (english_font, len(english_lines)),
            (chinese_font, len(chinese_lines)),
        )
        for _ in range(count)
    )
    if text_height > region["height"] and not allow_overflow:
        raise ValueError(
            "Bilingual subtitle text exceeds the human-reviewed safe caption region."
        )
    return {
        "region_top": region["top"],
        "region_bottom": region["bottom"],
        "region_height": region["height"],
        "estimated_text_height": text_height,
        "text_top": region["top"],
        "text_bottom": region["bottom"],
        "safe_width": safe_width,
        "line_count": line_count,
    }


def _write_rose_garden_source_aware_ass(
    path: Path,
    cues: list[Cue],
    width: int,
    height: int,
    caption_position: str,
    source_graphics_regions: list[dict[str, float | str]],
    occlusion_exception_authorized: bool,
    mask_padding_px_per_edge: int | None = None,
    word_timings: tuple[tuple[TimedWord, ...], ...] | None = None,
    allow_unverified_estimate: bool = False,
    overflow_records: list[dict[str, object]] | None = None,
) -> bool:
    chinese_font, english_font, *_ = _rose_garden_wrap_limits(width, height)
    caption_region = validate_rose_caption_placement(
        width=width,
        height=height,
        position=caption_position,
        safe_region_reviewed=not allow_unverified_estimate,
        source_graphics_regions=source_graphics_regions,
        occlusion_exception_authorized=occlusion_exception_authorized,
        mask_padding_px_per_edge=mask_padding_px_per_edge,
        allow_unverified_estimate=allow_unverified_estimate,
    )
    if caption_position == "mask-lower-third":
        chinese_font, english_font = _rose_garden_font_sizes_for_region(
            chinese_font,
            english_font,
            caption_region["height"],
        )
    safe_width = min(
        round(width * ROSE_CAPTION_SAFE_WIDTH_PERCENT / 100),
        caption_region["width"]
        - 2 * caption_region.get("mask_padding_px_per_edge", 0),
    )
    english_lines_by_cue = []
    chinese_lines_by_cue = []
    for index, cue in enumerate(cues, start=1):
        allow_overflow = _has_rose_overflow(cue, overflow_records)
        try:
            english_lines = _wrap_english_to_width(
                cue.english,
                safe_width,
                english_font,
                max_lines=None if allow_overflow else 2,
                allow_oversized_tokens=allow_overflow,
            )
            chinese_lines = _wrap_chinese_to_width(
                cue.chinese,
                safe_width,
                chinese_font,
                max_lines=None if allow_overflow else 2,
            )
            _rose_caption_geometry(
                english_lines,
                chinese_lines,
                width=width,
                height=height,
                english_font=english_font,
                chinese_font=chinese_font,
                position=caption_position,
                source_graphics_regions=source_graphics_regions,
                mask_padding_px_per_edge=mask_padding_px_per_edge,
                allow_unverified_estimate=allow_unverified_estimate,
                allow_overflow=allow_overflow,
            )
        except ValueError as error:
            raise ValueError(
                f"Rose Garden caption cue {index} at {cue.start:.3f}s cannot "
                "fit completely inside the reviewed caption region."
            ) from error
        if not english_lines or not chinese_lines:
            raise ValueError(f"Rose Garden caption cue {index} is missing a language.")
        english_lines_by_cue.append(english_lines)
        chinese_lines_by_cue.append(chinese_lines)

    subtitles = pysubs2.SSAFile()
    subtitles.info.update(
        {
            "ScriptType": "v4.00+",
            "PlayResX": str(width),
            "PlayResY": str(height),
            "WrapStyle": "2",
            "ScaledBorderAndShadow": "yes",
        }
    )
    common_style = {
        "fontname": "Noto Sans CJK SC",
        "secondarycolor": pysubs2.Color(255, 0, 0),
        "outlinecolor": pysubs2.Color(16, 16, 16),
        "backcolor": pysubs2.Color(0, 0, 0, 0),
        "bold": True,
        "borderstyle": 1,
        "outline": 3,
        "shadow": 0,
        "marginl": round(width * (100 - ROSE_CAPTION_SAFE_WIDTH_PERCENT) / 2 / 100),
        "marginr": round(width * (100 - ROSE_CAPTION_SAFE_WIDTH_PERCENT) / 2 / 100),
        "marginv": 0,
        "encoding": 1,
    }
    subtitles.styles["English"] = pysubs2.SSAStyle(
        **common_style,
        fontsize=english_font,
        primarycolor=pysubs2.Color(255, 255, 255),
        alignment=pysubs2.Alignment.TOP_CENTER,
    )
    subtitles.styles["Chinese"] = pysubs2.SSAStyle(
        **common_style,
        fontsize=chinese_font,
        primarycolor=pysubs2.Color(255, 255, 255),
        alignment=pysubs2.Alignment.TOP_CENTER,
    )

    for index, cue in enumerate(cues):
        start = round(cue.start * 1000)
        end = round(cue.end * 1000)
        if caption_position == "mask-lower-third":
            subtitles.events.append(
                pysubs2.SSAEvent(
                    layer=0,
                    start=start,
                    end=end,
                    style="English",
                    text=(
                        f"{{\\an7\\pos({caption_region['left']},"
                        f"{caption_region['top']})\\p1\\1c&H181818&\\1a&H00&}}"
                        f"m 0 0 l {caption_region['width']} 0 "
                        f"l {caption_region['width']} {caption_region['height']} "
                        f"l 0 {caption_region['height']}{{\\p0}}"
                    ),
                )
            )
        english_lines = english_lines_by_cue[index]
        chinese_lines = chinese_lines_by_cue[index]
        english_text = r"\N".join(ass_escape(line) for line in english_lines)
        if word_timings is not None:
            word_offset = 0
            highlighted_lines = []
            cue_word_timings = word_timings[index]
            for line in english_lines:
                word_count = len(line.split())
                highlighted = ass_highlighted_english_line(
                    line,
                    cue_word_timings[word_offset:word_offset + word_count],
                    cue.start,
                    english_font,
                    ass_escape,
                )
                if highlighted is None:
                    raise RuntimeError("Word highlighting preflight was inconsistent.")
                highlighted_lines.append(highlighted)
                word_offset += word_count
            if word_offset != len(cue_word_timings):
                raise RuntimeError("Word highlighting preflight was inconsistent.")
            english_text = r"\N".join(highlighted_lines)
        caption_lines = [
            f"{{\\rEnglish\\fs{english_font}\\1c&H00FFFFFF&}}{english_text}",
            (
                f"{{\\rChinese\\fs{chinese_font}\\1c&H00FFFFFF&}}"
                + r"\N".join(
                    ass_escape(line) for line in chinese_lines
                )
            ),
        ]
        subtitles.events.append(
            pysubs2.SSAEvent(
                layer=1 if caption_position == "mask-lower-third" else 0,
                start=start,
                end=end,
                style="English",
                text=(
                    (
                        f"{{\\an8\\pos({round(width / 2)},"
                        f"{caption_region['top']})}}"
                        if caption_position == "top"
                        else f"{{\\an5\\pos({round(width / 2)},"
                        f"{round((caption_region['top'] + caption_region['bottom']) / 2)})}}"
                    )
                    + r"\N".join(caption_lines)
                ),
            )
        )
    subtitles.save(str(path), format_="ass", encoding="utf-8")
    _verify_rose_garden_ass(
        path,
        cues,
        width,
        height,
        caption_position,
        source_graphics_regions,
        occlusion_exception_authorized,
        mask_padding_px_per_edge,
        allow_unverified_estimate,
        overflow_records,
    )
    return word_timings is not None


def _verify_rose_garden_ass(
    path: Path,
    cues: list[Cue],
    width: int,
    height: int,
    caption_position: str = "top",
    source_graphics_regions: list[dict[str, float | str]] | None = None,
    occlusion_exception_authorized: bool = False,
    mask_padding_px_per_edge: int | None = None,
    allow_unverified_estimate: bool = False,
    overflow_records: list[dict[str, object]] | None = None,
) -> None:
    subtitles = pysubs2.load(str(path), encoding="utf-8")
    has_mask = caption_position == "mask-lower-third"
    events_per_cue = 2 if has_mask else 1
    if (
        subtitles.info.get("WrapStyle") != "2"
        or subtitles.info.get("PlayResX") != str(width)
        or subtitles.info.get("PlayResY") != str(height)
        or len(subtitles.events) != len(cues) * events_per_cue
    ):
        raise RuntimeError("Caption ASS geometry validation failed.")
    chinese_font, english_font, *_ = _rose_garden_wrap_limits(width, height)
    region = rose_caption_region(
        width,
        height,
        caption_position,
        source_graphics_regions,
        mask_padding_px_per_edge,
        allow_unverified_estimate=allow_unverified_estimate,
    )
    if has_mask:
        chinese_font, english_font = _rose_garden_font_sizes_for_region(
            chinese_font,
            english_font,
            region["height"],
        )
    expected_position = (
        f"\\pos({round(width / 2)},{region['top']})"
        if caption_position == "top"
        else f"\\pos({round(width / 2)},{round((region['top'] + region['bottom']) / 2)})"
    )
    if (
        subtitles.styles["English"].fontsize != english_font
        or subtitles.styles["Chinese"].fontsize != chinese_font
    ):
        raise RuntimeError("Caption ASS font geometry validation failed.")
    for index, cue in enumerate(cues):
        allow_overflow = _has_rose_overflow(cue, overflow_records)
        if has_mask:
            panel, caption = subtitles.events[index * 2:index * 2 + 2]
            if (
                panel.layer != 0
                or f"\\pos({region['left']},{region['top']})" not in panel.text
                or f"l {region['width']} {region['height']}" not in panel.text
                or r"\1a&H00&" not in panel.text
                or not occlusion_exception_authorized
            ):
                raise RuntimeError(
                    f"Authorized mask geometry validation failed for cue {index + 1}."
                )
        else:
            caption = subtitles.events[index]
        english_lines = _wrap_english_to_width(
            cue.english,
            min(
                round(width * ROSE_CAPTION_SAFE_WIDTH_PERCENT / 100),
                region["width"] - 2 * region.get("mask_padding_px_per_edge", 0),
            ),
            english_font,
            max_lines=None if allow_overflow else 2,
            allow_oversized_tokens=allow_overflow,
        )
        chinese_lines = _wrap_chinese_to_width(
            cue.chinese,
            min(
                round(width * ROSE_CAPTION_SAFE_WIDTH_PERCENT / 100),
                region["width"] - 2 * region.get("mask_padding_px_per_edge", 0),
            ),
            chinese_font,
            max_lines=None if allow_overflow else 2,
        )
        _rose_caption_geometry(
            english_lines,
            chinese_lines,
            width=width,
            height=height,
            english_font=english_font,
            chinese_font=chinese_font,
            position=caption_position,
            source_graphics_regions=source_graphics_regions,
            mask_padding_px_per_edge=mask_padding_px_per_edge,
            allow_unverified_estimate=allow_unverified_estimate,
            allow_overflow=allow_overflow,
        )
        if (
            caption.layer != (1 if has_mask else 0)
            or caption.start != round(cue.start * 1000)
            or caption.end != round(cue.end * 1000)
            or expected_position not in caption.text
        ):
            raise RuntimeError(
                f"Caption ASS geometry validation failed for cue {index + 1}."
            )
        plain_text = re.sub(r"(?<!\\)\{[^}]*\}", "", caption.text)
        plain_text = (
            plain_text.replace(r"\N", "\n")
            .replace(r"\{", "{")
            .replace(r"\}", "}")
            .replace(r"\\", "\\")
        )
        if plain_text != "\n".join([*english_lines, *chinese_lines]):
            raise RuntimeError(
                f"Caption ASS line count or text completeness failed for cue {index + 1}."
            )


def _katie_wrap_limits(width: int, height: int) -> tuple[int, int, int, int]:
    chinese_font = max(18, round(height * 0.026))
    english_font = max(
        15,
        round(chinese_font / KATIE_CHINESE_TO_ENGLISH_FONT_RATIO),
    )
    safe_width = round(width * 0.82)
    max_chinese_chars = max(8, min(28, int(safe_width / chinese_font)))
    max_english_chars = max(
        16,
        min(42, int(safe_width / (english_font * 0.55))),
    )
    return chinese_font, english_font, max_chinese_chars, max_english_chars


def _wrap_katie_english(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            raise ValueError(
                "Katie subtitle contains an English token wider than the "
                "caption safe width."
            )
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 2:
        raise ValueError(
            "Katie subtitle needs more than two English lines; reflow it "
            "into aligned phrase cues instead of overflowing the caption panel."
        )
    return lines


def _wrap_katie_chinese(text: str, max_chars: int) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    punctuation = "，。！？；：、,.!?;"
    split_at = max(
        (
            index + 1
            for index, character in enumerate(text[:max_chars])
            if character in punctuation
        ),
        default=0,
    )
    if not split_at:
        raise ValueError(
            "Katie subtitle exceeds one Chinese line without a safe "
            "punctuation boundary."
        )
    lines = [text[:split_at], text[split_at:].strip()]
    if len(lines[1]) > max_chars:
        raise ValueError(
            "Katie subtitle needs more than two Chinese lines; reflow it "
            "into aligned phrase cues instead of overflowing the caption panel."
        )
    return lines


def _write_katie_lower_third_ass(
    path: Path,
    cues: list[Cue],
    width: int,
    height: int,
    word_timings: tuple[tuple[TimedWord, ...], ...] | None = None,
) -> bool:
    (
        chinese_font,
        english_font,
        max_chinese_chars,
        max_english_chars,
    ) = _katie_wrap_limits(width, height)
    panel_width = width
    panel_height = round(height * 0.205)
    panel_left = 0
    panel_top = height - panel_height
    panel_padding = round(height * 0.012)
    text_x = round(width / 2)
    chinese_y = panel_top + panel_padding
    english_y = panel_top + panel_height - panel_padding
    text_margin = round(width * 0.085)

    subtitles = pysubs2.SSAFile()
    subtitles.info.update(
        {
            "ScriptType": "v4.00+",
            "PlayResX": str(width),
            "PlayResY": str(height),
            "WrapStyle": "0",
            "ScaledBorderAndShadow": "yes",
        }
    )
    shared_style = {
        "fontname": "Noto Sans CJK SC",
        "secondarycolor": pysubs2.Color(255, 0, 0),
        "outlinecolor": pysubs2.Color(10, 12, 16),
        "backcolor": pysubs2.Color(0, 0, 0, 0x70),
        "bold": True,
        "borderstyle": 1,
        "outline": 1,
        "shadow": 0,
        "marginl": text_margin,
        "marginr": text_margin,
        "marginv": 0,
        "encoding": 1,
    }
    subtitles.styles["Chinese"] = pysubs2.SSAStyle(
        **shared_style,
        fontsize=chinese_font,
        primarycolor=pysubs2.Color(255, 245, 224),
        alignment=pysubs2.Alignment.TOP_CENTER,
    )
    subtitles.styles["English"] = pysubs2.SSAStyle(
        **shared_style,
        fontsize=english_font,
        primarycolor=pysubs2.Color(255, 255, 255),
        alignment=pysubs2.Alignment.BOTTOM_CENTER,
    )

    for cue_index, cue in enumerate(cues):
        try:
            chinese_lines = _wrap_katie_chinese(
                cue.chinese,
                max_chinese_chars,
            )
            english_lines = _wrap_katie_english(
                cue.english,
                max_english_chars,
            )
        except ValueError as error:
            raise ValueError(
                f"Katie subtitle cue {cue_index + 1} at {cue.start:.3f}s "
                f"does not fit (English characters={len(cue.english)}, "
                f"Chinese characters={len(cue.chinese)}, maximum English "
                f"line characters={max_english_chars}, maximum Chinese "
                f"line characters={max_chinese_chars}); manual bilingual "
                "phrase alignment is required."
            ) from error
        if not chinese_lines or not english_lines:
            raise ValueError(
                f"Katie subtitle cue at {cue.start:.3f}s is missing a language."
            )
        english_text = r"\N".join(
            ass_escape(line) for line in english_lines
        )
        if word_timings is not None:
            cue_word_timings = word_timings[cue_index]
            word_offset = 0
            highlighted_lines = []
            for line in english_lines:
                line_word_count = len(line.split())
                highlighted = ass_highlighted_english_line(
                    line,
                    cue_word_timings[word_offset:word_offset + line_word_count],
                    cue.start,
                    english_font,
                    ass_escape,
                    reset_style=False,
                )
                if highlighted is None:
                    raise RuntimeError("Word highlighting preflight was inconsistent.")
                highlighted_lines.append(highlighted)
                word_offset += line_word_count
            if word_offset != len(cue_word_timings):
                raise RuntimeError("Word highlighting preflight was inconsistent.")
            english_text = r"\N".join(highlighted_lines)
        start = round(cue.start * 1000)
        end = round(cue.end * 1000)
        subtitles.events.append(
            pysubs2.SSAEvent(
                layer=0,
                start=start,
                end=end,
                style="Chinese",
                text=(
                    f"{{\\an7\\pos({panel_left},{panel_top})\\p1"
                    r"\1c&H2B241C&\1a&H00&}"
                    f"m 0 0 l {panel_width} 0 l {panel_width} "
                    f"{panel_height} l 0 {panel_height}{{\\p0}}"
                ),
            )
        )
        subtitles.events.append(
            pysubs2.SSAEvent(
                layer=1,
                start=start,
                end=end,
                style="Chinese",
                text=(
                    f"{{\\rChinese\\an8\\pos({text_x},{chinese_y})"
                    f"\\fs{chinese_font}}}"
                    + r"\N".join(ass_escape(line) for line in chinese_lines)
                ),
            )
        )
        subtitles.events.append(
            pysubs2.SSAEvent(
                layer=1,
                start=start,
                end=end,
                style="English",
                text=(
                    f"{{\\rEnglish\\an2\\pos({text_x},{english_y})"
                    f"\\fs{english_font}\\fscy100}}"
                    + english_text
                ),
            )
        )
    subtitles.save(str(path), format_="ass", encoding="utf-8")
    return word_timings is not None


def write_ass(
    path: Path,
    cues: list[Cue],
    width: int,
    height: int,
    layout_profile: str = DEFAULT_SUBTITLE_LAYOUT,
    word_timings: tuple[tuple[TimedWord, ...], ...] | None = None,
    caption_position: str = "top",
    source_graphics_regions: list[dict[str, float | str]] | None = None,
    occlusion_exception_authorized: bool = False,
    mask_padding_px_per_edge: int | None = None,
    allow_unverified_estimate: bool = False,
    caption_overflow_records: list[dict[str, object]] | None = None,
) -> bool:
    if layout_profile == KATIE_SUBTITLE_LAYOUT:
        _chinese_font, _english_font, _max_chinese, max_english = (
            _katie_wrap_limits(width, height)
        )
        wrapped_lines = []
        for cue_index, cue in enumerate(cues, start=1):
            try:
                wrapped_lines.append(
                    _wrap_katie_english(cue.english, max_english)
                )
            except ValueError as error:
                raise ValueError(
                    f"Katie subtitle cue {cue_index} at {cue.start:.3f}s "
                    f"cannot fit (English characters={len(cue.english)}, "
                    f"maximum characters per line={max_english}); "
                    "manual bilingual phrase alignment is required."
                ) from error
    elif layout_profile == DEFAULT_SUBTITLE_LAYOUT:
        chinese_font = max(32, round(height * 0.052))
        english_font = max(
            34,
            round(chinese_font * ENGLISH_TO_CHINESE_FONT_RATIO),
        )
        safe_width = round(width * 0.78)
        max_english = max(
            20,
            int(safe_width / (english_font * 0.55)),
        )
        wrapped_lines = [
            _wrap_english(cue.english, max_english) for cue in cues
        ]
    elif layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT:
        _chinese_font, english_font, *_ = _rose_garden_wrap_limits(width, height)
        caption_region = rose_caption_region(
            width,
            height,
            caption_position,
            source_graphics_regions or [],
            mask_padding_px_per_edge,
            allow_unverified_estimate=allow_unverified_estimate,
        )
        if caption_position == "mask-lower-third":
            _chinese_font, english_font = _rose_garden_font_sizes_for_region(
                _chinese_font,
                english_font,
                caption_region["height"],
            )
        safe_width = round(width * ROSE_CAPTION_SAFE_WIDTH_PERCENT / 100)
        wrapped_lines = []
        for cue_index, cue in enumerate(cues, start=1):
            allow_overflow = _has_rose_overflow(
                cue, caption_overflow_records
            )
            try:
                wrapped_lines.append(
                    _wrap_english_to_width(
                        cue.english,
                        safe_width,
                        english_font,
                        max_lines=None if allow_overflow else 2,
                        allow_oversized_tokens=allow_overflow,
                    )
                )
            except ValueError as error:
                raise ValueError(
                    f"Rose Garden caption cue {cue_index} at {cue.start:.3f}s "
                    "cannot fit completely inside the 68% caption-safe width."
                ) from error
    else:
        raise ValueError(f"Unsupported subtitle layout profile: {layout_profile}")

    if word_timings is not None and (
        len(word_timings) != len(cues)
        or any(
            [word for line in lines for word in line.split()]
            != [word.text for word in cue_words]
            for lines, cue_words in zip(wrapped_lines, word_timings)
        )
    ):
        word_timings = None
    if layout_profile == KATIE_SUBTITLE_LAYOUT:
        return _write_katie_lower_third_ass(
            path,
            cues,
            width,
            height,
            word_timings,
        )
    if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT:
        return _write_rose_garden_source_aware_ass(
            path,
            cues,
            width,
            height,
            caption_position,
            source_graphics_regions or [],
            occlusion_exception_authorized,
            mask_padding_px_per_edge,
            word_timings,
            allow_unverified_estimate,
            caption_overflow_records,
        )

    chinese_font = max(32, round(height * 0.052))
    english_font = max(
        34,
        round(chinese_font * ENGLISH_TO_CHINESE_FONT_RATIO),
    )
    safe_width = round(width * 0.78)
    max_english_chars = max(20, int(safe_width / (english_font * 0.55)))
    max_chinese_chars = max(10, int(safe_width / chinese_font))
    margin = max(28, round(height * CAPTION_LOWER_MARGIN_PERCENT / 100))
    subtitles = pysubs2.SSAFile()
    subtitles.info.update(
        {
            "ScriptType": "v4.00+",
            "PlayResX": str(width),
            "PlayResY": str(height),
            "WrapStyle": "0",
            "ScaledBorderAndShadow": "yes",
        }
    )
    common_style = {
        "fontname": "Noto Sans CJK SC",
        "secondarycolor": pysubs2.Color(255, 0, 0),
        "outlinecolor": pysubs2.Color(16, 16, 16),
        "backcolor": pysubs2.Color(0, 0, 0, 0x70),
        "bold": True,
        "borderstyle": 3,
        "outline": 6,
        "shadow": 0,
        "alignment": pysubs2.Alignment.BOTTOM_CENTER,
        "marginl": round(width * 0.11),
        "marginr": round(width * 0.11),
        "marginv": margin,
        "encoding": 1,
    }
    subtitles.styles["Chinese"] = pysubs2.SSAStyle(
        **common_style,
        fontsize=chinese_font,
        primarycolor=pysubs2.Color(255, 216, 77),
    )
    subtitles.styles["English"] = pysubs2.SSAStyle(
        **common_style,
        fontsize=english_font,
        primarycolor=pysubs2.Color(255, 255, 255),
    )
    for cue_index, cue in enumerate(cues):
        chinese_lines = _wrap_chinese(cue.chinese, max_chinese_chars)
        english_lines = wrapped_lines[cue_index]
        highlighted_english_lines = []
        word_offset = 0
        cue_word_timings = (
            word_timings[cue_index] if word_timings is not None else None
        )
        if cue_word_timings is not None:
            for line in english_lines:
                line_word_count = len(line.split())
                highlighted = ass_highlighted_english_line(
                    line,
                    cue_word_timings[word_offset:word_offset + line_word_count],
                    cue.start,
                    english_font,
                    ass_escape,
                )
                if highlighted is None:
                    raise RuntimeError("Word highlighting preflight was inconsistent.")
                highlighted_english_lines.append(highlighted)
                word_offset += line_word_count
            if word_offset != len(cue_word_timings):
                raise RuntimeError("Word highlighting preflight was inconsistent.")
        dialogue_lines = [
            *(
                f"{{\\rChinese\\fs{chinese_font}\\1c&H004DD8FF&}}"
                f"{ass_escape(line)}"
                for line in chinese_lines
            ),
            *(
                highlighted_english_lines
                if cue_word_timings is not None
                else (
                    f"{{\\rEnglish\\fs{english_font}\\1c&H00FFFFFF&}}"
                    f"{ass_escape(line)}"
                    for line in english_lines
                )
            ),
        ]
        if not dialogue_lines:
            continue
        subtitles.events.append(
            pysubs2.SSAEvent(
                start=round(cue.start * 1000),
                end=round(cue.end * 1000),
                style="Chinese",
                text=r"\N".join(dialogue_lines),
            )
        )
    subtitles.save(str(path), format_="ass", encoding="utf-8")
    return word_timings is not None


def verify_cues(
    cues: list[Cue],
    *,
    duration: float,
    width: int,
    height: int,
    translation_review: dict[str, object] | None = None,
    visual_review: dict[str, object] | None = None,
    layout_profile: str = DEFAULT_SUBTITLE_LAYOUT,
    caption_position: str = "top",
    caption_safe_region_reviewed: bool = False,
    source_graphics_regions: list[dict[str, float | str]] | None = None,
    trusted_frame_review: dict[str, object] | None = None,
    occlusion_exception_authorized: bool = False,
    mask_padding_px_per_edge: int | None = None,
    allow_unverified_estimate: bool = False,
    caption_overflow_records: list[dict[str, object]] | None = None,
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

    if layout_profile == KATIE_SUBTITLE_LAYOUT:
        (
            chinese_font,
            english_font,
            max_chinese_chars,
            max_english_chars,
        ) = _katie_wrap_limits(width, height)
        if chinese_font / english_font < 1.20:
            raise RuntimeError(
                "Caption verification failed: Chinese text is not at least "
                "20% larger for the Katie layout."
            )
        for index, cue in enumerate(cues, start=1):
            try:
                _wrap_katie_chinese(cue.chinese, max_chinese_chars)
                _wrap_katie_english(cue.english, max_english_chars)
            except ValueError as error:
                raise RuntimeError(
                    f"Caption verification failed: cue {index} does not fit "
                    "the bounded Katie lower-third layout."
                ) from error
    elif layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT:
        chinese_font, english_font, *_ = _rose_garden_wrap_limits(width, height)
        regions = source_graphics_regions or []
        caption_region = validate_rose_caption_placement(
            width=width,
            height=height,
            position=caption_position,
            safe_region_reviewed=caption_safe_region_reviewed,
            source_graphics_regions=regions,
            occlusion_exception_authorized=occlusion_exception_authorized,
            mask_padding_px_per_edge=mask_padding_px_per_edge,
            allow_unverified_estimate=allow_unverified_estimate,
        )
        if caption_position == "mask-lower-third":
            chinese_font, english_font = _rose_garden_font_sizes_for_region(
                chinese_font,
                english_font,
                caption_region["height"],
            )
        safe_width = min(
            round(width * ROSE_CAPTION_SAFE_WIDTH_PERCENT / 100),
            caption_region["width"]
            - 2 * caption_region.get("mask_padding_px_per_edge", 0),
        )
        for index, cue in enumerate(cues, start=1):
            allow_overflow = _has_rose_overflow(
                cue, caption_overflow_records
            )
            try:
                english_lines = _wrap_english_to_width(
                    cue.english,
                    safe_width,
                    english_font,
                    max_lines=None if allow_overflow else 2,
                    allow_oversized_tokens=allow_overflow,
                )
                chinese_lines = _wrap_chinese_to_width(
                    cue.chinese,
                    safe_width,
                    chinese_font,
                    max_lines=None if allow_overflow else 2,
                )
                _rose_caption_geometry(
                    english_lines,
                    chinese_lines,
                    width=width,
                    height=height,
                    english_font=english_font,
                    chinese_font=chinese_font,
                    position=caption_position,
                    source_graphics_regions=regions,
                    mask_padding_px_per_edge=mask_padding_px_per_edge,
                    allow_unverified_estimate=allow_unverified_estimate,
                    allow_overflow=allow_overflow,
                )
            except ValueError as error:
                raise RuntimeError(
                    f"Caption verification failed: Rose Garden cue {index} "
                    "does not fit completely inside the selected caption region."
                ) from error
    elif layout_profile == DEFAULT_SUBTITLE_LAYOUT:
        chinese_font = max(32, round(height * 0.052))
        english_font = max(
            34,
            round(chinese_font * ENGLISH_TO_CHINESE_FONT_RATIO),
        )
        if english_font / chinese_font < 1.20:
            raise RuntimeError(
                "Caption verification failed: English text is not at least "
                "20% larger."
            )
    else:
        raise ValueError(f"Unsupported subtitle layout profile: {layout_profile}")
    review = translation_review or {}
    visual = visual_review or {}
    still_measurement = None
    if allow_unverified_estimate:
        verify_rose_garden_review = _rose_garden_review_module()
        still_measurement = verify_rose_garden_review.user_provided_still_measurement()

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
                "manual_review_required"
                if english_rate_flags
                or chinese_rate_flags
                or caption_overflow_records
                or (
                    layout_profile
                    in {KATIE_SUBTITLE_LAYOUT, ROSE_GARDEN_SUBTITLE_LAYOUT}
                    and visual.get("status") != "passed"
                )
                else "style_contract_passed"
            ),
            "layout_profile": layout_profile,
            "layout_configuration": (
                "passed"
                if layout_profile in {
                    KATIE_SUBTITLE_LAYOUT,
                    ROSE_GARDEN_SUBTITLE_LAYOUT,
                }
                else "default"
            ),
            "english_font_px": english_font,
            "chinese_font_px": chinese_font,
            "english_to_chinese_size_ratio": round(
                english_font / chinese_font, 3
            ),
            "chinese_to_english_size_ratio": round(
                chinese_font / english_font, 3
            ),
            "horizontal_safe_width_percent": (
                82
                if layout_profile == KATIE_SUBTITLE_LAYOUT
                else ROSE_CAPTION_SAFE_WIDTH_PERCENT
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                else 78
            ),
            "lower_margin_percent": (
                0
                if layout_profile == KATIE_SUBTITLE_LAYOUT
                else 0
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                else CAPTION_LOWER_MARGIN_PERCENT
            ),
            "max_lines_per_language": 2,
            "caption_overflow_exceptions": {
                "status": (
                    "manual_review_required"
                    if caption_overflow_records
                    else "none"
                ),
                "count": len(caption_overflow_records or []),
                "cues": caption_overflow_records or [],
            },
            "caption_region_height_percent": (
                20.5
                if layout_profile == KATIE_SUBTITLE_LAYOUT
                else round(caption_region["height"] / height * 100, 1)
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                else None
            ),
            "caption_region_validation": (
                "not_verified"
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                else "not_applicable"
            ),
            "caption_position_review": (
                "pending"
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                else "not_applicable"
            ),
            "caption_position": (
                caption_position
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                else None
            ),
            "caption_region_box_px": (
                caption_region
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                else None
            ),
            "source_graphics_review": (
                {
                    "status": (
                        "trusted_bbox_verified"
                        if trusted_frame_review is not None
                        else "user_provided_still_estimate"
                        if allow_unverified_estimate
                        else "not_verified"
                    ),
                    "review_status": (
                        "verified"
                        if trusted_frame_review is not None
                        else "pending"
                    ),
                    "controlled_cloud_review_route": (
                        "openssh_signature_allowlist"
                        if trusted_frame_review is not None
                        else "pending"
                        if allow_unverified_estimate
                        else "not_found_in_repository; confirmation_pending"
                    ),
                    "measurement_source": (
                        "user_provided_still"
                        if allow_unverified_estimate
                        else (
                            "trusted_frame_review"
                            if trusted_frame_review is not None
                            else "none"
                        )
                    ),
                    "measurement_status": (
                        "unverified_still_estimate"
                        if allow_unverified_estimate
                        else (
                            "human_verified"
                            if trusted_frame_review is not None
                            else "not_verified"
                        )
                    ),
                    "production_bbox_input": trusted_frame_review is not None,
                    "trusted_frame_review": (
                        trusted_frame_review
                        if trusted_frame_review is not None
                        else None
                    ),
                    "user_provided_still_measurement": (
                        still_measurement
                        if allow_unverified_estimate
                        else None
                    ),
                    "source_timecode": (
                        "not_verified" if allow_unverified_estimate else None
                    ),
                    "source_provenance": (
                        "not_verified" if allow_unverified_estimate else None
                    ),
                    "source_frame_review": "pending",
                    "visual_review": "pending",
                    "source_resolution_px": {
                        "width": width,
                        "height": height,
                    },
                    "regions": source_graphics_pixel_boxes(regions, width, height),
                }
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                else None
            ),
            "caption_band_occlusion": (
                {
                    "status": "source_lower_third_occluded_in_derivative",
                    "background": "opaque",
                    "original_source_unchanged": True,
                    "user_authorized_rose_exception": True,
                    "authorization_scope": "Rose Garden lower-third visual masking only",
                    "source_banner_bbox_px": next(
                        region["bbox_px"]
                        for region in source_graphics_pixel_boxes(
                            regions, width, height
                        )
                        if "lower-third" in str(region["label"]).lower()
                    ),
                    "mask_bbox_px": caption_region,
                    "expansion_direction": "outward on each of four edges",
                    "padding_selection": "implementation choice, not user-specified",
                    "output_resolution_px": {
                        "width": width,
                        "height": height,
                    },
                    "padding_px_per_edge": mask_padding_px_per_edge,
                    "status_label": "masked_not_clean",
                    "visual_review": "pending",
                }
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                and caption_position == "mask-lower-third"
                else {
                    "status": "non_mask_layout_selected",
                    "original_source_unchanged": True,
                    "visual_review": "pending",
                }
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                else None
            ),
            "rose_source_evidence": (
                {
                    "classification": "official_event_anchor_only",
                    "source_url": "https://www.youtube.com/watch?v=IySF_8OArvw",
                    "whitehouse_search": {
                        "url": (
                            "https://www.whitehouse.gov/"
                            "?s=President+Trump+Participates+in+a+Rose+Garden+Lunch"
                        ),
                        "status": "no_verifiable_event_article_or_embedded_video_found",
                        "thumbnail": (
                            "1280x720 search result only; not source-footage or "
                            "rights evidence"
                        ),
                        "wp_rest_access": "reported_403",
                    },
                    "reported_metadata": {
                        "title": (
                            "President Trump Participates in a Rose Garden Lunch, "
                            "Oct. 15, 2026"
                        ),
                        "channel": "The White House",
                        "player_duration": "36:33",
                    },
                    "event_match": "pending",
                    "exact_event_time_and_timezone": "pending",
                    "source_url_to_release_lineage": "pending",
                    "source_asset_hash_validation": "verified_by_cloud_workflow",
                    "candidate_angle_comparison": "not_verified",
                    "camera_position_map": "unavailable",
                    "source_graphics_and_frame_review": "pending",
                    "controlled_cloud_frame_review_route": (
                        "not_found_in_repository; confirmation_pending"
                    ),
                    "independent_reuse_rights_review": "pending",
                    "general_whitehouse_copyright_policy": {
                        "url": "https://www.whitehouse.gov/copyright/",
                        "specific_video_clearance": "not_established",
                    },
                }
                if layout_profile == ROSE_GARDEN_SUBTITLE_LAYOUT
                else None
            ),
            "line_order": (
                ["zh-Hans", "en"]
                if layout_profile == KATIE_SUBTITLE_LAYOUT
                else ["en", "zh-Hans"]
            ),
            "visual_frame_review": (
                "passed"
                if visual.get("status") == "passed"
                else "not_verified"
                if layout_profile in {
                    KATIE_SUBTITLE_LAYOUT,
                    ROSE_GARDEN_SUBTITLE_LAYOUT,
                }
                else "required"
            ),
            "english_reading_speed_over_20_cps_cues": english_rate_flags,
            "chinese_reading_speed_over_10_cps_cues": chinese_rate_flags,
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


def validate_asset_prefix(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", value):
        raise ValueError("Asset prefix must be a plain filename-safe identifier.")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--asset-prefix",
        default="whitehouse-oW-PQlgw1wo",
        help="Filename prefix for rendered video and subtitle assets.",
    )
    parser.add_argument(
        "--reuse-subtitles",
        type=Path,
        help="Reuse existing English and Chinese SRT files instead of rerunning ASR and translation.",
    )
    parser.add_argument(
        "--subtitle-layout",
        choices=(
            DEFAULT_SUBTITLE_LAYOUT,
            KATIE_SUBTITLE_LAYOUT,
            ROSE_GARDEN_SUBTITLE_LAYOUT,
        ),
        default=DEFAULT_SUBTITLE_LAYOUT,
        help=(
            "Subtitle layout profile. The Katie profile uses a fixed lower-third "
            "panel with larger Chinese above smaller English; the Rose Garden "
            "profile uses a human-reviewed source-aware caption region."
        ),
    )
    parser.add_argument(
        "--caption-position",
        choices=("top", "center", "mask-lower-third"),
        default="top",
    )
    parser.add_argument("--caption-safe-region-reviewed", action="store_true")
    parser.add_argument("--source-graphics-regions-json", default="[]")
    parser.add_argument("--source-frame-review-record-json", default="{}")
    parser.add_argument("--source-frame-review-signature", default="")
    parser.add_argument(
        "--frame-review-mode",
        choices=("trusted-signed-review", "unverified-review-draft"),
        default="trusted-signed-review",
    )
    parser.add_argument("--dispatch-actor", default="")
    parser.add_argument("--occlusion-exception-authorized", action="store_true")
    parser.add_argument("--mask-padding-px-per-edge", type=int)
    parser.add_argument(
        "--word-timings",
        type=Path,
        help=(
            "Reviewed JSON word timings for the final bilingual cues; "
            "invalid or unreviewed timings leave phrase captions unchanged."
        ),
    )
    parser.add_argument(
        "--disable-word-highlighting",
        action="store_true",
        help="Explicitly disable spoken-word highlighting.",
    )
    args = parser.parse_args()
    source_graphics_regions = (
        parse_source_graphics_regions(
            args.source_graphics_regions_json,
            require_human_verified=(
                args.caption_position == "mask-lower-third"
                and args.frame_review_mode != "unverified-review-draft"
            ),
            allow_empty=(
                args.caption_position != "mask-lower-third"
                or args.frame_review_mode == "unverified-review-draft"
            ),
        )
        if args.subtitle_layout == ROSE_GARDEN_SUBTITLE_LAYOUT
        else []
    )

    asset_prefix = validate_asset_prefix(args.asset_prefix)
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
    trusted_frame_review = require_trusted_mask_review(
        args.caption_position,
        source_path=source,
        source_width=width,
        source_height=height,
        source_duration=duration,
        source_frame_review_record_json=args.source_frame_review_record_json,
        source_frame_review_signature=args.source_frame_review_signature,
        source_graphics_regions_json=args.source_graphics_regions_json,
        dispatch_actor=args.dispatch_actor,
        frame_review_mode=args.frame_review_mode,
    )
    allow_unverified_estimate = (
        args.caption_position == "mask-lower-third"
        and args.frame_review_mode == "unverified-review-draft"
    )
    user_still_measurement = None
    if allow_unverified_estimate:
        verify_rose_garden_review = _rose_garden_review_module()
        user_still_measurement = (
            verify_rose_garden_review.user_provided_still_measurement()
        )
        source_graphics_regions = (
            verify_rose_garden_review.user_still_source_graphics_regions(
                width, height
            )
        )
    trusted_frame_review_evidence = (
        {
            "record": json.loads(args.source_frame_review_record_json),
            "signature_base64": args.source_frame_review_signature,
        }
        if trusted_frame_review is not None
        and trusted_frame_review.get("production_bbox_input") == "true"
        else None
    )
    if args.subtitle_layout == ROSE_GARDEN_SUBTITLE_LAYOUT:
        validate_rose_caption_placement(
            width=width,
            height=height,
            position=args.caption_position,
            safe_region_reviewed=args.caption_safe_region_reviewed,
            source_graphics_regions=source_graphics_regions,
            occlusion_exception_authorized=args.occlusion_exception_authorized,
            mask_padding_px_per_edge=args.mask_padding_px_per_edge,
            allow_unverified_estimate=allow_unverified_estimate,
        )
    language_probability = None
    translation_models_used = (
        [] if args.reuse_subtitles else [TRANSLATION_MODEL]
    )
    translation_review: dict[str, object] = {}
    visual_review: dict[str, object] = {}
    if args.reuse_subtitles:
        prefix = asset_prefix
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
        cues = merge_sentence_fragments(
            cues,
            preserve_katie_intro_boundary=(
                args.subtitle_layout == KATIE_SUBTITLE_LAYOUT
            ),
        )
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
    reflow_details: dict[str, object] = {
        "input_cue_count": len(cues),
        "reused_source_srt_preserved": args.reuse_subtitles is not None,
        "katie_intro_source_boundary_preserved": (
            args.subtitle_layout == KATIE_SUBTITLE_LAYOUT
            and any(
                _is_katie_intro_source_boundary(left, right)
                for left, right in zip(cues, cues[1:])
            )
        ),
        "alignment_policy": (
            "pinned_exact_phrase_maps_and_proportional_punctuation_alignment"
            if args.subtitle_layout == KATIE_SUBTITLE_LAYOUT
            else "proportional_punctuation_alignment_with_recorded_overflow_fallback"
            if args.subtitle_layout == ROSE_GARDEN_SUBTITLE_LAYOUT
            else "existing_clause_alignment"
        ),
    }
    caption_overflow_records: list[dict[str, object]] = []
    with audit.record(
        "subtitle_reflow",
        asset_id=source.name,
        tool="Python",
        version=platform.python_version(),
        details=reflow_details,
    ):
        if args.subtitle_layout == ROSE_GARDEN_SUBTITLE_LAYOUT:
            chinese_font, english_font, *_ = _rose_garden_wrap_limits(
                width, height
            )
            caption_region = rose_caption_region(
                width,
                height,
                args.caption_position,
                source_graphics_regions,
                args.mask_padding_px_per_edge,
                allow_unverified_estimate=allow_unverified_estimate,
            )
            if args.caption_position == "mask-lower-third":
                chinese_font, english_font = _rose_garden_font_sizes_for_region(
                    chinese_font,
                    english_font,
                    caption_region["height"],
                )
            safe_width = min(
                round(width * ROSE_CAPTION_SAFE_WIDTH_PERCENT / 100),
                caption_region["width"]
                - 2 * caption_region.get("mask_padding_px_per_edge", 0),
            )
            cues = reflow_rose_garden_cues(
                cues,
                safe_width=safe_width,
                chinese_font=chinese_font,
                english_font=english_font,
                safe_height=caption_region["height"],
                overflow_records=caption_overflow_records,
            )
        else:
            cues = reflow_cues(
                cues,
                align_sentence_to_clause_punctuation=(
                    args.subtitle_layout == KATIE_SUBTITLE_LAYOUT
                ),
            )
        reflow_details["output_cue_count"] = len(cues)
    if args.disable_word_highlighting:
        word_timings = None
        word_highlighting = disabled_word_highlighting_status()
    else:
        word_timings, word_highlighting = load_reviewed_word_timings(
            args.word_timings,
            cues,
        )

    prefix = asset_prefix
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
    ) as operation:
        english_srt.write_text(srt_text(cues, "en"), encoding="utf-8")
        chinese_srt.write_text(srt_text(cues, "zh"), encoding="utf-8")
        combined_srt = bilingual_srt_text(cues)
        bilingual_srt.write_text(combined_srt, encoding="utf-8")
        bilingual_vtt.write_text(
            vtt_from_bilingual_srt(combined_srt),
            encoding="utf-8",
        )
        highlighting_applied = write_ass(
            ass_path,
            cues,
            width,
            height,
            layout_profile=args.subtitle_layout,
            word_timings=word_timings,
            caption_position=args.caption_position,
            source_graphics_regions=source_graphics_regions,
            occlusion_exception_authorized=args.occlusion_exception_authorized,
            mask_padding_px_per_edge=args.mask_padding_px_per_edge,
            allow_unverified_estimate=allow_unverified_estimate,
            caption_overflow_records=caption_overflow_records,
        )
        if (
            word_highlighting["status"] == "enabled"
            and not highlighting_applied
        ):
            word_highlighting = {
                "status": "not_verified",
                "reason": "word_highlighting_render_preflight_failed",
            }
        operation["details"]["word_highlighting"] = word_highlighting

    output_video = output_dir / f"{prefix}-bilingual.mp4"
    ffmpeg_version = run(["ffmpeg", "-version"], capture=True).splitlines()[0]
    with audit.record(
        "subtitle_burn",
        asset_id=output_video.name,
        tool="ffmpeg",
        version=ffmpeg_version,
        details={
            "source_asset": source.name,
            "resolution": f"{width}x{height}",
            "word_highlighting": word_highlighting,
        },
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
        validate_release_asset_size(output_video.stat().st_size)
    quality_checks = verify_cues(
        cues,
        duration=duration,
        width=width,
        height=height,
        translation_review=translation_review,
        visual_review=visual_review,
        layout_profile=args.subtitle_layout,
        caption_position=args.caption_position,
        caption_safe_region_reviewed=args.caption_safe_region_reviewed,
        source_graphics_regions=source_graphics_regions,
        trusted_frame_review=trusted_frame_review_evidence,
        occlusion_exception_authorized=args.occlusion_exception_authorized,
        mask_padding_px_per_edge=args.mask_padding_px_per_edge,
        allow_unverified_estimate=allow_unverified_estimate,
        caption_overflow_records=caption_overflow_records,
    )
    quality_checks["word_highlighting"] = word_highlighting

    manifest = {
        "source_video": source.name,
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
        "subtitle_reflow": reflow_details,
        "subtitle_overflow_exceptions": caption_overflow_records,
        "subtitle_cues": len(cues),
        "languages": ["en", "zh-Hans"],
        "video_file": output_video.name,
        "subtitle_files": [
            english_srt.name,
            chinese_srt.name,
            bilingual_srt.name,
            *(
                [ass_path.name]
                if args.subtitle_layout == ROSE_GARDEN_SUBTITLE_LAYOUT
                else []
            ),
        ],
        "subtitle_ass_file": (
            ass_path.name
            if args.subtitle_layout == ROSE_GARDEN_SUBTITLE_LAYOUT
            else None
        ),
        "subtitle_ass_sha256": (
            hashlib.sha256(ass_path.read_bytes()).hexdigest()
            if args.subtitle_layout == ROSE_GARDEN_SUBTITLE_LAYOUT
            else None
        ),
        "subtitle_style": (
            (
                "fixed opaque lower-third backing (20.5% frame height, full "
                "frame width, bottom-flush) on the subtitle derivative only; "
                "Chinese above and at least 1.20x English font size; English "
                "below; reduced absolute font sizes; fixed "
                "positions; maximum two lines per language; "
                "authored with pysubs2 "
                f"{package_version('pysubs2')} and burned with FFmpeg libass; "
                "phrase-level timing; visual review remains required"
                + (
                    "; reviewed audio-derived spoken-word emphasis"
                    if word_highlighting["status"] == "enabled"
                    else ""
                )
            )
            if args.subtitle_layout == KATIE_SUBTITLE_LAYOUT
            else (
                "human-reviewed source-aware caption region with 68% line-width "
                "target; general positions avoid protected source graphics; "
                "the opt-in Rose exception uses an opaque mask limited to the "
                "human-verified lower-third BBox plus the recorded 1-5 px per "
                "edge; the source remains unchanged and the derivative is "
                "masked_not_clean; English is at least 1.20x Chinese; maximum "
                "two explicitly wrapped lines per language; libass automatic "
                "wrapping disabled; visual review remains pending"
                + (
                    "; reviewed audio-derived spoken-word emphasis"
                    if word_highlighting["status"] == "enabled"
                    else ""
                )
            )
            if args.subtitle_layout == ROSE_GARDEN_SUBTITLE_LAYOUT
            else (
                "gold Chinese above white English; English nominal font size is "
                "1.50x Chinese; authored with pysubs2 "
                f"{package_version('pysubs2')} and burned with FFmpeg libass; "
                "responsive phrase-level timing"
                + (
                    "; reviewed audio-derived spoken-word emphasis"
                    if word_highlighting["status"] == "enabled"
                    else ""
                )
            )
        ),
        "frame_review_mode": args.frame_review_mode,
        "source_frame_measurement": (
            {
                **user_still_measurement,
                "review_status": "pending",
            }
            if user_still_measurement is not None else None
        ),
        "render": {"word_highlighting": word_highlighting},
        "word_highlighting": word_highlighting,
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
    if args.subtitle_layout != ROSE_GARDEN_SUBTITLE_LAYOUT:
        ass_path.unlink(missing_ok=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
