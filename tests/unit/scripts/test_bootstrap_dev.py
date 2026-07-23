from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scripts.development import bootstrap_dev


def test_import_origin_accepts_invoking_worktree(tmp_path: Path) -> None:
    project = tmp_path / "lotus-core-current" / "src" / "libs" / "portfolio-common"
    package = project / "portfolio_common"
    package.mkdir(parents=True)
    origin = package / "__init__.py"

    assert (
        bootstrap_dev.require_portfolio_common_import_origin(
            expected_project=project,
            origin_resolver=lambda: origin,
        )
        == origin.resolve()
    )


def test_import_origin_rejects_another_worktree(tmp_path: Path) -> None:
    expected = tmp_path / "lotus-core-current" / "src" / "libs" / "portfolio-common"
    foreign = (
        tmp_path
        / "lotus-core-other"
        / "src"
        / "libs"
        / "portfolio-common"
        / "portfolio_common"
        / "__init__.py"
    )
    expected.mkdir(parents=True)
    foreign.parent.mkdir(parents=True)

    with pytest.raises(RuntimeError) as raised:
        bootstrap_dev.require_portfolio_common_import_origin(
            expected_project=expected,
            origin_resolver=lambda: foreign,
        )

    message = str(raised.value)
    assert str((expected / "portfolio_common").resolve()) in message
    assert str(foreign.resolve()) in message
    assert "make install" in message


def test_installed_origin_resolver_uses_isolated_child_interpreter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[list[str], Path, dict[str, str]]] = []
    origin = tmp_path / "portfolio_common" / "__init__.py"
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "foreign-worktree"))

    def _run(cmd, *, cwd, env, check, capture_output, text):  # noqa: ANN001
        assert check is False
        assert capture_output is True
        assert text is True
        calls.append((cmd, cwd, env))
        return CompletedProcess(cmd, 0, stdout=f"{origin}\n", stderr="")

    monkeypatch.setattr(bootstrap_dev.subprocess, "run", _run)

    assert bootstrap_dev.resolve_installed_portfolio_common_origin() == origin.resolve()
    assert calls[0][0][0:2] == [bootstrap_dev.sys.executable, "-P"]
    assert calls[0][1] == bootstrap_dev.ROOT
    assert "PYTHONPATH" not in calls[0][2]


def test_installed_origin_resolver_reports_import_failure(monkeypatch) -> None:
    def _run(cmd, **_kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, 1, stdout="", stderr="No module named portfolio_common")

    monkeypatch.setattr(bootstrap_dev.subprocess, "run", _run)

    with pytest.raises(RuntimeError, match="No module named portfolio_common"):
        bootstrap_dev.resolve_installed_portfolio_common_origin()


def test_import_origin_rejects_package_prefix_collision(tmp_path: Path) -> None:
    expected = tmp_path / "portfolio-common"
    lookalike = tmp_path / "portfolio-common-shadow" / "portfolio_common" / "__init__.py"

    with pytest.raises(RuntimeError):
        bootstrap_dev.require_portfolio_common_import_origin(
            expected_project=expected,
            origin_resolver=lambda: lookalike,
        )
