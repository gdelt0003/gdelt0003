# Full-video subtitle and source-footage verification

Use this checklist for every subtitle correction or replacement source. Do not mark a check passed from a plan, code change, search snippet, or inaccessible page alone.

## Acceptance scope

- Use the White House's official 58:52 recording as the event/timing reference: [official event page](https://www.whitehouse.gov/videos/president-trump-delivers-remarks-oct-6-2026/) and [official YouTube recording](https://www.youtube.com/watch?v=oW-PQlgw1wo).
- Treat the supplied 8:14 screenshot as a confirmed defect: the English cue `afternoon,` was paired with Chinese `大家`.
- Keep bilingual text synchronized; do not split English and Chinese by unrelated character counts.
- Make spoken English subtitles visibly larger than Chinese; use at least a 1.20 font-size ratio.
- Check translation fidelity, names, numbers, negation, sentence meaning, reading comfort, lower-third obstruction, source/output resolution and duration.
- Search for at least ten credible source publishers and classify usable footage as same angle, longer/more complete, or genuinely different angle; distinguish clean/unobstructed source footage from branded or overlaid copies.
- Run downloads, frame extraction, probing, rendering and deployment on GitHub-hosted cloud runners only. Do not use local video files or local video processing.

## Implemented in the repository

- [x] Group incomplete ASR subtitle fragments into phrase/sentence units before translation or re-rendering. The comma-alignment regression splits the greeting into `Good afternoon,` / `下午好,` and `everybody.` / `大家。` rather than mispairing fragments.
- [x] Preserve complete bilingual cues unless a shared sentence boundary or a defensible bilingual clause boundary exists.
- [x] Set the 1080p English font to 68 px versus 56 px Chinese (about 21.4% larger); use an 78% horizontal safe width and a 30% lower margin.
- [x] Add automated checks for missing-language cues, invalid/out-of-range timing, cue overlap, video resolution/duration preservation, minimum font-size ratio, and English/Chinese reading-speed outliers.
- [x] Record unresolved checks explicitly in `manifest.json`; cue-level pairing is not mislabeled as word-level audio alignment or translation accuracy.
- [x] Add a fail-closed pre-release workflow gate requiring verified source audio, at least three source cross-checks, ten translation models, three independent LLM judges, readable-speed checks, and a rendered-frame review.
- [x] Block Pages deployment on main-branch pushes unless the committed full-video manifest passes the same release-evidence gate; manual deployment is limited to successful full-video processing or restyling jobs.
- [x] Add reusable skills for credible footage research and bilingual subtitle verification.

## Required verification before release

- [x] Run the updated test suite, Python syntax check, workflow-YAML validation, and `git diff --check` after the latest edits.
- [x] Complete the sentence-level regression against the live defect: `Good afternoon,` pairs with `下午好,`, and `everybody.` pairs with `大家。`, with shared intervals covering each phrase.
- [ ] Compare the complete English transcript against the original event audio/video in three documented passes; resolve names, numbers, negation, quotes, sentence boundaries, and speaker changes.
- [ ] Translate the reviewed source with at least ten distinct models, blind-score a full-span/high-risk sample with at least three independent LLM judges, inspect disagreement flags, and select the best-supported Chinese text. Record model IDs, sample design, scores, costs, source checks and adjudication.
- [ ] Cross-check exact wording against the official recording and at least three genuinely independent transcript/subtitle/news references where available. News context is not proof of verbatim speech; label ASR and inaccessible sources accurately.
- [ ] Inspect rendered cloud-runner frames at representative opening, middle and ending timestamps plus every flagged cue. Confirm no clipping, unreadable line breaks, lower-third/banner collision, or subtitle overlap.
- [ ] Inspect at least ten actual publisher/source pages for event identity, attribution, duration, resolution, visible branding/overlays, camera angle and continuity. De-duplicate syndicated/re-uploaded footage; do not count a text article or search result as a verified video.
- [ ] For each verified candidate, record its direct URL, publisher, source lineage, recording/upload date, duration, resolution, relevant timestamps, clean-frame evidence and confidence. Use `Not found` for an unverified category.
- [ ] Confirm the verification manifest contains completed source-audio/model/judge/frame-review evidence and passes the fail-closed workflow gate.
- [ ] Merge the reviewed PR, run the full render on the highest GitHub-hosted runner available to the repository, deploy Pages, then check live VTT timing/text, MP4 asset update time/size/resolution/duration and all published URLs.

## Current evidence and blockers (13 October 2026)

- [x] The published VTT was fetched directly from Pages. Around 8:14 it shows:
  - `00:08:04.740–00:08:10.737`: `Good` / `下午好,`
  - `00:08:10.737–00:08:16.733`: `afternoon,` / `大家`
  - `00:08:16.733–00:08:22.730`: `everybody.` / `。`
- [x] The official White House page confirms the 58:52 source and the embedded YouTube video ID `oW-PQlgw1wo`.
- [x] Public-page attempts found the prior Reuters/AP/Baltimore Sun/WUSA9 leads, but access was blocked (401/403); C-SPAN search was blocked, and general search endpoints were rate-limited or returned no usable index results. A search lead is not verified footage.
- [ ] No independent clean, unobstructed source or distinct camera angle has yet been verified; ten clean video sources have not been established.
- [ ] No ten-model translation run, three-judge score, three-pass source-audio review, or visual review of a newly rendered cloud output has yet been completed.
- [ ] PR #4 remains open; the latest synchronization/style/quality-gate changes have not yet been merged, rendered, or published.
- [ ] The repository has no configured `OPENROUTER_API_KEY` Actions secret. The existing benchmark workflow estimates about US$25.12 for all 971 cues and the 120-cue judge sample; confirm the spending ceiling before any billable run.

## Release decision

Do not describe subtitles or footage as fully verified, and do not replace the published MP4/VTT, until every required release check above is passed with evidence. The currently published video remains the old render and still contains the demonstrated cue-level mismatch.
