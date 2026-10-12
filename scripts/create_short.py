"""Create a bounded vertical short on a GitHub-hosted runner."""

import json
import os
import re
import subprocess
import sys
import tempfile
from bisect import bisect_left
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "site" / "data" / "catalog.json"
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
MAX_SOURCE_BYTES = 500 * 1024 * 1024
MAX_CLIP_SECONDS = 60
MIN_CLIP_SECONDS = 10
MAX_OUTPUT_BYTES = 20 * 1024 * 1024
HOOK_TERMS = {
    "announced", "answer", "breaking", "challenge", "change", "decision",
    "important", "launch", "new", "now", "plan", "record", "result",
    "reveal", "surprise", "today", "why", "what", "how",
}
LOW_VALUE_TERMS = {"intro", "introduction", "welcome", "opening", "outro", "closing", "conclusion"}


class ShortCreationError(Exception):
    """An expected download, metadata, or ffmpeg failure."""


def validate_video_url(value):
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in YOUTUBE_HOSTS:
        raise ValueError("Provide a single https:// YouTube video URL")
    if parsed.hostname in {"youtu.be", "www.youtu.be"} and not parsed.path.strip("/"):
        raise ValueError("YouTube URL does not contain a video ID")
    if parsed.hostname not in {"youtu.be", "www.youtu.be"} and not (
        parsed.path.startswith("/watch") or parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/")
    ):
        raise ValueError("Provide a video URL, not a channel or playlist URL")
    return value


def video_id_from_url(value):
    try:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in YOUTUBE_HOSTS:
            return ""
        if parsed.hostname in {"youtu.be", "www.youtu.be"}:
            video_id = parsed.path.strip("/").split("/")[0]
        elif parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            match = re.match(r"^/(?:shorts|embed)/([^/]+)", parsed.path)
            video_id = match.group(1) if match else ""
        return video_id if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", video_id) else ""
    except ValueError:
        return ""


def choose_segment(metadata, clip_seconds):
    video_duration = metadata.get("duration")
    if not isinstance(video_duration, (int, float)) or video_duration < MIN_CLIP_SECONDS:
        raise ValueError("Video is shorter than the minimum clip length")

    target_length = min(clip_seconds, int(video_duration), MAX_CLIP_SECONDS)
    chapters = metadata.get("chapters") or []
    candidates = []
    for chapter in chapters:
        title = str(chapter.get("title") or "")
        start = chapter.get("start_time")
        end = chapter.get("end_time")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        if end - start < min(target_length, MIN_CLIP_SECONDS):
            continue
        tokens = set(re.findall(r"[a-z]+", title.lower()))
        score = 2 * len(tokens & HOOK_TERMS)
        score += 2 if re.search(r"\d", title) else 0
        score += 1 if "?" in title else 0
        score += 1 if "!" in title else 0
        score -= 4 * len(tokens & LOW_VALUE_TERMS)
        candidates.append((score, start, end, title))

    if candidates:
        score, start, end, title = max(candidates, key=lambda item: (item[0], -item[1], item[3]))
        length = min(target_length, int(end - start))
        return {
            "startSeconds": int(start),
            "durationSeconds": length,
            "selectionReason": f"Chapter-title hook heuristic (score {score}): {title}",
            "clipTitle": title,
        }

    start = min(15, max(0, int(video_duration) - target_length))
    return {
        "startSeconds": start,
        "durationSeconds": target_length,
        "selectionReason": "No suitable chapter metadata; selected a short segment after the opening.",
    }


