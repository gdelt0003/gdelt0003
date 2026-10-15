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

## Bilingual shorts pipeline (cloud-only)

`scripts/create_shorts.py` is the source-controlled shorts renderer. Per the source-review requirements, do not run video downloads, probing, frame extraction, ASR, or rendering on a local machine; run these only on a GitHub-hosted cloud runner after the selected event and its White House reference/source alternatives have been verified. The manual **Build cloud event video variants** workflow creates a review artifact; the separate **Publish reviewed event video variants** workflow requires post-build rights, exact event/source match, clean-frame, English ASR, and Chinese translation attestations backed by five distinct HTTPS evidence URLs before publishing. Neither workflow has been run for the current Columbus Day source audit, and the known White House video-frame banner/branding means that anchor is not a clean source.

Before running the build workflow, set the repository Actions variable `CLOUD_VIDEO_RUNNER` to the highest-capacity GitHub-hosted runner label enabled for this repository/plan. The workflow deliberately has no standard-runner fallback; an unset or unavailable label prevents the job from starting. The scheduled metadata discovery workflow uses a standard hosted runner and does not download or process video.

The renderer rejects source metadata or downloaded highlight segments below 1920x1080 rather than silently falling back/upscaling; preserves the full original frame in the portrait layout instead of cropping out the lower portion; and removes the old fixed October 6 banner. It accepts a reviewed JSON list of at least two distinct highlight intervals, each with an ID, source start/end, title, and editorial reason, and produces every requested edit style for every interval.

Ten selectable presets are available: `editorial`, `punchy`, `documentary`, `monochrome`, `warm`, `cool`, `cinematic`, `vivid`, `minimal`, and `outline`. Set `--styles` to any comma-separated subset or all ten. These are editing treatments, not ten different source angles or guarantees of popularity. For an already downloaded local runner input, pass `--source-file`; video operations still belong on the authorized cloud runner. The source URL is retained for metadata and caption retrieval.

It writes English subtitles from the source's YouTube caption track; when those captions are unavailable and a cloud-downloaded `--source-file` is supplied, it can use Whisper `large-v3-turbo` as an ASR fallback. Full-length Chinese machine translation is optional (`--translate-full-transcript`) because it makes many external MyMemory requests; the output manifest marks its sentence timings as heuristic rather than audio-aligned. A build processes one selected video source per run: automated cross-source event ranking, source fusion, and a resumable multi-source production queue remain unimplemented. “Viral” is an editorial goal, not a guaranteed outcome.

### Event discovery module and editable sources

The **Source Directory** sheet in [`outputs/event-source-review.xlsx`](outputs/event-source-review.xlsx) is the human-editable source list. It includes the source URLs supplied in the project instructions, category, enabled state, collection mode/frequency, last attempt/result, access status, run link, and an annotation field. To add or annotate a source, edit that sheet and commit the workbook; the scheduled workflow imports it before rebuilding the Excel workbook and Pages site. `User Instructions` preserves the relevant terminology and source-list statements verbatim; the exact URL in each row maps it to the user's listed source. “为御注” follows the user's latest clarification: the user-mentioned link and the user's own session annotation/explanation, not an annotation by a political leader. The annotation cell remains blank unless the user actually supplied an annotation for that specific source.

The cloud workflow runs two daily passes: daytime latest-event discovery at 10:15 China Standard Time and an evening cross-source review at 20:15. Both collect metadata only from the White House YouTube channel and GDELT DOC API (up to 250 articles from the previous week). GDELT contributes article title, publisher, URL, language, country, and article-seen metadata only; it does not fetch article bodies or verify event facts. The evening workbook includes a `Candidate Review` queue of up to ten existing video-source records per event, ordered by same-event evidence, clean-source status, observed stream resolution, and duration proximity; publisher/URL only break ties. The order is explicitly not a trust score, and no missing candidate is fabricated. A candidate replaces the White House event anchor only when same-speech-moment evidence, a passed clean-source review, and an observed stream resolution are all recorded; otherwise the White House YouTube anchor remains the event reference and its embedded graphics/unclean status are disclosed. Reuse rights and source lineage still require review.

The other listed Roll Call, Truth Social, prediction-market, pool (including the user-proposed Forth Trump lists URL), C-SPAN, X, and analytics pages are registered but **not connected to automated collectors**; the evening pass presents these as manual-review sources and does not claim to query them. Their availability, access, terms, and factual reliability have not been independently checked. Each active collector's outcome is recorded with timestamp and Actions run URL. Discovery rows stay unassigned until an event date/time, location, participants, and content are checked against evidence. Event rows reserve fields for verified attendance minutes, speech word count with language/method, source-backed topics, first discovery/last verification, confidence, and source-linked user annotations. These factual fields remain blank/unknown when evidence is unavailable; article-seen/upload time, prediction markets, and video runtime do not establish actual attendance or spoken word counts.

