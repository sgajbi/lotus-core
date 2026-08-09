from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RETIRED_DERIVED_STATE_SERVICES = {
    "timeseries_generator_service",
    "portfolio_aggregation_service",
}


def _section(document: str, start: str, end: str) -> str:
    return document.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]


def test_current_derived_state_ownership_docs_exclude_retired_deployables() -> None:
    current_documents = [
        REPO_ROOT / "docs/features/cashflow_calculator/01_Feature_Cashflow_Calculator_Overview.md",
        REPO_ROOT / "docs/architecture/repository-output-shape-standard.md",
    ]
    for path in current_documents:
        content = path.read_text(encoding="utf-8")
        assert "portfolio_derived_state_service" in content
        for retired_service in RETIRED_DERIVED_STATE_SERVICES:
            assert retired_service not in content


def test_current_event_topology_sections_exclude_retired_deployables() -> None:
    rfc = (
        REPO_ROOT / "docs/RFCs/RFC-083 - Kafka Topic Naming and Event Taxonomy Standard.md"
    ).read_text(encoding="utf-8")
    current_sections = (
        _section(rfc, "### 7.5 Exact Current Producer and Consumer Matrix", "## 8."),
        _section(rfc, "### 12.3 Valuation and Day-Level Chain", "## 13."),
    )
    for section in current_sections:
        assert "portfolio_derived_state_service" in section
        for retired_service in RETIRED_DERIVED_STATE_SERVICES:
            assert f"`{retired_service}`" not in section


def test_end_state_vision_distinguishes_implemented_topology_from_pending_certification() -> None:
    vision = (REPO_ROOT / "docs/architecture/lotus-core-end-state-runtime-vision.md").read_text(
        encoding="utf-8"
    )

    assert "topology contains\n10 deployables" in vision
    assert (
        "Current consolidated deployable with separate position and portfolio modules; final "
        "acceptance remains workload- and recovery-evidence-gated."
    ) in vision
    assert "Implemented as one derived-state deployable with separate modules" in vision
    assert "Target candidate combining generator and aggregation" not in vision


def test_fx_correction_docs_preserve_verified_main_closure_and_current_rerun_requirement() -> None:
    paths = (
        REPO_ROOT / "docs/features/portfolio-derived-state/operations-runbook.md",
        REPO_ROOT / "wiki/Timeseries-and-Aggregation.md",
        REPO_ROOT / "docs/architecture/codebase-reviews/CR-1628-EFFECTIVE-DATED-FX-REVALUATION.md",
    )
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "c44d863bb849eddb7c751dab4a02d1be18a3d75f" in content
        assert "29475491036" in content
        assert "#791 is locally fixed pending" not in content

    current_surfaces = "\n".join(path.read_text(encoding="utf-8") for path in paths[:2])
    assert "current-source FX restatement rerun" in current_surfaces

    review = paths[2].read_text(encoding="utf-8")
    assert "#791 is verified closed" in review

    ledger = (REPO_ROOT / "docs/architecture/CODEBASE-REVIEW-LEDGER.md").read_text(encoding="utf-8")
    cr_1628_row = next(line for line in ledger.splitlines() if line.startswith("| CR-1628 |"))
    assert "Verified merged main" in cr_1628_row
    assert "29475491036" in cr_1628_row
    assert "PR/main/QA pending" not in cr_1628_row


def test_managed_gate_failure_receipts_remain_explicitly_non_certifying() -> None:
    paths = (
        REPO_ROOT / "docs/features/portfolio-derived-state/operations-runbook.md",
        REPO_ROOT / "wiki/Timeseries-and-Aggregation.md",
        REPO_ROOT / "REPOSITORY-ENGINEERING-CONTEXT.md",
        REPO_ROOT
        / "docs/architecture/codebase-reviews"
        / "CR-1630-TRANSACTION-EVENT-IO-AND-PARTITION-AMPLIFICATION.md",
    )
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "lotus.managed-gate-orchestration-failure.v1" in content
        assert "non_certifying_failure" in content

    ledger = (REPO_ROOT / "docs/architecture/CODEBASE-REVIEW-LEDGER.md").read_text(encoding="utf-8")
    cr_1630_row = next(line for line in ledger.splitlines() if line.startswith("| CR-1630 |"))
    assert "credential-redacting" in cr_1630_row
    assert "a8e1b0611" in cr_1630_row
    assert "44cacab60" in cr_1630_row


def test_outbox_capacity_docs_preserve_profile_attribution_and_exact_total_contracts() -> None:
    paths = (
        REPO_ROOT / "docs/features/portfolio-derived-state/operations-runbook.md",
        REPO_ROOT / "docs/operations/bank-day-load-scenario.md",
        REPO_ROOT / "wiki/Timeseries-and-Aggregation.md",
        REPO_ROOT / "REPOSITORY-ENGINEERING-CONTEXT.md",
        REPO_ROOT
        / "docs/architecture/codebase-reviews"
        / "CR-1630-TRANSACTION-EVENT-IO-AND-PARTITION-AMPLIFICATION.md",
    )
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "10,000" in content
        assert "publication-age p50/p95/p99" in content
        assert "processed-event throughput" in content
        assert "outbox-capacity-profile.v1.json" in content
        assert "outbox-capacity-profile-guard" in content
        assert "producer" in content

    review = paths[4].read_text(encoding="utf-8")
    assert "63.624ms" in review
    assert "187.430ms" in review
    assert "outbox_events_pkey" in review
