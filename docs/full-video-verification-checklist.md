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

Run status below was last checked at **2026-10-13T14:10:39Z**. Live Pages artifacts were fetched at **2026-10-13T14:08:43Z**. UTC job times are from GitHub Actions; Pages `Last-Modified` values are HTTP response headers.

| Run | Observed result |
|---|---|
| `38393870553` (main, SHA `6f7a1dc`) | Render completed, but `Verify caption structure and visual-style contract` failed at 13:05:29Z. Release publication and Pages artifact upload were skipped; the deploy job was skipped at 13:05:33Z. |
| `38408560804` (main, SHA `496ad85`) | Still in progress at 14:10:39Z. Setup, dependencies, and source download succeeded; cloud generation/burn-in has been running since 13:54:11Z. Operation-audit validation/preservation, Release upload, Pages artifact upload, deploy, and post-deployment gate have not run yet. Translation comparison was skipped, so the ten-model/three-judge review remains unverified. Do not report this run as deployed or accepted. |

Latest live Pages evidence fetched at 14:08:43Z still predates run `38408560804`: manifest `Last-Modified` was 2026-10-13 07:33:08Z and VTT was 07:33:07Z. The manifest reports `translation_review.status: not_performed`, `llm_judges: 0`, `source_cross_check_passes: 0`, `reused_existing_subtitles: true`, and 2,021 cues. The live VTT still has the 8:14 mismatch:

- `00:08:04.740–00:08:10.737`: `Good` / `下午好,`
- `00:08:10.737–00:08:16.733`: `afternoon,` / `大家`
- `00:08:16.733–00:08:22.730`: `everybody.` / `。`

The Pages URL for `generated/full-video/whitehouse-oW-PQlgw1wo-bilingual.mp4` returned HTTP 404 at 14:08:43Z. A GitHub Release MP4 existed from an earlier render, but it is not evidence that the new run was published or that the current V0.03 checks passed.

## Release decision

At the status cutoff above, **V0.03 is not accepted**: the active run has not reached deployment, its ten-model/three-judge comparison is skipped, and known live output defects remain. Preserve every failed or unavailable check as `failed` or `not_verified`; do not convert it to passed based on a successful render or deploy.
