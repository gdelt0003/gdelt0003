import re
import unittest
from pathlib import Path


class PagesDeployGuardTests(unittest.TestCase):
    def test_deploy_only_runs_on_push_or_successful_manual_processing(self):
        workflow = Path(".github/workflows/deploy-pages.yml").read_text(
            encoding="utf-8"
        )
        deploy_job = re.search(
            r"(?ms)^  deploy:\n(?P<job>.*?)(?=^  [\w-]+:|\Z)", workflow
        )
        self.assertIsNotNone(deploy_job)
        condition = re.search(
            r"(?ms)^    if: >-\n(?P<condition>(?:      .*\n)+)",
            deploy_job.group("job"),
        )
        self.assertIsNotNone(condition)
        expression = " ".join(
            line.strip() for line in condition.group("condition").splitlines()
        )

        self.assertIn("always()", expression)
        self.assertIn("github.event_name == 'push'", expression)
        self.assertIn("github.event_name == 'workflow_dispatch'", expression)
        self.assertIn(
            "(inputs.process_full_video || inputs.restyle_full_video)", expression
        )
        self.assertIn(
            "needs.process-full-video.result == 'success' || "
            "needs.restyle-full-video.result == 'success'",
            expression,
        )
        for job in (
            "build",
            "download-source",
            "download-same-clip",
            "download-same-full-video",
            "process-full-video",
            "restyle-full-video",
        ):
            self.assertIn(f"needs.{job}.result != 'failure'", expression)
            self.assertIn(f"needs.{job}.result != 'cancelled'", expression)


if __name__ == "__main__":
    unittest.main()
