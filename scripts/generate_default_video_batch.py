import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

VIDEO_ID = "oW-PQlgw1wo"
VIDEO_TITLE = "President Trump Delivers Remarks, Oct. 6, 2026"
CHANNEL = "The White House"
VIDEO_DURATION = 3532
VIDEO_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
INVIDIOUS_INSTANCE = "https://invidious.f5.si"
OUTPUT = Path("generated")
CLIP_OUTPUT = OUTPUT / "clips"
SEGMENTS = [
    {
        "id": "arsenal-2-shipyard",
        "title": "宣布建设 Arsenal 2 新船厂",
        "start": 170,
        "end": 245,
        "note": "介绍 Arsenal 2 新船厂计划及重建造船能力。",
    },
    {
        "id": "submarine-production",
        "title": "扩大潜艇生产能力",
        "start": 690,
        "end": 770,
        "note": "介绍新船厂如何增加产能并缓解潜艇生产瓶颈。",
    },
    {
        "id": "golden-fleet",
        "title": "Golden Fleet 舰队计划",
        "start": 2385,
        "end": 2465,
        "note": "谈到美国海军 Golden Fleet 计划及造舰投资。",
    },
]


def run(command):
    subprocess.run(command, check=True)


def main():
    CLIP_OUTPUT.mkdir(parents=True, exist_ok=True)
    clips = []

    for item in SEGMENTS:
        if item["end"] > VIDEO_DURATION or item["end"] <= item["start"]:
            raise ValueError(f"Invalid segment range for {item['id']}")

        output = CLIP_OUTPUT / f"{item['id']}.%(ext)s"
        run([
            "yt-dlp",
            "--force-ipv4",
            "--js-runtimes",
            "node",
            "--no-playlist",
            "--force-overwrites",
            "--download-sections",
            f"*{item['start']}-{item['end']}",
            "--force-keyframes-at-cuts",
            "--recode-video",
            "mp4",
            "--format",
            "134+140",
            "--output",
            str(output),
            VIDEO_URL,
        ])

        clip_path = CLIP_OUTPUT / f"{item['id']}.mp4"
        if not clip_path.is_file() or clip_path.stat().st_size == 0:
            raise RuntimeError(f"yt-dlp did not create {clip_path}")

        duration_text = subprocess.check_output([
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(clip_path),
        ], text=True).strip()
        duration = round(float(duration_text))
        expected_duration = item["end"] - item["start"]
        if abs(duration - expected_duration) > 2:
            raise RuntimeError(
                f"Unexpected clip duration for {item['id']}: "
                f"expected {expected_duration}s, got {duration}s"
            )

        clips.append({
            "id": item["id"],
            "title": item["title"],
            "start_sec": item["start"],
            "end_sec": item["end"],
            "duration_sec": duration,
            "status": "available",
            "source_channel": CHANNEL,
            "source_title": VIDEO_TITLE,
            "source_url": VIDEO_URL,
            "play_url": (
                f"{INVIDIOUS_INSTANCE}/watch?v={VIDEO_ID}&t={item['start']}"
            ),
            "file": f"generated/clips/{clip_path.name}",
            "file_size_bytes": clip_path.stat().st_size,
            "note": item["note"],
        })

    manifest = {
        "status": "generated",
        "message": "白宫视频高光片段已剪辑为 MP4 并保存到 GitHub 仓库。",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_url": VIDEO_URL,
        "source_title": VIDEO_TITLE,
        "source_channel": CHANNEL,
        "source_duration_sec": VIDEO_DURATION,
        "invidious_instance": INVIDIOUS_INSTANCE,
        "batch": clips,
    }
    (OUTPUT / "default_batch.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated and validated {len(clips)} MP4 highlight clips.")


if __name__ == "__main__":
    main()
