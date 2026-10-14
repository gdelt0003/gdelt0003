# Full-video verification and V0.03 release checklist

Use this checklist for the current full-video instance and for later source-footage research. A planned check, code change, search result, inaccessible page, or manifest claim alone is not evidence that the check passed.

## Scope decision

The user decision is: “长期还没实现的宏观规划 可以放到下一期做,当前完成V0.03版本,可以跑通一个个例” (“Long-term macro plans that are not implemented can move to the next phase; complete V0.03 by running one example end to end”).

V0.03 is the single official White House recording `oW-PQlgw1wo` (58:52), from cloud processing through operation-audit verification, GitHub Release, Pages deployment, and post-deployment review. This narrower scope defers generalized multi-event and broad source-discovery work; it does **not** waive any quality check for the one V0.03 instance. The official event reference is the [White House event page](https://www.whitehouse.gov/videos/president-trump-delivers-remarks-oct-6-2026/) and [official YouTube recording](https://www.youtube.com/watch?v=oW-PQlgw1wo).

### V0.03 acceptance blockers

Do not mark V0.03 complete until every item below has evidence tied to the successful run and the deployed artifacts.

- [ ] Run the cloud ASR, Chinese translation, subtitle render/burn-in, and video encode for `oW-PQlgw1wo`; record source/output duration, resolution, audio presence, and encode result.
- [ ] Validate every required per-operation audit, retain the audit artifact, and confirm the audit identifies successful operations and their outputs.
- [ ] Publish the video and subtitle assets to the intended GitHub Release and upload the generated Pages subtitle/manifest artifact.
- [ ] Deploy Pages, then run the post-deployment quality gate against the live URLs. Match the deployed manifest, VTT/SRT, and video to the exact processing run; check HTTP status, timestamps, sizes, cue integrity, duration, resolution, and audio presence. A successful Pages deploy alone is not a quality pass.
- [ ] Review the full English transcript against the original event audio/video in three documented passes. Check names, numbers, negation, quotes, sentence boundaries, and speaker changes.
- [ ] Compare complete reviewed sentences with at least ten distinct translation models and blind-score a representative full-span/high-risk sample with at least three independent judges. Record exact model IDs, sample method, rubric, scores, costs, disagreements, and adjudication. Model agreement does not replace source-audio review.
- [ ] Cross-check exact wording against the official recording and at least three genuinely independent transcript/subtitle/news references where available. News context is not proof of verbatim speech; identify ASR and inaccessible sources accurately.
- [ ] Inspect actual frames from the cloud-rendered output at representative beginning, middle, and ending points and every flagged cue. Confirm English and Chinese stay paired, phrase boundaries are sensible, there are no overlaps/clipping or unreadable wraps, English is at least 1.20x the Chinese font size, both language lines stay within safe width, and captions do not obscure lower-thirds or essential scene content.
- [ ] Verify the known 8:14 defect is fixed in the deployed captions: `Good afternoon,` must pair with `下午好,`, and `everybody.` with `大家。`; confirm the live cue intervals, not just source files.
- [ ] Keep cue-level timing distinct from word-level forced alignment; do not describe subtitle accuracy as verified until the audio and independent comparison above are complete.

### Next-phase scope (explicit assumption; not completed)

The following broader work is deferred from V0.03 on the assumption that it is not necessary to prove one known official source can run end to end. These items remain **not done**, not passed:

- [ ] Generalize discovery and scheduled processing across multiple events; implement reusable batch processing and operations beyond this single source.
- [ ] Inspect at least ten actual publishers/source pages and classify footage as same angle, longer/more complete, or genuinely different angle. Deduplicate syndicated/re-uploaded copies; record provenance, date, duration, resolution, timestamps, clean-frame evidence, and confidence. The earlier ten-publisher / alternate-angle requirement is deferred only under this V0.03 scope assumption; if the selected V0.03 content requires an alternate source or camera angle, reinstate it as a V0.03 blocker.

## Deployment and re-verification plan

1. Run the single-instance cloud processing and operation-audit checks.
2. Publish the produced assets to the GitHub Release and Pages.
3. Run the post-deployment quality gate against the live deployment. The first Pages deployment is allowed before this gate; deployment status and release-quality status are separate.
4. If the post-deployment gate fails or reports `not_verified`, record the exact blocker, do not call V0.03 accepted, correct the processing/evidence, redeploy as needed, and rerun the post-deployment gate. Acceptance requires a passing gate against the current live artifacts.

## Run evidence and status

Run status was checked at **2026-10-14T00:39:59Z** (UTC). Live Pages artifacts and cues were checked at **2026-10-14T00:40:28Z** (UTC). GitHub Actions job times and HTTP `Last-Modified` values below are UTC.

| Run | Observed result |
|---|---|
| `38393870553` (main, SHA `6f7a1dc`) | Render completed, but `Verify caption structure and visual-style contract` failed at 13:05:29Z. Release publication and Pages artifact upload were skipped; the deploy job was skipped at 13:05:33Z. |
| `38408560804` (main, SHA `496ad85`) | Run concluded `failure` at 15:41:58Z. Cloud processing/burn-in succeeded at 15:38:57Z; operation-audit validation and preservation succeeded by 15:38:58Z; Release upload succeeded at 15:39:42Z; Pages artifact upload succeeded at 15:39:43Z; Pages deployment succeeded at 15:41:44Z. The post-deployment quality gate failed at 15:41:55Z. Translation comparison was skipped, so the ten-model/three-judge review was not performed. The first end-to-end cloud/publish path ran, but V0.03 is not accepted. |

The post-deployment gate log reports these blockers: audio-level alignment not passed; subtitle readability not passed; visual frame review not passed; English and Chinese reading-speed flags remain; translation accuracy not verified; fewer than ten translation models; fewer than three independent judges; fewer than three source cross-checks; translation review audio alignment not passed; source-audio review missing; independent translation review missing; fewer than ten distinct model-output records; fewer than three distinct judge reports; fewer than three independent source domains; three numbered full-span source-audio passes missing; and opening/middle/ending visual evidence incomplete. These are unverified/failed quality checks, not a failure of the deployment action.

Live Pages manifest returned HTTP 200 with `Last-Modified: 2026-10-13 15:41:32Z`; live bilingual VTT returned HTTP 200 with `Last-Modified: 2026-10-13 15:41:33Z`. The new manifest reports `asr_model: large-v3-turbo`, translation model `facebook/m2m100_1.2B`, `reused_existing_subtitles: false`, 725 cues, and duration 3532.021 seconds / resolution 1920x1080. Its processing-operation records identify task `38408560804.1`; the run's audit validation and artifact-preservation steps passed. Translation review remains `not_verified`: source-audio and independent translation reviews are false, model/judge/source counts are all zero. Readability is `manual_review_required`, visual review is `required`, audio-level alignment is `not_verified`; English reading-speed flags remain on 112 cues and Chinese flags on 7 cues.

The live VTT has consolidated the known 8:14 English greeting into one cue, `Good afternoon, everybody. What a great day here in Baltimore.` (00:08:04.740–00:08:24.870), paired with `大家好!在巴尔的摩度过了多么美好的一天。`. This removes the earlier fragment pairing (`Good` / `下午好,`, `afternoon,` / `大家`), but the Chinese omits the explicit afternoon greeting. Translation accuracy and source-audio alignment remain unverified and blocking pending actual review.

The new bilingual MP4 and three SRT files were uploaded to the intended GitHub Release; the MP4 asset metadata reports 1,110,703,899 bytes and an update time of 15:39:42Z, and its download URL returned HTTP 302. The MP4 is a Release asset, not a Pages file; the site path ending in `.mp4` returns 404 and is not the publication URL. The post-deployment gate ran after deployment, but its workflow downloads the generated subtitle/manifest artifact and invokes the manifest verifier; it does not fetch the live Pages URLs. This review independently confirmed the live manifest and VTT responses/timestamps above, but cloud-rendered frame review and independent probing of output duration/resolution/audio remain incomplete.

## Release decision

At the status cutoff above, the processing, audit, Release upload, Pages artifact upload, and deployment steps have passed, but **V0.03 is not accepted** because the post-deployment quality gate failed. The ten-model/three-judge comparison was skipped, and source-audio review, translation validation, reading-speed, and visual-frame checks remain failed or not verified. Keep the release in that state until the blockers are addressed and a new live-deployment gate passes.
