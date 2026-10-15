# Katie Zacharia full-video test preview

The workflow `.github/workflows/publish-katie-zacharia-preview.yml` is a manually dispatched, opt-in path for the October 13, 2026 White House media briefing. It runs only from `main` on a GitHub-hosted runner. It does not modify or publish the original draft source intake.

The workflow pins source release asset `642103215` by release tag, name, size, and SHA-256. Before inference it requires exact-event and reuse-rights confirmations, checks the official White House event listing and copyright policy over HTTPS, verifies the downloaded bytes, and rejects video below 1920x1080 rather than upscaling. It uses `scripts/process_full_video.py` with the local runner ASR/translation pipeline and FFmpeg; no paid model API or voice cloning is used.

The output is a public prerelease and a Pages test preview. The manifest and operation audit record source identity, hash, pipeline/model versions, and review state. ASR accuracy, Chinese translation, source audio/frame match, and complete visual/readability review remain `not_verified`; the release gate stays blocked. The White House copyright policy describes government-produced content as generally not copyright protected but notes transferred and third-party exceptions, which this preview does not independently clear. Do not treat this test preview as an approved final release.
