import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "outputs" / "pvXbHQrIvTw" / "comparison.json"
PAGE = ROOT / "events" / "pvXbHQrIvTw" / "index.html"
SCRIPT = ROOT / "assets" / "comparison.js"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-pages.yml"


class SubtitleComparisonPageTests(unittest.TestCase):
    def test_manifest_separates_media_routes_from_copilot_engineering_results(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        variants = {variant["id"]: variant for variant in manifest["variants"]}

        self.assertEqual(set(variants), {"open-source-baseline"})
        self.assertEqual(
            variants["open-source-baseline"]["status"],
            "preview_unverified",
        )
        self.assertEqual(
            variants["open-source-baseline"]["quality_checks"]["release_gate"],
            "blocked",
        )
        self.assertEqual(
            variants["open-source-baseline"]["quality_checks"][
                "source_audio_and_asr_accuracy"
            ],
            "not_verified",
        )
        self.assertEqual(
            variants["open-source-baseline"]["models"]["asr"],
            "large-v3-turbo",
        )
        self.assertEqual(
            variants["open-source-baseline"]["models"]["translation"],
            "facebook/m2m100_1.2B",
        )
        pathways = {pathway["id"]: pathway for pathway in manifest["pathways"]}
        self.assertEqual(
            set(pathways),
            {"smartsub-render", "caption-models", "autosubs", "whisperx"},
        )
        self.assertEqual(pathways["smartsub-render"]["status"], "executed_unverified")
        self.assertEqual(
            pathways["autosubs"]["status"],
            "proposed_not_runner_validated",
        )
        self.assertEqual(pathways["whisperx"]["status"], "research_only_not_run")
        self.assertEqual(
            manifest["copilot_engineering"]["status"],
            "implemented_and_deployed",
        )
        self.assertEqual(len(manifest["copilot_engineering"]["deliverables"]), 3)
        self.assertFalse(manifest["comparison_metrics"]["measured"])
        self.assertEqual(manifest["event"]["video_id"], "pvXbHQrIvTw")
        self.assertEqual(manifest["event"]["local_file_size_bytes"], 262338614)
        self.assertFalse(manifest["comparison_metrics"]["same_input_verified"])

    def test_page_does_not_advertise_missing_video_or_subtitles_as_available(self):
        page = PAGE.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("Copilot coding-agent", page)
        self.assertIn("不把代码代理与媒体模型混作同类模型", page)
        self.assertIn("proposed_not_runner_validated", json.loads(MANIFEST.read_text(encoding="utf-8"))["pathways"][2]["status"])
        self.assertIn("GPT-6", script)
        self.assertIn("pvXbHQrIvTw", page)

    def test_page_discloses_unverified_draft_and_known_blockers(self):
        page = PAGE.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        self.assertIn("AI 生成草稿，未经人工核验", page)
        self.assertIn("Hormone Strait", page)
        self.assertIn("sharing intel with his brain", page)
        self.assertIn("58 条英文字幕", page)
        self.assertIn("6 条中文字幕", page)
        self.assertIn("65 帧中的 5 帧", page)
        self.assertIn("机器生成、未经人工核验的草稿预览", script)
        self.assertEqual(
            manifest["smartsub_preview"]["review_status"]["release_gate"],
            "blocked",
        )
        self.assertTrue(manifest["variants"][0]["video_url"].startswith("https://"))
        self.assertTrue(
            all(
                value.startswith("https://")
                for value in manifest["variants"][0]["subtitles"].values()
            )
        )
        self.assertEqual(
            manifest["pathways"][0]["repository_url"],
            "https://github.com/buxuku/SmartSub",
        )
        self.assertEqual(
            manifest["pathways"][0]["source_commit"],
            manifest["smartsub_preview"]["render"]["source_commit"],
        )

    def test_homepage_surfaces_copilot_deliverables_and_credits_the_open_source_renderer(self):
        home = (ROOT / "index.html").read_text(encoding="utf-8")
        catalog = json.loads(
            (ROOT / "outputs" / "main-videos.json").read_text(encoding="utf-8")
        )
        preview = next(
            video
            for video in catalog["videos"]
            if video["id"] == "pvXbHQrIvTw-smartsub-draft-38540536544"
        )

        self.assertIn('id="copilot-results"', home)
        self.assertIn("PR #21", home)
        self.assertIn("PR #23", home)
        self.assertIn("PR #25", home)
        self.assertEqual(preview["render_engine"], "buxuku/SmartSub 3.9.0（上游开源项目，固定版本）")
        self.assertEqual(
            preview["render_engine_url"],
            "https://github.com/buxuku/SmartSub",
        )

    def test_event_page_changes_trigger_pages_deploy(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        push = workflow.split("  workflow_dispatch:", maxsplit=1)[0]

        self.assertIn("      - 'events/**'", push)
        self.assertIn("      - 'outputs/**'", push)


if __name__ == "__main__":
    unittest.main()
