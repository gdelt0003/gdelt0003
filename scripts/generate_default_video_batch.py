import argparse
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VIDEO_ID = "KroMEOZ8oFo"
VIDEO_TITLE = "President Trump and the President of China Deliver Remarks"
CHANNEL = "The White House"
VIDEO_DURATION = 1587
VIDEO_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
OUTPUT = Path("generated")
CLIP_OUTPUT = OUTPUT / "clips"
MAX_CLIPS = 5
MAX_CLIP_DURATION = 55
HOOK_LEAD_SECONDS = 12
KEYWORDS = re.compile(r"\b(china|chinese|xi(?:\s+jinping)?|jinping)\b|中国|习近平", re.I)
SPEAKER_COLORS = (
    "#40C4FF",
    "#FFB74D",
    "#69F0AE",
    "#FF80AB",
    "#B388FF",
    "#FF8A65",
    "#80DEEA",
    "#FFD54F",
)


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker_id: str


@dataclass
class Clip:
    start: int
    end: int
    title: str


def run(command):
    subprocess.run(command, check=True)


def parse_timestamp(value):
    value = value.replace(",", ".")
    parts = value.split(":")
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    else:
        hours, minutes, seconds = parts
    whole, _, fraction = seconds.partition(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(whole) + (
        float(f"0.{fraction}") if fraction else 0
    )


def read_vtt(path):
    cues = []
    content = path.read_text(encoding="utf-8-sig")
    for block in re.split(r"\r?\n\s*\r?\n", content):
        lines = block.splitlines()
        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line),
            None,
        )
        if timing_index is None:
            continue
        timing = lines[timing_index].split("-->")
        start = parse_timestamp(timing[0].strip().split()[0])
        end = parse_timestamp(timing[1].strip().split()[0])
        text = " ".join(lines[timing_index + 1:])
        text = html.unescape(re.sub(r"<[^>]*>", "", text))
        text = re.sub(r"\s+", " ", text).strip()
        if text and end > start:
            cues.append(Cue(start, end, text))
    return cues


def cue_file(directory, language_pattern):
    matches = sorted(directory.glob(f"{VIDEO_ID}.{language_pattern}*.vtt"))
    return matches[0] if matches else None


def build_clips(english, chinese):
    all_cues = english + chinese
    hits = [cue for cue in all_cues if KEYWORDS.search(cue.text)]
    candidates = []
    for hit in hits:
        start = max(0, int(hit.start) - HOOK_LEAD_SECONDS)
        end = min(VIDEO_DURATION, start + MAX_CLIP_DURATION)
        if end - start < 25:
            start = max(0, end - 25)
        matching = [
            cue for cue in all_cues
            if cue.end > start and cue.start < end
        ]
        matching_text = " ".join(cue.text for cue in matching)
        if not KEYWORDS.search(matching_text):
            continue
        score = len(KEYWORDS.findall(matching_text))
        has_xi = re.search(
            r"\bxi(?:\s+jinping)?\b|\bjinping\b|习近平",
            matching_text,
            re.I,
        )
        title = "中美与习近平现场对话" if has_xi else "特朗普谈中国"
        candidates.append((score, start, end, title, matching))

    selected = []
    for candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
        _, start, end, title, cues = candidate
        if any(start < chosen.end and end > chosen.start for chosen in selected):
            continue
        selected.append(Clip(start, end, title))
        if len(selected) == MAX_CLIPS:
            break
    selected.sort(key=lambda clip: clip.start)
    if not selected:
        raise RuntimeError(
            "No China/Xi Jinping caption matches were found; refusing to "
            "generate unrelated highlights."
        )
    return selected


