# gdelt0003
A small GitHub Pages repo that fetches latest YouTube videos via GitHub Actions and publishes them to Pages.

## Quick start

1. Create or update the repository variable `YOUTUBE_URL` to a target YouTube URL such as:
   - `https://www.youtube.com/@gdelt0003`
   - `https://www.youtube.com/playlist?list=...`
2. Optionally set `VIDEO_LIMIT` (default: `8`).
3. Optionally set `YT_DLP_BIN` to a custom `yt-dlp` binary path when you need to override the default executable.
4. Push to `main` or run the workflow manually.
5. GitHub Pages will publish the site automatically.

## Notes

- No local frontend install is required.
- The workflow runs in GitHub Actions, installs `yt-dlp`, fetches data, and deploys the static site.
- For production, replace the example YouTube URL with your real channel or playlist.
- The fetch script also accepts `YT_DLP_BIN` for local testing or custom installations.

## Generate bilingual shorts

The repository also includes a local short-video editing pipeline. It downloads a long source video and its English captions, translates captions to Simplified Chinese, then renders each selected highlight in two 1080x1920 styles with the original audio:

```powershell
python scripts/create_shorts.py
```

The default sample uses the White House's October 6, 2026 remarks video (58:52; 3,532 seconds) and creates three distinct highlight windows with both an editorial and a punchy variant: 12:03-12:59 (shipyard production/jobs), 20:58-21:44 (Navy systems), and 41:57-42:16 (Russia-Ukraine remarks). Outputs and a source/timing manifest are written to `outputs/whitehouse-oct-06-2026/`. Supply `--url` and `--output-dir` to process a different source. The script requires `yt-dlp`, `ffmpeg`, and `ffprobe` on `PATH`; optional executable overrides are `YT_DLP_BIN`, `FFMPEG_BIN`, and `FFPROBE_BIN`.

English captions are YouTube's auto-generated transcript, with rolling caption fragments deduplicated and obvious context errors corrected. Chinese captions use machine translation with reviewed corrections for the sample's key phrases. Review proper names, numbers, and translations before publication. The source link, upload date, durations, and exact highlight time ranges are recorded in `manifest.json`.
