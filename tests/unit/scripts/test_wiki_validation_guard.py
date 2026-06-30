from pathlib import Path

from scripts import wiki_validation_guard as guard


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _valid_wiki(repo_root: Path) -> None:
    _write(
        repo_root / "wiki" / "_Sidebar.md",
        "# repo\n\n- [Home](Home)\n- [Operations Runbook](Operations-Runbook)\n",
    )
    _write(repo_root / "wiki" / "Home.md", "# Home\n\nSee [Operations](Operations-Runbook).\n")
    _write(
        repo_root / "wiki" / "Operations-Runbook.md",
        "# Operations Runbook\n\nSee [Architecture](../docs/architecture/README.md).\n",
    )
    _write(repo_root / "docs" / "architecture" / "README.md", "# Architecture\n")


def test_evaluate_wiki_source_accepts_complete_wiki(tmp_path: Path) -> None:
    _valid_wiki(tmp_path)

    assert guard.evaluate_wiki_source(repo_root=tmp_path) == []


def test_evaluate_wiki_source_rejects_sidebar_missing_page(tmp_path: Path) -> None:
    _valid_wiki(tmp_path)
    (tmp_path / "wiki" / "Operations-Runbook.md").unlink()

    assert guard.evaluate_wiki_source(repo_root=tmp_path) == [
        "sidebar links to missing wiki page: wiki/Operations-Runbook.md",
        "wiki/Home.md links to missing path: Operations-Runbook",
    ]


def test_evaluate_wiki_source_rejects_orphaned_page(tmp_path: Path) -> None:
    _valid_wiki(tmp_path)
    _write(tmp_path / "wiki" / "Troubleshooting.md", "# Troubleshooting\n")

    assert guard.evaluate_wiki_source(repo_root=tmp_path) == [
        "wiki page is not linked from sidebar: wiki/Troubleshooting.md"
    ]


def test_evaluate_wiki_source_rejects_broken_repo_relative_link(tmp_path: Path) -> None:
    _valid_wiki(tmp_path)
    _write(
        tmp_path / "wiki" / "Operations-Runbook.md",
        "# Operations Runbook\n\nSee [Missing](../docs/architecture/MISSING.md).\n",
    )

    assert guard.evaluate_wiki_source(repo_root=tmp_path) == [
        "wiki/Operations-Runbook.md links to missing path: ../docs/architecture/MISSING.md"
    ]


def test_evaluate_wiki_source_rejects_unsafe_name_and_missing_h1(tmp_path: Path) -> None:
    _write(tmp_path / "wiki" / "_Sidebar.md", "# repo\n\n- [Bad](Bad Page)\n")
    _write(tmp_path / "wiki" / "Bad Page.md", "No heading\n")

    assert guard.evaluate_wiki_source(repo_root=tmp_path) == [
        "wiki page name is not publication-safe: wiki/Bad Page.md",
        "wiki page must start with a single H1 heading: wiki/Bad Page.md",
    ]


def test_evaluate_publication_parity_rejects_drift(tmp_path: Path) -> None:
    _valid_wiki(tmp_path)
    published = tmp_path / "published"
    _write(published / "_Sidebar.md", (tmp_path / "wiki" / "_Sidebar.md").read_text())
    _write(published / "Home.md", "# Home\n\nChanged.\n")
    _write(published / "Extra.md", "# Extra\n")

    errors = guard.evaluate_publication_parity(
        repo_root=tmp_path,
        published_wiki_dir=published,
    )

    assert errors == [
        "published wiki is missing authored page: Operations-Runbook.md",
        "published wiki has page absent from repo source: Extra.md",
        "published wiki page differs from repo source: Home.md",
    ]
