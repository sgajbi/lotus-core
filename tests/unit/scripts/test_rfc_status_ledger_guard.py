from pathlib import Path

from scripts import rfc_status_ledger_guard as guard


def _write_required_files(repo_root: Path) -> None:
    for path in (
        "docs/RFCs/RFC 001 - First.md",
        "docs/rfc-transaction-specs/transactions/BUY/RFC-BUY-01.md",
        "docs/architecture/RFC-0083-target-state-gap-analysis.md",
        "docs/operations/RFC-065-Calculator-Scalability-Operations-Playbook.md",
        "docs/RFCs/RFC-INDEX.md",
        "docs/rfc-transaction-specs/README.md",
        "docs/architecture/README.md",
        "wiki/RFC-Index.md",
        "docs/supported-features.md",
        "src/libs/portfolio-common/portfolio_common/transaction_type_registry.py",
        "tests/unit/scripts/test_rfc_status_ledger_guard.py",
    ):
        file_path = repo_root / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("ok\n", encoding="utf-8")


def _entry(path: str, family: str, *, status: str = "implemented") -> dict[str, object]:
    return {
        "rfc_id": Path(path).stem,
        "title": Path(path).stem.replace("-", " "),
        "family": family,
        "path": path,
        "status": status,
        "owner": "lotus-core",
        "affected_services": ["repository-wide"],
        "affected_routes": [],
        "affected_data_models": [],
        "implementation_refs": ["docs/RFCs/RFC-INDEX.md"],
        "test_evidence": ["tests/unit/scripts/test_rfc_status_ledger_guard.py"],
        "docs_links": ["docs/RFCs/RFC-INDEX.md"],
        "wiki_links": ["wiki/RFC-Index.md"],
        "supported_feature_refs": ["docs/supported-features.md"],
        "canonical_registry_refs": [],
        "supersedes": [],
        "superseded_by": [],
        "deprecation_relationship": "none",
        "status_rationale": "Guard fixture row.",
    }


def _ledger() -> dict[str, object]:
    return {
        "schema_version": guard.SCHEMA_VERSION,
        "repository": guard.REPOSITORY,
        "guard_command": guard.GUARD_COMMAND,
        "families": sorted(guard.REQUIRED_FAMILIES),
        "entries": [
            _entry("docs/RFCs/RFC 001 - First.md", "core"),
            _entry("docs/RFCs/RFC-INDEX.md", "core", status="historical"),
            _entry("docs/rfc-transaction-specs/README.md", "transaction"),
            {
                **_entry(
                    "docs/rfc-transaction-specs/transactions/BUY/RFC-BUY-01.md",
                    "transaction",
                ),
                "canonical_registry_refs": [guard.TRANSACTION_REGISTRY],
            },
            _entry("docs/architecture/RFC-0083-target-state-gap-analysis.md", "architecture"),
            _entry(
                "docs/operations/RFC-065-Calculator-Scalability-Operations-Playbook.md",
                "operations",
            ),
        ],
    }


def test_rfc_status_ledger_accepts_complete_metadata(tmp_path: Path) -> None:
    _write_required_files(tmp_path)

    assert guard.evaluate_ledger(_ledger(), repo_root=tmp_path) == []


def test_rfc_status_ledger_reports_missing_rfc_file_metadata(tmp_path: Path) -> None:
    _write_required_files(tmp_path)
    extra = tmp_path / "docs" / "RFCs" / "RFC 002 - Missing.md"
    extra.write_text("ok\n", encoding="utf-8")

    errors = guard.evaluate_ledger(_ledger(), repo_root=tmp_path)

    assert any(
        "RFC ledger is missing metadata for: docs/RFCs/RFC 002 - Missing.md" in error
        for error in errors
    )


def test_rfc_status_ledger_reports_stale_metadata(tmp_path: Path) -> None:
    _write_required_files(tmp_path)
    ledger = _ledger()
    ledger["entries"].append(_entry("docs/RFCs/RFC 999 - Stale.md", "core"))  # type: ignore[index]

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert any(
        "RFC ledger contains stale metadata for: docs/RFCs/RFC 999 - Stale.md" in error
        for error in errors
    )


def test_rfc_status_ledger_requires_transaction_registry_link(tmp_path: Path) -> None:
    _write_required_files(tmp_path)
    ledger = _ledger()
    ledger["entries"][3]["canonical_registry_refs"] = []  # type: ignore[index]

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert any(
        "transaction specs must link the canonical transaction registry" in error
        for error in errors
    )


def test_rfc_status_ledger_rejects_missing_path_reference(tmp_path: Path) -> None:
    _write_required_files(tmp_path)
    ledger = _ledger()
    ledger["entries"][0]["docs_links"] = ["docs/RFCs/missing.md"]  # type: ignore[index]

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert any(
        "docs_links reference does not exist: docs/RFCs/missing.md" in error for error in errors
    )


def test_rfc_status_ledger_rejects_implemented_entry_without_test_evidence(
    tmp_path: Path,
) -> None:
    _write_required_files(tmp_path)
    ledger = _ledger()
    ledger["entries"][0]["test_evidence"] = []  # type: ignore[index]

    errors = guard.evaluate_ledger(ledger, repo_root=tmp_path)

    assert any("implemented entries must define test_evidence" in error for error in errors)
