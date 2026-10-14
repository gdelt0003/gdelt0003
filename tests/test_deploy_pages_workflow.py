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

        self.assertNotIn("main_pages_quality_gate", deploy.split("    if:", 1)[0])
        self.assertIn("github.event_name == 'push'", deploy_condition)
        self.assertNotIn("needs.main_pages_quality_gate.result", deploy_condition)
        self.assertIn("needs: [deploy, process-full-video, restyle-full-video]", quality_gate)
        self.assertIn("needs.deploy.result == 'success'", quality_gate)

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

    def test_comparison_frame_review_is_cloud_only_and_captures_flagged_cues(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        review = job_body(workflow, "review-comparison-artifact")
        review_script = (
            WORKFLOW.parents[2] / "scripts" / "create_comparison_frame_review.py"
        ).read_text(encoding="utf-8")

        self.assertIn("inputs.review_comparison_artifact_run_id != ''", review)
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
        self.assertIn("pvXbHQrIvTw-frame-review-", review)
        self.assertNotIn("needs.review-comparison-artifact", job_body(workflow, "deploy"))
        upload = review.split("- name: Upload frame-only visual review artifact", 1)[1]
        self.assertNotIn("pvXbHQrIvTw-bilingual.mp4", upload)


if __name__ == "__main__":
    unittest.main()
