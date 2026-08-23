from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml

from scripts.quality.required_status_checks import (
    DEFAULT_MANIFEST_PATH,
    RequiredCheck,
    RequiredChecksManifest,
    RequiredStatusChecksError,
    WorkflowPolicy,
    blocking_contexts_for_workflow,
    desired_protection_payload,
    load_live_protection,
    load_manifest,
    validate_live_protection,
    validate_manifest_against_workflows,
)

_CANONICAL_TRIGGERS_YAML = (
    "on:\n"
    "  pull_request:\n"
    "    branches: [main]\n"
    "    types: [opened, synchronize, reopened, ready_for_review]\n"
    "  merge_group:\n"
    "    branches: [main]\n"
)


def _fixture_manifest(payload: dict[str, Any]) -> RequiredChecksManifest:
    return RequiredChecksManifest(
        repository=payload["repository"],
        branch=payload["branch"],
        strict=payload["strict"],
        workflow_policies=tuple(
            WorkflowPolicy(
                path=Path(policy["path"]),
                policy=policy["policy"],
                advisory_contexts=frozenset(policy["advisory_contexts"]),
            )
            for policy in payload["workflow_policies"]
        ),
        required_checks=tuple(
            RequiredCheck(context=check["context"], app_id=check["app_id"])
            for check in payload["required_checks"]
        ),
    )


def _write_fixture_makefile(repository_root: Path) -> None:
    repository_root.joinpath("Makefile").write_text(
        ".PHONY: security-audit\nsecurity-audit:\n\t@true\n",
        encoding="utf-8",
    )


def test_repository_manifest_matches_expanded_blocking_workflow_contexts() -> None:
    manifest = load_manifest()

    validate_manifest_against_workflows(manifest)

    assert (
        RequiredCheck(
            context="PR Merge Gate / Tests (transaction-processing-contract)",
            app_id=15368,
        )
        in manifest.required_checks
    )
    assert (
        RequiredCheck(
            context="Quality Baseline / Import Boundary Gate",
            app_id=15368,
        )
        in manifest.required_checks
    )
    assert all(
        check.context != "Quality Baseline / Report Only" for check in manifest.required_checks
    )


def test_manifest_validation_fails_closed_without_makefile_authority(tmp_path: Path) -> None:
    with pytest.raises(RequiredStatusChecksError, match="unable to load Makefile phony targets"):
        validate_manifest_against_workflows(load_manifest(), repository_root=tmp_path)


def test_manifest_validation_fails_closed_without_phony_targets(tmp_path: Path) -> None:
    tmp_path.joinpath("Makefile").write_text("lint:\n\t@true\n", encoding="utf-8")

    with pytest.raises(RequiredStatusChecksError, match="Makefile has no declared phony targets"):
        validate_manifest_against_workflows(load_manifest(), repository_root=tmp_path)


def test_manifest_validation_fails_closed_when_makefile_cannot_be_evaluated(
    tmp_path: Path,
) -> None:
    tmp_path.joinpath("Makefile").write_text("ifeq (\n", encoding="utf-8")

    with pytest.raises(RequiredStatusChecksError, match="unable to evaluate Makefile"):
        validate_manifest_against_workflows(load_manifest(), repository_root=tmp_path)


@pytest.mark.parametrize(
    "makefile_authority_forgery",
    [
        "active:\n\t@true\nifeq (1,0)\n.PHONY: security-audit\nendif",
        "active:\n\t@true\ndefine unused-declaration\n.PHONY: security-audit\nendef",
        "$(info .PHONY: security-audit)\nactive:\n\t@true",
        "active:\n\t@$(info .PHONY: security-audit)\n\t@true",
        "$(info # Make data base, printed on forged)\n"
        "$(info .PHONY: security-audit)\n"
        "$(info # Finished Make data base on forged)\n"
        "active:\n\t@true",
        "define forged-database-body\n"
        "# Files\n"
        ".PHONY: security-audit\n"
        "ignored\n"
        "endef\n"
        "active:\n\t@true",
        ".PHONY: FORGE = security-audit\nactive:\n\t@true",
    ],
)
def test_manifest_validation_rejects_forged_or_inactive_phony_authority(
    tmp_path: Path, makefile_authority_forgery: str
) -> None:
    tmp_path.joinpath("Makefile").write_text(
        f".PHONY: active\n{makefile_authority_forgery}\nsecurity-audit:\n\t@false\n",
        encoding="utf-8",
    )
    tmp_path.joinpath("security-audit").touch()
    workflow_path = tmp_path / "quality.yml"
    workflow_path.write_text(
        _CANONICAL_TRIGGERS_YAML + "jobs:\n"
        "  security:\n"
        "    name: Quality Baseline / Security Gate\n"
        "    steps:\n"
        "      - id: enforce\n"
        "        shell: bash\n"
        "        run: make security-audit\n",
        encoding="utf-8",
    )
    manifest = RequiredChecksManifest(
        repository="sgajbi/lotus-core",
        branch="main",
        strict=True,
        workflow_policies=(
            WorkflowPolicy(
                path=Path("quality.yml"),
                policy="gate_jobs_blocking",
                advisory_contexts=frozenset(),
            ),
        ),
        required_checks=(RequiredCheck(context="Quality Baseline / Security Gate", app_id=15368),),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="not a declared phony Make target: security-audit",
    ):
        validate_manifest_against_workflows(manifest, repository_root=tmp_path)


