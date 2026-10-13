# Full-video subtitle and source-footage verification

Use this checklist for every subtitle correction or replacement source. Do not mark a check passed from a plan, code change, search snippet, or inaccessible page alone.

## Acceptance scope

- Use the White House's official 58:52 recording as the event/timing reference: [official event page](https://www.whitehouse.gov/videos/president-trump-delivers-remarks-oct-6-2026/) and [official YouTube recording](https://www.youtube.com/watch?v=oW-PQlgw1wo).
- Treat the supplied 8:14 screenshot as a confirmed defect: the English cue `afternoon,` was paired with Chinese `大家`.
- Keep bilingual text synchronized; do not split English and Chinese by unrelated character counts.
- Make spoken English subtitles visibly larger than Chinese; use at least a 1.20 font-size ratio.
- Check translation fidelity, names, numbers, negation, sentence meaning, reading comfort, lower-third obstruction, source/output resolution and duration.
- Search for at least ten credible source publishers and classify usable footage as same angle, longer/more complete, or genuinely different angle; distinguish clean/unobstructed source footage from branded or overlaid copies.
- For each event, inspect source-embedded banners, tickers, logos, QR codes and lower-thirds separately from player controls; record location, coverage, timestamps and obstruction. Do not erase source graphics; do not call a source clean if relevant material is obscured.
- Give every event a 3D camera-position map only from evidenced measurements: WGS84 coordinates displayed to five decimal places with an independent horizontal uncertainty estimate, camera/stage distance, true-north azimuth, relative angle to stage orientation, lens height above ground, vertical viewing angle and source evidence. Mark unavailable/estimated geometry explicitly; never invent coordinates or expose private/security camera positions.
- Run downloads, frame extraction, probing, rendering and deployment on GitHub-hosted cloud runners only. Do not use local video files or local video processing.

## Implemented in the repository

- [x] Group incomplete ASR subtitle fragments into phrase/sentence units before translation or re-rendering. The comma-alignment regression splits the greeting into `Good afternoon,` / `下午好,` and `everybody.` / `大家。` rather than mispairing fragments.
- [x] Preserve complete bilingual cues unless a shared sentence boundary or a defensible bilingual clause boundary exists.
- [x] Set the 1080p English font to 68 px versus 56 px Chinese (about 21.4% larger); use an 78% horizontal safe width and a 30% lower margin.
- [x] Add automated checks for missing-language cues, invalid/out-of-range timing, cue overlap, video resolution/duration preservation, minimum font-size ratio, and English/Chinese reading-speed outliers.
- [x] Record unresolved checks explicitly in `manifest.json`; cue-level pairing is not mislabeled as word-level audio alignment or translation accuracy.
- [x] Add a candidate fail-closed release verifier requiring both status checks and evidence records/files with SHA-256 for ten model outputs, three judges, three independent source checks, three full-span source-audio passes, and opening/middle/ending frames.
- [x] Candidate branch routes main-push, process, and restyle release decisions through that verifier; manual deploy is limited to successful selected full-video jobs. The candidate is not merged, so this is not yet the active main-branch protection.
- [x] Add reusable skills for credible footage research (including source-overlay classification and evidenced 3D camera geometry) and bilingual subtitle verification.
- [x] Add a data contract and an event page placeholder for a 3D camera map. The White House event camera coordinates remain unverified; the UI must say so and never plot invented positions.

## Required verification before release

