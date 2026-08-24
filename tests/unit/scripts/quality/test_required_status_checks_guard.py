from __future__ import annotations

import copy
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
    desired_protection_payload,
    load_live_protection,
    load_manifest,
    validate_live_protection,
    validate_manifest_against_workflows,
)
from scripts.quality.required_status_checks import (
    blocking_contexts_for_workflow as _blocking_contexts_for_workflow,
)
from scripts.quality.required_status_checks import workflow as required_checks_workflow

_CANONICAL_TRIGGERS_YAML = (
    "on:\n"
    "  pull_request:\n"
    "    branches: [main]\n"
    "    types: [opened, synchronize, reopened, ready_for_review]\n"
    "  merge_group:\n"
    "    branches: [main]\n"
)


def blocking_contexts_for_workflow(
    workflow: dict[str, Any],
    *,
    policy: WorkflowPolicy,
    phony_make_targets: frozenset[str] | None = None,
) -> tuple[str, ...]:
    """Supply the audited default runner for focused fixtures not exercising job shape."""

    normalized = copy.deepcopy(workflow)
    jobs = normalized.get("jobs")
    if isinstance(jobs, dict):
        for job in jobs.values():
            if isinstance(job, dict):
                job.setdefault("runs-on", "ubuntu-latest")
    return _blocking_contexts_for_workflow(
        normalized,
        policy=policy,
        phony_make_targets=phony_make_targets,
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
    tmp_path.joinpath("Makefile").write_text(
        ".PHONY: lint\nlint:\nthis is not a recipe\n",
        encoding="utf-8",
    )

    with pytest.raises(RequiredStatusChecksError, match="unable to evaluate Makefile"):
        validate_manifest_against_workflows(load_manifest(), repository_root=tmp_path)


@pytest.mark.parametrize(
    ("makefile_authority_forgery", "error"),
    [
        (
            "active:\n\t@true\nifeq (1,0)\n.PHONY: security-audit\nendif",
            "Makefile phony authority must be static",
        ),
        (
            "active:\n\t@true\ndefine unused-declaration\n.PHONY: security-audit\nendef",
            "not a declared phony Make target",
        ),
        (
            "$(info .PHONY: security-audit)\nactive:\n\t@true",
            "not a declared phony Make target",
        ),
        (
            "$(info MAKEFLAGS=-n)\nactive:\n\t@true",
            "not a declared phony Make target",
        ),
        (
            "active:\n\t@$(info .PHONY: security-audit)\n\t@true",
            "not a declared phony Make target",
        ),
        (
            "$(info # Make data base, printed on forged)\n"
            "$(info .PHONY: security-audit)\n"
            "$(info # Finished Make data base on forged)\n"
            "active:\n\t@true",
            "not a declared phony Make target",
        ),
        (
            "define forged-database-body\n"
            "# Files\n"
            ".PHONY: security-audit\n"
            "ignored\n"
            "endef\n"
            "active:\n\t@true",
            "not a declared phony Make target",
        ),
        (
            "define environment-activated-authority\n"
            ".PHONY: security-audit\n"
            "endef\n"
            "$(if $(filter C,$(LC_ALL)),$(eval $(environment-activated-authority)))\n"
            "active:\n\t@true",
            "Makefile phony authority must be static",
        ),
        (
            ".PHONY: FORGE = security-audit\nactive:\n\t@true",
            "Makefile phony authority must be static",
        ),
    ],
)
def test_manifest_validation_rejects_forged_or_inactive_phony_authority(
    tmp_path: Path,
    makefile_authority_forgery: str,
    error: str,
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
        "    runs-on: ubuntu-latest\n"
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
        match=error,
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
        "    runs-on: ubuntu-latest\n"
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


@pytest.mark.parametrize(
    "unsafe_authority",
    [
        "ifneq ($(MAKELEVEL),0)\n.PHONY: security-audit\nendif",
        "ifneq ($(DEMO_DATA_PACK_INGEST_ONLY),true)\n.PHONY: security-audit\nendif",
        "include phony-authority.mk\n.PHONY: security-audit",
        "-include phony-authority.mk\n.PHONY: security-audit",
        "sinclude phony-authority.mk\n.PHONY: security-audit",
        "TARGETS := security-audit\n.PHONY: $(TARGETS)",
        "TARGETS := security-audit\n.PHONY: ${TARGETS}",
        ".PHONY: security-audit \\",
        "define BODY\n"
        "dummy:\n"
        "\tendef\n"
        ".PHONY: security-audit\n"
        "endef\n"
        "$(if $(filter C,$(LC_ALL)),$(eval $(BODY)))",
        "define BODY\n.PHONY: security-audit\nendef\n${eval ${BODY}}",
        "X := $(call eval,.IGNORE: security-audit)",
        "X := ${call eval,.IGNORE: security-audit}",
        "FUNCTION := eval\nX := $(call $(FUNCTION),.IGNORE: security-audit)",
    ],
)
def test_blocking_policy_rejects_non_static_phony_authority(
    tmp_path: Path,
    unsafe_authority: str,
) -> None:
    tmp_path.joinpath("Makefile").write_text(
        f"{unsafe_authority}\nsecurity-audit:\n\t@false\n",
        encoding="utf-8",
    )
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "runs-on": "ubuntu-latest",
                "steps": [
                    {
                        "id": "enforce",
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
        match="Makefile phony authority must be static: .*line=",
    ):
        _blocking_contexts_for_workflow(
            workflow,
            policy=policy,
            makefile_path=tmp_path / "Makefile",
        )


@pytest.mark.parametrize(
    "authority_function",
    [
        "$(eval SHELL:=/bin/true)",
        "${eval SHELL:=/bin/true}",
        "$(call eval,SHELL:=/bin/true)",
        "$(eval\\\n\tSHELL:=/bin/true)",
        "${eval\\\n\tSHELL:=/bin/true}",
        "$(call\\\n\teval,SHELL:=/bin/true)",
    ],
)
def test_make_authority_rejects_execution_state_functions_in_recipes(
    tmp_path: Path,
    authority_function: str,
) -> None:
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        f".PHONY: security-audit\nsecurity-audit:\n\t{authority_function}\n\t@false\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="Makefile phony authority must be static: .*line=3",
    ):
        required_checks_workflow._load_phony_make_targets(makefile_path)


def test_make_authority_rejects_a_continued_authority_function_at_eof(
    tmp_path: Path,
) -> None:
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        ".PHONY: security-audit\nsecurity-audit:\n\t$(eval SHELL:=/bin/true); false \\",
        encoding="utf-8",
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="Makefile phony authority must be static: .*line=3",
    ):
        required_checks_workflow._load_phony_make_targets(makefile_path)


@pytest.mark.parametrize(
    "recipe",
    ["-false", "@-false", "-@false", "+-false", "- false", "@\t-false", "\t-false"],
)
def test_make_authority_rejects_ignored_recipe_errors(
    tmp_path: Path,
    recipe: str,
) -> None:
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        f".PHONY: security-audit\nsecurity-audit:\n\t{recipe}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="Makefile execution state must be static: .*line=3",
    ):
        required_checks_workflow._load_phony_make_targets(makefile_path)


