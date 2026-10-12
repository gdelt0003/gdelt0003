import json
from datetime import datetime, timezone
from pathlib import Path

VIDEO_ID = "KFHqevUWLWE"
VIDEO_TITLE = "President Trump Makes an Announcement, Oct. 7, 2026"
CHANNEL = "The White House"
VIDEO_DURATION = 2990
INVIDIOUS_INSTANCE = "https://invidious.f5.si"
YOUTUBE_SOURCE = f"https://www.youtube.com/watch?v={VIDEO_ID}"
OUTPUT = Path("generated")
SEGMENTS = [
    {"id": "white-house-opening", "title": "开场片段", "start": 82, "end": 156},
    {"id": "white-house-middle", "title": "中段片段", "start": 542, "end": 612},
    {"id": "white-house-later", "title": "后段片段", "start": 1209, "end": 1294},
]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    segments = []
    for item in SEGMENTS:
        if item["end"] > VIDEO_DURATION or item["end"] <= item["start"]:
            raise ValueError(f"Invalid segment range for {item['id']}")
        segments.append({
            "id": item["id"],
            "title": item["title"],
            "start_sec": item["start"],
            "end_sec": item["end"],
            "duration_sec": item["end"] - item["start"],
            "status": "timestamp_link",
            "source_channel": CHANNEL,
            "source_title": VIDEO_TITLE,
            "source_url": YOUTUBE_SOURCE,
            "play_url": f"{INVIDIOUS_INSTANCE}/watch?v={VIDEO_ID}&t={item['start']}",
            "file": None,
            "note": "在 Invidious 打开白宫原视频并从该时间点播放；这不是单独导出的 MP4。",
        })

    manifest = {
        "status": "timestamp_links",
        "message": "白宫视频的分段播放链接已准备；Invidious 播放链接不会生成或保存独立 MP4。",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_url": YOUTUBE_SOURCE,
        "source_title": VIDEO_TITLE,
        "source_channel": CHANNEL,
        "source_duration_sec": VIDEO_DURATION,
        "invidious_instance": INVIDIOUS_INSTANCE,
        "batch": segments,
    }
    (OUTPUT / "default_batch.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(segments)} timestamped White House playback links.")


if __name__ == "__main__":
    main()
