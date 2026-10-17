#!/usr/bin/env python3
"""Discover and record bounded test waves for repositories tagged subtitle."""

from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_ROOT = "https://api.github.com"
QUERY = "topic:subtitle"
RESULT_CAP = 1000
WAVE_SIZE = 256
MAX_WAVES = 4
TEST_TIMEOUT_SECONDS = 8 * 60
MAX_LOG_BYTES = 1024 * 1024


@dataclass(frozen=True)
class TestPlan:
    stack: str
    command: str
    reason: str


def _request_json(url: str, token: str) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gdelt0003-subtitle-topic-test-matrix",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(
            f"GitHub API returned HTTP {error.code} for {url}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"GitHub API request failed for {url}: {error}") from error


def wave_bounds(wave: int) -> tuple[int, int, int, int]:
    if not 1 <= wave <= MAX_WAVES:
        raise ValueError(f"wave must be between 1 and {MAX_WAVES}")
    start = (wave - 1) * WAVE_SIZE
    end = min(start + WAVE_SIZE, RESULT_CAP)
    return start, end, start // 100 + 1, (end - 1) // 100 + 1


def discover_wave(wave: int, token: str) -> dict[str, Any]:
    start, end, first_page, last_page = wave_bounds(wave)
    pages: dict[int, list[dict[str, Any]]] = {}
    total_count: int | None = None
    for page in range(first_page, last_page + 1):
        params = urllib.parse.urlencode(
            {
                "q": QUERY,
                "sort": "stars",
                "order": "desc",
                "per_page": 100,
                "page": page,
            }
        )
        response = _request_json(f"{API_ROOT}/search/repositories?{params}", token)
        if response.get("incomplete_results"):
            raise RuntimeError(f"GitHub search page {page} returned incomplete results.")
        page_total = response.get("total_count")
        if not isinstance(page_total, int) or page_total < 0:
            raise RuntimeError("GitHub search response did not include a valid total_count.")
        if total_count is not None and page_total != total_count:
            raise RuntimeError("GitHub search result count changed while reading a wave.")
        total_count = page_total
        items = response.get("items")
        if not isinstance(items, list):
            raise RuntimeError(f"GitHub search page {page} did not include repository items.")
        pages[page] = items

    assert total_count is not None
    accessible_count = min(total_count, RESULT_CAP)
    repositories = []
    for position in range(start, min(end, accessible_count)):
        page = position // 100 + 1
        index = position % 100
        selected = pages.get(page, [])
        if index >= len(selected):
            raise RuntimeError(
                f"GitHub search result {position + 1} was missing from page {page}."
            )
        item = selected[index]
        full_name = item.get("full_name")
        default_branch = item.get("default_branch")
        if not isinstance(full_name, str):
            raise RuntimeError("GitHub search returned an item missing its repository name.")
        repositories.append(
            {
                "full_name": full_name,
                "default_branch": default_branch if isinstance(default_branch, str) else "",
                "stars": item.get("stargazers_count", 0),
                "language": item.get("language"),
                "search_position": position + 1,
            }
        )

    return {
        "query": QUERY,
        "sort": "stars",
        "order": "desc",
        "wave": wave,
        "wave_size": WAVE_SIZE,
        "wave_start": start + 1,
        "wave_end": min(end, accessible_count),
        "total_count": total_count,
        "accessible_count": accessible_count,
        "result_cap": RESULT_CAP,
        "repositories": repositories,
    }


def resolve_sha(repository: str, branch: str, token: str) -> str:
    encoded_branch = urllib.parse.quote(branch, safe="")
    url = f"{API_ROOT}/repos/{repository}/commits/{encoded_branch}"
    response = _request_json(url, token)
    commit = response.get("sha")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise RuntimeError(f"GitHub did not return a commit SHA for {repository}.")
    return commit.lower()


def _has_tests(root: Path, suffixes: set[str]) -> bool:
    test_dir = root / "tests"
    if test_dir.is_dir():
        for path in test_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes:
                return True
    return any(
        path.is_file() and path.suffix.lower() in suffixes
        for path in root.glob("test_*")
    )


