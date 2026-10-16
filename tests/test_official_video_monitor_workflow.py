import unittest
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "monitor-official-whitehouse-videos.yml"
)


class OfficialVideoMonitorWorkflowTests(unittest.TestCase):
    def test_uses_five_minute_schedule_and_default_branch_only(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('cron: "*/5 * * * *"', workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("cancel-in-progress: false", workflow)

    def test_deduplication_and_run_provenance_are_persisted_off_main(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("STATE_BRANCH: official-video-monitoring-state", workflow)
        self.assertIn("Load durable deduplication state", workflow)
        self.assertIn("Persist deduplication state and run provenance", workflow)
        self.assertIn('git checkout -B "$STATE_BRANCH" FETCH_HEAD', workflow)
        self.assertIn('git checkout --orphan "$STATE_BRANCH"', workflow)
        self.assertIn('runs/${GITHUB_RUN_ID}.json', workflow)
        self.assertIn('--summary-file "$GITHUB_STEP_SUMMARY"', workflow)
        self.assertIn('git push origin "HEAD:${STATE_BRANCH}"', workflow)
        self.assertNotIn("git push origin HEAD:main", workflow)

    def test_monitor_never_runs_video_processing_or_publication_steps(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        for forbidden in ("ffmpeg", "download_full_source", "deploy-pages", "create Release"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, workflow)
        self.assertIn("research each newly discovered official page", workflow)


if __name__ == "__main__":
    unittest.main()