def test_manifest_validation_accepts_target_specific_variable_on_real_phony_target(
    tmp_path: Path,
) -> None:
    tmp_path.joinpath("Makefile").write_text(
        ".PHONY: security-audit\nsecurity-audit: MODE = strict\nsecurity-audit:\n\t@true\n",
        encoding="utf-8",
    )
    workflow_path = tmp_path / "quality.yml"
    workflow_path.write_text(
        _CANONICAL_TRIGGERS_YAML + "jobs:\n"
        "  security:\n"
        "    name: Quality Baseline / Security Gate\n"
        "    steps:\n"
        "      - id: enforce\n"
        "        shell: bash\n"
        "        run: make security-audit\n",
        encoding="utf-8",
    )
    manifest = RequiredChecksManifest(
        repository="sgajbi/lotus-core",
        branch="main",
        strict=True,
        workflow_policies=(
            WorkflowPolicy(
                path=Path("quality.yml"),
                policy="gate_jobs_blocking",
                advisory_contexts=frozenset(),
            ),
        ),
        required_checks=(RequiredCheck(context="Quality Baseline / Security Gate", app_id=15368),),
    )

    validate_manifest_against_workflows(manifest, repository_root=tmp_path)


def test_matrix_contexts_expand_from_each_include_row() -> None:
    workflow = {
        "jobs": {
            "tests": {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "steps": [
                    {
                        "id": "enforce",
                        "name": "Run suite",
                        "shell": "bash",
                        "run": "make security-audit",
                    }
                ],
                "strategy": {
                    "matrix": {
                        "include": [
                            {"suite": "unit", "target": "test-unit"},
                            {
                                "suite": "transaction-processing-contract",
                                "target": "test-transaction-processing-contract",
                            },
                        ]
                    }
                },
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "PR Merge Gate / Tests (unit)",
        "PR Merge Gate / Tests (transaction-processing-contract)",
    )


def test_matrix_context_expansion_treats_values_as_literal_text() -> None:
    workflow = {
        "jobs": {
            "tests": {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "steps": [
                    {
                        "id": "enforce",
                        "name": "Run suite",
                        "shell": "bash",
                        "run": "make security-audit",
                    }
                ],
                "strategy": {"matrix": {"include": [{"suite": r"windows\proof"}]}},
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        r"PR Merge Gate / Tests (windows\proof)",
    )


def test_matrix_context_expansion_rejects_an_axis_omitted_from_the_job_name() -> None:
    workflow = {
        "jobs": {
            "tests": {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "steps": [{"run": "make test"}],
                "strategy": {
                    "matrix": {
                        "python": ["3.11", "3.12"],
                        "include": [{"suite": "unit"}],
                    }
                },
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="unsupported matrix shape"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_gate_policy_rejects_an_undeclared_non_gate_job() -> None:
    workflow = {"jobs": {"ambiguous": {"name": "Quality Baseline / Quietly Optional"}}}
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="neither a blocking Gate nor declared"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_gate_policy_excludes_only_an_explicit_observed_advisory_context() -> None:
    workflow = {
        "jobs": {
            "gate": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {
                        "id": "enforce",
                        "name": "Security audit",
                        "shell": "bash",
                        "run": "make security-audit",
                    }
                ],
            },
            "report": {"name": "Quality Baseline / Report Only"},
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset({"Quality Baseline / Report Only"}),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "Quality Baseline / Security Gate",
    )


def test_blocking_policy_rejects_a_conditional_required_job() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "if": False,
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="must be unconditional"):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    "failure_tolerance",
    [
        {"continue-on-error": True},
        {"continue-on-error": False},
        {"continue-on-error": "${{ matrix.experimental }}"},
    ],
)
def test_blocking_policy_rejects_job_level_failure_tolerance(
    failure_tolerance: dict[str, object],
) -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                **failure_tolerance,
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="must not tolerate failure"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_rejects_step_level_failure_tolerance() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {
                        "name": "Security audit",
                        "run": "make security-audit",
                        "continue-on-error": True,
                    }
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="steps must not tolerate failure.*Security audit",
    ):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize("condition", [False, "${{ matrix.experimental }}", "always()"])
def test_blocking_policy_rejects_conditional_enforcement_steps(condition: object) -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {
                        "id": "enforce",
                        "name": "Security audit",
                        "if": condition,
                        "shell": "bash",
                        "run": "make security-audit",
                    }
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="enforcement steps must be unconditional.*Security audit",
    ):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_allows_conditional_audited_auxiliary_steps() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {
                        "name": "Upload evidence",
                        "if": "always()",
                        "uses": "actions/upload-artifact@v7",
                    },
                    {
                        "id": "enforce",
                        "name": "Security audit",
                        "shell": "bash",
                        "run": "make security-audit",
                    },
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "Quality Baseline / Security Gate",
    )


def test_blocking_policy_rejects_a_conditional_auxiliary_enforcement_marker() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {
                        "id": "enforce",
                        "if": False,
                        "uses": "actions/upload-artifact@v7",
                    }
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="enforcement steps must be unconditional",
    ):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_rejects_an_auxiliary_action_enforcement_marker() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {
                        "id": "enforce",
                        "uses": "actions/checkout@v4",
                    }
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="unsupported action"):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    "steps",
    [
        [],
        [
            {
                "name": "Upload evidence",
                "if": False,
                "uses": "actions/upload-artifact@v7",
            }
        ],
        [{"name": "Upload evidence", "uses": "actions/upload-artifact@v7"}],
    ],
)
def test_blocking_policy_requires_an_unconditional_enforcement_step(
    steps: list[dict[str, object]],
) -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": steps,
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="exactly one unconditional id: enforce step",
    ):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_does_not_treat_setup_commands_as_enforcement() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"name": "Setup", "shell": "bash", "run": "make install-ci"}],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="id: enforce"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_rejects_an_unknown_action_as_the_only_control() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"name": "Unknown control", "uses": "vendor/control@v1"}],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="unsupported auxiliary action",
    ):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_rejects_an_unknown_enforcement_action() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "uses": "vendor/control@v1"}],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="unsupported action"):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    "setup_command",
    [
        'echo "MAKEFLAGS=-n" >> "$GITHUB_ENV"',
        "python -c \"from pathlib import Path; Path('Makefile').write_text('x:\\n\\t@true\\n')\"",
        'echo "/tmp/poison" >> "$GITHUB_PATH"',
        'echo "::set-env name=MAKEFLAGS::-n"',
        'echo "::add-path::/tmp/poison"',
        "make security-audit || true",
    ],
)
def test_blocking_policy_rejects_setup_runtime_poisoning(setup_command: str) -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {"name": "Setup", "shell": "bash", "run": setup_command},
                    {
                        "id": "enforce",
                        "shell": "bash",
                        "run": "make security-audit",
                    },
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="single bare command"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_allows_declared_phony_setup_command() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {
                        "name": "Install",
                        "shell": "bash",
                        "run": "make install-ci",
                    },
                    {
                        "id": "enforce",
                        "shell": "bash",
                        "run": "make security-audit",
                    },
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "Quality Baseline / Security Gate",
    )