@pytest.mark.parametrize("continuation_indent", ["\t", "  "])
def test_make_authority_accepts_hyphenated_recipe_continuation_arguments(
    tmp_path: Path,
    continuation_indent: str,
) -> None:
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        ".PHONY: security-audit\n"
        "security-audit:\n"
        "\t@printf '%s\\n' command \\\n"
        f"{continuation_indent}--candidate-release-manifest\n",
        encoding="utf-8",
    )

    assert required_checks_workflow._load_phony_make_targets(makefile_path) == frozenset(
        {"security-audit"}
    )


def test_make_authority_accepts_a_fail_propagating_recipe(tmp_path: Path) -> None:
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        ".PHONY: security-audit\nsecurity-audit:\n\t@false\n",
        encoding="utf-8",
    )

    assert required_checks_workflow._load_phony_make_targets(makefile_path) == frozenset(
        {"security-audit"}
    )
    result = subprocess.run(  # noqa: S603
        ("make", "--file", str(makefile_path), "security-audit"),
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 2


@pytest.mark.parametrize(
    "execution_state",
    [
        ".RECIPEPREFIX := $(if $(PYTHON_VERSION),.,)",
        ".SHELLFLAGS := -c",
        "GNUMAKEFLAGS += -n",
        "MAKE := /bin/true",
        "MAKEFILES ?= alternate.mk",
        "MAKEFLAGS += -n",
        "SHELL := /bin/true",
        "VPATH = shadow",
        "define SHELL\n/bin/true\nendef",
        "define SHELL :=\n/bin/true\nendef",
        "override define MAKEFLAGS\n-n\nendef",
        "$(strip SHELL\\\n) := /bin/true",
        "security-audit: private .SHELLFLAGS ::= -c",
        ".DEFAULT:",
        ".EXPORT_ALL_VARIABLES:",
        ".IGNORE:",
        "dummy .IGNORE: security-audit",
        ".ONESHELL:",
        ".POSIX:",
        ".SILENT:",
        "vpath %.py shadow",
    ],
)
def test_blocking_policy_rejects_mutable_make_execution_state(
    tmp_path: Path,
    execution_state: str,
) -> None:
    tmp_path.joinpath("Makefile").write_text(
        f"{execution_state}\n.PHONY: security-audit\nsecurity-audit:\n\t@false\n",
        encoding="utf-8",
    )
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "runs-on": "ubuntu-latest",
                "steps": [
                    {
                        "id": "enforce",
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
        match="Makefile execution state must be static: .*line=1",
    ):
        _blocking_contexts_for_workflow(
            workflow,
            policy=policy,
            makefile_path=tmp_path / "Makefile",
        )


@pytest.mark.parametrize(
    "computed_state",
    [
        "S = SHELL\n$S := /bin/true",
        "S = SHELL\n$(S) := /bin/true",
        "S = SHELL\n${S} := /bin/true",
        "S = SHELL\nsecurity-audit: $S := /bin/true",
        "I = .IGNORE\n$I: security-audit",
        "I = .IGNORE\n$(I): security-audit",
        "I = .IGNORE\n${I}: security-audit",
        "X = .IGNORE: security-audit\n$X",
        "X = .IGNORE: security-audit\n$(X)",
        "X = .IGNORE: security-audit\n${X}",
        "X = .IGNORE: security-audit\n$(strip $(X))",
        "X := .IGNORE: security-audit\ndummy $X",
        "X := .IGNORE: security-audit\ndummy $(X)",
        "X := .IGNORE: security-audit\ndummy ${X}",
        "X := .IGNORE: security-audit\ndummy $(strip $(X))",
        "S = SHELL\ndefine $S\n/bin/true\nendef",
    ],
)
def test_blocking_policy_rejects_computed_make_execution_state_names(
    tmp_path: Path,
    computed_state: str,
) -> None:
    tmp_path.joinpath("Makefile").write_text(
        f"{computed_state}\n.PHONY: security-audit\nsecurity-audit:\n\t@false\n",
        encoding="utf-8",
    )
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "runs-on": "ubuntu-latest",
                "steps": [
                    {
                        "id": "enforce",
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
        match="Makefile execution state must be static: .*line=2",
    ):
        _blocking_contexts_for_workflow(
            workflow,
            policy=policy,
            makefile_path=tmp_path / "Makefile",
        )


def test_make_authority_keeps_tab_indented_endef_inside_define_body(
    tmp_path: Path,
) -> None:
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        "define BODY\n"
        "dummy:\n"
        "\tendef\n"
        ".PHONY: security-audit\n"
        "endef\n"
        ".PHONY: active\n"
        "active:\n\t@true\n",
        encoding="utf-8",
    )

    assert required_checks_workflow._load_phony_make_targets(makefile_path) == frozenset({"active"})


@pytest.mark.parametrize(
    "rule",
    [
        "security-audit: $(DEPS) # documented=x\n\t@true",
        'security-audit: $(DEPS); printf "key=value"',
    ],
)
def test_make_authority_ignores_assignment_tokens_after_rule_boundaries(
    tmp_path: Path,
    rule: str,
) -> None:
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        f"DEPS =\n.PHONY: security-audit\n{rule}\n",
        encoding="utf-8",
    )

    assert required_checks_workflow._load_phony_make_targets(makefile_path) == frozenset(
        {"security-audit"}
    )


@pytest.mark.parametrize(
    "static_declaration",
    [
        "VALUE := $(shell echo safe)",
        "security-audit: VALUE := $(strip safe)",
    ],
)
def test_make_authority_accepts_expansions_after_static_declaration_separators(
    tmp_path: Path,
    static_declaration: str,
) -> None:
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        f"{static_declaration}\n.PHONY: security-audit\nsecurity-audit:\n\t@true\n",
        encoding="utf-8",
    )

    assert required_checks_workflow._load_phony_make_targets(makefile_path) == frozenset(
        {"security-audit"}
    )