def detect_test_plan(root: Path, language: str | None = None) -> TestPlan:
    python_files = _has_tests(root, {".py"})
    python_config = any(
        (root / name).is_file()
        for name in ("pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg")
    )
    if python_files and python_config:
        test_sources = [
            path
            for path in (root / "tests").rglob("*.py")
            if path.is_file()
        ] if (root / "tests").is_dir() else list(root.glob("test_*.py"))
        pytest_style = any(
            re.search(
                r"(^|\s)(import pytest|from pytest import)|^def test_",
                path.read_text(encoding="utf-8", errors="replace"),
                flags=re.MULTILINE,
            )
            for path in test_sources[:100]
        )
        pytest_config = (root / "pytest.ini").exists()
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            pytest_config = pytest_config or "[tool.pytest" in pyproject.read_text(
                encoding="utf-8", errors="replace"
            )
        if pytest_style or pytest_config:
            python_command = "python -m pytest -q"
        else:
            python_command = "python -m unittest discover -s tests -v"
        if language in (None, "Python"):
            return TestPlan("Python", python_command, "Python test files and project configuration found.")

    package_file = root / "package.json"
    if package_file.is_file() and language in (None, "JavaScript", "TypeScript"):
        try:
            package = json.loads(package_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return TestPlan("Node.js", "", f"package.json could not be parsed: {error}")
        scripts = package.get("scripts", {})
        if isinstance(scripts, dict) and isinstance(scripts.get("test"), str):
            return TestPlan("Node.js", "npm test", "package.json defines a test script.")
        return TestPlan("Node.js", "", "package.json does not define a test script.")

    if (root / "go.mod").is_file() and language in (None, "Go"):
        if any(root.rglob("*_test.go")):
            return TestPlan(
                "Go",
                "GOPROXY=off GOSUMDB=off go test ./...",
                "Go test files and go.mod found; module downloads are disabled.",
            )
        return TestPlan("Go", "", "go.mod exists but no Go test files were found.")

    if (root / "Cargo.toml").is_file() and language in (None, "Rust"):
        if (root / "tests").is_dir() or (root / "src").is_dir():
            return TestPlan(
                "Rust",
                "cargo test --locked --offline",
                "Cargo project found; dependency downloads are disabled.",
            )
        return TestPlan("Rust", "", "Cargo.toml exists but no conventional test source was found.")

    detected = language or "unknown"
    return TestPlan(
        detected,
        "",
        "No supported test suite was detected among Python, Node.js, Go, and Rust.",
    )


def _command_argv(plan: TestPlan, root: Path) -> list[str]:
    if plan.stack == "Go":
        return ["go", "test", "./..."]
    if plan.stack == "Rust":
        return ["cargo", "test", "--locked", "--offline"]
    if plan.stack == "Node.js":
        return ["npm", "test"]
    if plan.command == "python -m pytest -q":
        return [sys.executable, "-m", "pytest", "-q"]
    if plan.stack == "Python":
        if (root / "tests").is_dir():
            return [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        return [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            ".",
            "-p",
            "test*.py",
            "-v",
        ]
    return []


def _sandbox_ids() -> tuple[int, int]:
    import grp
    import pwd

    return pwd.getpwnam("nobody").pw_uid, grp.getgrnam("nogroup").gr_gid


def _sandbox_path() -> str:
    paths = [
        "/usr/local/sbin",
        "/usr/local/bin",
        "/usr/sbin",
        "/usr/bin",
        "/sbin",
        "/bin",
    ]
    for executable in ("node", "npm", "go", "cargo"):
        path = shutil.which(executable)
        if path:
            paths.insert(0, str(Path(path).parent))
    return os.pathsep.join(dict.fromkeys(paths))


def _capture_process_output(
    process: subprocess.Popen[bytes], timeout_seconds: int
) -> tuple[int | None, str, bool]:
    output = bytearray()
    truncated = False
    timed_out = False
    stop_deadline: float | None = None
    deadline = time.monotonic() + timeout_seconds
    selector = selectors.DefaultSelector()
    if process.stdout is None:
        raise RuntimeError("Test process stdout was not captured.")
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while selector.get_map() or process.poll() is None:
            now = time.monotonic()
            if not timed_out and now >= deadline:
                timed_out = True
                stop_deadline = now + 5
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            elif stop_deadline is not None and now >= stop_deadline:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stop_deadline = None

            if selector.get_map():
                for key, _ in selector.select(timeout=0.2):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = MAX_LOG_BYTES - len(output)
                    if remaining > 0:
                        output.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        truncated = True
            elif process.poll() is None:
                time.sleep(0.2)
        return_code = process.wait()
    finally:
        selector.close()
        process.stdout.close()
    log = output.decode("utf-8", errors="replace")
    if truncated:
        log += f"\n[output truncated after {MAX_LOG_BYTES} bytes]\n"
    return return_code, log, timed_out


def _test_process(
    plan: TestPlan, root: Path, timeout_seconds: int = TEST_TIMEOUT_SECONDS
) -> tuple[str, str]:
    command = _command_argv(plan, root)
    if not command:
        return "unsupported", "No executable test command was identified."
    try:
        sandbox_uid, sandbox_gid = _sandbox_ids()
    except (ImportError, KeyError) as error:
        return "skipped", f"Unprivileged sandbox account is unavailable: {error}"
    try:
        isolation = subprocess.run(
            ["sudo", "-n", "unshare", "--net", "--", "true"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return "skipped", f"Network isolation check failed: {error}"
    if isolation.returncode != 0:
        return "skipped", (
            "Network-isolated execution is unavailable on this runner; "
            f"unshare exited {isolation.returncode}: {isolation.stdout[-1000:]}"
        )

    runner_temp = Path(
        os.environ.get("RUNNER_TEMP", tempfile.gettempdir())
    ).resolve()
    temp_root = Path(
        tempfile.mkdtemp(
            prefix="subtitle-topic-sandbox-",
            dir=str(runner_temp),
        )
    )
    os.chmod(temp_root, 0o711)
    test_root = temp_root / "repository"
    test_home = temp_root / "home"
    test_tmp = temp_root / "tmp"
    try:
        for directory in (test_root, test_home, test_tmp):
            subprocess.run(
                [
                    "sudo",
                    "-n",
                    "install",
                    "-d",
                    "-o",
                    str(sandbox_uid),
                    "-g",
                    str(sandbox_gid),
                    "--",
                    str(directory),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=15,
            )
        subprocess.run(
            [
                "sudo",
                "-n",
                "cp",
                "-a",
                "--",
                f"{root.resolve()}/.",
                f"{test_root}/",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
        )
        subprocess.run(
            [
                "sudo",
                "-n",
                "chmod",
                "-R",
                "o+rwX",
                "--",
                str(test_root),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        shutil.rmtree(temp_root, ignore_errors=True)
        return "skipped", f"Unable to prepare unprivileged test sandbox: {error}"

    clean_environment = {
        "PATH": _sandbox_path(),
        "HOME": str(test_home),
        "TMPDIR": str(test_tmp),
        "CI": "true",
        "GIT_TERMINAL_PROMPT": "0",
        "npm_config_offline": "true",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_update_notifier": "false",
        "GOPROXY": "off",
        "GOSUMDB": "off",
        "CARGO_NET_OFFLINE": "true",
    }
    sandbox_prefix = [
        "prlimit",
        "--cpu=480:480",
        "--nproc=128:128",
        "--fsize=104857600:104857600",
        "--",
        "sudo",
        "-n",
        "unshare",
        "--net",
        "--",
        "setpriv",
        f"--reuid={sandbox_uid}",
        f"--regid={sandbox_gid}",
        "--init-groups",
        "--",
    ]
    sandbox_environment = [
        "env",
        "-i",
        *[f"{key}={value}" for key, value in clean_environment.items()],
    ]
    try:
        version_command = (
            [command[0], "version"] if plan.stack == "Go" else [command[0], "--version"]
        )
        try:
            preflight = subprocess.run(
                [*sandbox_prefix, *sandbox_environment, *version_command],
                cwd=test_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return "skipped", f"Test executable preflight failed: {error}"
        if preflight.returncode != 0:
            return "skipped", (
                "Test executable is unavailable to the unprivileged sandbox user "
                f"(preflight exited {preflight.returncode}): "
                f"{preflight.stdout[-1000:]}"
            )

        process = subprocess.Popen(
            [*sandbox_prefix, *sandbox_environment, *command],
            cwd=test_root,
            env={"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return_code, output, timed_out = _capture_process_output(
            process, timeout_seconds
        )
        if timed_out:
            return "failed", f"Test command exceeded {timeout_seconds} seconds."
    except OSError as error:
        return "failed", f"Unable to start test command: {error}"
    finally:
        try:
            subprocess.run(
                ["sudo", "-n", "rm", "-rf", "--", str(temp_root)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
            )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)
    if return_code == 0:
        return "passed", output
    return "failed", f"Test command exited {return_code}.\n{output or ''}"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _summary_line(result: dict[str, Any], summary_path: str | None) -> None:
    if not summary_path:
        return
    summary = Path(summary_path)
    if not summary.exists() or summary.stat().st_size == 0:
        summary.write_text(
            "| Repository | Pinned SHA | Stack | Test command | Outcome | Logs |\n"
            "|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    with open(summary_path, "a", encoding="utf-8") as stream:
        stream.write(
            "| {repository} | `{sha}` | {stack} | `{command}` | **{outcome}** | "
            "[run logs]({log_link}) |\n".format(
                repository=result.get("repository", ""),
                sha=result.get("sha", "unresolved"),
                stack=result.get("stack", ""),
                command=result.get("test_command") or "-",
                outcome=result.get("outcome", ""),
                log_link=result.get("log_link", ""),
            )
        )
        if result.get("reason"):
            stream.write(f"\n{result['reason']}\n")


def record_attempt_failure(
    output_dir: Path,
    repository: str,
    wave: int,
    search_position: int,
    run_url: str,
    reason: str,
    sha: str = "",
) -> dict[str, Any]:
    result = {
        "repository": repository,
        "sha": sha or None,
        "wave": wave,
        "search_position": search_position,
        "stack": "unknown",
        "test_command": None,
        "outcome": "failed",
        "reason": reason,
        "log_link": run_url,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(output_dir / "result.json", result)
    (output_dir / "test.log").write_text(reason + "\n", encoding="utf-8")
    _summary_line(result, os.environ.get("GITHUB_STEP_SUMMARY"))
    return result


def run_candidate(
    root: Path,
    output_dir: Path,
    repository: str,
    sha: str,
    language: str | None,
    wave: int,
    search_position: int,
    run_url: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        plan = detect_test_plan(root, language)
        command = plan.command
        if not command:
            outcome = "unsupported"
            log = plan.reason
        else:
            outcome, log = _test_process(plan, root)
        result = {
            "repository": repository,
            "sha": sha,
            "wave": wave,
            "search_position": search_position,
            "stack": plan.stack,
            "test_command": command or None,
            "outcome": outcome,
            "reason": (
                plan.reason
                if outcome == "unsupported"
                else log.splitlines()[0]
                if outcome != "passed" and log
                else None
            ),
            "log_link": run_url,
            "tested_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as error:
        outcome = "failed"
        log = f"Harness error: {type(error).__name__}: {error}"
        result = {
            "repository": repository,
            "sha": sha,
            "wave": wave,
            "search_position": search_position,
            "stack": "unknown",
            "test_command": None,
            "outcome": outcome,
            "reason": log,
            "log_link": run_url,
            "tested_at": datetime.now(timezone.utc).isoformat(),
        }
    _write_json(output_dir / "result.json", result)
    (output_dir / "test.log").write_text(log.rstrip() + "\n", encoding="utf-8")
    _summary_line(result, os.environ.get("GITHUB_STEP_SUMMARY"))
    return result


def _write_action_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        raise RuntimeError("GITHUB_OUTPUT is not set.")
    with open(output_file, "a", encoding="utf-8") as stream:
        stream.write(f"{name}={value}\n")


def _discover_cli(args: argparse.Namespace) -> int:
    result = discover_wave(args.wave, os.environ.get(args.token_env, ""))
    _write_action_output("matrix", json.dumps(result["repositories"], separators=(",", ":")))
    for name in (
        "query",
        "sort",
        "order",
        "wave",
        "wave_size",
        "wave_start",
        "wave_end",
        "total_count",
        "accessible_count",
        "result_cap",
    ):
        _write_action_output(name, str(result[name]))
    print(
        f"Query {QUERY!r}: {result['total_count']} results reported, "
        f"{result['accessible_count']} retrievable (API cap {RESULT_CAP}); "
        f"wave {args.wave} contains {len(result['repositories'])} repositories."
    )
    return 0


def _pin_cli(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    try:
        sha = resolve_sha(args.repository, args.branch, os.environ.get(args.token_env, ""))
        _write_action_output("sha", sha)
        _write_action_output("pin_error", "")
        return 0
    except Exception as error:
        reason = f"Unable to resolve commit SHA: {type(error).__name__}: {error}"
        _write_action_output("sha", "")
        _write_action_output("pin_error", reason)
        record_attempt_failure(
            output_dir,
            args.repository,
            args.wave,
            args.search_position,
            args.run_url,
            reason,
        )
        return 0


def _run_cli(args: argparse.Namespace) -> int:
    result = run_candidate(
        Path(args.root),
        Path(args.output_dir),
        args.repository,
        args.sha,
        args.language or None,
        args.wave,
        args.search_position,
        args.run_url,
    )
    return 0 if result["outcome"] == "passed" else 1


def _failure_cli(args: argparse.Namespace) -> int:
    record_attempt_failure(
        Path(args.output_dir),
        args.repository,
        args.wave,
        args.search_position,
        args.run_url,
        args.reason,
        args.sha,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    discover_parser = subparsers.add_parser("discover")
    discover_parser.add_argument("--wave", type=int, required=True)
    discover_parser.add_argument("--token-env", default="MATRIX_GITHUB_TOKEN")
    discover_parser.set_defaults(handler=_discover_cli)

    pin_parser = subparsers.add_parser("pin")
    pin_parser.add_argument("--repository", required=True)
    pin_parser.add_argument("--branch", required=True)
    pin_parser.add_argument("--wave", type=int, required=True)
    pin_parser.add_argument("--search-position", type=int, required=True)
    pin_parser.add_argument("--output-dir", required=True)
    pin_parser.add_argument("--run-url", required=True)
    pin_parser.add_argument("--token-env", default="MATRIX_GITHUB_TOKEN")
    pin_parser.set_defaults(handler=_pin_cli)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--root", required=True)
    run_parser.add_argument("--output-dir", required=True)
    run_parser.add_argument("--repository", required=True)
    run_parser.add_argument("--sha", required=True)
    run_parser.add_argument("--language", default="")
    run_parser.add_argument("--wave", type=int, required=True)
    run_parser.add_argument("--search-position", type=int, required=True)
    run_parser.add_argument("--run-url", required=True)
    run_parser.set_defaults(handler=_run_cli)

    failure_parser = subparsers.add_parser("failure")
    failure_parser.add_argument("--output-dir", required=True)
    failure_parser.add_argument("--repository", required=True)
    failure_parser.add_argument("--wave", type=int, required=True)
    failure_parser.add_argument("--search-position", type=int, required=True)
    failure_parser.add_argument("--run-url", required=True)
    failure_parser.add_argument("--reason", required=True)
    failure_parser.add_argument("--sha", default="")
    failure_parser.set_defaults(handler=_failure_cli)

    args = parser.parse_args()
    try:
        return args.handler(args)
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
