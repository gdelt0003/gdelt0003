import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "render-rose-garden-private.yml"
SKILL = (
    ROOT
    / ".github"
    / "skills"
    / "multi-source-event-video-production"
    / "SKILL.md"
)


class RoseGardenPrivateWorkflowTests(unittest.TestCase):
    def test_workflow_uses_user_caption_box_without_added_rights_attestations(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('default: "66,883,1852,1022"', workflow)
        self.assertIn('--caption-box "$CAPTION_BOX"', workflow)
        self.assertIn("reference_box_xyxy_half_open", workflow)
        self.assertIn('"status": "not_assessed"', workflow)
        self.assertNotIn("rights_evidence_url", workflow)
        self.assertNotIn("reuse_rights_confirmed", workflow)
        self.assertNotIn("exact_event_match_confirmed", workflow)

    def test_private_dispatch_validation_does_not_require_rights_evidence(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "verify_rose_garden_review.py"),
                "--validate-dispatch-inputs",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_skill_does_not_turn_added_evidence_checklists_into_private_gates(self):
        skill = SKILL.read_text(encoding="utf-8")

        self.assertIn(
            "Do not make private processing conditional on HTTPS evidence links",
            skill,
        )
        self.assertIn("unresolved status is not represented as permission", skill)


if __name__ == "__main__":
    unittest.main()