def test_make_authority_evaluation_uses_only_fixed_minimal_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_fixture_makefile(tmp_path)
    observed_environments: list[dict[str, str]] = []
    real_run = required_checks_workflow.subprocess.run

    def record_environment(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed_environments.append(dict(kwargs["env"]))
        return real_run(*args, **kwargs)

    monkeypatch.setenv("MAKELEVEL", "1")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(required_checks_workflow.subprocess, "run", record_environment)

    required_checks_workflow._load_phony_make_targets(tmp_path / "Makefile")

    assert len(observed_environments) == 1
    assert set(observed_environments[0]) == {"LC_ALL", "PATH"}
    assert observed_environments[0]["LC_ALL"] == "C"


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
                        "with": {"name": "evidence", "path": "output/evidence.json"},
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

    with pytest.raises(RequiredStatusChecksError, match="unaudited action reference"):
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
                "with": {"name": "evidence", "path": "output/evidence.json"},
            }
        ],
        [
            {
                "name": "Upload evidence",
                "uses": "actions/upload-artifact@v7",
                "with": {"name": "evidence", "path": "output/evidence.json"},
            }
        ],
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
        match="unaudited action reference",
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

    with pytest.raises(RequiredStatusChecksError, match="unaudited action reference"):
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


def test_blocking_policy_rejects_workflow_asserted_runtime_image_authority() -> None:
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
                ],
            }
        },
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match="environment key is not admitted.*LOTUS_RUNTIME_IMAGE_SET_VERIFIED",
    ):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    ("action", "inputs", "match"),
    [
        (
            "actions/checkout@v6",
            {"repository": "someone/other", "path": "other"},
            "alternate checkout",
        ),
        ("actions/checkout@v6", {"ref": "unreviewed"}, "unsupported with keys"),
        (
            "actions/download-artifact@v8",
            {"name": "runtime", "path": "."},
            "stay under output",
        ),
        (
            "actions/download-artifact@v8",
            {"name": "runtime", "path": "output/${{ '..' }}"},
            "must not contain expressions",
        ),
        (
            "actions/upload-artifact@v7",
            {"name": "evidence", "path": "output/${{ github.sha }}"},
            "must not contain expressions",
        ),
        (
            "actions/cache@v5",
            {"key": "poison", "path": "Makefile"},
            "cache path is not audited",
        ),
        (
            "actions/setup-python@v6",
            {"python-version": "${{ matrix.python }}"},
            "version is not audited",
        ),
        (
            "actions/upload-artifact@v7",
            {"name": "evidence", "path": "Makefile"},
            "stay under output",
        ),
        ("actions/checkout@v6", {"fetch-depth": 1}, "fetch-depth must be 0"),
        (
            "actions/checkout@v6",
            {"persist-credentials": True},
            "persist-credentials must be false",
        ),
        ("actions/checkout@v6", {"path": "nested"}, "path requires repository"),
        (
            "actions/cache@v5",
            {"key": "", "path": ".buildx-cache"},
            "cache key must be non-empty",
        ),
        (
            "actions/cache@v5",
            {"key": "key", "path": ".buildx-cache", "restore-keys": ""},
            "restore-keys must be non-empty",
        ),
        (
            "actions/download-artifact@v8",
            {"name": "runtime", "path": "output/runtime", "pattern": ""},
            "pattern must be non-empty",
        ),
        (
            "actions/download-artifact@v8",
            {"name": "runtime", "path": "output/runtime", "merge-multiple": "yes"},
            "merge-multiple must be boolean",
        ),
        (
            "actions/upload-artifact@v7",
            {"name": "", "path": "output/evidence"},
            "name must be one non-empty line",
        ),
        (
            "actions/upload-artifact@v7",
            {"name": "evidence", "path": "", "retention-days": 14},
            "path must be non-empty",
        ),
        (
            "actions/upload-artifact@v7",
            {"name": "evidence", "path": "output/evidence", "if-no-files-found": "pass"},
            "if-no-files-found value is not audited",
        ),
        (
            "actions/upload-artifact@v7",
            {"name": "evidence", "path": "output/evidence", "retention-days": 0},
            "retention-days must be between 1 and 30",
        ),
        (
            "actions/upload-artifact@v7",
            {"name": "evidence", "path": "output/evidence", "compression-level": 10},
            "compression-level must be between 0 and 9",
        ),
        (
            "actions/setup-python@v6",
            {"python-version": "${{ env.PYTHON_VERSION }}", "cache": "npm"},
            "setup-python cache must be pip",
        ),
        (
            "actions/setup-node@v6",
            {
                "node-version": "20",
                "cache": "npm",
                "cache-dependency-path": "tools/api_governance/package-lock.json",
            },
            "setup-node version is not audited",
        ),
        (
            "actions/setup-node@v6",
            {"node-version": "${{ env.NODE_VERSION }}", "cache": "pip"},
            "setup-node cache inputs are not audited",
        ),
        ("actions/checkout@v6", [], "with must be an object"),
        ("actions/checkout@v6", {1: "value"}, "with keys must be strings"),
    ],
)
def test_blocking_policy_rejects_unsafe_action_inputs(
    action: str, inputs: object, match: str
) -> None:
    workflow = {
        "defaults": {"run": {"shell": "bash"}},
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {"name": "Setup", "uses": action, "with": inputs},
                    {"id": "enforce", "run": "make security-audit"},
                ],
            }
        },
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match=match):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    ("runner", "python_version", "accepted"),
    [
        ("ubuntu-latest", "${{ env.PYTHON_VERSION }}", True),
        ("ubuntu-latest", "3.11", False),
        ("windows-latest", "3.11", True),
        ("windows-latest", "${{ env.PYTHON_VERSION }}", False),
    ],
)
def test_blocking_policy_pins_setup_python_version_to_runner(
    runner: str,
    python_version: str,
    accepted: bool,
) -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "runs-on": runner,
                "steps": [
                    {
                        "name": "Setup Python",
                        "uses": "actions/setup-python@v6",
                        "with": {"python-version": python_version},
                    },
                    {"id": "enforce", "shell": "bash", "run": "make security-audit"},
                ],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    if accepted:
        assert blocking_contexts_for_workflow(workflow, policy=policy) == (
            "Quality Baseline / Security Gate",
        )
    else:
        with pytest.raises(RequiredStatusChecksError, match="version is not audited"):
            blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    ("action", "enforcement"),
    [
        ("actions/checkout@main", False),
        ("actions/checkout@0123456789abcdef0123456789abcdef01234567", False),
        ("actions/checkout@v5", False),
        ("reviewdog/action-actionlint@main", True),
        ("reviewdog/action-actionlint@0123456789abcdef0123456789abcdef01234567", True),
        ("reviewdog/action-actionlint@v0", True),
    ],
)
def test_blocking_policy_rejects_unpinned_action_references(
    action: str,
    enforcement: bool,
) -> None:
    action_step: dict[str, Any] = {"uses": action}
    if enforcement:
        action_step["id"] = "enforce"
        steps = [action_step]
    else:
        steps = [
            action_step,
            {"id": "enforce", "shell": "bash", "run": "make security-audit"},
        ]
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

    with pytest.raises(RequiredStatusChecksError, match="unaudited action reference"):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    ("action", "inputs", "enforcement"),
    [
        ("actions/cache@v5", {"key": "key", "path": ".buildx-cache"}, False),
        ("actions/cache/restore@v5", {"key": "key", "path": ".buildx-cache"}, False),
        ("actions/cache/save@v5", {"key": "key", "path": ".buildx-cache"}, False),
        ("actions/checkout@v6", {}, False),
        (
            "actions/download-artifact@v8",
            {"name": "runtime", "path": "output/runtime"},
            False,
        ),
        (
            "actions/setup-node@v6",
            {
                "node-version": "${{ env.NODE_VERSION }}",
                "cache": "npm",
                "cache-dependency-path": "tools/api_governance/package-lock.json",
            },
            False,
        ),
        (
            "actions/setup-python@v6",
            {"python-version": "${{ env.PYTHON_VERSION }}"},
            False,
        ),
        (
            "actions/upload-artifact@v7",
            {"name": "evidence", "path": "output/evidence"},
            False,
        ),
        ("docker/setup-buildx-action@v4", {}, False),
        ("reviewdog/action-actionlint@v1", {}, True),
    ],
)
def test_blocking_policy_accepts_exact_audited_action_references(
    action: str,
    inputs: dict[str, object],
    enforcement: bool,
) -> None:
    action_step: dict[str, Any] = {"uses": action, "with": inputs}
    if enforcement:
        action_step["id"] = "enforce"
        steps = [action_step]
    else:
        steps = [
            action_step,
            {"id": "enforce", "shell": "bash", "run": "make security-audit"},
        ]
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

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "Quality Baseline / Security Gate",
    )


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