The user-submitted video `https://www.youtube.com/watch?v=rQlpuY2tj-4` is recorded in `Candidate Review` as an **unassigned lead**, not associated with Columbus Day or the October 13 Katie event. Its user-provided “longer/clean/HD/trusted” characterization, 90-point rating, and favorable angle opinion are preserved as subjective claims only. Event/time match, runtime, actual stream resolution, graphics/occlusion, provenance, reuse rights, and camera-position fields (location, coordinates, azimuth, height, pitch, equipment, department/crew and media-seat annotation) remain pending/unknown until evidence is supplied and independently reviewed; no private identities or unsupported camera measurements are inferred.

The user-submitted video `https://www.youtube.com/watch?v=UgIivPOerNc` is likewise unassigned and has a user-given 50-point rating, not an independent score. The reported long duration, station/signal idents or repeated static scenes, logo, and banner obstruction remain unverified user observations. Runtime is not a ranking shortcut: repetition, embedded graphics, stream resolution, exact event/time, credibility, independent camera, and source lineage are separate review fields. Compare this lead with `rQlpuY2tj-4` only after exact-event/time match and source-angle/lineage review; do not assume they show the same event or different camera angles.

The user-submitted video `https://www.youtube.com/watch?v=Uya88MLbHV0` is another unassigned lead. The user's overall 50 and feature 10 are recorded separately as subjective scores; the feature-score rubric and remaining components are unspecified. “Similar to White House official,” “banner too large,” and “different angles” are preserved as user commentary, not verified event/source/angle facts. Do not group it with either other lead until exact event/time, people, stage/background, audio continuity, views, and repost/source lineage are compared; independent-camera status is pending.

The user-submitted video `https://www.youtube.com/watch?v=h30qlVplAsE` is also unassigned, with the user-provided score of 30 and comments that it is shorter than the official video and has a logo recorded as unverified observations. Its proposed use is limited to background reference/backup, not production. After exact event/time matching, the requested follow-up is to look for same-event alternate camera views and backstage/b-roll while verifying content and publisher/repost lineage; no event, distinct camera, or unblocked picture is assumed. Actual runtime, stream resolution, visible logo/graphics, credibility, event match, camera independence, lineage, and reuse rights remain pending.

## Process the complete October 6, 2026 video

The Pages workflow can process the complete source video without fetching it from YouTube:

1. Upload the original source MP4 to the GitHub Release `white-house-source-oW-PQlgw1wo`.
2. Run **Publish stored White House clips to Pages** with `process_full_video` enabled.

The existing processing route uses Whisper `large-v3-turbo` for English transcription and only Meta's M2M100 1.2B model for Simplified Chinese translation. It does not perform the requested ten-model comparison, web-source cross-check, or multi-LLM scoring, so its translation must not be described as independently verified. It groups incomplete ASR-sized fragments into sentence-level translation units before rendering, then reflows bilingual cues only at sentence boundaries shared by both languages or confidently matched clause connectors. The short-video translation cache now parses wrapped SRT text by language and reuses only complete sentence pairs; this prevents wrapped English lines or partial phrases such as `of the systems` from being mistaken for Chinese translations. These safeguards do not claim word-level forced alignment. Automated pre-release checks reject invalid or overlapping cues, missing-language pairs, changed output resolution/duration, and an English font-size ratio below 1.20. The manifest explicitly records source-audio and independent translation review as `not_verified` until those checks actually happen. English is white and at least 20% larger than gold Chinese; full-video captions use a compact, bottom-centered layout with a translucent dark backing and an 18% lower-third clearance. The published rendition still needs a cloud re-render and actual frame review before these code changes can be considered visible or accepted.

Before replacing or publishing subtitles, use the [`bilingual-subtitle-verification` skill](.github/skills/bilingual-subtitle-verification/SKILL.md): compare wording and timing with the original audio, review names/numbers/negation and Chinese fidelity, blind-score a representative sample across ten translation systems with three independent judges when authorized, inspect rendered frames from the cloud runner, and verify the deployed VTT and video asset correspond. A successful structural/style check is not a translation-accuracy pass.

