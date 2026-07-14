"""Guard local and hosted CI test-evidence composition."""

from pathlib import Path


def _make_target_dependencies() -> dict[str, list[str]]:
    lines = Path("Makefile").read_text(encoding="utf-8").splitlines()
    return {
        target: dependencies.split()
        for line in lines
        if ":" in line and not line.startswith(("\t", "#", "."))
        for target, dependencies in (line.split(":", maxsplit=1),)
    }


def test_local_ci_runs_unit_and_integration_lite_once_through_coverage_gate() -> None:
    dependencies = _make_target_dependencies()["ci-local"]

    assert dependencies.count("coverage-gate") == 1
    assert "warning-gate" not in dependencies
    assert "test-unit" not in dependencies
    assert "test-integration-lite" not in dependencies
    assert "test-unit-db" in dependencies


def test_hosted_ci_retains_standalone_warning_and_coverage_gates() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    ci_gates = next(
        line.removeprefix("CI_GATES :=").split()
        for line in makefile.splitlines()
        if line.startswith("CI_GATES :=")
    )

    assert "warning-gate" in ci_gates
    assert "coverage-gate" in ci_gates
