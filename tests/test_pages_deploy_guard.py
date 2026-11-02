import re
import unittest
from pathlib import Path


class PagesDeployGuardTests(unittest.TestCase):
    def test_deploy_is_gated_to_push_or_an_explicit_manual_action(self):
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
            "(inputs.regenerate_clips || inputs.diarize_speakers)", expression
        )
        self.assertIn("needs.build.result == 'success'", expression)
        self.assertIn(
            "inputs.process_smartsub_draft && inputs.publish_smartsub_draft",
            expression,
        )
        self.assertIn("needs.render-smartsub-draft.result == 'success'", expression)
        self.assertIn("inputs.deploy_site_only", expression)
        self.assertIn(
            "(inputs.process_full_video || inputs.restyle_full_video)", expression
        )
        self.assertIn("needs.process-full-video.result == 'success'", expression)
        self.assertIn("needs.restyle-full-video.result == 'success'", expression)


if __name__ == "__main__":
    unittest.main()