For reusable research of public event footage, the repository skill [`credible-video-footage-research`](.github/skills/credible-video-footage-research/SKILL.md) searches and classifies credible clips as **same angle**, **longer version**, or **different angle**, records provenance and timestamps, and distinguishes independent recordings from syndicated copies.

The [`multi-source-event-video-production` skill](.github/skills/multi-source-event-video-production/SKILL.md) documents end-to-end event identity, rights and frame-review gates, source grouping, translation/review status, ten edit presets, and Pages publication. A daily cloud workflow refreshes up to 20 recent White House channel uploads as **unassigned leads** and publishes the source workbook; it does not infer event dates from upload timestamps or automatically generate/publish video.

Download the current evidence workbook from [`outputs/event-source-review.xlsx`](outputs/event-source-review.xlsx). Its `Events`, `Sources`, and `Candidate Review` sheets preserve incomplete event identity and explicitly distinguish uninspected frames, thumbnail resolution, and unknown video resolution. The scheduled workflow adds `New White House leads` and `GDELT Article Leads`; both contain metadata-only, unassigned leads and are not verified event alternatives.

The full-video renderer supports opt-in spoken-English word emphasis through `--word-timings`. It modestly enlarges only words with complete, audio-derived timings whose input explicitly records soundtrack review; absent, invalid, incomplete, or unreviewed timings keep the usual phrase-level captions and are marked `not_verified` in the manifest and operation audit. The effect preserves horizontal line width and caption positioning. This code-level feature has not been validated against rendered production footage. See [spoken-word subtitle emphasis](docs/spoken-word-subtitle-emphasis.md) for the timing-file schema and command options. The short renderer remains phrase-level and does not claim audio-derived word alignment. Public-figure voice cloning is not enabled; generated voice requires documented authorization and consent. The existing source audio remains unchanged.

Footage research is grouped by a deterministic event key over event date/time (with timezone and stated precision), location, event type/title, and participants. Upload dates are not treated as event times, and a key does not by itself prove that a candidate shows the same moment. See [`outputs/event-catalog.json`](outputs/event-catalog.json) for the current separate shipyard and Columbus Day records; the latter has incomplete event-time evidence and therefore no event ID or verified alternate source.

The White House Columbus Day recording remains the event/factual comparison anchor even though its banner, logo, and QR make it unsuitable as clean editing material. Candidates must be checked against corresponding official content and contradictions in date, speech, sequence, or scene details flagged; titles and thumbnails alone are insufficient. Background references (such as long news coverage with surrounding programming) are not editing sources. Resolution, frame obstruction, and burned-in graphics are assessed separately, and source graphics must not be digitally erased to label a copy clean.

The event page includes a 3D camera-map panel. It renders only after an event's `camera-map.json` contains verified WGS84 stage and public media-camera positions, horizontal uncertainty, stage-facing azimuth, camera distance, lens height, pitch angle, and direct evidence URLs. Coordinates are displayed to five decimal places without treating display precision as survey accuracy. The October 6 White House event currently has no verified camera-position measurements, so its panel explicitly withholds a speculative map.

### Single-event subtitle comparison

[`events/pvXbHQrIvTw/`](events/pvXbHQrIvTw/) is a comparison-page scaffold for the October 13, 2026 White House departure gaggle source. Its manifest separates the repository's open-source Whisper/M2M100 baseline from the requested Microsoft Copilot/GPT-6 variant. Until the source is verified on an authorized cloud runner and an official Microsoft model ID/endpoint and authorized credential are configured, both variants remain `not_run`/blocked; no video or transcript is implied to exist. Comparison metrics remain empty until the exact input, runtime output, and review evidence are recorded. The size shown is local file metadata only and does not prove the cloud job processed that file. A static page deploy is not media processing or subtitle-quality acceptance.

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

### Speaker-colored captions

The `diarize_speakers` input on **Publish stored White House clips to Pages** is an opt-in GitHub-hosted runner path. It installs the pinned AutoSubs v3.11.0 Linux package after SHA-256 verification, uses its pinned Sortformer model metadata, and colors each bilingual caption by the speaker with the greatest overlap. Ties and unmatched captions remain in the default style; speaker IDs are not real-world identity claims. The static Pages job only publishes the generated files. Do not run diarization or media processing on a workstation.

AutoSubs application code is MIT-licensed; the separately downloaded model is governed by OpenMDW-1.1 and carries its own attribution and third-party-rights review obligations. The optional MMS aligner is not used. The first `diarize_speakers` run still needs to verify package dependencies, model download, and output on the hosted runner before this feature can be called production-validated.