def parse_webvtt(contents):
    cues = []
    lines = contents.replace("\r", "").splitlines()
    index = 0
    pattern = re.compile(
        r"(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{3})\s+-->\s+"
        r"(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{3})"
    )
    while index < len(lines):
        match = pattern.match(lines[index].strip())
        if not match:
            index += 1
            continue
        values = [int(value or 0) for value in match.groups()]
        start = values[0] * 3600 + values[1] * 60 + values[2] + values[3] / 1000
        end = values[4] * 3600 + values[5] * 60 + values[6] + values[7] / 1000
        index += 1
        text_lines = []
        while index < len(lines) and lines[index].strip():
            cleaned = re.sub(r"<[^>]*>", "", lines[index]).strip()
            if cleaned:
                text_lines.append(unescape(cleaned))
            index += 1
        text = re.sub(r"\s+", " ", " ".join(text_lines)).strip()
        if text and end > start:
            cues.append({"start": start, "end": end, "text": text})
        index += 1
    return cues


def choose_transcript_segment(cues, video_duration, clip_seconds):
    target_length = min(clip_seconds, int(video_duration), MAX_CLIP_SECONDS)
    if not cues or target_length < MIN_CLIP_SECONDS:
        return None
    ordered_cues = sorted(cues, key=lambda cue: cue["start"])
    starts = [cue["start"] for cue in ordered_cues]
    word_prefix = [0]
    hook_prefix = [0]
    question_prefix = [0]
    music_prefix = [0]
    for cue in ordered_cues:
        words = re.findall(r"[\w']+", cue["text"].lower())
        word_prefix.append(word_prefix[-1] + len(words))
        hook_prefix.append(hook_prefix[-1] + len(set(words) & HOOK_TERMS))
        question_prefix.append(question_prefix[-1] + cue["text"].count("?"))
        music_prefix.append(music_prefix[-1] + int(bool(
            re.search(r"\[(?:music|applause|laughter)\]", cue["text"], re.IGNORECASE)
        )))

    candidates = []
    for index, cue in enumerate(ordered_cues):
        start = max(0, int(cue["start"]))
        end = min(video_duration, start + target_length)
        if end - start < target_length * 0.8:
            continue
        right = bisect_left(starts, end, lo=index + 1)
        word_count = word_prefix[right] - word_prefix[index]
        if word_count < 8:
            continue
        hooks = hook_prefix[right] - hook_prefix[index]
        questions = question_prefix[right] - question_prefix[index]
        music = music_prefix[right] - music_prefix[index]
        score = min(word_count, 160) / 20 + hooks * 2 + min(questions, 2) - music * 8
        candidates.append((score, start, end, word_count, hooks, questions, ordered_cues[index:right]))
    if not candidates:
        return None
    score, start, end, word_count, hooks, questions, window = max(
        candidates,
        key=lambda item: (item[0], -item[1]),
    )
    hook_cues = [
        cue["text"] for cue in window
        if "?" in cue["text"] or set(re.findall(r"[a-z]+", cue["text"].lower())) & HOOK_TERMS
    ]
    clip_title = (hook_cues[0] if hook_cues else window[0]["text"]).strip()
    if len(clip_title) > 100:
        clip_title = clip_title[:97].rsplit(" ", 1)[0] + "..."
    return {
        "startSeconds": start,
        "durationSeconds": min(target_length, int(end - start)),
        "clipTitle": clip_title,
        "selectionReason": (
            f"Transcript-window heuristic (score {score:.1f}, {word_count} words, "
            f"{hooks} hook terms, {questions} questions); editorial review recommended."
        ),
    }


def format_srt_time(milliseconds):
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def write_srt(cues, segment, path):
    clip_start = segment["startSeconds"]
    clip_end = clip_start + segment["durationSeconds"]
    blocks = []
    for cue in cues:
        if cue["end"] <= clip_start or cue["start"] >= clip_end:
            continue
        start = max(0, int((cue["start"] - clip_start) * 1000))
        end = min(segment["durationSeconds"] * 1000, int((cue["end"] - clip_start) * 1000))
        text = cue["text"].replace("{", "(").replace("}", ")")
        if end > start and text:
            blocks.append(f"{len(blocks) + 1}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}")
    if blocks:
        path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return bool(blocks)


def run_checked(command, *, timeout):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ShortCreationError(str(error)) from error
    if result.returncode:
        raise ShortCreationError((result.stderr.strip() or "Command failed")[-1500:])
    return result


