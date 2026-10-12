# Open Video Catalog

A static, searchable catalog of public YouTube videos with an optional hosted-runner short generator. Scheduled runs index public metadata, append it to a durable repository archive, and publish the searchable catalog to GitHub Pages. An optional manual run can download one selected source video **inside a GitHub-hosted Actions runner**, make a vertical short, and publish that derived clip to Pages for in-page playback. Original YouTube videos are never downloaded into or mirrored by this repository. Public videos need no cookies or login, but being public does not grant reuse rights: only generate clips from videos you own or are authorized to adapt.

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

In **Actions → Update catalog and deploy Pages → Run workflow**, paste one public video URL into **Optional public video URL to turn into a vertical short** and explicitly check **I own this video or have permission to create an edit** (default **false**). Without confirmation, the clip step records a refusal before requesting metadata/subtitles for that selected clip or downloading its source video; the separate catalog metadata fetch still runs. Set the requested duration to 10–60 seconds (default 45). The hosted Ubuntu runner fetches metadata and English subtitles when available, downloads a source copy limited to 500 MB, and uses ffmpeg to create a 9:16 MP4; each output clip is capped at 20 MiB. Video processing and all video downloads run only on the GitHub-hosted runner. The original YouTube link remains on its catalog card, alongside an in-page player and download link for its related derived short.

The segment selector is a **heuristic candidate**, not an AI highlighter: it scores available English transcript windows for speech density, question marks, and a small set of hook words; if captions are absent, it falls back to chapter-title cues, then a short segment after the opening. Captions are burned in when English subtitles are available; otherwise the clip is made without captions. Review the result manually. This does not guarantee a viral result, does not auto-post to social networks, and does not generate B-roll or voiceovers.

`archive/catalog.json` is an append-by-video-ID metadata archive committed to the current branch. On bootstrap it merges the currently published Pages catalog with the new feed before writing the archive, so videos already on the site are not discarded. The full archive is copied to the Pages catalog and is searchable/paginated there. The metadata archive is capped at 90 MiB so the tracked JSON file remains below GitHub's 100 MiB hard file limit.

Short MP4s are stored under `site/clips/`, deployed to Pages, and restored from the previous Pages deployment on each run. Restore requests are limited to HTTPS `*.github.io` URLs, validated relative clip paths, a 90 MiB catalog response cap / 20 MiB per-clip cap, a 20-second catalog timeout / 45-second timeout per clip, and at most 100 restore attempts. Clips are retained newest-first up to **100 files / 700 MiB total**, with an overall Pages output safety threshold of **950 MiB** (below GitHub Pages' 1 GiB site limit). When a cap is reached, older clips are evicted and their available-player entries are omitted; metadata remains archived. GitHub Pages and repository storage are not unlimited: GitHub recommends keeping repositories under 1 GiB, and individual tracked files above 50 MiB trigger a warning while files above 100 MiB are rejected. A short at 20 MiB is below that warning threshold, but the cumulative archive may eventually approach repository limits; monitor usage and prune/archive externally before that point. Metadata commits use the Actions token with `contents: write`; because this workflow only triggers on schedules and manual dispatch (not `push`), its own archive commit does not cause an Actions loop. A protected branch that rejects the bot push fails the workflow before deployment, and repository rules must allow the workflow token to update `archive/catalog.json`.

## Run and publish

1. Commit `sources.txt` and the workflow to the repository’s default branch.
2. In **Settings → Pages**, set **Build and deployment → Source** to **GitHub Actions**.
3. In **Settings → Actions → General → Workflow permissions**, allow workflows to have read and write permissions. The workflow declares `contents: write` for the metadata archive and `pages: write` / `id-token: write` for Pages deployment.
4. Run the workflow manually from the Actions tab, or wait for its six-hour schedule. The workflow installs `yt-dlp` and, only for an authorized requested short, `ffmpeg` on `ubuntu-latest` (a GitHub-hosted runner; never a self-hosted runner). The Pages artifact contains only the generated `site/` directory. The runner has finite time/storage and the job has a six-hour limit; each selected source is limited to 500 MB, each clip to 60 seconds/20 MiB, and one manual run processes one video. Short selection uses transcript/chapter hook heuristics and an opening-offset fallback; it is not an AI highlighter and cannot guarantee reach or virality. Review clips before sharing. Auto-posting, B-roll, and voice generation are out of scope.

The frontend is plain HTML, CSS, and JavaScript; no local frontend dependencies or build step are needed. Unit tests exercise metadata selection, caption parsing, and validation using Python’s standard library; they do not download or process video:

```text
python -m unittest discover -s tests
```
