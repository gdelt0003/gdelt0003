"""Prepare a clearly pending, per-run Rose Garden Pages review preview."""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import shutil
from pathlib import Path

try:
    from .verify_rose_garden_publication_review import (
        EVENT_ID,
        RENDERED_ASSET,
        SOURCE_ASSET,
    )
except ImportError:
    from verify_rose_garden_publication_review import (
        EVENT_ID,
        RENDERED_ASSET,
        SOURCE_ASSET,
    )


REPOSITORY = "gdelt0003/gdelt0003"


def prepare_preview(*, artifact_dir: Path, site_dir: Path, render_run_id: str) -> Path:
    if not re.fullmatch(r"\d{1,20}", render_run_id):
        raise RuntimeError("render_run_id must be a numeric GitHub Actions run ID.")
    manifest_path = artifact_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("The private render artifact has no valid manifest.") from error
    identity = manifest.get("event_identity") if isinstance(manifest, dict) else None
    if not isinstance(identity, dict) or identity.get("event_id") != EVENT_ID:
        raise RuntimeError("The artifact manifest is not for the pinned Rose Garden event.")
    if manifest.get("source_video") != SOURCE_ASSET:
        raise RuntimeError("The artifact manifest does not identify the pinned source.")
    rendered = manifest.get("rendered_video")
    if not isinstance(rendered, dict) or rendered.get("file") != RENDERED_ASSET:
        raise RuntimeError("The artifact manifest does not identify the expected review MP4.")
    expected_digest = rendered.get("sha256")
    if not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise RuntimeError("The manifest MP4 SHA-256 is invalid.")
    mp4_path = artifact_dir / RENDERED_ASSET
    if not mp4_path.is_file():
        raise RuntimeError("The rendered review MP4 is missing.")
    digest = hashlib.sha256()
    with mp4_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_digest or mp4_path.stat().st_size != rendered.get(
        "size_bytes"
    ):
        raise RuntimeError("The rendered MP4 does not match its manifest.")
    subtitle_files = manifest.get("subtitle_files")
    if not isinstance(subtitle_files, list) or not subtitle_files:
        raise RuntimeError("The render manifest has no subtitle files.")

    event_dir = site_dir / "events" / EVENT_ID
    preview_relative_path = Path("review-previews") / f"run-{render_run_id}" / RENDERED_ASSET
    preview_path = event_dir / preview_relative_path
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(mp4_path, preview_path)
    for filename in [*subtitle_files, "manifest.json", "operation-audit.json"]:
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise RuntimeError("The render artifact contains an unsafe review filename.")
        source = artifact_dir / filename
        if not source.is_file() or source.stat().st_size == 0:
            raise RuntimeError(f"The render review artifact is missing: {filename}")
        shutil.copyfile(source, preview_path.parent / filename)

    page_path = event_dir / "index.html"
    html = page_path.read_text(encoding="utf-8")
    old_asset = (
        f"https://github.com/{REPOSITORY}/releases/download/"
        f"rose-garden-lunch-review/{RENDERED_ASSET}"
    )
    new_asset = preview_relative_path.as_posix()
    if html.count(old_asset) != 2:
        raise RuntimeError("Expected exactly two legacy review-video URLs on the page.")
    pending_label = "PUBLIC · EXTERNAL REVIEW DRAFT · PENDING"
    if html.count(pending_label) != 1:
        raise RuntimeError("The source Pages page is not in its pending review state.")
    old_media_note = (
        "以下为公开预发布版中的双语烧录视频，不是原始来源或最终批准版本。"
    )
    new_media_note = (
        f"当前为公开 Pages 评审预览（render run {render_run_id}）；"
        "来源画面、英语 ASR、中文翻译及发布复核仍待审。"
    )
    old_host_note = (
        "派生审查视频由 GitHub 公开预发布版托管，不在 Pages 部署包中包含大型 MP4；"
        "原始视频没有被重新托管。"
    )
    new_host_note = (
        "本预览仅供公开外部评审，尚未通过五项产物复核，不是正式 Release；"
        "MP4 由本次 Pages 预览托管，原始视频没有被重新托管。"
    )
    old_artifact_links = (
        '<p><a href="https://www.youtube.com/watch?v=IySF_8OArvw" '
        'rel="noopener noreferrer">查看提交的 YouTube 原始来源（次要来源链接）</a></p>'
    )
    if html.count(old_media_note) != 1 or html.count(old_host_note) != 1:
        raise RuntimeError("The pending Pages preview copy did not match expected text.")
    if html.count(old_artifact_links) != 1:
        raise RuntimeError("The source link anchor for review artifacts was not found.")
    preview_dir = preview_relative_path.parent.as_posix()
    review_files = ["manifest.json", "operation-audit.json", *subtitle_files]
    review_links = " · ".join(
        f'<a href="{preview_dir}/{html_lib.escape(filename, quote=True)}">'
        f"{html_lib.escape(filename)}</a>"
        for filename in dict.fromkeys(review_files)
    )
    artifact_links = (
        f'<p>本次构建的复核文件：{review_links}</p>\n      {old_artifact_links}'
    )
    html = html.replace(old_asset, new_asset)
    html = html.replace(old_media_note, new_media_note)
    html = html.replace(old_host_note, new_host_note)
    html = html.replace(old_artifact_links, artifact_links)
    page_path.write_text(html, encoding="utf-8")
    return preview_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--render-run-id", required=True)
    args = parser.parse_args()
    preview_path = prepare_preview(
        artifact_dir=args.artifact_dir,
        site_dir=args.site_dir,
        render_run_id=args.render_run_id,
    )
    print(f"Pending public Pages review preview prepared: {preview_path}")


if __name__ == "__main__":
    main()