def discover_video(directory):
    candidates = [
        path for path in directory.iterdir()
        if path.is_file() and path.name.startswith("source.")
    ]
    if len(candidates) != 1:
        raise ShortCreationError("Could not identify the downloaded source video")
    if candidates[0].stat().st_size > MAX_SOURCE_BYTES:
        raise ShortCreationError("Downloaded video exceeds the 500 MB source limit")
    return candidates[0]


def make_clip(source_path, output_path, segment, subtitles_path=None):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subtitle_filter = ""
    if subtitles_path:
        subtitle_filter = (
            f",subtitles='{subtitles_path.as_posix()}':"
            "force_style='FontName=DejaVu Sans,FontSize=22,Outline=2,Shadow=1,Alignment=2,MarginV=120'"
        )
    filter_graph = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=20:10[bg];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30{subtitle_filter}[v]"
    )
    run_checked([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", str(segment["startSeconds"]),
        "-i", str(source_path),
        "-t", str(segment["durationSeconds"]),
        "-filter_complex", filter_graph,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
        "-maxrate", "4500k", "-bufsize", "9000k",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(output_path),
    ], timeout=600)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise ShortCreationError("ffmpeg did not produce a clip")
    if output_path.stat().st_size > MAX_OUTPUT_BYTES:
        output_path.unlink()
        raise ShortCreationError("Generated clip exceeds the 20 MiB Pages per-clip limit")


