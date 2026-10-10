"""Classify a verified merge-base diff; only authored Markdown can omit PR runtime proof."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "sgajbi/lotus-core"
DOCUMENT_FILES = frozenset({"README.md", "CHANGELOG.md", "REPOSITORY-ENGINEERING-CONTEXT.md"})
DOCUMENT_PARENTS = frozenset(
    {
        "wiki",
        "docs/architecture",
        "docs/architecture/codebase-reviews",
        "docs/operations",
        "docs/integration",
    }
)


def surface(path: str) -> str:
    candidate = PurePosixPath(path)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or "\\" in path
        or ":" in path
        or candidate.as_posix() != path
    ):
        return "unknown"
    if path in DOCUMENT_FILES or (
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.md", candidate.name)
        and candidate.parent.as_posix() in DOCUMENT_PARENTS
    ):
        return "authored-documentation"
    if "Dockerfile" in candidate.name or path.startswith("docker-compose"):
        return "image"
    if candidate.name in {
        "Makefile",
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "requirements.txt",
        "uv.lock",
        "poetry.lock",
        ".python-version",
    }:
        return "dependency-or-build"
    for prefix, category in (
        (".github/", "workflow"),
        ("requirements/", "dependency"),
        ("alembic/", "migration"),
        ("contracts/", "contract"),
        ("docs/standards/", "generated-contract-input"),
        ("tests/", "test"),
        ("src/libs/", "shared-library"),
        ("src/services/", "application"),
        ("scripts/", "governance-code"),
        ("quality/", "governance-input"),
        ("tools/", "build-tool"),
    ):
        if path.startswith(prefix):
            return category
    return "unknown"


def parse_changes(raw: str) -> list[dict[str, str]]:
    """Consume Git's unquoted NUL-delimited status/path records, including old rename paths."""
    tokens = raw.split("\0")
    if not tokens or tokens[-1] != "":
        raise ValueError("diff must have a terminal NUL")
    tokens.pop()
    changes: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        width = 3 if status.startswith(("R", "C")) else 2
        if len(tokens) - index < width or not status or not tokens[index + 1]:
            raise ValueError("malformed name-status diff")
        path = tokens[index + width - 1]
        if not path:
            raise ValueError("empty changed path")
        item = {"status": status, "path": path, "surface": surface(path)}
        if width == 3:
            item["previous_path"] = tokens[index + 1]
        changes.append(item)
        index += width
    return changes


def classify_changes(changes: list[dict[str, str]]) -> tuple[str, list[str]]:
    if not changes:
        return "full", ["empty-diff"]
    reasons = sorted(
        {
            f"{item['status']}:{item['surface']}:{item['path']}"
            for item in changes
            if item["status"] not in {"A", "M"} or item["surface"] != "authored-documentation"
        }
    )
    return ("full", reasons) if reasons else ("docs-only", ["only-allowlisted-authored-markdown"])


def git(*args: str, root: Path = ROOT) -> str:
    output = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    ).stdout
    return output if args[0] == "diff" else output.strip()


def classify_range(base: str, head: str, *, root: Path = ROOT) -> dict[str, Any]:
    resolved_base = git("rev-parse", "--verify", f"{base}^{{commit}}", root=root)
    resolved_head = git("rev-parse", "--verify", f"{head}^{{commit}}", root=root)
    merge_base = git("merge-base", resolved_base, resolved_head, root=root)
    changes = parse_changes(
        git("diff", "--name-status", "-z", "--find-renames", merge_base, resolved_head, root=root)
    )
    for item in changes:
        if item["surface"] == "authored-documentation" and item["status"] in {"A", "M"}:
            tree_entry = git("ls-tree", resolved_head, "--", item["path"], root=root)
            if not tree_entry.startswith("100644 blob "):
                item["surface"] = "nonregular-documentation"
    mode, reasons = classify_changes(changes)
    return {
        "base_sha": resolved_base,
        "source_head_sha": resolved_head,
        "merge_base_sha": merge_base,
        "mode": mode,
        "reasons": reasons,
        "changes": changes,
    }


def current_plan(*, root: Path = ROOT) -> dict[str, Any]:
    """Omissions require a trusted PR event and checkout/source ancestry, never an env mode flag."""
    identity: dict[str, Any] = {
        "schema_version": "pr-change-classification.v1",
        "repository": os.environ.get("GITHUB_REPOSITORY", "local"),
        "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "workflow": os.environ.get("GITHUB_WORKFLOW", "local"),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "local"),
        "job": os.environ.get("GITHUB_JOB", "local"),
        "mode": "full",
        "reasons": ["non-pr-validation-is-always-full"],
        "changes": [],
    }
    try:
        checkout = git("rev-parse", "HEAD", root=root)
        identity.update(
            checkout_sha=checkout, checkout_tree=git("rev-parse", "HEAD^{tree}", root=root)
        )
        if (
            identity["event"] != "pull_request"
            or identity["repository"] != REPOSITORY
            or identity["workflow"] != "Pull Request Merge Gate"
        ):
            return identity
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        pr = event["pull_request"]
        if pr["base"]["ref"] != "main" or pr["base"]["repo"]["full_name"] != REPOSITORY:
            raise ValueError("noncanonical PR base")
        source = pr["head"]["sha"]
        base = pr["base"]["sha"]
        if os.environ.get("GITHUB_SHA") != checkout:
            raise ValueError("checkout/event SHA mismatch")
        parents = git("rev-list", "--parents", "-n", "1", checkout, root=root).split()[1:]
        if checkout != source and parents != [base, source]:
            raise ValueError("checkout is neither PR source nor its exact base/source merge")
        if git("status", "--porcelain", "--untracked-files=no", root=root):
            raise ValueError("tracked source is dirty")
        identity.update(classify_range(base, source, root=root), pr_number=pr["number"])
    except (OSError, KeyError, ValueError, TypeError, subprocess.CalledProcessError):
        identity.update(mode="full", reasons=["unverified-event-source-or-diff"])
    return identity


def emit(plan: dict[str, Any]) -> None:
    print(json.dumps(plan, sort_keys=True))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"mode={plan['mode']}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("\n```json\n" + json.dumps(plan, sort_keys=True, indent=2) + "\n```\n")
    destination = ROOT / "output/pr-validation/classification.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(plan, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    plan = classify_range(args.base, args.head) if args.base else current_plan()
    emit(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
