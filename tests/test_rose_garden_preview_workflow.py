import unittest
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "render-rose-garden-lunch-preview.yml"
)


class RoseGardenPreviewWorkflowTests(unittest.TestCase):
    def test_renders_the_named_official_source_only_on_github_runner(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("https://www.youtube.com/watch?v=IySF_8OArvw", workflow)
        self.assertIn('metadata.get("id") != "IySF_8OArvw"', workflow)
        self.assertIn("Rose Garden Lunch", workflow)
        self.assertIn("Oct. 15, 2026", workflow)
        self.assertIn('"white house" not in uploader', workflow)
        self.assertIn('"reuse_rights_status": "not independently verified; private preview only"', workflow)
        self.assertIn('"source_match_status": "title and publisher metadata matched; frame/audio review not verified"', workflow)
        self.assertIn("width>=1920][height>=1080", workflow)
        self.assertIn("no upscaling is allowed", workflow)
        self.assertIn("python scripts/process_full_video.py", workflow)

    def test_preserves_review_status_and_does_not_publish_publicly(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('manifest["translation_review"] = "machine translation not reviewed"', workflow)
        self.assertIn('manifest["source_frame_review"] = "not reviewed"', workflow)
        self.assertIn('manifest["publication_status"] = "private review artifact; not published"', workflow)
        self.assertIn("name: rose-garden-lunch-2026-10-15-preview-${{ github.run_id }}", workflow)
        self.assertIn("retention-days: 14", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("actions/deploy-pages", workflow)
        self.assertNotIn("pages: write", workflow)

    def test_artifact_contains_rendered_frame_samples_and_operation_audit(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Extract representative rendered frames for review", workflow)
        self.assertIn('"beginning", 0.02', workflow)
        self.assertIn('"middle", 0.50', workflow)
        self.assertIn('"ending", 0.98', workflow)
        self.assertIn("python scripts/verify_operation_audit.py", workflow)
        self.assertIn("operation-audit.json", workflow)
        self.assertIn("SHA256SUMS", workflow)


if __name__ == "__main__":
    unittest.main()
