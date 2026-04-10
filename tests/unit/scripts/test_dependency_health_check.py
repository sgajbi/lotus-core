from pathlib import Path

from scripts import dependency_health_check


def test_discover_editable_projects_returns_sorted_project_roots(tmp_path: Path) -> None:
    alpha = tmp_path / "src" / "services" / "alpha_service"
    beta = tmp_path / "src" / "libs" / "beta_lib"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    (alpha / "pyproject.toml").write_text("[project]\nname='alpha'\n", encoding="utf-8")
    (beta / "pyproject.toml").write_text("[project]\nname='beta'\n", encoding="utf-8")

    projects = dependency_health_check.discover_editable_projects(tmp_path)

    assert projects == [beta, alpha]


def test_constrained_install_command_uses_shared_runtime_lock() -> None:
    python_bin = Path("/tmp/python")
    command = dependency_health_check.constrained_install_command(
        python_bin,
        "-e",
        "src/services/query_service",
    )

    assert command[:6] == [
        str(python_bin),
        "-m",
        "pip",
        "install",
        "-c",
        str(dependency_health_check.RUNTIME_LOCK_FILE),
    ]
    assert command[-2:] == ["-e", "src/services/query_service"]


def test_pip_audit_command_scopes_to_site_packages_path() -> None:
    python_bin = Path("/tmp/python")
    site_packages = Path("/tmp/venv/site-packages")
    command = dependency_health_check.pip_audit_command(
        python_bin,
        site_packages,
    )

    assert command == [
        str(python_bin),
        "-m",
        "pip_audit",
        "--path",
        str(site_packages),
    ]