def create_short(video_url, clip_seconds, clip_dir, run_url):
    validate_video_url(video_url)
    if not MIN_CLIP_SECONDS <= clip_seconds <= MAX_CLIP_SECONDS:
        raise ValueError(f"Clip duration must be between {MIN_CLIP_SECONDS} and {MAX_CLIP_SECONDS} seconds")
    metadata_result = run_checked([
        "yt-dlp", "--no-warnings", "--skip-download", "--no-playlist",
        "--socket-timeout", "20", "--retries", "2", "--dump-single-json", video_url,
    ], timeout=90)
    try:
        metadata = json.loads(metadata_result.stdout)
    except json.JSONDecodeError as error:
        raise ShortCreationError(f"Could not parse video metadata: {error}") from error
    video_id = str(metadata.get("id") or "")
    resolved_url = metadata.get("webpage_url") or video_url
    validate_video_url(resolved_url)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", video_id):
        raise ShortCreationError("Metadata returned an invalid YouTube video ID")
    segment = choose_segment(metadata, clip_seconds)
    segment.setdefault("clipTitle", metadata.get("title") or "Short from this video")
    clip_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="source-") as temporary:
        download_dir = Path(temporary)
        try:
            run_checked([
                "yt-dlp", "--no-warnings", "--no-playlist", "--skip-download",
                "--write-subs", "--write-auto-subs", "--sub-langs", "en",
                "--sub-format", "vtt", "--socket-timeout", "20", "--retries", "1",
                "-o", str(download_dir / "source.%(ext)s"),
                resolved_url,
            ], timeout=90)
        except ShortCreationError as error:
            print(f"Captions unavailable; continuing without burned subtitles: {error}", file=sys.stderr)
        cues = []
        for subtitle_file in download_dir.glob("source*.vtt"):
            cues.extend(parse_webvtt(subtitle_file.read_text(encoding="utf-8", errors="replace")))
        transcript_segment = choose_transcript_segment(cues, metadata["duration"], clip_seconds)
        if transcript_segment:
            segment = transcript_segment
        srt_path = download_dir / "captions.srt"
        captions_available = write_srt(cues, segment, srt_path)

        run_checked([
            "yt-dlp", "--no-warnings", "--no-playlist",
            "--socket-timeout", "20", "--retries", "2",
            "--fragment-retries", "2", "--max-filesize", "500M",
            "--format", "bv*[height<=1080]+ba/b[height<=1080]",
            "--merge-output-format", "mp4",
            "-o", str(download_dir / "source.%(ext)s"),
            resolved_url,
        ], timeout=900)
        source_path = discover_video(download_dir)
        filename = f"{video_id}-short.mp4"
        output_path = clip_dir / filename
        make_clip(source_path, output_path, segment, srt_path if captions_available else None)
        if captions_available:
            (clip_dir / f"{video_id}-captions.srt").write_text(
                srt_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

    return {
        "videoId": video_id,
        "title": metadata.get("title") or "Untitled video",
        "author": metadata.get("channel") or metadata.get("uploader") or "YouTube",
        "originalDuration": metadata.get("duration_string") or "",
        "originalDurationSeconds": metadata.get("duration"),
        "thumbnail": metadata.get("thumbnail") or "",
        "uploadDate": metadata.get("upload_date") or "",
        "sourceUrl": resolved_url,
        "clipFile": filename,
        "clipPath": f"clips/{filename}",
        "clipBytes": output_path.stat().st_size,
        **segment,
        "status": "available",
        "captions": "English captions burned in" if captions_available else "No English captions available",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "reachDisclaimer": "Heuristic candidate only; no reach or virality is guaranteed.",
    }


def write_output(name, value):
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output_file:
            output_file.write(f"{name}={value}\n")


def require_clip_authorization(value):
    if str(value).strip().lower() != "true":
        raise ShortCreationError(
            "Refused: confirm you own this video or are authorized to edit it; "
            "no metadata or subtitle request for this clip and no source-video download was made."
        )


def update_catalog(catalog, short):
    videos = catalog.setdefault("videos", [])
    if short.get("videoId") and not any(
        str(video.get("id")) == str(short["videoId"]) for video in videos
    ):
        videos.append({
            "id": short["videoId"],
            "title": short.get("title") or "Original video (metadata not fetched)",
            "author": short.get("author") or "YouTube",
            "duration": short.get("originalDuration") or "",
            "durationSeconds": short.get("originalDurationSeconds"),
            "url": short["sourceUrl"],
            "thumbnail": short.get("thumbnail") or "",
            "source": short["sourceUrl"],
            "uploadDate": short.get("uploadDate") or "",
        })
    active_shorts = []
    for old in catalog.get("shorts", []):
        if old.get("status") != "available" or not old.get("clipPath"):
            continue
        if old.get("videoId") != short.get("videoId"):
            active_shorts.append(old)
    active_shorts.append(short)
    catalog["shorts"] = active_shorts[-100:]
    return catalog


def main():
    video_url = os.environ.get("SHORT_VIDEO_URL", "").strip()
    run_url = os.environ.get("ACTIONS_RUN_URL", "").strip()
    clip_dir = Path(os.environ.get(
        "SHORTS_OUTPUT_DIR",
        str(Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "derived-shorts"),
    ))
    try:
        require_clip_authorization(os.environ.get("CLIP_AUTHORIZED", "false"))
        clip_seconds = int(os.environ.get("CLIP_DURATION_SECONDS", "45"))
        short = create_short(video_url, clip_seconds, clip_dir, run_url)
        status = 0
        write_output("clip_created", "true")
        print(f"Created {short['clipFile']}: {short['selectionReason']}")
    except (OSError, ValueError, ShortCreationError) as error:
        short = {
            "videoId": video_id_from_url(video_url),
            "title": "Original video (metadata not fetched)",
            "sourceUrl": video_url,
            "runUrl": run_url,
            "status": "failed",
            "error": str(error)[:500],
        }
        status = 1
        write_output("clip_created", "false")
        print(f"Short generation failed: {error}", file=sys.stderr)

    try:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        catalog = update_catalog(catalog, short)
        CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if short["status"] == "available":
            manifest = clip_dir / "manifest.json"
            manifest.write_text(json.dumps({
                "original": {"videoId": short["videoId"], "url": short["sourceUrl"], "title": short["title"]},
                "derivedShort": short,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, KeyError) as error:
        print(f"Could not update catalog with short status: {error}", file=sys.stderr)
        return 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
