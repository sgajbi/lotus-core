from pathlib import Path

import pytest

from scripts import clean_generated_artifacts as clean


def _write(path: Path, content: str = "generated") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_clean_generated_artifacts_removes_repo_governed_artifacts(tmp_path: Path) -> None:
    disposable_files = [
        tmp_path / ".coverage",
        tmp_path / ".coverage.unit",
        tmp_path / "coverage.xml",
        tmp_path / "src" / "services" / "query_service" / "app" / "module.pyc",
    ]
    disposable_dirs = [
        tmp_path / ".pytest_cache",
        tmp_path / ".ruff_cache",
        tmp_path / ".mypy_cache",
        tmp_path / ".hypothesis",
        tmp_path / ".import_linter_cache",
        tmp_path / "__pycache__",
        tmp_path / "src" / "services" / "query_service" / "build" / "lib",
        tmp_path / "src" / "services" / "query_service" / "app" / "__pycache__",
        tmp_path / "src" / "services" / "query_service" / "app" / "demo.egg-info",
        tmp_path / "dist",
        tmp_path / "htmlcov",
        tmp_path / "output" / "openapi",
    ]
    preserved_files = [
        tmp_path / ".git" / "config",
        tmp_path / "docs" / "architecture.md",
        tmp_path / "wiki" / "Home.md",
        tmp_path / "contracts" / "contract.json",
        tmp_path / "migrations" / "versions" / "001_initial.py",
        tmp_path / "src" / "services" / "query_service" / "app" / "main.py",
    ]

    for file_path in disposable_files + preserved_files:
        _write(file_path)
    for directory in disposable_dirs:
        _write(directory / "artifact.txt")
    _write(tmp_path / ".venv" / "build" / "artifact.txt")
    _write(tmp_path / "node_modules" / ".cache" / "artifact.txt")

    removed = clean.clean_generated_artifacts(repo_root=tmp_path)
    removed_relative = {
        path.resolve(strict=False).relative_to(tmp_path).as_posix() for path in removed
    }

    assert ".pytest_cache" in removed_relative
    assert ".ruff_cache" in removed_relative
    assert ".mypy_cache" in removed_relative
    assert ".hypothesis" in removed_relative
    assert ".import_linter_cache" in removed_relative
    assert "__pycache__" in removed_relative
    assert "src/services/query_service/build" in removed_relative
    assert "src/services/query_service/app/__pycache__" in removed_relative
    assert "src/services/query_service/app/demo.egg-info" in removed_relative
    assert "output" in removed_relative
    assert ".coverage" in removed_relative
    assert ".coverage.unit" in removed_relative
    assert "coverage.xml" in removed_relative
    assert "src/services/query_service/app/module.pyc" in removed_relative

    for file_path in disposable_files:
        assert not file_path.exists()
    for directory in disposable_dirs:
        assert not directory.exists()
    for file_path in preserved_files:
        assert file_path.exists()
    assert (tmp_path / ".venv" / "build" / "artifact.txt").exists()
    assert (tmp_path / "node_modules" / ".cache" / "artifact.txt").exists()


def test_clean_generated_artifacts_dry_run_preserves_targets(tmp_path: Path) -> None:
    artifact = tmp_path / ".pytest_cache" / "artifact.txt"
    _write(artifact)

    removed = clean.clean_generated_artifacts(repo_root=tmp_path, dry_run=True)

    assert removed == [tmp_path / ".pytest_cache"]
    assert artifact.exists()


def test_remove_cleanup_targets_refuses_outside_repo_paths(tmp_path: Path) -> None:
    outside_path = tmp_path.parent / "outside-generated-artifact"
    _write(outside_path)

    with pytest.raises(ValueError, match="outside repository root"):
        clean.remove_cleanup_targets(repo_root=tmp_path, targets=[outside_path])

    assert outside_path.exists()
    outside_path.unlink()