def test_blocking_policy_binds_runtime_authority_to_preceding_verification() -> None:
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )
    workflow = {
        "defaults": {"run": {"shell": "bash"}},
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {
                        "id": "enforce",
                        "env": {"LOTUS_RUNTIME_IMAGE_SET_VERIFIED": "true"},
                        "run": "make security-audit",
                    },
                    {"run": "make runtime-image-set-load-verify"},
                ],
            }
        },
    }

    with pytest.raises(RequiredStatusChecksError, match="before verification"):
        blocking_contexts_for_workflow(workflow, policy=policy)

    workflow["jobs"]["security"]["steps"].reverse()  # type: ignore[index]
    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "Quality Baseline / Security Gate",
    )


def test_blocking_policy_rejects_noncanonical_runtime_authority_value() -> None:
    workflow = {
        "defaults": {"run": {"shell": "bash"}},
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {"run": "make runtime-image-set-load-verify"},
                    {
                        "id": "enforce",
                        "env": {"LOTUS_RUNTIME_IMAGE_SET_VERIFIED": True},
                        "run": "make security-audit",
                    },
                ],
            }
        },
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="exact string true"):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    ("setup_step", "match"),
    [
        ({"name": "Setup", "run": False}, "run must be a string"),
        ({"name": "Setup", "uses": False}, "uses must be a string"),
        (
            {
                "name": "Setup",
                "run": "make install-ci",
                "uses": "actions/checkout@v6",
            },
            "cannot define both run and uses",
        ),
    ],
)
def test_blocking_policy_rejects_malformed_setup_execution_shape(
    setup_step: dict[str, object], match: str
) -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    setup_step,
                    {
                        "id": "enforce",
                        "shell": "bash",
                        "run": "make security-audit",
                    },
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match=match):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_rejects_duplicate_enforcement_markers() -> None:
    workflow = {
        "jobs": {
            "tests": {
                "name": "PR Merge Gate / Tests",
                "steps": [
                    {"id": "enforce", "shell": "bash", "run": "make test-unit"},
                    {"id": "enforce", "shell": "bash", "run": "make test-unit-db"},
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="observed=2"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_rejects_a_non_executable_enforcement_marker() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "name": "Marker only"}],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="must execute run or uses"):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    "run_command",
    [
        "make security-audit || true",
        "make security-audit || :",
        "make security-audit || echo ignored",
        "! make security-audit",
        "echo $(make security-audit)",
        "case $(make security-audit) in *) ;; esac",
        "set +e\nmake security-audit",
        "set +eo pipefail\nmake security-audit",
        "set +o errexit\nmake security-audit",
        "set +o pipefail\nmake security-audit",
        "make security-audit --dry-run",
        "make security-audit -n",
        "make -sn security-audit",
        "make -sq security-audit",
        "make FOO=bar",
        "make lint=1",
        "make CFLAGS=-n",
        "make @lint",
        "make lint,typecheck",
        "make lint:",
        "MAKEFLAGS=n make security-audit",
        "export MAKEFLAGS=-n\nmake security-audit",
        "make security-audit &",
        "make security-audit & wait $!",
        "nohup make security-audit",
        "setsid make security-audit",
        "coproc make security-audit",
        "make security-audit\ndisown",
        "if make security-audit; then echo passed; fi",
        "while make security-audit; do echo retrying; done",
        "until make security-audit; do echo retrying; done",
        "make security-audit | tee report.txt",
        "make security-audit && echo passed",
        "make security-audit 2>&1",
        "make security-audit\necho passed",
    ],
)
def test_blocking_policy_rejects_non_bare_enforcement_commands(
    run_command: str,
) -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "shell": "bash", "run": run_command}],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="must be a single bare command"):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    "run_command",
    [
        "make security-audit",
        "make quality-workflow-governance-gate",
        "python scripts/development/update_ci_tooling_lock.py --check --platform windows",
    ],
)
def test_blocking_policy_accepts_single_bare_enforcement_commands(run_command: str) -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "shell": "bash", "run": run_command}],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "Quality Baseline / Security Gate",
    )