@pytest.mark.parametrize(
    ("job_patch", "error"),
    [
        ({"container": {"image": "python:3.13", "env": {"MAKEFLAGS": "-n"}}}, "unsupported key"),
        ({"container": {"image": "someone/poisoned:latest"}}, "unsupported key"),
        ({"container": {"image": "python:3.13", "options": "--privileged"}}, "unsupported key"),
        ({"services": {"database": {"image": "postgres:18"}}}, "unsupported key"),
        ({"runs-on": ["self-hosted", "linux"]}, "runner is not audited"),
        ({"runs-on": "${{ matrix.os }}"}, "runner is not audited"),
        ({"environment": "production"}, "unsupported key"),
    ],
)
def test_blocking_policy_rejects_unaudited_job_shape(job_patch: dict[str, Any], error: str) -> None:
    job: dict[str, Any] = {
        "name": "Quality Baseline / Security Gate",
        "runs-on": "ubuntu-latest",
        "steps": [{"id": "enforce", "shell": "bash", "run": "make security-audit"}],
    }
    job.update(job_patch)
    workflow = {"jobs": {"security": job}}
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match=error):
        _blocking_contexts_for_workflow(workflow, policy=policy)


def test_blocking_policy_requires_an_audited_literal_runner() -> None:
    workflow = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "shell": "bash", "run": "make security-audit"}],
            }
        }
    }
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match="runner is not audited"):
        _blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    ("scope", "variable"),
    [
        ("job", "PATH"),
        ("step", "PATH"),
        ("step", "PYTHONPATH"),
        ("step", "PYTHONSTARTUP"),
        ("step", "LD_PRELOAD"),
        ("step", "MAKE"),
        ("workflow", "CI"),
        ("job", "MAKEFLAGS"),
    ],
)
def test_blocking_policy_rejects_unadmitted_environment_keys(scope: str, variable: str) -> None:
    workflow: dict[str, Any] = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [{"id": "enforce", "shell": "bash", "run": "make security-audit"}],
            }
        }
    }
    if scope == "workflow":
        workflow["env"] = {variable: "untrusted"}
    elif scope == "job":
        workflow["jobs"]["security"]["env"] = {variable: "untrusted"}
    else:
        workflow["jobs"]["security"]["steps"][0]["env"] = {variable: "untrusted"}
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(
        RequiredStatusChecksError,
        match=rf"environment key is not admitted: .*key={variable}",
    ):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    ("scope", "variable", "value"),
    [
        ("workflow", "COMPOSE_DOCKER_CLI_BUILD", "1"),
        ("workflow", "DOCKER_BUILDKIT", "1"),
        ("workflow", "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24", "true"),
        ("workflow", "NODE_VERSION", "22"),
        ("workflow", "PIP_DISABLE_PIP_VERSION_CHECK", "1"),
        ("workflow", "PYTHONUNBUFFERED", "1"),
        ("workflow", "PYTHON_VERSION", "3.12"),
        ("job", "LOTUS_PLATFORM_ROOT", "${{ github.workspace }}/lotus-platform"),
        ("step", "DEMO_DATA_PACK_HISTORY_DAYS", "240"),
        ("step", "DEMO_DATA_PACK_INGEST_ONLY", "true"),
        ("step", "DEMO_DATA_PACK_PORTFOLIO_IDS", "DEMO_DPM_EUR_001"),
        ("step", "E2E_INGESTION_URL", "http://localhost:8400"),
        ("step", "E2E_QUERY_URL", "http://localhost:8401"),
        ("step", "GH_TOKEN", "${{ github.token }}"),
        (
            "step",
            "HOST_DATABASE_URL",
            "postgresql://user:password@localhost:57432/portfolio_db",
        ),
        (
            "step",
            "LOTUS_COVERAGE_CHANGED_BASE",
            "${{ github.event_name == 'pull_request' && "
            "format('origin/{0}', github.base_ref) || 'HEAD~1' }}",
        ),
        ("step", "LOTUS_RUNTIME_IMAGE_SET_CI_RUN_ID", "${{ github.run_id }}"),
        ("step", "LOTUS_RUNTIME_IMAGE_SET_GROUP", "pr-runtime-image-set"),
        (
            "step",
            "LOTUS_RUNTIME_IMAGE_SET_REPOSITORY_URL",
            "${{ github.server_url }}/${{ github.repository }}",
        ),
        (
            "step",
            "LOTUS_RUNTIME_IMAGE_SET_SOURCE_BRANCH",
            "${{ github.head_ref || github.ref_name }}",
        ),
        ("step", "LOTUS_RUNTIME_IMAGE_SET_SOURCE_COMMIT_SHA", "${{ github.sha }}"),
        (
            "step",
            "LOTUS_TESTS_COMPOSE_LOG_FILE",
            "output/e2e-smoke/e2e-smoke-logs.txt",
        ),
        ("step", "LOTUS_TEST_ENV_PROFILE", "e2e"),
    ],
)
def test_blocking_policy_accepts_inventoried_environment_value(
    scope: str, variable: str, value: str
) -> None:
    workflow: dict[str, Any] = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "steps": [
                    {
                        "id": "enforce",
                        "shell": "bash",
                        "run": "make security-audit",
                    }
                ],
            }
        },
    }
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

    assert blocking_contexts_for_workflow(workflow, policy=policy) == (
        "Quality Baseline / Security Gate",
    )


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("LOTUS_COVERAGE_CHANGED_BASE", "HEAD"),
        (
            "LOTUS_RUNTIME_IMAGE_SET_SOURCE_COMMIT_SHA",
            "${{ github.event.pull_request.head.sha }}",
        ),
        ("LOTUS_TEST_ENV_PROFILE", "local"),
        ("PYTHON_VERSION", "3.11"),
        ("LOTUS_PLATFORM_ROOT", "${{ github.workspace }}/foreign-platform"),
        ("PYTHONUNBUFFERED", 1),
    ],
)
def test_blocking_policy_rejects_unadmitted_environment_values(
    variable: str, value: object
) -> None:
    workflow: dict[str, Any] = {
        "jobs": {
            "security": {
                "name": "Quality Baseline / Security Gate",
                "env": {variable: value},
                "steps": [{"id": "enforce", "shell": "bash", "run": "make security-audit"}],
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
        match=rf"environment value is not admitted: .*key={variable}",
    ):
        blocking_contexts_for_workflow(workflow, policy=policy)


@pytest.mark.parametrize(
    ("action_role", "scope", "variable", "value", "error"),
    [
        (
            "enforcement",
            "job",
            "PATH",
            "${{ github.workspace }}/fake-bin:/usr/bin:/bin",
            "environment key is not admitted",
        ),
        (
            "enforcement",
            "step",
            "PATH",
            "${{ github.workspace }}/fake-bin:/usr/bin:/bin",
            "environment key is not admitted",
        ),
        (
            "enforcement",
            "step",
            "PYTHON_VERSION",
            "3.11",
            "environment value is not admitted",
        ),
        (
            "auxiliary",
            "step",
            "PATH",
            "${{ github.workspace }}/fake-bin:/usr/bin:/bin",
            "environment key is not admitted",
        ),
    ],
)
def test_blocking_policy_validates_environment_for_every_action_step(
    action_role: str,
    scope: str,
    variable: str,
    value: str,
    error: str,
) -> None:
    action_step: dict[str, Any]
    if action_role == "enforcement":
        action_step = {"id": "enforce", "uses": "reviewdog/action-actionlint@v1"}
        steps = [action_step]
    else:
        action_step = {"uses": "actions/checkout@v6"}
        steps = [
            action_step,
            {"id": "enforce", "shell": "bash", "run": "make security-audit"},
        ]
    job: dict[str, Any] = {
        "name": "Quality Baseline / Security Gate",
        "steps": steps,
    }
    if scope == "job":
        job["env"] = {variable: value}
    else:
        action_step["env"] = {variable: value}
    workflow = {"jobs": {"security": job}}
    policy = WorkflowPolicy(
        path=Path("fixture.yml"),
        policy="gate_jobs_blocking",
        advisory_contexts=frozenset(),
    )

    with pytest.raises(RequiredStatusChecksError, match=error):
        blocking_contexts_for_workflow(workflow, policy=policy)


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
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - id: enforce\n"
        "        shell: bash\n"
        "        run: make security-audit\n"
        "  new_control:\n"
        "    name: Quality Baseline / New Control Gate\n"
        "    runs-on: ubuntu-latest\n"
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
        "    runs-on: ubuntu-latest\n"
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
        "    runs-on: ubuntu-latest\n"
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
        "    runs-on: ubuntu-latest\n"
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