- [x] Run the updated test suite (44 Python tests and 3 camera-map Node tests), Python syntax checks, workflow-YAML parse, and `git diff --check` after the latest edits.
- [x] Complete the sentence-level regression against the live defect: `Good afternoon,` pairs with `下午好,`, and `everybody.` pairs with `大家。`, with shared intervals covering each phrase.
- [ ] Compare the complete English transcript against the original event audio/video in three documented passes; resolve names, numbers, negation, quotes, sentence boundaries, and speaker changes.
- [ ] Translate the reviewed source with at least ten distinct models, blind-score a full-span/high-risk sample with at least three independent LLM judges, inspect disagreement flags, and select the best-supported Chinese text. Record model IDs, sample design, scores, costs, source checks and adjudication.
- [ ] Cross-check exact wording against the official recording and at least three genuinely independent transcript/subtitle/news references where available. News context is not proof of verbatim speech; label ASR and inaccessible sources accurately.
- [ ] Inspect rendered cloud-runner frames at representative opening, middle and ending timestamps plus every flagged cue. Confirm no clipping, unreadable line breaks, lower-third/banner collision, or subtitle overlap.
- [ ] Inspect at least ten actual publisher/source pages for event identity, attribution, duration, resolution, visible branding/overlays, camera angle and continuity. De-duplicate syndicated/re-uploaded footage; do not count a text article or search result as a verified video.
- [ ] For each verified candidate, record its direct URL, publisher, source lineage, recording/upload date, duration, resolution, relevant timestamps, clean-frame evidence and confidence. Use `Not found` for an unverified category.
- [ ] Verify the embedded-banner/logo obstruction in actual source frames and classify overlays by origin, position, coverage and time; no candidate may be called clean based only on a player or article thumbnail.
- [ ] Measure and evidence stage orientation/coordinates and each public media camera's coordinates, positional uncertainty, distance, true-north and relative azimuths, lens height and pitch; render the event's 3D map only for complete verified records.
- [ ] Confirm the verification manifest contains completed source-audio/model/judge/frame-review evidence and passes the fail-closed workflow gate.
- [ ] Obtain independent acceptance reports from three separate nested project sessions; resolve every blocking finding before deployment.
- [ ] After acceptance, have a separate deployment session run the render on the highest GitHub-hosted runner actually available to the repository, deploy Pages, then check live VTT timing/text, MP4 asset update time/size/resolution/duration and all published URLs.
- [ ] Have separate independent nested sessions review the live deployed page and footage evidence; capture their reports only after deployment, without assuming the code review proves the live result.

## Current evidence and blockers (13 October 2026)

The following source-page and frame observations were reported by the independent footage-audit session. The measured 1280x720 value is the browser player rendition decoded during review, not the platform maximum or source master. “Page/poster only” rows were paused at 00:00; a thumbnail is not evidence of in-video graphics or clean footage.

