# gdelt0003 White House highlights

## Publish and download

1. Create or update the repository variable `YOUTUBE_URL` to a target YouTube URL such as:
   - `https://www.youtube.com/@gdelt0003`
   - `https://www.youtube.com/playlist?list=...`
2. Optionally set `VIDEO_LIMIT` (default: `8`).
3. Optionally set `YT_DLP_BIN` to a custom `yt-dlp` binary path when you need to override the default executable.
4. Push to `main` or run the workflow manually. For the Pages workflow, pushing to `main` or running the workflow_dispatch will publish site assets.

## Notes

- No local frontend install is required.
- The workflow runs in GitHub Actions, installs `yt-dlp` and `ffmpeg` as needed, fetches data, and deploys the static site.
- For production, replace the example YouTube URL with your real channel or playlist.
- The fetch script also accepts `YT_DLP_BIN` for local testing or custom installations.

## Deploy / regeneration caveats

- Three short MP4 highlights from the public White House video `oW-PQlgw1wo` are committed to `generated/clips/` and referenced by `generated/default_batch.json` when present.
- The workflow can be run with `regenerate_clips` to attempt re-cutting from the official source; set `download_full_source` to attach a full-source Release asset when possible.
- YouTube may challenge automated runners (cookies/auth required). When the runner cannot access formats or subtitles, the workflow fails and leaves the published clips unchanged.

## Generate bilingual shorts (local)

The repository also includes a local short-video editing pipeline. It downloads a long source video and its English captions, translates captions to Simplified Chinese, then renders each selected highlight in two 1080x1920 styles with the original audio:

```powershell
python scripts/create_shorts.py
```

The default sample uses the White House's October 6, 2026 remarks video (58:52; 3,532 seconds) and creates three distinct highlight windows with both an editorial and a punchy variant: 12:03-12:59 (shipyard production/jobs), 20:58-21:44 (Navy systems), and 41:57-42:16 (Russia-Ukraine remarks). Outputs and a source/timing manifest are written to `outputs/whitehouse-oct-06-2026/`. Supply `--url` and `--output-dir` to process a different source. The script requires `yt-dlp`, `ffmpeg`, and `ffprobe` on `PATH`; optional executable overrides are `YT_DLP_BIN`, `FFMPEG_BIN`, and `FFPROBE_BIN`.

English captions are YouTube's auto-generated transcript, with rolling caption fragments deduplicated and obvious context errors corrected. Chinese captions use machine translation with reviewed corrections for the sample's key phrases. Review proper names, numbers, and translations before publication. The source link, upload date, durations, and exact highlight time ranges are recorded in `manifest.json`.

## Process the complete October 6, 2026 video

The Pages workflow can process the complete source video without fetching it from YouTube:

1. Upload the source MP4 as `whitehouse-oW-PQlgw1wo-source.mp4` to the GitHub Release `white-house-source-oW-PQlgw1wo`.
2. Run **Publish stored White House clips to Pages** with `process_full_video` enabled.

The runner uses Whisper `large-v3-turbo` for English transcription and Meta's M2M100 1.2B model for Simplified Chinese translation, then burns both subtitle lines into the full-resolution MP4. The subtitled MP4 and three SRT files are attached to the same Release; the Pages site embeds the video and serves its VTT/SRT subtitle files. Model output is machine-generated and should be reviewed before citation or republication.
