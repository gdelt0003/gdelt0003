# Highest directives: V0.03 release scope

## User decision

> “长期还没实现的宏观规划 可以放到下一期做,当前完成V0.03版本,可以跑通一个个例”

Interpretation for this release: complete one real end-to-end example first. Do not block V0.03 on generalized multi-event infrastructure, but do not relax quality or evidence requirements for the selected example.

## V0.03: one-instance end-to-end acceptance

The selected instance is the official White House recording `oW-PQlgw1wo`. V0.03 must demonstrate, on GitHub-hosted cloud runners, this complete path:

1. Source input → ASR → Chinese translation → subtitle burn-in/video encoding.
2. Validate and retain the per-operation processing audit.
3. Publish the output video and subtitle assets to the intended GitHub Release and Pages.
4. After Pages deployment, independently inspect the live output and run the post-deployment quality gate.

The single instance must still pass evidence-based checks for source-audio wording, English/Chinese translation fidelity, cue synchronization and timing, readability/style, rendered frames, source/output duration and resolution, audio presence, and correspondence between the successful run and live artifacts. The ten-model comparison, three independent judges, and at least three independent source cross-checks remain V0.03 instance-level quality requirements. If billable API authorization or budget is absent, do not call paid services; leave those items `not_verified` and keep the release blocked.

The verified 8:14 phrase-pairing regression is an acceptance item: `Good afternoon,` / `下午好,` and `everybody.` / `大家。` must be confirmed in the **deployed** captions with their live cue timing.

## Next phase: deferred macro work

Under the explicit scope assumption that these capabilities are not needed to exercise one known source, defer the following to the next phase:

- Multi-event discovery and recurring coverage.
- Generalized batch processing and reusable operations beyond the selected instance.
- The broad ten-publisher / alternate-camera-angle source-footage survey.

The ten-publisher/alternate-angle survey was previously listed as a requirement. Deferring it here is a scope decision, **not completion**: keep it recorded as incomplete. If an alternate source or camera angle is required for the selected instance, bring that work back into V0.03 blockers.

## Deployment and quality-gate semantics

The first Pages deployment may happen before the post-deployment gate. A successful deployment only means the deployment step completed; it does not mean the release passed quality acceptance. The gate must inspect the live deployed files and verify they correspond to the current processing run. If the gate fails or any required check is `not_verified`, record the exact blockers, keep V0.03 unaccepted, make corrections, redeploy when needed, and rerun the gate.

## Current recorded run status

Run-status cutoff: **2026-10-14T00:39:59Z**. Live Pages evidence was fetched at **2026-10-14T00:40:28Z**.

- Earlier run `38393870553` (main SHA `6f7a1dc`): generation succeeded, visual/style verification failed at 13:05:29Z, Release and Pages artifact steps were skipped, and deploy was skipped at 13:05:33Z.
- Current run `38408560804` (main SHA `496ad85`): processing/burn-in passed at 15:38:57Z, operation-audit validation and preservation passed by 15:38:58Z, Release upload passed at 15:39:42Z, Pages artifact upload passed at 15:39:43Z, and deployment passed at 15:41:44Z. The post-deployment quality gate failed at 15:41:55Z; the run concluded `failure` at 15:41:58Z. Translation comparison was skipped.
- Exact post-deployment blockers: audio-level alignment, readability, visual frame review, English and Chinese reading-speed flags, translation accuracy, <10 models, <3 judges, <3 source cross-checks, missing source-audio and independent translation reviews, missing ten model outputs, three judge reports and three independent source domains, missing three numbered full-span audio passes, and incomplete opening/middle/ending visual evidence.
- Live Pages manifest/VTT now correspond in modification time to the new deployment (15:41:32Z / 15:41:33Z) and return HTTP 200. Manifest shows `large-v3-turbo` ASR, M2M100 translation, 725 cues, 1920x1080 / 3532.021 seconds, fresh subtitles (`reused_existing_subtitles: false`), and operation records for task `38408560804.1`. It also explicitly leaves translation review `not_verified`, source-audio and independent translation review false, model/judge/source counts zero, readability `manual_review_required`, visual review `required`, audio-level alignment `not_verified`, and reading-speed flags (112 English, 7 Chinese). The earlier greeting fragment mismatch is consolidated to a shared 20-second cue, but the Chinese omits the explicit afternoon greeting and no independent transcript/audio judgment has verified it. The MP4 and SRT files exist on the GitHub Release; its MP4 URL returns HTTP 302. The guessed Pages `.mp4` URL returns 404 because the video is published as a Release asset, not as a Pages file.
- The post-deployment gate runs after Pages deployment but downloads the processing job's generated subtitle/manifest artifact and verifies that artifact; it does not fetch live Pages URLs. This review independently fetched the live manifest and VTT (HTTP 200 and current modification times), but the automated live-endpoint verification requirement is not yet implemented. No cloud-rendered frame inspection or post-deployment video probe has been done.

Therefore the single-instance workflow has executed through deployment, but V0.03 acceptance remains blocked by the failed post-deployment gate and its outstanding evidence checks. A successful deployment must not be represented as a successful quality acceptance.

For the full checklist and evidence details, see [full-video-verification-checklist.md](full-video-verification-checklist.md).
