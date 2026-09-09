from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "merged-pr-main-releasability.yml"
PR_NUMBER = "1077"


def _git_bash() -> str | None:
    git = shutil.which("git")
    if git:
        for parent in Path(git).resolve().parents:
            candidate = parent / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
    bash = shutil.which("bash")
    return None if bash and "system32" in bash.lower() else bash


BASH = _git_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="Git Bash is required")


def _dispatch_script() -> str:
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "run: |":
            continue
        indent = len(line) - len(line.lstrip())
        body: list[str] = []
        body_indent: int | None = None
        for candidate in lines[index + 1 :]:
            if not candidate.strip():
                body.append("")
                continue
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if candidate_indent <= indent:
                break
            body_indent = body_indent or candidate_indent
            body.append(candidate[body_indent:])
        script = "\n".join(body)
        if "git rev-list --reverse" in script:
            return script
    raise AssertionError("dispatcher shell was not found")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, filename: str) -> str:
    (repo / filename).write_text(filename + "\n", encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "--quiet", "-m", f"add {filename}")
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet", "--initial-branch=main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "remote", "add", "origin", str(repo))
    _commit(repo, "root")
    return repo, _git(repo, "rev-parse", "HEAD")


def _run_dispatch(
    repo: Path,
    tmp_path: Path,
    *,
    base_sha: str,
    merge_sha: str,
    commit_count: int,
) -> tuple[int, str, list[str]]:
    assert BASH is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    calls = tmp_path / "gh-calls.txt"
    calls.write_text("", encoding="utf-8")
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{calls.as_posix()}"\n'
        'case "$*" in *git/ref/tags/*) exit 1;; *) exit 0;; esac\n',
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    jq = bin_dir / "jq"
    jq.write_text("#!/bin/sh\necho '{}';\n", encoding="utf-8", newline="\n")
    jq.chmod(0o755)
    script = tmp_path / "dispatch.sh"
    script.write_text(_dispatch_script(), encoding="utf-8", newline="\n")
    environment = dict(os.environ)
    environment.update(
        {
            "PATH": f"{bin_dir.as_posix()}{os.pathsep}{environment['PATH']}",
            "RUNNER_TEMP": tmp_path.as_posix(),
            "GITHUB_REPOSITORY": "sgajbi/lotus-core",
            "GH_TOKEN": "test-only",
            "BASE_SHA": base_sha,
            "COVERAGE_BASELINE_SHA": base_sha,
            "MERGE_COMMIT_SHA": merge_sha,
            "COMMIT_COUNT": str(commit_count),
            "PR_NUMBER": PR_NUMBER,
        }
    )
    completed = subprocess.run(
        [BASH, str(script)],
        cwd=repo,
        env=environment,
        capture_output=True,
        text=True,
    )
    dispatched = [
        line.split("expected_sha=", 1)[1].split()[0]
        for line in calls.read_text(encoding="utf-8").splitlines()
        if "workflow run" in line and "expected_sha=" in line
    ]
    return completed.returncode, completed.stdout + completed.stderr, dispatched


def test_dispatches_every_rebased_revision_in_ancestry_order(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    _git(repo, "switch", "--quiet", "-c", "feature")
    first = _commit(repo, "first")
    second = _commit(repo, "second")
    _git(repo, "update-ref", f"refs/pull/{PR_NUMBER}/head", second)
    _git(repo, "switch", "--quiet", "main")
    _git(repo, "cherry-pick", first, second)
    revisions = _git(repo, "rev-list", "--reverse", f"{base}..HEAD").splitlines()

    code, output, dispatched = _run_dispatch(
        repo,
        tmp_path,
        base_sha=base,
        merge_sha=revisions[-1],
        commit_count=2,
    )

    assert code == 0, output
    assert dispatched == revisions


def test_refuses_a_window_that_does_not_match_the_pr_commit_count(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    _git(repo, "switch", "--quiet", "-c", "feature")
    feature = _commit(repo, "feature")
    _git(repo, "update-ref", f"refs/pull/{PR_NUMBER}/head", feature)
    _git(repo, "switch", "--quiet", "main")
    _commit(repo, "foreign")
    _git(repo, "cherry-pick", feature)
    merge_sha = _git(repo, "rev-parse", "HEAD")

    code, output, dispatched = _run_dispatch(
        repo,
        tmp_path,
        base_sha=base,
        merge_sha=merge_sha,
        commit_count=1,
    )

    assert code != 0
    assert dispatched == []
    assert "resolved 2" in output


def test_refuses_a_two_parent_merge(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    _git(repo, "switch", "--quiet", "-c", "feature")
    feature = _commit(repo, "feature")
    _git(repo, "update-ref", f"refs/pull/{PR_NUMBER}/head", feature)
    _git(repo, "switch", "--quiet", "main")
    _commit(repo, "main")
    _git(repo, "merge", "--quiet", "--no-ff", "-m", "merge feature", "feature")

    code, output, dispatched = _run_dispatch(
        repo,
        tmp_path,
        base_sha=base,
        merge_sha=_git(repo, "rev-parse", "HEAD"),
        commit_count=2,
    )

    assert code != 0
    assert dispatched == []
    assert "single-parent" in output
