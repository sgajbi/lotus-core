"""Replay identity proof for the common cashflow evidence cut."""

from dataclasses import replace
from datetime import UTC, datetime

from src.services.query_service.app.repositories.cashflow_repository import (
    CashflowSourceCutEvidence,
)
from src.services.query_service.app.services.cashflow_source_cut import build_cashflow_source_cut


def _evidence() -> CashflowSourceCutEvidence:
    return CashflowSourceCutEvidence(
        portfolio_base_currency="USD",
        cashflow_revision_count=1,
        cashflow_revision_digest="cashflow-source-revision-digest",
        settlement_revision_count=1,
        settlement_revision_digest="settlement-source-revision-digest",
        materialized_at=datetime(2026, 3, 3, 12, 30, tzinfo=UTC),
    )


def test_common_cashflow_cut_is_stable_and_cross_product_comparable() -> None:
    evidence = _evidence()

    movement = build_cashflow_source_cut(
        tenant_id="tenant-a", portfolio_id="P1", as_of_date="2026-03-03", evidence=evidence
    )
    projection = build_cashflow_source_cut(
        tenant_id="tenant-a", portfolio_id="P1", as_of_date="2026-03-03", evidence=evidence
    )

    assert movement == projection
    assert movement.source_cut_id.startswith("cashflow-source-cut:")
    assert movement.materialized_at == datetime(2026, 3, 3, 12, 30, tzinfo=UTC)


def test_cashflow_restatement_changes_common_cut_and_materialization() -> None:
    original = _evidence()
    restated = replace(
        original,
        cashflow_revision_digest="restated-cashflow-source-revision-digest",
        materialized_at=datetime(2026, 3, 4, 7, tzinfo=UTC),
    )

    original_cut = build_cashflow_source_cut(
        tenant_id="tenant-a", portfolio_id="P1", as_of_date="2026-03-03", evidence=original
    )
    restated_cut = build_cashflow_source_cut(
        tenant_id="tenant-a", portfolio_id="P1", as_of_date="2026-03-03", evidence=restated
    )

    assert restated_cut.source_cut_id != original_cut.source_cut_id
    assert restated_cut.materialized_at == datetime(2026, 3, 4, 7, tzinfo=UTC)


def test_portfolio_base_currency_change_changes_common_cut() -> None:
    original = _evidence()
    recast = replace(original, portfolio_base_currency="EUR")

    original_cut = build_cashflow_source_cut(
        tenant_id="tenant-a", portfolio_id="P1", as_of_date="2026-03-03", evidence=original
    )
    recast_cut = build_cashflow_source_cut(
        tenant_id="tenant-a", portfolio_id="P1", as_of_date="2026-03-03", evidence=recast
    )

    assert recast_cut.source_cut_id != original_cut.source_cut_id


def test_empty_cashflow_window_uses_portfolio_revision_without_inventing_event_time() -> None:
    evidence = CashflowSourceCutEvidence(
        portfolio_base_currency="USD",
        cashflow_revision_count=0,
        cashflow_revision_digest="empty-cashflow-source-revision-digest",
        settlement_revision_count=0,
        settlement_revision_digest="empty-settlement-source-revision-digest",
        materialized_at=datetime(2026, 3, 1, 8, tzinfo=UTC),
    )

    cut = build_cashflow_source_cut(
        tenant_id="tenant-a", portfolio_id="P1", as_of_date="2026-03-03", evidence=evidence
    )

    assert cut.materialized_at == datetime(2026, 3, 1, 8, tzinfo=UTC)
