# Open Video Catalog

A static, searchable catalog of public YouTube videos with an optional hosted-runner short generator. Normal scheduled runs read public metadata and publish only the static catalog to GitHub Pages. An optional manual run can download one selected source video **inside a GitHub-hosted Actions runner**, make a vertical short, and attach it to that run as a temporary artifact. Neither source nor generated video files are published to GitHub Pages. Public videos need no cookies or login, but being public does not grant reuse rights: only generate clips from videos you own or are authorized to adapt.

## Configure channels and playlists

Edit [`sources.txt`](sources.txt). Add one public YouTube channel or playlist URL per line:

```text
# A public channel
https://www.youtube.com/@WhiteHouse/videos

# A playlist
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx
```

Blank lines and lines beginning with `#` are ignored. Duplicate URLs are removed. Supported source URL hosts are `youtube.com` and `youtu.be`, and each URL must use HTTPS. The checked-in White House channel is a public demo source; replace it or add your own sources as needed.

The source list accepts up to **1,000 channels/playlists**. Sources are processed sequentially, with at least a one-second pause between sources, to avoid parallel request bursts. Individual requests time out after at most 90 seconds and the whole run has a five-hour fetch budget. This is best-effort for very large or slow lists: if time runs out, unvisited sources are explicitly recorded as failed/skipped rather than silently treated as empty. A source can contribute at most **50 videos**; the default is 12.

Set the repository Actions variable `VIDEO_LIMIT_PER_SOURCE` to change the scheduled-run limit (1–50). A manual run can override it in the **Actions → Update catalog and deploy Pages → Run workflow** form. Source errors, successful sources with no public videos, and successful sources with videos are reported separately in the site’s “Source update status” panel. One failed source does not prevent the rest of the catalog from being published.

## Optional: make a linked vertical short

In **Actions → Update catalog and deploy Pages → Run workflow**, paste one public video URL into **Optional public video URL to turn into a vertical short**. Set the requested duration to 10–60 seconds (default 45). The hosted Ubuntu runner fetches metadata and English subtitles when available, downloads a source copy limited to 500 MB, and uses ffmpeg to create a 9:16 MP4; the output is capped at 100 MB. Video processing and all video downloads run only on the GitHub-hosted runner. The original YouTube link remains on the video card, with a related-short panel linking to the workflow run and its artifact.

The segment selector is a **heuristic candidate**, not an AI highlighter: it scores available English transcript windows for speech density, question marks, and a small set of hook words; if captions are absent, it falls back to chapter-title cues, then a short segment after the opening. Captions are burned in when English subtitles are available; otherwise the clip is made without captions. Review the result manually. This does not guarantee a viral result, does not auto-post to social networks, and does not generate B-roll or voiceovers.

Short MP4s and their manifest are kept out of the Pages artifact and uploaded as a separate Actions artifact for **14 days**. Catalog deployments fetch the previous public Pages catalog and retain valid original/short relationships until their artifact expiry; the selected video's original metadata is kept alongside it even if that video is not in `sources.txt`. If Pages uses a custom domain or URL, set the repository Actions variable `PAGES_BASE_URL` to the full Pages base URL (including any repository path) so the prior short index can be carried forward. Artifact download requires repository access (subject to repository visibility and GitHub permissions). Do not use the pipeline to redistribute material without rights.

## Run and publish

1. Commit `sources.txt` and the workflow to the repository’s default branch.
2. In **Settings → Pages**, set **Build and deployment → Source** to **GitHub Actions**.
3. In **Settings → Actions → General → Workflow permissions**, allow workflows to use the repository’s read permissions. The workflow itself declares the `pages: write` and `id-token: write` permissions required by the Pages deployment action.
4. Run the workflow manually from the Actions tab, or wait for its six-hour schedule. The workflow installs `yt-dlp` and, only for a requested short, `ffmpeg` on `ubuntu-latest` (a GitHub-hosted runner; never a self-hosted runner). It uploads **only the generated `site/` directory** as the Pages artifact. The runner has finite time/storage; each selected source is limited to 500 MB, each clip to 60 seconds/100 MB, and one manual run processes one video.

The frontend is plain HTML, CSS, and JavaScript; no local frontend dependencies or build step are needed. Unit tests exercise metadata selection, caption parsing, and validation using Python’s standard library; they do not download or process video:

```text
python -m unittest discover -s tests
```
