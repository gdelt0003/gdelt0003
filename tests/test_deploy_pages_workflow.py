import re
import unittest
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "deploy-pages.yml"
)


def job_body(workflow: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
        workflow,
    )
    if match is None:
        raise AssertionError(f"Workflow job {name!r} was not found.")
    return match.group("body")


class DeployPagesWorkflowTests(unittest.TestCase):
    def test_push_deploy_is_limited_to_published_site_content(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        push = workflow.split("  workflow_dispatch:", maxsplit=1)[0]

        self.assertIn("    paths:", push)
        for path in ("'index.html'", "'assets/**'", "'outputs/**'", "'generated/**'"):
            with self.subTest(path=path):
                self.assertIn(f"      - {path}", push)
        self.assertNotIn("'scripts/**'", push)
        self.assertNotIn("'docs/**'", push)

    def test_push_deploy_is_not_blocked_by_the_post_deploy_quality_gate(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        deploy = job_body(workflow, "deploy")
        quality_gate = job_body(workflow, "main_pages_quality_gate")
        deploy_condition = deploy.split("    runs-on:", maxsplit=1)[0]
        gate_condition = quality_gate.split("    runs-on:", maxsplit=1)[0]

        self.assertNotIn("main_pages_quality_gate", deploy.split("    if:", 1)[0])
        self.assertIn("github.event_name == 'push'", deploy_condition)
        self.assertNotIn("needs.main_pages_quality_gate.result", deploy_condition)
        self.assertIn("needs: [deploy, process-full-video, restyle-full-video]", quality_gate)
        self.assertIn("needs.deploy.result == 'success'", quality_gate)
        self.assertNotIn("github.event_name == 'push'", gate_condition)
        self.assertNotIn("inputs.deploy_site_only", gate_condition)
        self.assertIn("inputs.validate_release_evidence", gate_condition)
        self.assertIn("inputs.process_full_video", gate_condition)
        self.assertIn("inputs.restyle_full_video", gate_condition)

    def test_full_video_quality_gate_runs_only_after_pages_deployment(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        process = job_body(workflow, "process-full-video")
        restyle = job_body(workflow, "restyle-full-video")
        deploy = job_body(workflow, "deploy")
        quality_gate = job_body(workflow, "main_pages_quality_gate")

        self.assertNotIn("verify_full_video_release.py", process)
        self.assertNotIn("verify_full_video_release.py", restyle)
        self.assertIn("needs.process-full-video.result == 'success'", deploy)
        self.assertIn("needs.deploy.result == 'success'", quality_gate)
        self.assertIn("verify_full_video_release.py", quality_gate)

    def test_post_deploy_gate_checks_the_new_render_manifest(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        quality_gate = job_body(workflow, "main_pages_quality_gate")

        self.assertIn("Download the manifest for the newly rendered video", quality_gate)
        self.assertIn("name: full-video-pages-subtitles", quality_gate)
        self.assertIn(
            "--manifest generated/full-video/manifest.json",
            quality_gate,
        )

    def test_comparison_video_job_checks_exact_uploaded_asset_before_rendering(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        job = job_body(workflow, "process-comparison-video")

        self.assertIn("inputs.process_comparison_video", job)
        self.assertIn("contents: write", job)
        self.assertIn("actions: read", job)
        self.assertIn("RIGHTS_CONFIRMED", job)
        self.assertIn("SAME_EVENT_CONFIRMED", job)
        self.assertIn("releases/assets/639463349", job)
        self.assertIn("262338614", job)
        self.assertIn(
            "33bf25655531190a2d73510649b780b21343481b308f993c107d87053e067171",
            job,
        )
        self.assertIn("--asset-prefix pvXbHQrIvTw", job)
        self.assertIn("pvXbHQrIvTw-comparison-review-", job)

    def test_comparison_video_can_restyle_prior_private_subtitles_only(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        job = job_body(workflow, "process-comparison-video")

        self.assertIn("comparison_reuse_artifact_run_id", workflow)
        self.assertIn("actions/download-artifact@v4", job)
        self.assertIn("run-id: ${{ inputs.comparison_reuse_artifact_run_id }}", job)
        self.assertIn("test -s \"$reuse_dir/pvXbHQrIvTw.en.srt\"", job)
        self.assertIn("test -s \"$reuse_dir/pvXbHQrIvTw.zh-Hans.srt\"", job)
        self.assertIn("--reuse-subtitles \"$reuse_dir\"", job)
        self.assertIn('"input_size_bytes": 262338614', job)
        self.assertIn(
            '"input_sha256": "33bf25655531190a2d73510649b780b21343481b308f993c107d87053e067171"',
            job,
        )
        self.assertIn("pysubs2==1.8.0", workflow)
        self.assertIn("if [[ -n \"$REUSE_RUN_ID\" ]]; then", job)
        self.assertIn("python -m pip install pysubs2==1.8.0", job)
        self.assertIn("authored with pysubs2 ", (
            WORKFLOW.parents[2] / "scripts" / "process_full_video.py"
        ).read_text(encoding="utf-8"))

    def test_smartsub_preview_uses_pinned_runner_composition_and_exact_source(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        job = job_body(workflow, "render-smartsub-draft")

        self.assertIn("inputs.process_smartsub_draft", job)
        self.assertIn("submodules: true", job)
        self.assertIn("a2b164b3dd86388355c6a4b84e4a49825a0e7f57", job)
        self.assertIn("pysubs2==1.8.0", job)
        self.assertIn("SmartSub_Linux_3.9.0_amd64.deb", job)
        self.assertIn("208f14dec45ea03be649780507707bff3b4dd4fbe0a219928a4a07d10bca5693", job)
        self.assertIn("releases/assets/639463349", job)
        self.assertIn("262338614", job)
        self.assertIn(
            "33bf25655531190a2d73510649b780b21343481b308f993c107d87053e067171",
            job,
        )
        self.assertIn("pvXbHQrIvTw-comparison-review-${{ inputs.smartsub_source_artifact_run_id }}", job)
        self.assertIn("compose run", job)
        self.assertIn('test -n "$cli" && test -x "$cli"', job)
        self.assertIn('xvfb-run --auto-servernum "$cli" compose run', job)
        self.assertNotIn("chmod +x", job)
        self.assertNotIn('install -m 755 "$cli"', job)
        self.assertIn('"outputMode":"hardcode"', job)
        self.assertIn("source_audio_and_asr_accuracy", job)
        self.assertIn('"not_verified"', job)
        self.assertIn("release gate is blocked", job)
        self.assertIn("validate_release_asset_size", job)
        self.assertIn("No Microsoft/GPT-6 model", job)
        self.assertNotIn("pipeline run", job)

    def test_smartsub_preview_deploys_a_player_with_disclosed_release_links(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        deploy = job_body(workflow, "deploy")

        self.assertIn("needs.render-smartsub-draft.result == 'success'", deploy)
        self.assertIn("inputs.publish_smartsub_draft", deploy)
        self.assertIn("pvXbHQrIvTw-smartsub-preview-${{ github.run_id }}", deploy)
        self.assertIn("scripts/publish_smartsub_preview.py", deploy)
        self.assertIn("--main-videos outputs/main-videos.json", deploy)
        self.assertIn("releases/download/pvXbHQrIvTw-smartsub-draft-", deploy)
        page = (WORKFLOW.parents[2] / "events" / "pvXbHQrIvTw" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("机器生成", page)
        self.assertIn("未经人工核验", page)
        script = (WORKFLOW.parents[2] / "assets" / "comparison.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("preview_unverified", script)

    def test_smartsub_can_render_privately_without_bypassing_publication_evidence(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        render = job_body(workflow, "render-smartsub-draft")
        deploy = job_body(workflow, "deploy")

        self.assertIn("comparison_review_evidence_json", workflow)
        self.assertIn("publish_smartsub_draft:\n        description:", workflow)
        self.assertIn("default: false", workflow.split("publish_smartsub_draft:", 1)[1].split(
            "smartsub_source_artifact_run_id:", 1
        )[0])
        self.assertIn("if: inputs.publish_smartsub_draft", render)
        self.assertIn("five distinct HTTPS evidence URLs", render)
        self.assertIn("CLEAN_FRAMES_CONFIRMED", render)
        self.assertIn("ENGLISH_ASR_CONFIRMED", render)
        self.assertIn("CHINESE_TRANSLATION_CONFIRMED", render)
        self.assertIn("pvXbHQrIvTw-smartsub-draft.mp4", render.split(
            "- name: Upload rendered draft and private runner evidence", 1
        )[1])
        self.assertIn("inputs.process_smartsub_draft && inputs.publish_smartsub_draft", deploy)

    def test_workflow_dispatch_stays_within_github_input_limit(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        dispatch = workflow.split("  workflow_dispatch:", maxsplit=1)[1].split(
            "\npermissions:", maxsplit=1
        )[0]
        inputs = re.findall(r"(?m)^      [A-Za-z0-9_-]+:", dispatch)

        self.assertLessEqual(len(inputs), 25)

    def test_comparison_frame_review_is_cloud_only_and_captures_flagged_cues(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        review = job_body(workflow, "review-comparison-artifact")
        review_script = (
            WORKFLOW.parents[2] / "scripts" / "create_comparison_frame_review.py"
        ).read_text(encoding="utf-8")

        self.assertIn("inputs.review_comparison_artifact_run_id != ''", review)
        self.assertIn("contents: read", review)
        self.assertIn("actions: read", review)
        self.assertNotIn("contents: write", review)
        self.assertNotIn("pages: write", review)
        self.assertIn("actions/download-artifact@v4", review)
        self.assertIn("run-id: ${{ inputs.review_comparison_artifact_run_id }}", review)
        self.assertIn("scripts/create_comparison_frame_review.py", review)
        self.assertIn("input_sha256", review_script)
        self.assertIn(
            "33bf25655531190a2d73510649b780b21343481b308f993c107d87053e067171",
            review_script,
        )
        self.assertIn("ffprobe", review_script)
        self.assertIn("ffmpeg", review_script)
        self.assertIn("english_reading_speed_over_20_cps_cues", review_script)
        self.assertIn("chinese_reading_speed_over_10_cps_cues", review_script)
        self.assertIn('"release_status": "blocked"', review_script)
        self.assertIn('"source_audio_and_asr_accuracy"', review_script)
        self.assertIn('"translation_accuracy"', review_script)
        self.assertIn('"readability_and_visual_style"', review_script)
        self.assertIn("--sampled-review-json", review_script)
        self.assertIn("review_comparison_sampled_review_json", workflow)
        self.assertIn("--sampled-review-json", review)
        self.assertIn("pvXbHQrIvTw-frame-review-", review)
        self.assertNotIn("needs.review-comparison-artifact", job_body(workflow, "deploy"))
        upload = review.split("- name: Upload frame-only visual review artifact", 1)[1]
        self.assertNotIn("pvXbHQrIvTw-bilingual.mp4", upload)


if __name__ == "__main__":
    unittest.main()