def merge_bilingual_cues(clip, english, chinese):
    rows = []
    for en_cue in english:
        if en_cue.end <= clip.start or en_cue.start >= clip.end:
            continue
        midpoint = (en_cue.start + en_cue.end) / 2
        zh_cue = min(
            chinese,
            key=lambda cue: abs((cue.start + cue.end) / 2 - midpoint),
            default=None,
        )
        zh_text = ""
        if zh_cue and abs((zh_cue.start + zh_cue.end) / 2 - midpoint) <= 2.5:
            zh_text = zh_cue.text
        text = en_cue.text
        if zh_text and zh_text != text:
            text = f"{text}\\N{zh_text}"
        start = max(en_cue.start, clip.start) - clip.start
        end = min(en_cue.end, clip.end) - clip.start
        if end > start:
            rows.append((start, end, text))
    if not rows:
        raise RuntimeError(
            f"No bilingual captions overlap selected clip at {clip.start}s."
        )
    return rows


def read_autosubs_speakers(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise RuntimeError(f"AutoSubs JSON has no segments list: {path}")

    turns = []
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise RuntimeError(f"Invalid AutoSubs segment at index {index}")
        speaker_id = segment.get("speaker_id")
        if speaker_id is None or str(speaker_id).strip() in {"", "?"}:
            continue
        try:
            start = float(segment["start"])
            end = float(segment["end"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                f"Invalid timestamps in AutoSubs segment {index}"
            ) from error
        if end <= start:
            raise RuntimeError(f"Invalid interval in AutoSubs segment {index}")
        turns.append(SpeakerTurn(start, end, str(speaker_id)))
    return turns


def assign_speakers(rows, turns):
    assigned = []
    for start, end, text in rows:
        overlap_by_speaker = {}
        for turn in turns:
            overlap = max(0.0, min(end, turn.end) - max(start, turn.start))
            if overlap:
                overlap_by_speaker[turn.speaker_id] = (
                    overlap_by_speaker.get(turn.speaker_id, 0.0) + overlap
                )
        speaker_id = None
        if overlap_by_speaker:
            ranked = sorted(
                overlap_by_speaker.items(),
                key=lambda item: (-item[1], item[0]),
            )
            if len(ranked) == 1 or ranked[0][1] > ranked[1][1] + 1e-6:
                speaker_id = ranked[0][0]
        assigned.append((start, end, text, speaker_id))
    return assigned


def ass_color(hex_color):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_color):
        raise ValueError(f"Invalid speaker color: {hex_color}")
    red, green, blue = (
        hex_color[index:index + 2] for index in (1, 3, 5)
    )
    return f"&H00{blue.upper()}{green.upper()}{red.upper()}&"


def ass_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole = int(seconds % 60)
    centiseconds = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02}:{whole:02}.{centiseconds:02}"


def srt_timestamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole, milliseconds = divmod(milliseconds, 1000)
    return (
        f"{hours:02}:{minutes:02}:{whole:02},"
        f"{milliseconds:03}"
    )


def ass_escape(text):
    return text.replace("{", "").replace("}", "").replace("\n", " ")


def write_ass(path, clip, rows, width, height):
    hook_font = max(32, round(height * 0.054))
    caption_font = max(24, round(height * 0.035))
    vertical_margin = round(height * 0.07)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,Noto Sans CJK SC,{hook_font},&H00FFFFFF,&H000000FF,&H00120A05,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,8,56,56,{vertical_margin},1
