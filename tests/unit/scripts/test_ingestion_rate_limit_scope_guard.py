from pathlib import Path

from scripts import ingestion_rate_limit_scope_guard as guard


def test_ingestion_rate_limit_scope_guard_accepts_current_truth() -> None:
    assert guard.evaluate_ingestion_rate_limit_scope_truth() == []


def test_ingestion_rate_limit_scope_guard_rejects_missing_doc_scope(tmp_path: Path) -> None:
    doc_path = tmp_path / "docs" / "operations"
    doc_path.mkdir(parents=True)
    (doc_path / "ingestion-api-gold-standard.md").write_text(
        "Canonical ingestion write APIs support rolling-window rate limits.\n",
        encoding="utf-8",
    )

    findings = guard.evaluate_ingestion_rate_limit_scope_truth(
        repo_root=tmp_path,
        required_phrases={
            "docs/operations/ingestion-api-gold-standard.md": (
                "local_process",
                "not a global service-level limit",
            )
        },
    )

    assert findings == [
        {
            "file": "docs/operations/ingestion-api-gold-standard.md",
            "missing_phrases": [
                "local_process",
                "not a global service-level limit",
            ],
        }
    ]


def test_ingestion_rate_limit_scope_guard_rejects_local_global_claim() -> None:
    findings = guard.evaluate_ingestion_rate_limit_scope_truth(
        contract={
            "enforcement_scope": "local_process",
            "global_enforcement_claimed": True,
            "local_process_enforcement": True,
            "gateway_policy_id": None,
        },
        required_phrases={},
    )

    assert findings == [
        {"runtime_contract": ["local_process scope must not claim global enforcement"]}
    ]
