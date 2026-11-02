"""Point the Rose Garden review page at a per-render pending review draft."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


OLD_RELEASE_TAG = "rose-garden-lunch-review"
VIDEO_FILE = "RoseGardenLunch-IySF_8OArvw-bilingual.mp4"
REPOSITORY = "gdelt0003/gdelt0003"
REVIEW_LABELS = {
    "pending": "待审",
    "unverified": "未核验",
    "passed": "操作员记录通过",
    "failed": "操作员记录未通过",
}
REVIEW_CATEGORIES = (
    "source_event_match",
    "reuse_rights",
    "clean_source_frames",
    "english_asr",
    "chinese_translation",
)


def update_review_page(
    page_path: Path,
    release_tag: str,
    review_verification: dict[str, object] | None = None,
) -> None:
    if not re.fullmatch(r"rose-garden-lunch-review-\d{1,20}", release_tag):
        raise RuntimeError("Release tag must be a unique Rose Garden render tag.")
    html = page_path.read_text(encoding="utf-8")
    old_asset = f"releases/download/{OLD_RELEASE_TAG}/{VIDEO_FILE}"
    new_asset = f"releases/download/{release_tag}/{VIDEO_FILE}"
    if html.count(old_asset) != 2:
        raise RuntimeError("Expected exactly two pinned review-video URLs on the page.")
    if html.count("data-review-category=") != len(REVIEW_CATEGORIES):
        raise RuntimeError("Expected five categorized review-state entries.")
    if html.count("id=\"review-verification-link\"") != 1:
        raise RuntimeError("Expected the review record link placeholder.")

    checks: dict[str, object] = {}
    if review_verification is not None:
        verified_checks = review_verification.get("reviewed_checks")
        if not isinstance(verified_checks, dict) or set(verified_checks) != set(
            REVIEW_CATEGORIES
        ):
            raise RuntimeError("Review-state verification must contain five categories.")
        checks = verified_checks

    def replace_category(match: re.Match[str]) -> str:
        category = match.group(1)
        body = match.group(2)
        check = checks.get(category, {})
        if not isinstance(check, dict):
            raise RuntimeError(f"Invalid review-state entry for {category}.")
        status = check.get("status", "pending")
        if status not in REVIEW_LABELS:
            raise RuntimeError(f"Unknown review state for {category}: {status!r}.")
        checked = ' checked="checked"' if status == "passed" else ""
        body, input_count = re.subn(
            r'<input type="checkbox"(?: checked="checked")? disabled>',
            f'<input type="checkbox"{checked} disabled>',
            body,
        )
        body, label_count = re.subn(
            r"<span data-review-status>.*?</span>",
            f"<span data-review-status>{REVIEW_LABELS[status]}</span>",
            body,
            count=1,
            flags=re.DOTALL,
        )
        if input_count != 1 or label_count != 1:
            raise RuntimeError(f"Review page markup did not match {category}.")
        return f'<li data-review-category="{category}">{body}</li>'

    for category in REVIEW_CATEGORIES:
        html, count = re.subn(
            rf'<li data-review-category="({re.escape(category)})">(.*?)</li>',
            lambda match: replace_category(match),
            html,
            count=1,
            flags=re.DOTALL,
        )
        if count != 1:
            raise RuntimeError(f"Review page is missing {category}.")

    html = html.replace(old_asset, new_asset)
    report_url = f"https://github.com/{REPOSITORY}/releases/download/{release_tag}/publication-review-verification.json"
    html = html.replace(
        '<span id="review-verification-link">记录链接将在发布时填入。</span>',
        f'<a id="review-verification-link" href="{report_url}">查看本次复核状态记录（不代表独立认证）</a>',
    )
    page_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", type=Path, required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--review-verification", type=Path, required=True)
    args = parser.parse_args()
    review_verification = json.loads(
        args.review_verification.read_text(encoding="utf-8")
    )
    if not isinstance(review_verification, dict):
        raise RuntimeError("Review-state verification must be a JSON object.")
    update_review_page(args.page, args.release_tag, review_verification)


if __name__ == "__main__":
    main()
