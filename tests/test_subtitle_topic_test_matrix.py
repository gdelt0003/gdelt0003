import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import subtitle_topic_test_matrix as matrix


class SubtitleTopicMatrixTests(unittest.TestCase):
    @patch.object(matrix.urllib.request, "urlopen")
    def test_api_token_is_sent_only_as_an_authorization_header(self, urlopen):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"ok": true}'

        urlopen.return_value.__enter__.return_value = Response()

        result = matrix._request_json("https://api.github.com/repos/example/repo", "test-token")

        self.assertTrue(result["ok"])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")

    def test_wave_ranges_cover_all_api_results_without_exceeding_search_cap(self):
        first = matrix.wave_bounds(1)
        middle = matrix.wave_bounds(2)
        last = matrix.wave_bounds(4)

        self.assertEqual(first, (0, 256, 1, 3))
        self.assertEqual(middle, (256, 512, 3, 6))
        self.assertEqual(last, (768, 1000, 8, 10))
        self.assertEqual(
            sum(
                min(matrix.wave_bounds(wave)[1], 999) - matrix.wave_bounds(wave)[0]
                for wave in range(1, 5)
            ),
            999,
        )
        with self.assertRaises(ValueError):
            matrix.wave_bounds(5)

    @patch.object(matrix, "_request_json")
    def test_discovery_uses_topic_search_star_sort_and_exact_wave_slice(self, request):
        request.side_effect = [
            {
                "total_count": 999,
                "incomplete_results": False,
                "items": [
                    {
                        "full_name": f"owner/repo-{page_index * 100 + index}",
                        "default_branch": "main",
                        "stargazers_count": 1000 - page_index * 100 - index,
                        "language": "Python",
                    }
                    for index in range(100)
                ],
            }
            for page_index in range(3)
        ]

        result = matrix.discover_wave(1, "read-token")

        self.assertEqual(result["accessible_count"], 999)
        self.assertEqual(result["wave_start"], 1)
        self.assertEqual(result["wave_end"], 256)
        self.assertEqual(len(result["repositories"]), 256)
        self.assertEqual(result["repositories"][0]["search_position"], 1)
        self.assertEqual(result["repositories"][-1]["search_position"], 256)
        url = request.call_args_list[0].args[0]
        self.assertIn("q=topic%3Asubtitle", url)
        self.assertIn("sort=stars", url)
        self.assertIn("order=desc", url)
        self.assertIn("page=1", url)
        self.assertIn("page=3", request.call_args_list[-1].args[0])
        self.assertEqual(request.call_args_list[0].args[1], "read-token")

    @patch.object(matrix, "_request_json")
    def test_last_wave_stops_at_999_results_across_search_pages(self, request):
        request.side_effect = [
            {
                "total_count": 999,
                "incomplete_results": False,
                "items": [
                    {
                        "full_name": f"owner/repo-{(page - 1) * 100 + index + 1}",
                        "default_branch": "main",
                        "stargazers_count": 999 - ((page - 1) * 100 + index),
                        "language": "Python",
                    }
                    for index in range(100 if page < 10 else 99)
                ],
            }
            for page in range(8, 11)
        ]

        result = matrix.discover_wave(4, "")

        self.assertEqual(len(result["repositories"]), 231)
        self.assertEqual(result["repositories"][0]["search_position"], 769)
        self.assertEqual(result["repositories"][-1]["search_position"], 999)
        self.assertEqual(result["wave_end"], 999)
        self.assertEqual(request.call_count, 3)

    def test_detects_python_unittest_suite_without_installing_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[project]\nname='sample'\n")
            (root / "tests").mkdir()
            (root / "tests" / "test_basic.py").write_text("import unittest\n")

            plan = matrix.detect_test_plan(root, "Python")

        self.assertEqual(plan.stack, "Python")
        self.assertEqual(plan.command, "python -m unittest discover -s tests -v")

    def test_detects_documented_node_test_script(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"scripts": {"test": "node --test"}}), encoding="utf-8"
            )

            plan = matrix.detect_test_plan(root, "JavaScript")

        self.assertEqual(plan.stack, "Node.js")
        self.assertEqual(plan.command, "npm test")

    def test_disables_go_and_rust_dependency_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "go.mod").write_text("module example\n")
            (root / "main_test.go").write_text("package example\n")
            go_plan = matrix.detect_test_plan(root, "Go")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Cargo.toml").write_text("[package]\nname='example'\n")
            (root / "src").mkdir()
            rust_plan = matrix.detect_test_plan(root, "Rust")

        self.assertEqual(go_plan.command, "GOPROXY=off GOSUMDB=off go test ./...")
        self.assertEqual(rust_plan.command, "cargo test --locked --offline")

    def test_unknown_project_is_recorded_as_unsupported_not_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = matrix.detect_test_plan(root, "Haskell")
            result = matrix.run_candidate(
                root,
                root / "evidence",
                "owner/unsupported",
                "a" * 40,
                "Haskell",
                1,
                1,
                "https://github.com/owner/repo/actions/runs/42",
            )
            evidence = json.loads(
                (root / "evidence" / "result.json").read_text(encoding="utf-8")
            )

        self.assertEqual(plan.command, "")
        self.assertEqual(result["outcome"], "unsupported")
        self.assertEqual(evidence["outcome"], "unsupported")
        self.assertIsNone(evidence["test_command"])

    @patch.object(matrix, "run_candidate", return_value={"outcome": "skipped"})
    def test_non_pass_outcomes_fail_the_matrix_job(self, run_candidate):
        args = type(
            "Args",
            (),
            {
                "root": ".",
                "output_dir": ".",
                "repository": "owner/repo",
                "sha": "a" * 40,
                "language": "",
                "wave": 1,
                "search_position": 1,
                "run_url": "https://github.com/owner/repo/actions/runs/42",
            },
        )()

        self.assertEqual(matrix._run_cli(args), 1)
        run_candidate.assert_called_once()

    @patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}, clear=False)
    @patch.object(matrix, "_sandbox_ids", return_value=(65534, 65534))
    @patch.object(matrix.subprocess, "run")
    def test_network_isolation_unavailable_is_recorded_as_skipped(self, run, _sandbox_ids):
        run.return_value.returncode = 1
        run.return_value.stdout = "unshare: Operation not permitted"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[project]\nname='sample'\n")
            (root / "tests").mkdir()
            (root / "tests" / "test_basic.py").write_text("import unittest\n")

            outcome, log = matrix._test_process(
                matrix.detect_test_plan(root, "Python"), root
            )

        self.assertEqual(outcome, "skipped")
        self.assertIn("Network-isolated execution is unavailable", log)
        self.assertEqual(run.call_count, 1)

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "must-not-reach-test-process",
            "PATH": "/usr/bin",
        },
        clear=False,
    )
    def test_test_command_is_offline_and_runs_as_an_unprivileged_user(
        self,
    ):
        with (
            patch.object(matrix, "_sandbox_ids", return_value=(65534, 65534)),
            patch.object(matrix.subprocess, "Popen") as popen,
            patch.object(matrix.subprocess, "run") as run,
            patch.object(
                matrix,
                "_capture_process_output",
                return_value=(0, "tests passed\n", False),
            ) as capture,
            tempfile.TemporaryDirectory() as directory,
        ):
            run.return_value.returncode = 0
            run.return_value.stdout = ""
            base = Path(directory)
            root = base / "workspace" / "repo"
            root.mkdir(parents=True)
            runner_temp = base / "runner-temp"
            runner_temp.mkdir()
            (root / "pyproject.toml").write_text("[project]\nname='sample'\n")
            (root / "tests").mkdir()
            (root / "tests" / "test_basic.py").write_text("import unittest\n")

            with patch.dict(
                os.environ, {"RUNNER_TEMP": str(runner_temp)}, clear=False
            ):
                outcome, log = matrix._test_process(
                    matrix.detect_test_plan(root, "Python"), root
                )

        invocation = popen.call_args.args[0]
        self.assertEqual(outcome, "passed")
        self.assertIn("tests passed", log)
        self.assertIn("--net", invocation)
        self.assertIn("prlimit", invocation)
        self.assertIn("--reuid=65534", invocation)
        self.assertIn("-i", invocation)
        self.assertNotIn("must-not-reach-test-process", invocation)
        self.assertEqual(popen.call_args.kwargs["env"], {"PATH": "/usr/bin"})
        self.assertGreaterEqual(run.call_count, 4)
        capture.assert_called_once()
        self.assertTrue(
            any(
                "cp" in call.args[0] and "-a" in call.args[0]
                for call in run.call_args_list
            )
        )
        self.assertTrue(
            any(
                "test" in call.args[0]
                and "-x" in call.args[0]
                and call.args[0][-1] == str(runner_temp.resolve())
                for call in run.call_args_list
            )
        )
        self.assertTrue(
            any("--version" in call.args[0] for call in run.call_args_list)
        )
        self.assertTrue(
            any("chmod" in call.args[0] and "o+rwX" in call.args[0] for call in run.call_args_list)
        )
        self.assertEqual(
            Path(popen.call_args.kwargs["cwd"]),
            Path(popen.call_args.kwargs["cwd"]).parent / "repository",
        )

    def test_unavailable_sandbox_executable_is_recorded_as_skipped(self):
        def run_command(command, **_kwargs):
            return matrix.subprocess.CompletedProcess(
                command,
                126 if "--version" in command else 0,
                stdout="env: cargo: Permission denied\n" if "--version" in command else "",
            )

        with (
            patch.object(matrix, "_sandbox_ids", return_value=(65534, 65534)),
            patch.object(matrix.subprocess, "Popen") as popen,
            patch.object(matrix.subprocess, "run", side_effect=run_command),
            tempfile.TemporaryDirectory() as directory,
        ):
            base = Path(directory)
            root = base / "workspace" / "repo"
            root.mkdir(parents=True)
            runner_temp = base / "runner-temp"
            runner_temp.mkdir()
            (root / "pyproject.toml").write_text("[project]\nname='sample'\n")
            (root / "tests").mkdir()
            (root / "tests" / "test_basic.py").write_text("import unittest\n")

            with patch.dict(
                os.environ, {"RUNNER_TEMP": str(runner_temp)}, clear=False
            ):
                outcome, log = matrix._test_process(
                    matrix.detect_test_plan(root, "Python"), root
                )

        self.assertEqual(outcome, "skipped")
        self.assertIn("Test executable is unavailable", log)
        self.assertIn("preflight exited 126", log)
        popen.assert_not_called()

    @patch.object(matrix.subprocess, "run")
    def test_runner_temp_traversal_stops_at_first_accessible_ancestor(self, run):
        with tempfile.TemporaryDirectory() as directory:
            runner_temp = Path(directory) / "runner-temp"
            run.side_effect = [
                matrix.subprocess.CompletedProcess([], 1),
                matrix.subprocess.CompletedProcess([], 0),
                matrix.subprocess.CompletedProcess([], 1),
                matrix.subprocess.CompletedProcess([], 0),
                matrix.subprocess.CompletedProcess([], 0),
            ]

            changed_directories = matrix._ensure_sandbox_path_traversal(
                runner_temp, 65534, 65534
            )

        calls = [call.args[0] for call in run.call_args_list]
        changed_commands = [
            Path(command[-1]).name
            for command in calls
            if command[0:4] == ["sudo", "-n", "chmod", "o+x"]
        ]
        self.assertEqual(changed_commands, ["runner-temp", Path(directory).name])
        self.assertEqual(
            changed_directories,
            [str(runner_temp), str(Path(directory))],
        )
        self.assertEqual(
            changed_directories, [str(runner_temp), str(runner_temp.parent)]
        )
        self.assertEqual(calls[0][calls[0].index("test") + 1], "-x")
        self.assertEqual(calls[2][calls[2].index("test") + 1], "-x")
        self.assertEqual(calls[4][calls[4].index("test") + 1], "-x")


