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
            f"{cue.english}\n{cue.chinese}"
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


def write_ass(path: Path, cues: list[Cue], width: int, height: int) -> None:
    font_size = max(30, round(height * 0.038))
    margin = max(28, round(height * 0.045))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Bilingual,Noto Sans CJK SC,{font_size},&H00FFFFFF,&H000000FF,&H00101010,&H90000000,0,0,0,0,100,100,0,0,1,3,1,2,80,80,{margin},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header]
    for cue in cues:
        text = (
            f"{ass_escape(cue.english)}\\N"
            f"{ass_escape(cue.chinese)}"
        )
        lines.append(
            f"Dialogue: 0,{ass_time(cue.start)},{ass_time(cue.end)},"
            f"Bilingual,,0,0,0,,{text}"
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.resolve()
    output_dir = args.output_dir.resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise FileNotFoundError(f"Input video is missing or empty: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)

    duration, width, height = probe_video(source)
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
    if not cues:
        raise RuntimeError("Translation produced no Chinese subtitle cues.")

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
        "asr_model": ASR_MODEL,
        "translation_model": TRANSLATION_MODEL,
        "subtitle_cues": len(cues),
        "languages": ["en", "zh-Hans"],
        "video_file": output_video.name,
        "subtitle_files": [
            english_srt.name,
            chinese_srt.name,
            bilingual_srt.name,
        ],
        "whisper_detected_language_probability": round(
            float(info.language_probability),
            4,
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
