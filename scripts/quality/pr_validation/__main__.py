"""Run one fixed native PR target or prove its documentation-only omission."""

from __future__ import annotations

import argparse
import json
import os
import subprocess

from scripts.quality.change_classification import ROOT, current_plan, emit
from scripts.quality.pr_validation.policy import TARGETS, selected_commands


def run_target(target: str) -> int:
    plan = current_plan()
    commands = selected_commands(target, plan["mode"])
    plan.update(
        target=target,
        decision="omit-runtime-docs-only" if plan["mode"] == "docs-only" else "execute-full",
        selected_commands=commands,
    )
    emit(plan)
    result = 0
    command_results = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, check=False).returncode
        command_results.append({"command": command, "native_exit": result})
        if result:
            break
    plan["native_exit"] = result
    plan["command_results"] = command_results
    if plan["mode"] == "docs-only" and result == 0:
        evidence_path = ROOT / "output/documentation-evidence/documentation-evidence-pack.json"
        plan["documentation_evidence_pack"] = json.loads(evidence_path.read_text(encoding="utf-8"))
    path = ROOT / "output/pr-validation" / f"{target}.json"
    path.write_text(json.dumps(plan, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(
                f"\nPR validation `{target}`: **{plan['decision']}**, native exit `{result}`.\n"
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(TARGETS))
    return run_target(parser.parse_args().target)


if __name__ == "__main__":
    raise SystemExit(main())
