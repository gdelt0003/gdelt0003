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

Run-status cutoff: **2026-10-13T14:10:39Z**. Live Pages evidence was fetched at **2026-10-13T14:08:43Z**.

- Earlier run `38393870553` (main SHA `6f7a1dc`): generation succeeded, visual/style verification failed at 13:05:29Z, Release and Pages artifact steps were skipped, and deploy was skipped at 13:05:33Z.
- Current run `38408560804` (main SHA `496ad85`): still processing at 14:10:39Z; source download succeeded, cloud generation/burn-in was in progress since 13:54:11Z, and audit validation, Release/Pages publication, deploy, and post-deploy gate had not started. Translation comparison was skipped. It is not yet a deployed or accepted V0.03 run.
- Last-observed live Pages manifest and VTT predate the current run (modified 07:33:08Z and 07:33:07Z respectively). The manifest says translation review was not performed, and the VTT still shows the known 8:14 pairing defect. The Pages MP4 URL returned HTTP 404. These observations remain blockers until current-run artifacts replace them and pass post-deployment review.

For the full checklist and evidence details, see [full-video-verification-checklist.md](full-video-verification-checklist.md).
