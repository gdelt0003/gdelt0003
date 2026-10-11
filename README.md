# Open Video Catalog

A static, searchable catalog that indexes and links to public YouTube videos; it does not download or host the video files. GitHub Actions runs `yt-dlp` to read public video metadata, then publishes the generated static site to GitHub Pages. Public sources do not require cookies, login, or credentials.

## Configure channels and playlists

Edit [`sources.txt`](sources.txt). Add one public YouTube channel or playlist URL per line:

```text
# A public channel
https://www.youtube.com/@WhiteHouse

# A playlist
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx
```

Blank lines and lines beginning with `#` are ignored. Duplicate URLs are removed. Supported source URL hosts are `youtube.com` and `youtu.be`, and each URL must use HTTPS. The checked-in White House channel is a public demo source; replace it or add your own sources as needed.

The source list accepts up to **1,000 channels/playlists**. Sources are processed sequentially, with at least a one-second pause between sources, to avoid parallel request bursts. Individual requests time out after at most 90 seconds and the whole run has a five-hour fetch budget. This is best-effort for very large or slow lists: if time runs out, unvisited sources are explicitly recorded as failed/skipped rather than silently treated as empty. A source can contribute at most **50 videos**; the default is 12.

Set the repository Actions variable `VIDEO_LIMIT_PER_SOURCE` to change the scheduled-run limit (1–50). A manual run can override it in the **Actions → Update catalog and deploy Pages → Run workflow** form. Source errors, successful sources with no public videos, and successful sources with videos are reported separately in the site’s “Source update status” panel. One failed source does not prevent the rest of the catalog from being published.

## Run and publish

1. Commit `sources.txt` and the workflow to the repository’s default branch.
2. In **Settings → Pages**, set **Build and deployment → Source** to **GitHub Actions**.
3. In **Settings → Actions → General → Workflow permissions**, allow workflows to use the repository’s read permissions. The workflow itself declares the `pages: write` and `id-token: write` permissions required by the Pages deployment action.
4. Run the workflow manually from the Actions tab, or wait for its six-hour schedule. The workflow installs `yt-dlp` only on the GitHub-hosted runner, fetches metadata, and uploads **only the generated `site/` directory** as the Pages artifact.

The frontend is plain HTML, CSS, and JavaScript; no local frontend dependencies or build step are needed. Run the metadata fetcher’s unit tests locally with Python’s standard library:

```text
python -m unittest discover -s tests
```
