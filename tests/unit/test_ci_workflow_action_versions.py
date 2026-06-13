from pathlib import Path

GOVERNED_RUNTIME_WORKFLOWS = (
    Path(".github/workflows/pr-merge-gate.yml"),
    Path(".github/workflows/main-releasability.yml"),
)

ALL_WORKFLOWS = tuple(Path(".github/workflows").glob("*.yml"))

NODE20_DEPRECATED_ACTION_PINS = (
    "actions/cache@v4",
    "actions/upload-artifact@v4",
    "actions/download-artifact@v4",
    "docker/setup-buildx-action@v3",
)

EXPECTED_RUNTIME_ACTION_PINS = (
    "actions/cache@v5",
    "actions/upload-artifact@v5",
    "docker/setup-buildx-action@v4",
)


def test_runtime_workflows_do_not_use_node20_deprecated_action_pins() -> None:
    deprecated_pins: list[str] = []
    for workflow_path in GOVERNED_RUNTIME_WORKFLOWS:
        workflow_text = workflow_path.read_text(encoding="utf-8")
        for action_pin in NODE20_DEPRECATED_ACTION_PINS:
            if action_pin in workflow_text:
                deprecated_pins.append(f"{workflow_path}: {action_pin}")

    assert deprecated_pins == []


def test_runtime_workflows_use_current_action_pins_for_cache_artifacts_and_buildx() -> None:
    workflow_text = "\n".join(
        workflow_path.read_text(encoding="utf-8") for workflow_path in GOVERNED_RUNTIME_WORKFLOWS
    )

    for action_pin in EXPECTED_RUNTIME_ACTION_PINS:
        assert action_pin in workflow_text

    assert "actions/download-artifact@v5" in Path(
        ".github/workflows/main-releasability.yml"
    ).read_text(encoding="utf-8")


def test_workflows_opt_into_node24_action_runtime() -> None:
    missing_opt_in = [
        str(workflow_path)
        for workflow_path in ALL_WORKFLOWS
        if 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"'
        not in workflow_path.read_text(encoding="utf-8")
    ]

    assert missing_opt_in == []


def test_pr_auto_merge_does_not_probe_branch_protection_with_github_token() -> None:
    workflow_text = Path(".github/workflows/pr-auto-merge.yml").read_text(encoding="utf-8")

    assert "/branches/main/protection" not in workflow_text
    assert "administration:" not in workflow_text