| # | Direct source | Upload date; runtime; observed rendition | Inspection | Overlay / captions | Angle and provenance | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | [White House event page](https://www.whitehouse.gov/videos/president-trump-delivers-remarks-oct-6-2026/) / [official YouTube](https://www.youtube.com/watch?v=oW-PQlgw1wo) | 2026-10-06; 58:52; 1280x720 | Played at about 08:15 and 35:07 | Both frames show in-picture White House emblem, `TEXT "POTUS" TO 45470 FOR WHITE HOUSE UPDATES` lower third, and QR. At 35:07 the YouTube CC layer is separate from those graphics. | Official event page identifies Baltimore, MD; used as reference camera framing. | Directly verified; **fails clean-source requirement**. |
| 2 | [Moneycontrol YouTube](https://www.youtube.com/watch?v=jAq7oEbw9Hs) | 2026-10-06; 2:02:00; 1280x720 | Played at about 1:00:01 | In-picture green `m` mark. YouTube CC displays the same “changed the name to Secretary of War” speech and is distinct from the in-picture mark. | Matched speech at tighter framing than White House at about 35:06–35:12; camera station, signal source and continuity are unproved. | Different-framing lead only; marked footage fails clean-source, and a different physical camera position is unverified. |
| 3 | [NDTV Profit YouTube](https://www.youtube.com/watch?v=CRiW-xC_-WU) | 2026-10-06; 1:18:41; 1280x720 | Played at about 30:01 | Crowd and camera operator in foreground; CC appeared as a player subtitle layer. No complete graphic-origin audit. | Ship/stage scene, not the matched speaking moment; station and continuity unproved. | Sampled, but not accepted as clean or as a verified alternate angle. |
| 4 | [RSBN YouTube](https://www.youtube.com/watch?v=1FHGW2UPqcU) | 2026-10-06; 2:22:21; 1280x720 | Played at about 60:01 and 80:01 | Samples show branded studio discussion/interview or split-screen graphics, not matched on-site speech. | Sampled times do not establish a continuous event camera feed. | Not usable evidence for event footage at sampled times; other parts remain unverified. |
| 5 | [Diya TV YouTube](https://www.youtube.com/watch?v=1lwIzuvwjDc) | 2026-10-06; 2:08:08; 1280x720 | Played at about 60:01 | “Resuming Shortly” slate with White House and Diya TV marks; upload poster is not used as in-video evidence. | No continuous event-camera speech established. | Not a clean event-footage candidate at sampled time. |
| 6 | [CNBC Television YouTube](https://www.youtube.com/watch?v=d0s-G8BgzPk) | 2026-10-06; 36:40; 1280x720 | 00:00 page/poster only; no event frame sampled | CNBC logo/title are visible on the poster only; video overlay and CC status are unverified. | Event angle and continuity unverified. | Page metadata only; do not count as clean footage. |
| 7 | [CNN-News18 YouTube](https://www.youtube.com/watch?v=fhFkM4xnA1A) | 2026-10-06; 11:26; 1280x720 | 00:00 page/poster only; no event frame sampled | CNN Edge/title composition is poster-only evidence; video overlay and CC status unverified. | No matched speech, station, or continuity evidence. | Page metadata only; do not count as clean footage. |
| 8 | [The Hill YouTube](https://www.youtube.com/watch?v=4RwCOx3xmzM) | 2026-10-06; 34:36; 1280x720 | 00:00 page/poster only; no event frame sampled | The Hill logo/subscribe text are poster-only; video overlay and CC status unverified. | Title mentions Baltimore remarks but does not prove camera location or uninterrupted event coverage. | Page metadata only; do not count as clean footage. |
| 9 | [India Today Global YouTube](https://www.youtube.com/watch?v=QRRnVmyoVYw) | 2026-10-07; 3:43:18; 1280x720 | 00:00 page/poster only; no event frame sampled | Branded title panel/ship visible on poster only; video overlay and CC status unverified. | Long runtime does not prove uninterrupted coverage or a particular camera station. | Page metadata only; do not count as clean footage. |
| 10 | [WMAR-2 News YouTube](https://www.youtube.com/watch?v=zfXZdSzlOoo) | 2026-10-06; 0:57; 1280x720 | 00:00 page/poster only; no event frame sampled | WMAR side branding is poster-only; video overlay and CC status unverified. | Local-event title does not prove matching speech, continuity, or camera station. | Page metadata only; do not count as clean footage. |

- Source-audit classification: same-angle replacement **Not found**; verified continuous longer source **Not found**; a tighter Moneycontrol framing is a different-framing lead, but neither a clean source nor a distinct physical station is established. Ten publisher pages were opened, but they are not ten accepted or clean video sources.
- Camera-map evidence: only Baltimore, MD / venue-area identification is public in this audit. GPS coordinates and uncertainty, camera-to-stage distance, true-north and relative azimuth, lens height, pitch/elevation, and station provenance are unavailable. Keep the camera map unverified and empty; do not derive a station or 3D geometry from framing alone.

- [x] The published VTT was fetched directly from Pages. Around 8:14 it shows:
  - `00:08:04.740–00:08:10.737`: `Good` / `下午好,`
  - `00:08:10.737–00:08:16.733`: `afternoon,` / `大家`
  - `00:08:16.733–00:08:22.730`: `everybody.` / `。`
- [x] The official White House page confirms the 58:52 source and the embedded YouTube video ID `oW-PQlgw1wo`.
- [x] Commits `ffde6f0` and `db641c6` are pushed to PR #4; the local Python unit suite passed (40 tests at ffde6f0), syntax checks passed, workflow YAML parsed, and staged diff checks passed. Subsequent gate-evidence and 3D-map changes are not yet committed.
- [x] Three independent nested project sessions were created for subtitle synchronization, footage-source, and release-gate acceptance; a fourth nested session, `最高指示`, was created to record the user's instructions and implementation/acceptance methods.
- [x] Public search surfaced PBS, C-SPAN, The Hill, WUSA9, WBAL, WBFF, Fox News, Washington Examiner, AP, Reuters, DefenseScoop, WYPR and other event-related pages. These are leads, not ten verified clean videos; C-SPAN and multiple publisher pages were inaccessible or not inspected in the actual video.
- [x] The subtitle and release-gate acceptance reports identify blockers. The footage audit opened direct video pages for White House, NBC News, CNBC, CNN-News18, Moneycontrol, NDTV Profit, The Hill, India Today Global, WMAR-2 News and New York Post, but most were not sampled at a matched event timestamp. Ten opened pages are not ten accepted sources. No post-deployment review sessions have been started.
- [x] Footage-audit observations above distinguish in-picture source graphics from player CC and poster art; they are attributed to the independent audit rather than presented as a new local inspection.
- [ ] No independent clean, unobstructed source or verified camera angle has been established; ten clean video sources and evidence-backed per-event camera coordinates have not been established. Publicly available venue-area information does not establish station coordinates, uncertainty, bearing, distance, lens height or pitch; do not create a 3D map from guesses.
- [ ] No ten-model translation run, three-judge score, three-pass source-audio review, or visual review of a newly rendered cloud output has yet been completed.
- [ ] PR #4 remains open; candidate synchronization/style/quality-gate changes have not been merged. Main has a newer restyled deployment, but independent review confirms its live VTT still contains the 8:14 mismatch; rendering changes did not verify translation or audio-level timing.
- [ ] The repository has no configured `OPENROUTER_API_KEY` Actions secret. The existing benchmark workflow estimates about US$25.12 for all 971 cues and the 120-cue judge sample; confirm the spending ceiling before any billable run.
- [x] The committed source manifest has no `quality_checks`; the candidate release verifier blocks it. The assertion-only weakness reported by acceptance is addressed in the working tree with per-record evidence paths and content hashes; process/restyle jobs call the same verifier, and restyle copies reused review evidence into the output. Python tests cover missing records, missing/escaped/tampered evidence, and safe evidence copying. These controls validate manifest consistency, not the truth/authenticity of human or model review claims.

## Release decision

Do not describe subtitles or footage as fully verified, and do not replace the published MP4/VTT, until every required release check above is passed with evidence. The live VTT currently contains the demonstrated cue-level mismatch despite a newer restyled deployment. Do not publish a purported clean-source result or populated camera map until direct source-frame and location/angle evidence is available.

## Additional product scope recorded (not implemented)

The user additionally requested multi-source topic selection; long-video generation and translation; batch generation of multiple videos for one event/topic; and original-voice cloning with a stated “99%+ similarity” target. This is separate from the current subtitle-release acceptance and has no implementation evidence yet.

- [ ] Define multi-source candidate ranking, source attribution/rights, deduplication, and a reviewable reason for each selected topic.
- [ ] Define long-video generation/translation inputs, outputs, and a resumable batch workflow that isolates failures and reports each result.
- [ ] Define repeatable batch constraints for producing multiple distinct videos about one event/topic. Treat “viral” only as an editorial goal; no reach or popularity outcome can be guaranteed.
- [ ] Before any voice-cloning work, define an objective similarity measure and evaluation protocol, verify voice rights and explicit informed consent, and ensure the result cannot mislead viewers about what the source speaker actually said. Do not imitate a public figure for fabricated translated speech or claim “99%” without measured evidence.
