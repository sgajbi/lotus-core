from pathlib import Path

from scripts import front_door_sync_guard as guard


def _write_front_door_fixture(repo_root: Path) -> None:
    for path in (
        "REPOSITORY-ENGINEERING-CONTEXT.md",
        "docs/architecture/README.md",
        "docs/standards/api-route-catalog.v1.json",
        "docs/standards/rfc-status-ledger.v1.json",
        "contracts/supported-features/lotus-core-supported-features.v1.json",
        "docs/operations-runbook.md",
        "wiki/API-Surface.md",
        "wiki/Supported-Features.md",
        "wiki/Operations-Runbook.md",
        "wiki/Validation-and-CI.md",
        "wiki/Architecture.md",
        "wiki/RFC-Index.md",
        "wiki/Home.md",
        "wiki/_Sidebar.md",
        "wiki/Getting-Started.md",
        "wiki/Development-Workflow.md",
        "wiki/Overview.md",
        ".github/pull_request_template.md",
    ):
        target = repo_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ok\n", encoding="utf-8")
    (repo_root / "README.md").write_text(
        "\n".join(
            [
                "REPOSITORY-ENGINEERING-CONTEXT.md",
                "docs/architecture/README.md",
                "docs/standards/api-route-catalog.v1.json",
                "wiki/API-Surface.md",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "wiki" / "Home.md").write_text(
        "[API](API-Surface) [Supported](Supported-Features) [Ops](Operations-Runbook)\n",
        encoding="utf-8",
    )
    (repo_root / "wiki" / "_Sidebar.md").write_text(
        "[Home](Home) [API](API-Surface) [Supported](Supported-Features)\n",
        encoding="utf-8",
    )
    (repo_root / ".github" / "pull_request_template.md").write_text(
        "README API catalog wiki source post-merge no-doc-change rationale\n",
        encoding="utf-8",
    )


def _contract() -> dict:
    return {
        "schema_version": guard.SCHEMA_VERSION,
        "repository": guard.REPOSITORY,
        "guard_command": guard.GUARD_COMMAND,
        "canonical_sources": [
            {"id": "context", "path": "REPOSITORY-ENGINEERING-CONTEXT.md", "role": "truth"},
            {"id": "architecture", "path": "docs/architecture/README.md", "role": "truth"},
        ],
        "summary_sources": [
            {"id": "readme", "path": "README.md", "role": "front door"},
            {"id": "wiki_home", "path": "wiki/Home.md", "role": "front door"},
        ],
        "readme_required_links": [
            "REPOSITORY-ENGINEERING-CONTEXT.md",
            "docs/architecture/README.md",
            "docs/standards/api-route-catalog.v1.json",
            "wiki/API-Surface.md",
        ],
        "wiki_home_required_links": [
            "API-Surface",
            "Supported-Features",
            "Operations-Runbook",
        ],
        "wiki_sidebar_required_pages": ["Home", "API-Surface", "Supported-Features"],
        "pr_template_required_terms": ["README", "API catalog", "wiki source", "post-merge"],
        "update_checklist": ["update contract", "record no-doc-change", "publish wiki"],
    }


def test_front_door_sync_guard_accepts_current_contract(tmp_path: Path) -> None:
    _write_front_door_fixture(tmp_path)

    assert guard.evaluate_contract(_contract(), repo_root=tmp_path) == []


def test_front_door_sync_guard_reports_missing_readme_link(tmp_path: Path) -> None:
    _write_front_door_fixture(tmp_path)
    (tmp_path / "README.md").write_text("missing links\n", encoding="utf-8")

    errors = guard.evaluate_contract(_contract(), repo_root=tmp_path)

    assert any("README.md is missing required front-door link" in error for error in errors)


def test_front_door_sync_guard_reports_missing_sidebar_page(tmp_path: Path) -> None:
    _write_front_door_fixture(tmp_path)
    (tmp_path / "wiki" / "_Sidebar.md").write_text("[Home](Home)\n", encoding="utf-8")

    errors = guard.evaluate_contract(_contract(), repo_root=tmp_path)

    assert any(
        "wiki/_Sidebar.md is missing required page: API-Surface" in error for error in errors
    )


def test_front_door_sync_guard_reports_missing_pr_template_term(tmp_path: Path) -> None:
    _write_front_door_fixture(tmp_path)
    (tmp_path / ".github" / "pull_request_template.md").write_text("README\n", encoding="utf-8")

    errors = guard.evaluate_contract(_contract(), repo_root=tmp_path)

    assert any(
        "pull request template is missing required docs term: API catalog" in error
        for error in errors
    )
