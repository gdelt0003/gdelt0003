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

    def test_post_deploy_gate_checks_the_new_render_manifest(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        quality_gate = job_body(workflow, "main_pages_quality_gate")

        self.assertIn("Download the manifest for the newly rendered video", quality_gate)
        self.assertIn("name: full-video-pages-subtitles", quality_gate)
        self.assertIn(
            "--manifest generated/full-video/manifest.json",
            quality_gate,
        )


if __name__ == "__main__":
    unittest.main()
