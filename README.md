# Open Video Catalog

Open Video is a static YouTube catalog and an Actions-hosted short-edit workflow. Pages provides a searchable UI, original-video links, and in-page playback/download for retained derived clips. Video fetching, translation, speech synthesis, B-roll downloads, encoding, and platform uploads run only on GitHub-hosted Actions runners; the Pages site contains no credentials and never mirrors original long-video files.

## Search and creator console

The Pages catalog supports multiple space-separated keywords with **AND** (all words) or **OR** (any word) matching, selectable fields (title/ID, channel, description, source), a source filter, and pagination. Search state is shareable in the URL. Metadata currently available from YouTube's flat channel/playlist feed includes titles, channel, source and sometimes description; a field with no metadata cannot match.

The creator console prepares the workflow input names/values and links to **Actions → Update catalog and deploy Pages → Run workflow**. It cannot start a workflow itself: a static public Pages page must not hold a GitHub token. Sign in to GitHub, copy the prepared values into `workflow_dispatch`, and confirm source-video editing rights in the workflow form. If an example-video URL is supplied, separately confirm the right to use its English caption pacing as a style reference. The example's video file is never downloaded.

The workflow offers:

- A single authorized YouTube video, 10–60 second segment, and `auto-hook`, `bold-captions`, `clean-captions`, `match-example`, or Pexels B-roll style. The hook picker scores transcript/chapter metadata with simple heuristics and falls back to a segment after the opening; it is **not an AI highlighter** and cannot guarantee a viral result.
- Optional target locales (up to four): `en-US`, `en-GB`, `es-ES`, `fr-FR`, `de-DE`, `it-IT`, `ja-JP`, `ko-KR`, `pt-BR`, `zh-CN`. If caption translation and TTS providers are configured, translated subtitles are burned into a separate localized 9:16 clip and an Azure neural voice narrates it. Voice overrides use `locale=VoiceName` pairs, e.g. `es-ES=es-ES-ElviraNeural`.
- Optional Pexels B-roll: searches by selected segment title, downloads one licensed Pexels MP4 on the runner, overlays a short picture-in-picture cutaway, and records contributor/license attribution in the Pages catalog. It is skipped if unchecked or `PEXELS_API_KEY` is absent; a provider failure is reported but does not discard the regular short.
- Optional publication of the generated original/localized assets to YouTube Shorts, TikTok, Instagram Reels, Facebook Reels, and/or X. The publish job runs only after the Pages deployment, uses each platform's official API, and reports each selected platform's result in the Actions run summary. Missing secrets are explicitly marked **skipped**; an API rejection fails the publishing job but does not roll back the Pages deployment.

An example style reference is consent-gated and reads English subtitles only to choose a simple caption-pacing template (bold for short cues, clean for longer cues); it does not copy a reference video's visual content. No automatic B-roll is downloaded without Pexels configuration. Generated source clips, translated clips, and B-roll are only made after the `clip_authorized` workflow confirmation. Review all outputs and platform privacy settings before sharing.

## Optional provider configuration

Add credentials only under **Repository Settings → Secrets and variables → Actions → Secrets**. Never put them in `sources.txt`, the Pages site, workflow inputs, or committed files.

