"""Defer an optional push lane only to a positively observed exact-head PR producer."""

from __future__ import annotations

import json
import os
import subprocess

from scripts.quality.change_classification import REPOSITORY, ROOT, git


def api(path: str) -> dict | list:
    return json.loads(
        subprocess.run(
            ["gh", "api", path], check=True, capture_output=True, text=True, timeout=30
        ).stdout
    )


def feature_plan() -> dict:
    plan = {
        "schema_version": "feature-pr-authority.v1",
        "run_feature": True,
        "reason": "no-verified-exact-head-pr-authority",
        "repository": REPOSITORY,
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
    }
    try:
        head = git("rev-parse", "HEAD")
        plan["source_head_sha"] = head
        if (
            os.environ.get("GITHUB_EVENT_NAME") != "push"
            or os.environ.get("GITHUB_WORKFLOW") != "Remote Feature Lane"
            or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or os.environ.get("GITHUB_SHA") != head
        ):
            return plan
        pulls = api(f"repos/{REPOSITORY}/commits/{head}/pulls?per_page=100")
        runs = api(
            f"repos/{REPOSITORY}/actions/runs?event=pull_request&head_sha={head}&per_page=100"
        )
        if not isinstance(pulls, list) or not isinstance(runs, dict):
            return plan
        for pull in pulls:
            if (
                pull.get("state") != "open"
                or pull.get("head", {}).get("sha") != head
                or pull.get("base", {}).get("ref") != "main"
                or pull.get("base", {}).get("repo", {}).get("full_name") != REPOSITORY
            ):
                continue
            for run in runs.get("workflow_runs", []):
                if (
                    run.get("head_sha") == head
                    and run.get("event") == "pull_request"
                    and run.get("path") == ".github/workflows/pr-merge-gate.yml"
                    and run.get("status") in {"queued", "in_progress", "completed"}
                    and (
                        run.get("status") != "completed"
                        or run.get("conclusion") in {"success", "failure"}
                    )
                    and any(
                        item.get("number") == pull["number"]
                        for item in run.get("pull_requests", [])
                    )
                ):
                    plan.update(
                        run_feature=False,
                        reason="delegated-to-exact-head-required-pr-lane",
                        pr_number=pull["number"],
                        pr_run_id=run["id"],
                    )
                    return plan
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        plan["reason"] = "pr-authority-unavailable-full-feature-fallback"
    return plan


def main() -> int:
    plan = feature_plan()
    payload = json.dumps(plan, sort_keys=True, indent=2)
    print(payload)
    destination = ROOT / "output/pr-validation/feature-authority.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload + "\n", encoding="utf-8")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"run_feature={str(plan['run_feature']).lower()}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("\n```json\n" + payload + "\n```\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