class SubtitleTopicMatrixWorkflowTests(unittest.TestCase):
    def test_workflow_is_manual_read_only_and_uses_separate_ephemeral_jobs(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "test-subtitle-topic-repositories.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("fail-fast: false", workflow)
        self.assertIn("max-parallel: 256", workflow)
        self.assertIn("timeout-minutes: 15", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("lfs: false", workflow)
        self.assertIn("!**/*.mp4", workflow)
        self.assertIn("!**/*.webm", workflow)
        self.assertGreaterEqual(workflow.count("/scripts/subtitle_topic_test_matrix.py"), 2)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("npm ci", workflow)
        self.assertNotIn("curl ", workflow)
        harness = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "subtitle_topic_test_matrix.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"sudo", "-n", "unshare", "--net"', harness)
        self.assertIn('"--reuid={sandbox_uid}"', harness)
        self.assertIn('"env",\n        "-i"', harness)
        run_step = workflow.split("Run detected test suite with network disabled", 1)[1].split(
            "      - name:", 1
        )[0]
        self.assertNotIn("GITHUB_TOKEN:", run_step)
        self.assertNotIn("MATRIX_GITHUB_TOKEN:", run_step)

    def test_matrix_is_explicitly_a_bounded_wave_and_preserves_each_result(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "test-subtitle-topic-repositories.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("options:", workflow)
        self.assertIn('"wave_size": WAVE_SIZE', (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "subtitle_topic_test_matrix.py"
        ).read_text(encoding="utf-8"))
        self.assertIn("if: always()", workflow)
        self.assertIn("options:\n          - \"1\"\n          - \"2\"\n          - \"3\"\n          - \"4\"", workflow)
        self.assertIn("retention-days: 30", workflow)
        self.assertIn("actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683", workflow)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", workflow)


if __name__ == "__main__":
    unittest.main()
