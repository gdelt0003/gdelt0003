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

## Continuous integration

Pull requests and pushes run the read-only CI workflow. It runs the Python unit tests, checks the frontend JavaScript syntax, and parses the repository's JSON data files. It does not download media, call external APIs, or deploy GitHub Pages.

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

1. Upload the original source MP4 to the GitHub Release `white-house-source-oW-PQlgw1wo`.
2. Run **Publish stored White House clips to Pages** with `process_full_video` enabled.

The existing processing route uses Whisper `large-v3-turbo` for English transcription and only Meta's M2M100 1.2B model for Simplified Chinese translation. It does not perform the requested ten-model comparison, web-source cross-check, or multi-LLM scoring, so its translation must not be described as independently verified. A style-only re-render with `restyle_full_video` reuses those same translations; it places gold Chinese above larger white English, lifts captions above the common lower-third area, and preserves the source resolution and aspect ratio. The subtitled MP4 and three SRT files are attached to the same Release; the Pages site embeds the video and serves its VTT/SRT subtitle files.

To run the requested comparison, add an OpenRouter API key as the repository Actions secret `OPENROUTER_API_KEY`, then run **Publish stored White House clips to Pages** with `compare_full_video_translations` enabled and `translation_review_budget_usd` set to at least `$26` (the current live-catalog estimate is `$25.12` for all 971 cues and a 120-cue blind review). This job stores ten full-model SRT outputs and the three-judge report as a 30-day Actions artifact only; it does not deploy or replace the published subtitles. Review the source-fetch statuses and flagged cues against the official recording, then explicitly run the processing workflow to publish any approved translation. The model scores rank only the blind sample and are not a substitute for human review.

### Translation benchmark evidence (13 October 2026)

WMT25 published a matched English-to-Simplified-Chinese evaluation. These are the paper's cross-domain mean human scores, sorted by score; its significance-tested rank intervals overlap, so adjacent rows are not necessarily statistically distinguishable. Scores are not percentages and are not evaluations of this video's translation.

| System | WMT25 human score | Rank interval |
| --- | ---: | ---: |
| Algharb | 88.4 | 1–1 |
| Shy-hunyuan-MT | 88.2 | 2–4 |
| Claude-4 | 86.9 | 2–5 |
| Wenyiil | 86.3 | 2–5 |
| DeepSeek-V3 | 85.0 | 3–6 |
| GemTrans | 84.4 | 5–10 |
| Qwen3-235B | 84.0 | 6–11 |
| GPT-4.1 | 84.0 | 5–10 |
| Gemini-2.5-Pro | 83.8 | 6–11 |
| UvA-MT | 83.4 | 5–10 |

For the WMT25 speech domain specifically, the top ten reported human scores are Gemini-2.5-Pro (83.7), Wenyiil (82.0), Algharb (81.9), GPT-4.1 (80.2), Shy-hunyuan-MT (80.1), DeepSeek-V3 (80.1), Claude-4 (79.7), Mistral-Medium (79.7), CommandA-WMT (75.0), and UvA-MT (74.4). This measures speech-translation content, not subtitle timing or readability. See the [WMT25 cross-domain table](https://aclanthology.org/2025.wmt-1.22.pdf#page=22), its [speech-domain table](https://aclanthology.org/2025.wmt-1.22.pdf#page=51), and the [official system-output repository](https://github.com/wmt-conference/wmt25-general-mt).

These benchmark results can guide a candidate shortlist but cannot select the best translation of this particular recording. The current SRTs remain single-model M2M100 output; multi-system translations, web/source comparison, and independent LLM judging must be run on the recording before replacing the published captions. News coverage may corroborate event facts, but exact wording must be checked against the audio/video; the available YouTube captions are ASR, not a verified transcript.