Style: Dual,Noto Sans CJK SC,{caption_font},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,2,56,56,{vertical_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [
        header,
        (
            "Dialogue: 1,0:00:00.00,0:00:04.00,Hook,,0,0,0,,"
            f"{ass_escape(clip.title)}"
        ),
    ]
    for row in rows:
        start, end, text = row[:3]
        speaker_id = row[3] if len(row) > 3 else None
        speaker_tag = ""
        if speaker_id is not None:
            try:
                color = SPEAKER_COLORS[
                    (int(speaker_id) - 1) % len(SPEAKER_COLORS)
                ]
            except ValueError:
                color = SPEAKER_COLORS[
                    sum(speaker_id.encode("utf-8")) % len(SPEAKER_COLORS)
                ]
            speaker_tag = f"{{\\c{ass_color(color)}}}"
        lines.append(
            "Dialogue: 0,"
            f"{ass_timestamp(start)},"
            f"{ass_timestamp(end)},Dual,,0,0,0,,"
            f"{speaker_tag}{ass_escape(text)}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def probe_video(path):
    data = json.loads(subprocess.check_output([
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(path),
    ], text=True))
    if not data.get("streams"):
        raise RuntimeError(f"No video stream found in {path}")
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"])


def main():
    parser = argparse.ArgumentParser(
        description="Generate vertical bilingual highlights from the White House source."
    )
    parser.add_argument(
        "--diarize",
        action="store_true",
        help="Use the installed AutoSubs CLI to color captions by speaker.",
    )
    parser.add_argument(
        "--autosubs-bin",
        default=os.environ.get("AUTOSUBS_BIN", "autosubs"),
        help="AutoSubs CLI path (default: AUTOSUBS_BIN or autosubs).",
    )
    parser.add_argument(
        "--max-speakers",
        type=int,
        help="Optional upper bound passed to AutoSubs diarization.",
    )
    args = parser.parse_args()
    if args.max_speakers is not None and args.max_speakers < 1:
        parser.error("--max-speakers must be at least 1")
    if args.diarize and not (
        shutil.which(args.autosubs_bin) or Path(args.autosubs_bin).is_file()
    ):
        parser.error(
            f"AutoSubs CLI not found: {args.autosubs_bin}. "
            "Install AutoSubs or set AUTOSUBS_BIN."
        )

    CLIP_OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="whitehouse-highlights-") as temporary:
        work = Path(temporary)
        source_template = work / f"{VIDEO_ID}.%(ext)s"
        run([
            "yt-dlp",
            "--force-ipv4",
            "--js-runtimes",
            "node",
            "--no-playlist",
            "--write-auto-subs",
            "--sub-langs",
            "en.*,zh-Hans,zh-CN,zh",
            "--sub-format",
            "vtt",
            "--output",
            str(source_template),
            "--skip-download",
            VIDEO_URL,
        ])

        english_path = cue_file(work, "en")
        chinese_path = (
            cue_file(work, "zh-Hans")
            or cue_file(work, "zh-CN")
            or cue_file(work, "zh")
        )
        if not english_path or not chinese_path:
            raise RuntimeError(
                "Both English and Simplified Chinese subtitle tracks are "
                "required; no partial-caption clips will be published."
            )
        english = read_vtt(english_path)
        chinese = read_vtt(chinese_path)
        if not english or not chinese:
            raise RuntimeError("The downloaded bilingual subtitle tracks are empty.")
        clips = build_clips(english, chinese)
        manifest_clips = []

        for number, clip in enumerate(clips, start=1):
            clip_id = f"china-xi-highlight-{number}"
            raw_template = work / f"{clip_id}.%(ext)s"
            run([
                "yt-dlp",
                "--force-ipv4",
                "--js-runtimes",
                "node",
                "--no-playlist",
                "--download-sections",
                f"*{clip.start}-{clip.end}",
                "--force-keyframes-at-cuts",
                "--format",
                "bestvideo+bestaudio/best",
                "--merge-output-format",
                "mkv",
                "--output",
                str(raw_template),
                VIDEO_URL,
            ])
            raw_candidates = [
                path for path in work.glob(f"{clip_id}.*")
                if path.suffix.lower() in {".mkv", ".mp4", ".webm"}
            ]
            if not raw_candidates:
                raise RuntimeError(f"yt-dlp did not create input for {clip_id}")
            raw_clip = raw_candidates[0]
            rows = merge_bilingual_cues(clip, english, chinese)
            if args.diarize:
                transcript_path = work / f"{clip_id}.transcript.json"
                diarize_command = [
                    args.autosubs_bin,
                    str(raw_clip),
                    "--diarize",
                    "--lang",
                    "en",
                    "-f",
                    "json",
                    "-o",
                    str(transcript_path),
                ]
                if args.max_speakers is not None:
                    diarize_command.extend([
                        "--max-speakers",
                        str(args.max_speakers),
                    ])
                run(diarize_command)
                rows = assign_speakers(
                    rows,
                    read_autosubs_speakers(transcript_path),
                )
            source_width, source_height = probe_video(raw_clip)
            output_width = source_height + source_height % 2
            output_height = round(output_width * 16 / 9)
            output_height += output_height % 2
            source_resolution = f"{source_width}x{source_height}"

            subtitle_path = CLIP_OUTPUT / f"{clip_id}.ass"
            write_ass(
                subtitle_path,
                clip,
                rows,
                output_width,
                output_height,
            )
            clip_path = CLIP_OUTPUT / f"{clip_id}.mp4"
            run([
                "ffmpeg",
                "-y",
                "-i",
                str(raw_clip),
                "-vf",
                (
                    "split=2[bg][fg];"
                    f"[bg]scale={output_width}:{output_height}:"
                    "force_original_aspect_ratio=increase,"
                    f"crop={output_width}:{output_height},boxblur=30:15[bgblur];"
                    f"[fg]scale={output_width}:{output_height}:"
                    "force_original_aspect_ratio=decrease[fgfit];"
                    "[bgblur][fgfit]overlay=(W-w)/2:(H-h)/2,setsar=1,"
                    f"ass={subtitle_path.as_posix()}"
                ),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "18",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(clip_path),
            ])
            duration = round(float(subprocess.check_output([
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(clip_path),
            ], text=True).strip()))
            expected_duration = clip.end - clip.start
            if abs(duration - expected_duration) > 2:
                raise RuntimeError(
                    f"Unexpected clip duration for {clip_id}: "
                    f"expected {expected_duration}s, got {duration}s"
                )

            srt_path = CLIP_OUTPUT / f"{clip_id}.srt"
            srt_lines = []
            for index, row in enumerate(rows, start=1):
                start, end, text = row[:3]
                plain_text = text.replace("\\N", "\n")
                srt_lines.append(
                    f"{index}\n{srt_timestamp(start)} --> "
                    f"{srt_timestamp(end)}\n{plain_text}"
                )
            srt_path.write_text("\n\n".join(srt_lines) + "\n", encoding="utf-8")
            subtitle_path.unlink()
            manifest_clips.append({
                "id": clip_id,
                "title": clip.title,
                "start_sec": clip.start,
                "end_sec": clip.end,
                "duration_sec": duration,
                "status": "available",
                "source_channel": CHANNEL,
                "source_title": VIDEO_TITLE,
                "source_url": VIDEO_URL,
                "file": f"generated/clips/{clip_path.name}",
                "subtitle_file": f"generated/clips/{srt_path.name}",
                "source_resolution": source_resolution,
                "output_resolution": f"{output_width}x{output_height}",
                "subtitle_languages": ["en", "zh-Hans"],
                "speaker_diarization": args.diarize,
                "file_size_bytes": clip_path.stat().st_size,
                "note": (
                    "按 China/Xi 字幕命中截取；竖屏短视频，烧录中英双语字幕；"
                    + ("已按说话人着色。" if args.diarize else "未启用说话人着色。")
                ),
            })

        current_outputs = {
            path.resolve()
            for clip in manifest_clips
            for path in (
                CLIP_OUTPUT / Path(clip["file"]).name,
                CLIP_OUTPUT / Path(clip["subtitle_file"]).name,
            )
        }
        for path in CLIP_OUTPUT.iterdir():
            if path.suffix.lower() in {".mp4", ".srt"} and path.resolve() not in current_outputs:
                path.unlink()

        manifest = {
            "status": "generated",
            "message": "白宫中美会谈高光已按最高可用源分辨率重新编码，并烧录中英双语字幕。",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_url": VIDEO_URL,
            "source_title": VIDEO_TITLE,
            "source_channel": CHANNEL,
            "source_duration_sec": VIDEO_DURATION,
            "video_format": "vertical_9x16",
            "subtitle_languages": ["en", "zh-Hans"],
            "speaker_diarization": args.diarize,
            "batch": manifest_clips,
        }
        (OUTPUT / "default_batch.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"Generated {len(manifest_clips)} vertical 9:16 "
            "China/Xi clips with English and Simplified Chinese captions."
        )


if __name__ == "__main__":
    main()
