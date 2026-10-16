"""Register a per-render Rose Garden review release in the homepage catalog."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


EVENT_DATE = "2026-10-15"
EVENT_TITLE = "President Trump Participates in a Rose Garden Lunch, Oct. 15, 2026"
SOURCE_URL = "https://www.youtube.com/watch?v=IySF_8OArvw"
VIDEO_FILE = "RoseGardenLunch-IySF_8OArvw-bilingual.mp4"
SUBTITLE_FILES = (
    ("English SRT · 复核声明已记录", "RoseGardenLunch-IySF_8OArvw.en.srt"),
    ("简体中文 SRT · 复核声明已记录", "RoseGardenLunch-IySF_8OArvw.zh-Hans.srt"),
    ("中英双语 SRT · 复核声明已记录", "RoseGardenLunch-IySF_8OArvw.en-zh.srt"),
    ("中英双语 VTT · 复核声明已记录", "RoseGardenLunch-IySF_8OArvw.en-zh.vtt"),
    ("中英双语 ASS · 复核声明已记录", "RoseGardenLunch-IySF_8OArvw.en-zh.ass"),
)


def update_main_video_catalog(
    main_videos_path: Path, release_tag: str, render_run_id: str
) -> None:
    if not re.fullmatch(r"rose-garden-lunch-review-\d{1,20}", release_tag):
        raise RuntimeError("Release tag must identify a per-render Rose Garden review.")
    if not re.fullmatch(r"\d{1,20}", render_run_id):
        raise RuntimeError("Render run ID must be numeric.")
    if release_tag != f"rose-garden-lunch-review-{render_run_id}":
        raise RuntimeError("Release tag must match the reviewed render run ID.")

    catalog = json.loads(main_videos_path.read_text(encoding="utf-8"))
    videos = catalog.get("videos")
    if not isinstance(videos, list):
        raise ValueError("Main video catalog must contain a videos array.")

    release_url = (
        f"https://github.com/gdelt0003/gdelt0003/releases/download/{release_tag}"
    )
    video_id = f"rose-garden-lunch-review-{render_run_id}"
    videos[:] = [video for video in videos if video.get("id") != video_id]
    videos.append(
        {
            "id": video_id,
            "title": f"{EVENT_TITLE} · 外部审查草稿",
            "event_date": EVENT_DATE,
            "homepage_status": "外部审查草稿 · 五项复核声明已记录",
            "publisher": "GDELT · Rose Garden bilingual review render",
            "video_url": f"{release_url}/{VIDEO_FILE}",
            "source_url": SOURCE_URL,
            "source_details_url": "events/rose-garden-lunch-2026-10-15/",
            "review_status": (
                "五项构建后复核声明及其 HTTPS 证据已记录并绑定本次 MP4；"
                "这仍是外部审查草稿，不代表最终发布批准。"
            ),
            "note": (
                "本条目指向本次已复核构建的公开预发布资产。复核状态仅反映"
                "工作流验证的操作员声明，不构成独立认证或最终发布批准。"
            ),
            "subtitles": [
                {"label": label, "url": f"{release_url}/{asset}"}
                for label, asset in SUBTITLE_FILES
            ],
        }
    )
    main_videos_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-videos", type=Path, required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--render-run-id", required=True)
    args = parser.parse_args()
    update_main_video_catalog(
        args.main_videos, args.release_tag, args.render_run_id
    )


if __name__ == "__main__":
    main()
