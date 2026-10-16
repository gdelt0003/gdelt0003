"""Point the Rose Garden review page at an approved, per-render release."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


OLD_RELEASE_TAG = "rose-garden-lunch-review"
VIDEO_FILE = "RoseGardenLunch-IySF_8OArvw-bilingual.mp4"
REPOSITORY = "gdelt0003/gdelt0003"


def update_review_page(page_path: Path, release_tag: str) -> None:
    if not re.fullmatch(r"rose-garden-lunch-review-\d{1,20}", release_tag):
        raise RuntimeError("Release tag must be a unique Rose Garden render tag.")
    html = page_path.read_text(encoding="utf-8")
    old_asset = f"releases/download/{OLD_RELEASE_TAG}/{VIDEO_FILE}"
    new_asset = f"releases/download/{release_tag}/{VIDEO_FILE}"
    if html.count(old_asset) != 2:
        raise RuntimeError("Expected exactly two pinned review-video URLs on the page.")
    pending_intro = "以下项目均为未完成状态；本页没有提供已核实的审查结论。"
    reviewed_intro = (
        "操作员声明以下五项已针对本次构建的视频复核并通过；这不是独立认证。"
        "逐项 HTTPS 证据及 MP4 SHA-256 绑定记录见对应 Release 中的 "
        "publication-review-verification.json。"
    )
    pending_header = "PUBLIC · EXTERNAL REVIEW DRAFT · PENDING"
    reviewed_header = "PUBLIC · EXTERNAL REVIEW DRAFT · REVIEW ATTESTATIONS RECORDED"
    pending_identity = (
        "事件标题、日期（2026-10-15）及地点（White House Rose Garden）来自提交信息，"
        "尚未独立核实。原视频与所述事件的匹配、音频/字幕、中文翻译均未核验。"
    )
    reviewed_identity = (
        "事件身份、来源/事件匹配、英语 ASR 与中文翻译已由操作员针对本次构建的视频"
        "声明通过；该声明及其证据链接记录于对应 Release。"
    )
    pending_warning = (
        "ASR 与机器翻译未经人工核验；该页面和公开预发布资产均不代表字幕准确性"
        "或最终发布批准。"
    )
    reviewed_warning = (
        "本次构建的 ASR、中文翻译、来源画面及权利审查由操作员声明通过；"
        "该页面仍是外部审查草稿，不代表最终发布批准。"
    )
    pending_description = (
        "玫瑰园午餐事件的公开外部审查草稿。来源匹配、字幕、翻译及延时效果均未核验。"
    )
    reviewed_description = (
        "玫瑰园午餐外部审查草稿；五项操作员复核声明已记录，不代表最终批准。"
    )
    if html.count(pending_intro) != 1:
        raise RuntimeError("The review checklist intro did not match the pending page.")
    if html.count('<input type="checkbox" disabled>') != 5:
        raise RuntimeError("Expected exactly five pending review checkboxes.")
    if html.count("<span>待审</span>") != 5:
        raise RuntimeError("Expected exactly five pending review labels.")
    if html.count(pending_header) != 1 or html.count(pending_identity) != 1:
        raise RuntimeError("The event review header did not match its pending state.")
    if html.count(pending_warning) != 1:
        raise RuntimeError("The pending ASR/translation warning did not match.")
    if html.count(pending_description) != 1:
        raise RuntimeError("The pending page description did not match.")

    html = html.replace(old_asset, new_asset)
    report_url = (
        f"https://github.com/{REPOSITORY}/releases/download/{release_tag}/"
        "publication-review-verification.json"
    )
    reviewed_intro_html = (
        f'{reviewed_intro}<a href="{report_url}">查看五项复核声明与证据链接</a>。'
    )
    html = html.replace(pending_intro, reviewed_intro_html)
    html = html.replace(pending_header, reviewed_header)
    html = html.replace(pending_identity, reviewed_identity)
    html = html.replace(pending_warning, reviewed_warning)
    html = html.replace(pending_description, reviewed_description)
    html = html.replace(
        '<input type="checkbox" disabled>',
        '<input type="checkbox" checked disabled>',
    )
    html = html.replace("<span>待审</span>", "<span>已复核</span>")
    page_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", type=Path, required=True)
    parser.add_argument("--release-tag", required=True)
    args = parser.parse_args()
    update_review_page(args.page, args.release_tag)


if __name__ == "__main__":
    main()
