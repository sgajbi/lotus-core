"""Validate README/wiki front-door synchronization governance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "docs" / "standards" / "front-door-sync.v1.json"
SCHEMA_VERSION = "lotus-core.front-door-sync.v1"
REPOSITORY = "lotus-core"
GUARD_COMMAND = "python scripts/front_door_sync_guard.py"
PR_TEMPLATE = REPO_ROOT / ".github" / "pull_request_template.md"


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_contract(payload: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"front-door contract schema_version must be {SCHEMA_VERSION!r}")
    if payload.get("repository") != REPOSITORY:
        errors.append(f"front-door contract repository must be {REPOSITORY!r}")
    if payload.get("guard_command") != GUARD_COMMAND:
        errors.append(f"front-door contract guard_command must be {GUARD_COMMAND!r}")

    for section in ("canonical_sources", "summary_sources"):
        errors.extend(_source_errors(payload.get(section), section=section, repo_root=repo_root))
    errors.extend(_readme_link_errors(payload.get("readme_required_links"), repo_root=repo_root))
    errors.extend(
        _wiki_home_link_errors(payload.get("wiki_home_required_links"), repo_root=repo_root)
    )
    errors.extend(
        _wiki_sidebar_errors(payload.get("wiki_sidebar_required_pages"), repo_root=repo_root)
    )
    errors.extend(
        _pr_template_errors(payload.get("pr_template_required_terms"), repo_root=repo_root)
    )
    checklist = payload.get("update_checklist")
    if not isinstance(checklist, list) or len(checklist) < 3:
        errors.append("front-door contract update_checklist must contain at least three items")
    return errors


def _source_errors(value: object, *, section: str, repo_root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, list) or not value:
        return [f"front-door contract {section} must be a non-empty list"]
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{section}[{index}] must be an object")
            continue
        source_id = item.get("id")
        path = item.get("path")
        role = item.get("role")
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(f"{section}[{index}] must define id")
        elif source_id in seen:
            errors.append(f"{section} contains duplicate id {source_id}")
        else:
            seen.add(source_id)
        if not isinstance(role, str) or not role.strip():
            errors.append(f"{section}[{index}] must define role")
        if not isinstance(path, str) or not path.strip():
            errors.append(f"{section}[{index}] must define path")
        elif Path(path).is_absolute() or not (repo_root / path).exists():
            errors.append(f"{section}[{index}] path must exist and be repo-relative: {path}")
    return errors


def _readme_link_errors(value: object, *, repo_root: Path) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["front-door contract readme_required_links must be a non-empty list"]
    readme = _read_text(repo_root / "README.md")
    errors: list[str] = []
    for link in value:
        if not isinstance(link, str) or not link.strip():
            errors.append(f"readme_required_links contains invalid link {link!r}")
            continue
        if not (repo_root / link).exists():
            errors.append(f"README required link target does not exist: {link}")
        if link not in readme:
            errors.append(f"README.md is missing required front-door link: {link}")
    return errors


def _wiki_home_link_errors(value: object, *, repo_root: Path) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["front-door contract wiki_home_required_links must be a non-empty list"]
    home = _read_text(repo_root / "wiki" / "Home.md")
    errors: list[str] = []
    for page in value:
        if not isinstance(page, str) or not page.strip():
            errors.append(f"wiki_home_required_links contains invalid page {page!r}")
            continue
        if not (repo_root / "wiki" / f"{page}.md").exists():
            errors.append(f"wiki home required page target does not exist: {page}")
        if f"]({page})" not in home:
            errors.append(f"wiki/Home.md is missing required front-door link: {page}")
    return errors


def _wiki_sidebar_errors(value: object, *, repo_root: Path) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["front-door contract wiki_sidebar_required_pages must be a non-empty list"]
    sidebar = _read_text(repo_root / "wiki" / "_Sidebar.md")
    errors: list[str] = []
    for page in value:
        if not isinstance(page, str) or not page.strip():
            errors.append(f"wiki_sidebar_required_pages contains invalid page {page!r}")
            continue
        if not (repo_root / "wiki" / f"{page}.md").exists():
            errors.append(f"wiki sidebar required page target does not exist: {page}")
        if f"]({page})" not in sidebar:
            errors.append(f"wiki/_Sidebar.md is missing required page: {page}")
    return errors


def _pr_template_errors(value: object, *, repo_root: Path) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["front-door contract pr_template_required_terms must be a non-empty list"]
    template = _read_text(repo_root / PR_TEMPLATE.relative_to(REPO_ROOT))
    errors: list[str] = []
    for term in value:
        if not isinstance(term, str) or not term.strip():
            errors.append(f"pr_template_required_terms contains invalid term {term!r}")
            continue
        if term not in template:
            errors.append(f"pull request template is missing required docs term: {term}")
    return errors


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def main() -> int:
    errors = evaluate_contract(load_contract())
    if errors:
        print("Front-door sync guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Front-door sync guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
