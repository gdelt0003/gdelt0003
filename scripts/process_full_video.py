"""Transcribe, translate, and burn bilingual captions into a full video."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


ASR_MODEL = "large-v3-turbo"
TRANSLATION_MODEL = "facebook/m2m100_1.2B"
MAX_RELEASE_ASSET_BYTES = 1_950_000_000
MAX_SUBTITLE_CUE_SECONDS = 7.0
MIN_SUBTITLE_CUE_SECONDS = 0.83
ENGLISH_READING_SPEED = 18.0
CHINESE_READING_SPEED = 8.0


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


def _split_english(text: str, count: int) -> list[str]:
    words = text.split()
    if not words:
        return ["" for _ in range(count)]
    count = min(count, len(words))
    chunks = []
    start = 0
    break_before = {
        "and", "although", "as", "because", "but", "for", "from", "if",
        "in", "into", "of", "on", "or", "since", "that", "though", "to",
        "when", "while", "with", "which", "who",
    }
    for index in range(count):
        groups_left = count - index
        words_left = len(words) - start
        target = max(1, round(words_left / groups_left))
        end = min(len(words), start + target)
        if index < count - 1:
            latest_end = min(
                len(words) - (groups_left - 1),
                end + 2,
            )
            punctuation = [
                position + 1
                for position in range(start, latest_end)
                if re.search(r"[.!?;:,]$", words[position])
            ]
            connectors = [
                position
                for position in range(start + 1, latest_end + 1)
                if words[position].lower().strip("\"'“”‘’([{") in break_before
            ]
            preferred = punctuation or connectors
            if preferred:
                end = min(
                    preferred,
                    key=lambda position: abs(position - (start + target)),
                )
        chunks.append(" ".join(words[start:end]))
        start = end
    return chunks


def _is_ascii_word_character(character: str) -> bool:
    return character.isascii() and (
        character.isalnum() or character in "'-"
    )


def _split_chinese(text: str, count: int) -> list[str]:
    characters = list(text.strip())
    if not characters:
        return ["" for _ in range(count)]
    count = min(count, len(characters))
    chunks = []
    start = 0
    break_chars = set("，。！？；：、,.!?;")
    for index in range(count):
        groups_left = count - index
        chars_left = len(characters) - start
        target = max(1, round(chars_left / groups_left))
        end = min(len(characters), start + target)
        if index < count - 1:
            window_end = min(len(characters) - groups_left + 1, end + 5)
            preferred = [
                position + 1
                for position in range(start, window_end)
                if characters[position] in break_chars
            ]
            if preferred:
                end = min(
                    preferred,
                    key=lambda position: abs(position - (start + target)),
                )
            if (
                end < len(characters)
                and _is_ascii_word_character(characters[end - 1])
                and _is_ascii_word_character(characters[end])
            ):
                word_start = end - 1
                while (
                    word_start > start
                    and _is_ascii_word_character(characters[word_start - 1])
                ):
                    word_start -= 1
                word_end = end
                while (
                    word_end < len(characters)
                    and _is_ascii_word_character(characters[word_end])
                ):
                    word_end += 1
                valid_boundaries = [
                    boundary
                    for boundary in (word_start, word_end)
                    if boundary > start
                    and len(characters) - boundary >= groups_left - 1
                ]
                if valid_boundaries:
                    end = min(
                        valid_boundaries,
                        key=lambda position: abs(position - (start + target)),
                    )
        chunks.append("".join(characters[start:end]).strip())
        start = end
    return chunks


def _cjk_character_count(text: str) -> int:
    return sum(
        "\u3400" <= character <= "\u9fff"
        or "\uf900" <= character <= "\ufaff"
        for character in text
    )


def reflow_cues(cues: list[Cue], width: int, height: int) -> list[Cue]:
    chinese_font = max(32, round(height * 0.052))
    english_font = max(28, round(height * 0.046))
    safe_width = round(width * 0.68)
    max_english_chars = max(20, int(safe_width / (english_font * 0.55)))
    max_chinese_chars = max(10, int(safe_width / chinese_font))
    reflowed = []

    for cue in cues:
        duration = cue.end - cue.start
        if duration <= 0:
            continue
        english_chars = len(cue.english.replace(" ", ""))
        chinese_chars = _cjk_character_count(cue.chinese)
        requested_parts = max(
            1,
            round((duration + MAX_SUBTITLE_CUE_SECONDS - 1e-9)
                  // MAX_SUBTITLE_CUE_SECONDS),
            (english_chars + max_english_chars - 1) // max_english_chars,
            (chinese_chars + max_chinese_chars - 1) // max_chinese_chars,
            int(english_chars / (ENGLISH_READING_SPEED * duration) + 0.999),
            int(chinese_chars / (CHINESE_READING_SPEED * duration) + 0.999),
        )
        max_parts_for_readability = max(
            1,
            int(duration / MIN_SUBTITLE_CUE_SECONDS),
        )
        max_parts_for_text = min(
            max(1, len(cue.english.split())),
            max(1, len(cue.chinese.strip())),
        )
        parts = min(
            requested_parts,
            max_parts_for_readability,
            max_parts_for_text,
        )
        while True:
            english_chunks = _split_english(cue.english, parts)
            chinese_chunks = _split_chinese(cue.chinese, parts)
            if (
                parts >= min(max_parts_for_readability, max_parts_for_text)
                or (
                    all(len(chunk) <= max_english_chars for chunk in english_chunks)
                    and all(
                        _cjk_character_count(chunk) <= max_chinese_chars
                        for chunk in chinese_chunks
                    )
                )
            ):
                break
            parts += 1
        part_duration = duration / len(english_chunks)
        for index, (english, chinese) in enumerate(
            zip(english_chunks, chinese_chunks, strict=True)
        ):
            start = cue.start + part_duration * index
            end = (
                cue.end
                if index == len(english_chunks) - 1
                else cue.start + part_duration * (index + 1)
            )
            reflowed.append(Cue(start, end, english, chinese))
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
    english_font = max(28, round(height * 0.046))
    safe_width = round(width * 0.68)
    max_english_chars = max(20, int(safe_width / (english_font * 0.55)))
    max_chinese_chars = max(10, int(safe_width / chinese_font))
    margin = max(28, round(height * 0.20))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Chinese,Noto Sans CJK SC,{chinese_font},&H004DD8FF,&H000000FF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,3,1,2,{round(width * 0.16)},{round(width * 0.16)},{margin},1
Style: English,Noto Sans CJK SC,{english_font},&H00FFFFFF,&H000000FF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,3,1,2,{round(width * 0.16)},{round(width * 0.16)},{margin},1

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


def vtt_from_bilingual_srt(content: str) -> str:
    timing = re.compile(
        r"(\d{2}:\d{2}:\d{2}),(\d{3})( --> "
        r"\d{2}:\d{2}:\d{2}),(\d{3})"
    )
    return "WEBVTT\n\n" + timing.sub(r"\1.\2\3.\4", content)


def translate_batches(texts: list[str], *, batch_size: int = 8) -> list[str]:
    import torch
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

    model_id = TRANSLATION_MODEL
    tokenizer = M2M100Tokenizer.from_pretrained(model_id, src_lang="en")
    model = M2M100ForConditionalGeneration.from_pretrained(model_id)
    model.eval()
    target_language = tokenizer.get_lang_id("zh")
    translated: list[str] = []

    with torch.inference_mode():
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset:offset + batch_size]
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
            translated.extend(
                value.strip()
                for value in tokenizer.batch_decode(
                    generated,
                    skip_special_tokens=True,
                )
            )
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
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

    duration, width, height = probe_video(source)
    language_probability = None
    translation_models_used = (
        [] if args.reuse_subtitles else [TRANSLATION_MODEL]
    )
    if args.reuse_subtitles:
        prefix = "whitehouse-oW-PQlgw1wo"
        prior_manifest_path = args.reuse_subtitles / "manifest.json"
        if prior_manifest_path.is_file():
            prior_manifest = json.loads(
                prior_manifest_path.read_text(encoding="utf-8")
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
    else:
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

        chinese_texts = translate_batches([cue[2] for cue in english_cues])
        if len(chinese_texts) != len(english_cues):
            raise RuntimeError("Translation output count did not match transcript cues.")
        cues = [
            Cue(start, end, english, chinese)
            for (start, end, english), chinese in zip(
                english_cues,
                chinese_texts,
                strict=True,
            )
            if chinese
        ]
        language_probability = float(info.language_probability)
    if not cues:
        raise RuntimeError("Translation produced no Chinese subtitle cues.")
    cues = reflow_cues(cues, width, height)

    prefix = "whitehouse-oW-PQlgw1wo"
    english_srt = output_dir / f"{prefix}.en.srt"
    chinese_srt = output_dir / f"{prefix}.zh-Hans.srt"
    bilingual_srt = output_dir / f"{prefix}.en-zh.srt"
    bilingual_vtt = output_dir / f"{prefix}.en-zh.vtt"
    ass_path = output_dir / f"{prefix}.en-zh.ass"
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
        "translation_review": {
            "status": "not_performed",
            "llm_judges": 0,
            "source_cross_check_passes": 0,
        },
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
        "source_resolution_preserved": True,
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