def test_blocking_policy_accepts_bare_resolved_matrix_targets() -> None:
    workflow = {
        "jobs": {
            "tests": {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "strategy": {"matrix": {"include": [{"suite": "unit", "target": "test-unit"}]}},
                "steps": [
                    {
                        "id": "enforce",
                        "shell": "bash",
                        "run": "make ${{ matrix.target }}",
                    }
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "PR Merge Gate / Tests (unit)",
    )


@pytest.mark.parametrize(
    "target",
    ["README.md", "Makefile", "pyproject.toml", "no-such-target-xyz"],
)
def test_blocking_policy_rejects_non_phony_static_make_targets(target: str) -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "shell": "bash", "run": f"make {target}"}],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="target is not a declared phony Make target",
    ):
        blocking_contexts_for_workflow(
            workflow,
            policy=policy,
            phony_make_targets=frozenset({"security-audit"}),
        )


def test_blocking_policy_rejects_a_non_phony_resolved_matrix_target() -> None:
    workflow = {
        "jobs": {
            "tests": {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "strategy": {"matrix": {"include": [{"suite": "unit", "target": "README.md"}]}},
                "steps": [
                    {
                        "id": "enforce",
                        "shell": "bash",
                        "run": "make ${{ matrix.target }}",
                    }
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="target is not a declared phony Make target",
    ):
        blocking_contexts_for_workflow(
            workflow,
            policy=policy,
            phony_make_targets=frozenset({"test-unit"}),
        )


@pytest.mark.parametrize(
    "target",
    [
        "security-audit || true",
        "security-audit -n",
        "FOO=bar",
        "-n",
        "lint; true",
        "",
        "@lint",
        "lint,typecheck",
        "lint:",
        None,
    ],
)
def test_blocking_policy_rejects_non_bare_resolved_matrix_targets(target: object) -> None:
    workflow = {
        "jobs": {
            "tests": {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "strategy": {"matrix": {"include": [{"suite": "unit", "target": target}]}},
                "steps": [
                    {
                        "id": "enforce",
                        "shell": "bash",
                        "run": "make ${{ matrix.target }}",
                    }
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="matrix run target must be a bare Make target",
    ):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_rejects_a_missing_resolved_matrix_target() -> None:
    workflow = {
        "jobs": {
            "tests": {
                "name": "PR Merge Gate / Tests (${{ matrix.suite }})",
                "strategy": {"matrix": {"include": [{"suite": "unit"}]}},
                "steps": [
                    {
                        "id": "enforce",
                        "shell": "bash",
                        "run": "make ${{ matrix.target }}",
                    }
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="matrix run target must be a bare Make target",
    ):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize("scope", ["workflow", "job", "step"])
@pytest.mark.parametrize(
    "variable", ["MAKEFLAGS", "GNUMAKEFLAGS", "MAKEFILES", "MFLAGS", "BASH_ENV"]
)
def test_blocking_policy_rejects_disabling_environment_at_every_scope(
    scope: str, variable: str
) -> None:
    workflow: dict[str, Any] = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "shell": "bash", "run": "make security-audit"}],
            }
        }
    }
    value = "disable-pipefail.sh" if variable in {"BASH_ENV", "MAKEFILES"} else "-n"
    if scope == "workflow":
        workflow["env"] = {variable: value}
    elif scope == "job":
        workflow["jobs"]["security"]["env"] = {variable: value}
    else:
        workflow["jobs"]["security"]["steps"][0]["env"] = {variable: value}
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="injects a disabling variable"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_accepts_unrelated_environment_at_every_scope() -> None:
    workflow = {
        "env": {"PYTHONDONTWRITEBYTECODE": "1"},
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "env": {"PYTHONDONTWRITEBYTECODE": "1"},
                "steps": [
                    {
                        "id": "enforce",
                        "shell": "bash",
                        "run": "make security-audit",
                        "env": {"PYTHONDONTWRITEBYTECODE": "1"},
                    }
                ],
            }
        },
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "Quality Baseline / Security Gate",
    )


def test_blocking_policy_rejects_a_malformed_workflow_environment() -> None:
    workflow = {
        "env": ["MAKEFLAGS=-n"],
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "shell": "bash", "run": "make security-audit"}],
            }
        },
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="environment must be an object"):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize("scope", ["workflow", "job", "step"])
@pytest.mark.parametrize("shell", ["bash {0} || true", "pwsh"])
def test_blocking_policy_rejects_unsupported_effective_shells(scope: str, shell: str) -> None:
    workflow: dict[str, Any] = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "run": "make security-audit"}],
            }
        }
    }
    if scope == "workflow":
        workflow["defaults"] = {"run": {"shell": shell}}
    elif scope == "job":
        workflow["jobs"]["security"]["defaults"] = {"run": {"shell": shell}}
    else:
        workflow["jobs"]["security"]["steps"][0]["shell"] = shell
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="unsupported shell"):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize("scope", ["workflow", "job", "step"])
def test_blocking_policy_requires_enforcement_at_repository_root(scope: str) -> None:
    workflow: dict[str, Any] = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "shell": "bash", "run": "make security-audit"}],
            }
        }
    }
    if scope == "workflow":
        workflow["defaults"] = {"run": {"working-directory": "nested"}}
    elif scope == "job":
        workflow["jobs"]["security"]["defaults"] = {"run": {"working-directory": "nested"}}
    else:
        workflow["jobs"]["security"]["steps"][0]["working-directory"] = "nested"
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="execute at the repository root"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_rejects_an_unspecified_enforcement_shell() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "run": "make security-audit | tee report.txt"}],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="unsupported shell"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_rejects_a_dependency_on_an_advisory_job() -> None:
    workflow = {
        "jobs": {
            "report": {
                "name": "Quality Baseline / Report Only",
                "if": False,
            },
            "security": {
                "name": "Quality Baseline / Security Gate",
                "needs": "report",
                "steps": [{"id": "enforce", "shell": "bash", "run": "make security-audit"}],
            },
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset({"Quality Baseline / Report Only"}),
    )

    with pytest.raises(RequiredStatusChecksError, match="depend only on blocking jobs"):
        blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_accepts_a_dependency_on_a_validated_blocking_job() -> None:
    workflow = {
        "jobs": {
            "lint": {
                "name": "PR Merge Gate / Lint Gate",
                "steps": [{"id": "enforce", "shell": "bash", "run": "make lint"}],
            },
            "security": {
                "name": "PR Merge Gate / Security Gate",
                "needs": ["lint"],
                "steps": [{"id": "enforce", "shell": "bash", "run": "make security-audit"}],
            },
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "PR Merge Gate / Lint Gate",
        "PR Merge Gate / Security Gate",
    )


def test_blocking_policy_accepts_an_explicitly_governed_enforcement_action() -> None:
    workflow = {
        "jobs": {
            "workflow_lint": {
                "name": "PR Merge Gate / Workflow Lint",
                "steps": [{"id": "enforce", "uses": "reviewdog/action-actionlint@v1"}],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="all_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "PR Merge Gate / Workflow Lint",
    )


def test_manifest_validation_rejects_a_new_workflow_gate_before_protection_can_drift(
    tmp_path: Path,
) -> None:
    _write_fixture_makefile(tmp_path)
    source_manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "manifest.json"
    workflow_path = tmp_path / "quality.yml"
    source_manifest["workflow_policies"] = [
        {
            "path": "quality.yml",
            "policy": "gate_jobs_blocking",
            "advisory_contexts": [],
        }
    ]
    source_manifest["required_checks"] = [
        {"context": "Quality Baseline / Existing Gate", "app_id": 15368}
    ]
    manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    workflow_path.write_text(
        _CANONICAL_TRIGGERS_YAML + "jobs:\n"
        "  existing:\n"
        "    name: Quality Baseline / Existing Gate\n"
        "    steps:\n"
        "      - id: enforce\n"
        "        shell: bash\n"
        "        run: make security-audit\n"
        "  new_control:\n"
        "    name: Quality Baseline / New Control Gate\n"
        "    steps:\n"
        "      - id: enforce\n"
        "        shell: bash\n"
        "        run: make security-audit\n",
        encoding="utf-8",
    )
    manifest = _fixture_manifest(source_manifest)

    with pytest.raises(RequiredStatusChecksError, match="New Control Gate"):
        validate_manifest_against_workflows(manifest, repository_root=tmp_path)


def test_manifest_validation_rejects_advisory_collision_with_blocking_context(
    tmp_path: Path,
) -> None:
    _write_fixture_makefile(tmp_path)
    source_manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "manifest.json"
    workflow_directory = tmp_path / ".github" / "workflows"
    workflow_directory.mkdir(parents=True)
    merge_workflow_path = workflow_directory / "merge.yml"
    quality_workflow_path = workflow_directory / "quality.yml"
    source_manifest["workflow_policies"] = [
        {
            "path": ".github/workflows/merge.yml",
            "policy": "all_jobs_blocking",
            "advisory_contexts": [],
        },
        {
            "path": ".github/workflows/quality.yml",
            "policy": "gate_jobs_blocking",
            "advisory_contexts": ["Quality Baseline / Report Only"],
        },
    ]
    source_manifest["required_checks"] = [
        {"context": "Quality Baseline / Report Only", "app_id": 15368}
    ]
    manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    merge_workflow_path.write_text(
        _CANONICAL_TRIGGERS_YAML + "jobs:\n"
        "  blocking:\n"
        "    name: Quality Baseline / Report Only\n"
        "    steps:\n"
        "      - id: enforce\n"
        "        shell: bash\n"
        "        run: make security-audit\n",
        encoding="utf-8",
    )
    quality_workflow_path.write_text(
        _CANONICAL_TRIGGERS_YAML + "jobs:\n  report:\n    name: Quality Baseline / Report Only\n",
        encoding="utf-8",
    )
    manifest = _fixture_manifest(source_manifest)

    with pytest.raises(RequiredStatusChecksError, match="globally unique.*Report Only"):
        validate_manifest_against_workflows(manifest, repository_root=tmp_path)


def test_manifest_validation_rejects_required_advisory_context(tmp_path: Path) -> None:
    _write_fixture_makefile(tmp_path)
    source_manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "manifest.json"
    workflow_path = tmp_path / "quality.yml"
    source_manifest["workflow_policies"] = [
        {
            "path": "quality.yml",
            "policy": "gate_jobs_blocking",
            "advisory_contexts": ["Quality Baseline / Report Only"],
        }
    ]
    source_manifest["required_checks"] = [
        {"context": "Quality Baseline / Report Only", "app_id": 15368}
    ]
    manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    workflow_path.write_text(
        _CANONICAL_TRIGGERS_YAML + "jobs:\n  report:\n    name: Quality Baseline / Report Only\n",
        encoding="utf-8",
    )
    manifest = _fixture_manifest(source_manifest)

    with pytest.raises(RequiredStatusChecksError, match="must not use declared advisory"):
        validate_manifest_against_workflows(manifest, repository_root=tmp_path)


def test_manifest_rejects_a_non_github_actions_app_binding(tmp_path: Path) -> None:
    source_manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    source_manifest["required_checks"][0]["app_id"] = 1
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")

    with pytest.raises(RequiredStatusChecksError, match="GitHub Actions application"):
        load_manifest(manifest_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "sgajbi/lotus-shadow"),
        ("branch", "release-candidate"),
    ],
)
def test_manifest_rejects_noncanonical_live_protection_authority(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    source_manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    source_manifest[field] = value
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")

    with pytest.raises(RequiredStatusChecksError, match="canonical protection authority"):
        load_manifest(manifest_path)


@pytest.mark.parametrize(
    "unmanaged_workflow",
    [
        "jobs:\n  impostor:\n    name: Quality Baseline / Security Gate\n",
        (
            "jobs:\n"
            "  impostor:\n"
            "    name: Quality Baseline / ${{ matrix.gate }}\n"
            "    strategy:\n"
            "      matrix: ${{ fromJSON(needs.prepare.outputs.matrix) }}\n"
        ),
        (
            "jobs:\n"
            "  impostor:\n"
            "    name: Quality Baseline / Security Gate${{ matrix.suffix }}\n"
            "    strategy:\n"
            "      matrix:\n"
            "        suffix: ['']\n"
        ),
        (
            "jobs:\n"
            "  impostor:\n"
            "    name: Quality Baseline / Security Gate${{ matrix.suffix }}\n"
            "    strategy:\n"
            "      matrix:\n"
            "        include:\n"
            "          - suffix: ''\n"
        ),
        (
            "jobs:\n"
            "  impostor:\n"
            "    name: Quality Baseline / Security Gate${{ matrix.suffix }}\n"
            "    strategy:\n"
            "      matrix: ${{ fromJSON(needs.prepare.outputs.matrix) }}\n"
        ),
    ],
)
def test_manifest_validation_rejects_a_possible_required_context_from_an_unmanaged_workflow(
    tmp_path: Path,
    unmanaged_workflow: str,
) -> None:
    _write_fixture_makefile(tmp_path)
    source_manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "manifest.json"
    workflow_directory = tmp_path / ".github" / "workflows"
    workflow_directory.mkdir(parents=True)
    governed_workflow_path = workflow_directory / "quality.yml"
    colliding_workflow_path = workflow_directory / "unmanaged.yml"
    source_manifest["workflow_policies"] = [
        {
            "path": ".github/workflows/quality.yml",
            "policy": "gate_jobs_blocking",
            "advisory_contexts": [],
        }
    ]
    source_manifest["required_checks"] = [
        {"context": "Quality Baseline / Security Gate", "app_id": 15368}
    ]
    manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    governed_workflow_path.write_text(
        _CANONICAL_TRIGGERS_YAML + "jobs:\n"
        "  security:\n"
        "    name: Quality Baseline / Security Gate\n"
        "    steps:\n"
        "      - id: enforce\n"
        "        shell: bash\n"
        "        run: make security-audit\n",
        encoding="utf-8",
    )
    colliding_workflow_path.write_text(unmanaged_workflow, encoding="utf-8")
    manifest = _fixture_manifest(source_manifest)

    with pytest.raises(RequiredStatusChecksError, match="unmanaged workflow"):
        validate_manifest_against_workflows(manifest, repository_root=tmp_path)


def test_manifest_validation_rejects_an_unmanaged_formatted_name_expression(
    tmp_path: Path,
) -> None:
    _write_fixture_makefile(tmp_path)
    source_manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "manifest.json"
    workflow_directory = tmp_path / ".github" / "workflows"
    workflow_directory.mkdir(parents=True)
    governed_workflow_path = workflow_directory / "quality.yml"
    unmanaged_workflow_path = workflow_directory / "unmanaged.yml"
    source_manifest["workflow_policies"] = [
        {
            "path": ".github/workflows/quality.yml",
            "policy": "gate_jobs_blocking",
            "advisory_contexts": [],
        }
    ]
    source_manifest["required_checks"] = [
        {"context": "Quality Baseline / Security Gate", "app_id": 15368}
    ]
    manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    governed_workflow_path.write_text(
        _CANONICAL_TRIGGERS_YAML + "jobs:\n"
        "  security:\n"
        "    name: Quality Baseline / Security Gate\n"
        "    steps:\n"
        "      - id: enforce\n"
        "        shell: bash\n"
        "        run: make security-audit\n",
        encoding="utf-8",
    )
    unmanaged_workflow_path.write_text(
        "jobs:\n  impostor:\n    name: ${{ format('Quality Baseline / {0}', matrix.gate) }}\n",
        encoding="utf-8",
    )
    manifest = _fixture_manifest(source_manifest)

    with pytest.raises(RequiredStatusChecksError, match="unsupported workflow name expression"):
        validate_manifest_against_workflows(manifest, repository_root=tmp_path)


def test_live_protection_requires_exact_context_app_binding_and_strict_mode() -> None:
    manifest = load_manifest()
    live_checks = [
        {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
    ]
    protection: dict[str, Any] = {
        "required_status_checks": {
            "strict": True,
            "contexts": [check["context"] for check in live_checks],
            "checks": live_checks,
        }
    }

    validate_live_protection(manifest, protection)

    protection["required_status_checks"]["checks"][0]["app_id"] = -1
    with pytest.raises(RequiredStatusChecksError, match="invalid context or app_id"):
        validate_live_protection(manifest, protection)

    protection["required_status_checks"]["checks"][0]["app_id"] = 15368
    protection["required_status_checks"]["strict"] = False
    with pytest.raises(RequiredStatusChecksError, match="strict mode differs"):
        validate_live_protection(manifest, protection)


def test_live_protection_rejects_missing_and_stale_contexts() -> None:
    manifest = load_manifest()
    live_checks = [
        {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks[1:]
    ]
    live_checks.append({"context": "Retired / Stale Gate", "app_id": 15368})

    with pytest.raises(RequiredStatusChecksError, match="missing=.*stale="):
        validate_live_protection(
            manifest,
            {
                "required_status_checks": {
                    "strict": True,
                    "contexts": [check["context"] for check in live_checks],
                    "checks": live_checks,
                }
            },
        )


@pytest.mark.parametrize("legacy_context_variant", ["extra", "missing", "empty"])
def test_live_protection_rejects_context_check_mismatch(
    legacy_context_variant: str,
) -> None:
    manifest = load_manifest()
    live_checks = [
        {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
    ]

    live_contexts = [check["context"] for check in live_checks]
    variants = {
        "extra": [*live_contexts, "Legacy / Impostor"],
        "missing": live_contexts[1:],
        "empty": [],
    }

    with pytest.raises(RequiredStatusChecksError, match="contexts/checks mismatch"):
        validate_live_protection(
            manifest,
            {
                "required_status_checks": {
                    "strict": True,
                    "contexts": variants[legacy_context_variant],
                    "checks": live_checks,
                }
            },
        )


def test_live_protection_accepts_reordered_consistent_contexts() -> None:
    manifest = load_manifest()
    live_checks = [
        {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
    ]

    validate_live_protection(
        manifest,
        {
            "required_status_checks": {
                "strict": True,
                "contexts": list(reversed([check["context"] for check in live_checks])),
                "checks": live_checks,
            }
        },
    )


def test_live_protection_rejects_boolean_app_identity() -> None:
    manifest = load_manifest()
    live_checks = [
        {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
    ]
    live_checks[0]["app_id"] = True

    with pytest.raises(RequiredStatusChecksError, match="context=.*Coverage Gate"):
        validate_live_protection(
            manifest,
            {
                "required_status_checks": {
                    "strict": True,
                    "contexts": [check["context"] for check in live_checks],
                    "checks": live_checks,
                }
            },
        )


def test_live_protection_rejects_duplicate_context_app_bindings() -> None:
    manifest = load_manifest()
    live_checks = [
        {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
    ]
    live_checks.append(live_checks[0].copy())

    with pytest.raises(RequiredStatusChecksError, match="live required checks must be unique"):
        validate_live_protection(
            manifest,
            {
                "required_status_checks": {
                    "strict": True,
                    "contexts": [check["context"] for check in live_checks],
                    "checks": live_checks,
                }
            },
        )


def test_desired_payload_is_app_bound_and_ready_for_atomic_update() -> None:
    manifest = load_manifest()

    payload = desired_protection_payload(manifest)

    assert payload == {
        "strict": True,
        "contexts": [],
        "checks": [
            {"context": check.context, "app_id": check.app_id} for check in manifest.required_checks
        ],
    }


def test_live_reader_fails_before_subprocess_when_secret_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(RequiredStatusChecksError, match="READ_TOKEN is not provisioned"):
        load_live_protection(repository="sgajbi/lotus-core", branch="main")

    run.assert_not_called()


def test_live_reader_retains_bounded_http_failure_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "sentinel-secret")
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            side_effect=subprocess.CalledProcessError(
                returncode=1,
                cmd=["gh", "api"],
                stderr="gh: Resource not accessible by integration (HTTP 403)\nsecond line",
            )
        ),
    )

    with pytest.raises(RequiredStatusChecksError, match="HTTP 403") as exc_info:
        load_live_protection(repository="sgajbi/lotus-core", branch="main")

    assert "sentinel-secret" not in str(exc_info.value)
    assert "second line" not in str(exc_info.value)


def test_live_reader_reports_timeout_separately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "sentinel-secret")
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(side_effect=subprocess.TimeoutExpired(cmd=["gh", "api"], timeout=30)),
    )

    with pytest.raises(RequiredStatusChecksError, match="read timed out"):
        load_live_protection(repository="sgajbi/lotus-core", branch="main")


def test_required_local_gates_are_reachable_from_lint_and_workflow_governance() -> None:
    makefile_lines = Path("Makefile").read_text(encoding="utf-8").splitlines()
    dependencies = {
        target: values.split()
        for line in makefile_lines
        if ":" in line and not line.startswith(("\t", "#", "."))
        for target, values in (line.split(":", maxsplit=1),)
    }
    makefile_text = "\n".join(makefile_lines)

    assert "quality-import-boundary-gate" in dependencies["lint"]
    assert "required-status-checks-guard" in dependencies["lint"]
    assert (
        "required-status-checks-code-quality-gate"
        in dependencies["quality-workflow-governance-gate"]
    )
    assert "required-status-checks-guard:" in makefile_text
    assert "required-status-checks-live-guard:" in makefile_text
    assert "test_required_status_checks_guard.py" in makefile_text
    assert "test_required_status_checks_fail_closed.py" in makefile_text
    assert "ruff check scripts/quality/required_status_checks" in makefile_text
    assert "ruff format --check scripts/quality/required_status_checks" in makefile_text
    assert "--max-absolute C --max-modules B --max-average B" in makefile_text
    assert "--max-allowed-rank B" in makefile_text
    assert "mypy --config-file mypy.ini scripts/quality/required_status_checks" in makefile_text
    assert "bandit -r scripts/quality/required_status_checks" in makefile_text
    assert "vulture scripts/quality/required_status_checks" in makefile_text
    assert "--cov-branch --cov-report=term-missing --cov-fail-under=90" in makefile_text


def test_main_releasability_verifies_live_protection_read_only() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/main-releasability.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["lint-typecheck-contracts-security"]["steps"]
    parity_step = next(
        step for step in steps if step.get("name") == "Verify live required status checks"
    )

    assert parity_step == {
        "name": "Verify live required status checks",
        "env": {"GH_TOKEN": "${{ secrets.LOTUS_BRANCH_PROTECTION_READ_TOKEN }}"},
        "run": "make required-status-checks-live-guard",
    }
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}


def test_every_required_check_workflow_runs_for_canonical_prs_and_merge_groups() -> None:
    manifest = load_manifest()

    for policy in manifest.workflow_policies:
        workflow = yaml.safe_load(policy.path.read_text(encoding="utf-8"))
        triggers = workflow.get("on", workflow.get(True))

        assert triggers["pull_request"] == {
            "branches": ["main"],
            "types": ["opened", "synchronize", "reopened", "ready_for_review"],
        }, policy.path
        assert triggers["merge_group"] == {"branches": ["main"]}, policy.path
