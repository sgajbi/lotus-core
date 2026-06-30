from pathlib import Path

import yaml

DEPENDABOT_CONFIG_PATH = Path(".github/dependabot.yml")

IGNORED_MANIFEST_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "htmlcov",
    "output",
    "venv",
}


def _repository_directory(path: Path) -> str:
    if path == Path("."):
        return "/"
    return f"/{path.as_posix()}"


def _configured_directories(package_ecosystem: str) -> set[str]:
    config = yaml.safe_load(DEPENDABOT_CONFIG_PATH.read_text(encoding="utf-8"))
    configured_directories: set[str] = set()

    for update in config["updates"]:
        if update["package-ecosystem"] != package_ecosystem:
            continue
        if "directory" in update:
            configured_directories.add(update["directory"])
        configured_directories.update(update.get("directories", ()))

    return configured_directories


def _is_governed_manifest(path: Path) -> bool:
    return not any(part in IGNORED_MANIFEST_PARTS for part in path.parts)


def test_dependabot_covers_all_python_dependency_manifests() -> None:
    manifest_directories = {
        _repository_directory(path.parent)
        for pattern in ("pyproject.toml", "requirements.txt")
        for path in Path(".").rglob(pattern)
        if _is_governed_manifest(path)
    }

    assert _configured_directories("pip") == manifest_directories


def test_dependabot_covers_all_runtime_dockerfiles() -> None:
    dockerfile_directories = {
        _repository_directory(path.parent)
        for path in Path("src/services").rglob("Dockerfile")
        if _is_governed_manifest(path)
    }

    assert _configured_directories("docker") == dockerfile_directories


def test_dependabot_covers_github_actions_with_pr_flood_limits() -> None:
    config = yaml.safe_load(DEPENDABOT_CONFIG_PATH.read_text(encoding="utf-8"))
    updates = config["updates"]

    assert _configured_directories("github-actions") == {"/"}
    assert {update["package-ecosystem"] for update in updates} == {
        "docker",
        "github-actions",
        "pip",
    }
    assert all(update["open-pull-requests-limit"] <= 4 for update in updates)
    assert all(update.get("groups") for update in updates)
