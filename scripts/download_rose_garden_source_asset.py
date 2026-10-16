"""Download the pinned Rose Garden source from its draft Release asset."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


def find_draft_asset(
    releases: list[dict[str, Any]], release_tag: str, asset_name: str
) -> tuple[int, int]:
    matches = [
        release
        for release in releases
        if isinstance(release, dict) and release.get("tag_name") == release_tag
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one source release named {release_tag!r}; "
            f"found {len(matches)}."
        )
    release = matches[0]
    if release.get("draft") is not True:
        raise RuntimeError("The pinned source intake release must remain a draft.")
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("The pinned source release has no asset list.")
    matching_assets = [
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("name") == asset_name
    ]
    if len(matching_assets) != 1:
        raise RuntimeError(
            f"Expected exactly one {asset_name!r} asset in the source draft; "
            f"found {len(matching_assets)}."
        )
    release_id = release.get("id")
    asset_id = matching_assets[0].get("id")
    if type(release_id) is not int or release_id <= 0:
        raise RuntimeError("The source draft has an invalid release ID.")
    if type(asset_id) is not int or asset_id <= 0:
        raise RuntimeError("The pinned source asset has an invalid asset ID.")
    return release_id, asset_id


def download_source_asset(
    *,
    repo: str,
    release_tag: str,
    asset_name: str,
    expected_sha256: str,
    output: Path,
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise RuntimeError("repo must be a GitHub owner/repository identifier.")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise RuntimeError("expected_sha256 must be a lowercase SHA-256 digest.")
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", f"repos/{repo}/releases"],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        pages = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("GitHub returned invalid Release metadata JSON.") from error
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise RuntimeError("GitHub returned an invalid paginated Release response.")
    releases = [release for page in pages for release in page]
    release_id, asset_id = find_draft_asset(releases, release_tag, asset_name)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as destination:
        subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/releases/assets/{asset_id}",
                "--header",
                "Accept: application/octet-stream",
            ],
            check=True,
            stdout=destination,
        )
    digest = hashlib.sha256()
    with output.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"Downloaded source SHA-256 mismatch: expected {expected_sha256}, "
            f"received {actual_sha256}."
        )
    print(
        f"Downloaded draft Release {release_id} asset {asset_id}: "
        f"{asset_name} (SHA-256 {actual_sha256})"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--asset-name", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    download_source_asset(
        repo=args.repo,
        release_tag=args.release_tag,
        asset_name=args.asset_name,
        expected_sha256=args.sha256,
        output=args.output,
    )


if __name__ == "__main__":
    main()
