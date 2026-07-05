from pathlib import Path

from scripts.architecture_documentation_catalog_guard import (
    find_architecture_catalog_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base_catalog() -> str:
    return """
{
  "schema_version": "lotus-core.architecture-documentation-catalog.v1",
  "related_navigation": [
    "docs/standards/verified-api-examples.v1.json",
    "docs/standards/rfc-0083-implementation-ledger.json",
    "docs/operations-runbook.md",
    "docs/supported-features.md",
    "wiki/Architecture.md",
    "wiki/API-Surface.md",
    "wiki/Supported-Features.md"
  ],
  "entries": [
    {
      "path": "docs/architecture/architecture-documentation-catalog.v1.json",
      "type": "catalog",
      "topics": ["documentation-governance"],
      "status": "active",
      "owner": "lotus-core",
      "freshness_date": "2026-07-05",
      "related": {"issues": [620], "rfcs": [], "prs": []},
      "truth_role": "catalog-metadata",
      "summary": "Catalog metadata."
    },
    {
      "path": "docs/architecture/README.md",
      "type": "index",
      "topics": ["architecture-navigation"],
      "status": "active",
      "owner": "lotus-core",
      "freshness_date": "2026-07-05",
      "related": {"issues": [620], "rfcs": [], "prs": []},
      "truth_role": "current-state-truth",
      "summary": "Architecture index."
    },
    {
      "path": "docs/architecture/historical.md",
      "type": "background",
      "topics": ["history"],
      "status": "historical",
      "owner": "lotus-core",
      "freshness_date": "2026-07-05",
      "related": {"issues": [], "rfcs": [], "prs": []},
      "truth_role": "historical-context",
      "summary": "Historical background."
    }
  ],
  "coverage_rules": [
    {
      "glob": "CR-*.md",
      "type": "codebase-review-record",
      "status": "review-evidence",
      "owner": "lotus-core",
      "truth_role": "review-evidence",
      "freshness_policy": "Use the ledger first."
    },
    {
      "glob": "templates/*.md",
      "type": "template",
      "status": "active",
      "owner": "lotus-core",
      "truth_role": "template",
      "freshness_policy": "Template coverage."
    }
  ]
}
"""


def _write_required_files(tmp_path: Path) -> None:
    for path in (
        "docs/standards/verified-api-examples.v1.json",
        "docs/standards/rfc-0083-implementation-ledger.json",
        "docs/operations-runbook.md",
        "docs/supported-features.md",
        "wiki/Architecture.md",
        "wiki/API-Surface.md",
        "wiki/Supported-Features.md",
    ):
        _write(tmp_path / path, "{}\n" if path.endswith(".json") else "# Doc\n")
    _write(
        tmp_path / "docs/architecture/README.md",
        "# Index\n\narchitecture-documentation-catalog.v1.json current-state truth review evidence historical context\n",
    )
    _write(tmp_path / "docs/architecture/historical.md", "# Historical\n")
    _write(tmp_path / "docs/architecture/CR-001.md", "# Review\n")
    _write(tmp_path / "docs/architecture/templates/example.md", "# Template\n")
    _write(
        tmp_path / "docs/architecture/architecture-documentation-catalog.v1.json",
        _base_catalog(),
    )


def test_architecture_catalog_guard_accepts_cataloged_and_rule_covered_docs(
    tmp_path: Path,
) -> None:
    _write_required_files(tmp_path)

    assert find_architecture_catalog_findings(tmp_path) == []


def test_architecture_catalog_guard_rejects_uncataloged_architecture_doc(
    tmp_path: Path,
) -> None:
    _write_required_files(tmp_path)
    _write(tmp_path / "docs/architecture/new-current-doc.md", "# New\n")

    findings = find_architecture_catalog_findings(tmp_path)

    assert any(f.rule == "uncataloged-architecture-document" for f in findings)


def test_architecture_catalog_guard_requires_metadata_and_navigation(
    tmp_path: Path,
) -> None:
    _write_required_files(tmp_path)
    _write(
        tmp_path / "docs/architecture/architecture-documentation-catalog.v1.json",
        """
{
  "schema_version": "lotus-core.architecture-documentation-catalog.v1",
  "related_navigation": [],
  "entries": [
    {
      "path": "docs/architecture/README.md",
      "type": "index",
      "topics": [],
      "status": "future",
      "owner": "lotus-core",
      "freshness_date": "2026-07-05",
      "related": {"issues": []},
      "truth_role": "optimistic",
      "summary": "Bad entry."
    }
  ],
  "coverage_rules": []
}
""",
    )

    rules = {finding.rule for finding in find_architecture_catalog_findings(tmp_path)}

    assert "missing-related-navigation" in rules
    assert "invalid-truth-role" in rules
    assert "invalid-status" in rules
    assert "missing-topics" in rules
    assert "invalid-related-shape" in rules