| Feature / platform | Required Actions secrets | Required provider authorization / notes |
|---|---|---|
| Translation | `DEEPL_AUTH_KEY` | DeepL API authentication key with text-translation API access; `:fx` keys use the Free API endpoint. |
| Neural narration | `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | Azure AI Speech resource key and its region; Speech Synthesis REST access. |
| Licensed stock B-roll | `PEXELS_API_KEY` | Pexels API key and compliance with Pexels' license/terms; attribution is retained with the short. |
| YouTube Shorts | `YT_OAUTH_CLIENT_ID`, `YT_OAUTH_CLIENT_SECRET`, `YT_OAUTH_REFRESH_TOKEN` | Google OAuth user consent with `https://www.googleapis.com/auth/youtube.upload`; YouTube Data API enabled. `unlisted` is the default visibility. |
| TikTok | `TIKTOK_ACCESS_TOKEN` | TikTok Content Posting API app/user authorization with `video.publish`; app approval/direct-post eligibility is required. TikTok has no unlisted state here: `unlisted` maps to `SELF_ONLY`. |
| Instagram Reels | `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID` | Instagram professional account connected to a Facebook Page; Graph API `instagram_content_publish` and account/Page discovery/read permissions as required by the app review. Visibility follows account settings. |
| Facebook Reels | `FACEBOOK_PAGE_ACCESS_TOKEN`, `FACEBOOK_PAGE_ID` | Page token with `pages_manage_posts` and `pages_read_engagement` (and `pages_show_list` when needed to obtain the Page token); Meta app review may be required. `private` requests a draft; `unlisted` is published because Facebook Reels has no unlisted state in this adapter. |
| X video posts | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` | X developer app with user-context Read/Write and media upload/post access enabled. X posts are public; it has no unlisted setting in this adapter. |

The optional repository Actions variable `META_GRAPH_API_VERSION` selects the Graph API version (default `v22.0`). API quotas, moderation, account eligibility, app review, and provider charges/terms are outside this repository. Configure only the providers you intend to use.

## Channels, playlists, archive, and retention

Edit [`sources.txt`](sources.txt), one public HTTPS YouTube channel or playlist URL per line. Blank/comment lines are ignored and duplicates removed. Up to **1,000 sources** run sequentially with a one-second pause, per-source request timeout, and five-hour total fetch budget. Each source contributes at most **50** videos (default 12; change with Actions variable `VIDEO_LIMIT_PER_SOURCE` or the manual input). Per-source failure, successful empty result, and success with videos are distinguished in the UI.

`archive/catalog.json` is an append-by-video-ID metadata archive. On bootstrap, the runner merges the readable current Pages catalog with the new feed so existing collected records are not lost; every refresh then merges metadata without duplicating IDs. The archive is committed to the selected branch by the Actions token. The workflow triggers only on a schedule or manual dispatch—not on `push`—so its own bot commit cannot create a workflow loop. The workflow has `contents: write`; if repository rules or branch protection reject the bot push, the build fails with a clear archive-write error before deploying Pages.

Short files are retained in `site/clips/` and playable on Pages. At each run, the hosted runner restores prior clip files from the published catalog (or its archive fallback). Requests are limited to public HTTPS `*.github.io`, validated video-ID/language paths, Content-Length and actual-size checks, one 20-second catalog / 45-second clip timeout, and at most 100 restore attempts. Retention is newest-first, with a shared cap of **100 MP4 files / 700 MiB**, **20 MiB per clip**, and a **950 MiB total site-output safety ceiling** (below GitHub Pages' 1 GiB published-site limit). Metadata archive is capped at **90 MiB** so one tracked JSON file stays below GitHub's 100 MiB hard per-file limit. Localized clips count toward the same media limits; when a cap is reached, older MP4s and their player entries are omitted, while original metadata remains archived.

This does not make storage unlimited: GitHub recommends repositories stay below 1 GiB, tracked files above 50 MiB warn and files above 100 MiB are rejected, and Pages has a 100 GiB/month soft bandwidth limit and 10-minute deployment limit. The archive is a tracked JSON snapshot and its history consumes repository storage over time; monitor repository size and prune/archive before approaching the recommendation. Runner processing is also finite: one source video up to 500 MB, one 10–60 second base short, up to four locale variants, and one B-roll asset per manual run, with a six-hour job timeout. Large/slow provider calls may time out or fail; localized outputs fail independently where possible.

## Pages setup and validation

1. In **Settings → Pages**, set **Build and deployment → Source** to **GitHub Actions**.
2. In **Settings → Actions → General → Workflow permissions**, allow read and write permissions. The workflow scopes `contents: write`, `pages: write`, and `id-token: write`.
3. Use the creator console's GitHub Actions link or the Actions tab to run the workflow manually. A no-media scheduled/manual run only fetches metadata and publishes the static catalog. Video processing requires GitHub-hosted `ubuntu-latest`; no self-hosted/local video runner is used.
4. The frontend is plain HTML/CSS/JavaScript. The Python tests use only the standard library and mocks; the Node interaction tests use the built-in test runner. They do not download or process media:

```text
python -m unittest discover -s tests
node --test tests/app.test.js
```
