from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from src.services.query_control_plane_service.app.application.core_snapshot.market_data import (
    MarketDataObservation,
    ResolvedFxRate,
)
from src.services.query_control_plane_service.app.application.core_snapshot.source_provenance import (  # noqa: E501
    resolve_core_snapshot_source_provenance,
)
from src.services.query_control_plane_service.app.contracts.core_snapshot import (
    CoreSnapshotValuationReason,
    CoreSnapshotValuationSupportability,
)
from src.services.query_control_plane_service.app.domain.core_snapshot import (
    CoreSnapshotInstrument,
    CoreSnapshotPositionSource,
)


def _row(
    security_id: str,
    *,
    business_date: date | None = date(2026, 2, 27),
    market_value: Decimal | None = Decimal("100"),
) -> CoreSnapshotPositionSource:
    evidence_timestamp = datetime(2026, 2, 27, 10, tzinfo=UTC)
    return CoreSnapshotPositionSource(
        security_id=security_id,
        quantity=Decimal("10"),
        market_value=market_value,
        market_value_local=market_value,
        cost_basis=Decimal("80"),
        cost_basis_local=Decimal("80"),
        epoch=7,
        source_created_at=evidence_timestamp,
        source_updated_at=evidence_timestamp,
        state_created_at=evidence_timestamp,
        state_updated_at=evidence_timestamp,
        instrument=CoreSnapshotInstrument(
            security_id=security_id,
            name=security_id,
            currency="USD",
            asset_class="EQUITY",
            sector=None,
            country_of_risk=None,
            isin=None,
            issuer_id=None,
            issuer_name=None,
            ultimate_parent_issuer_id=None,
            ultimate_parent_issuer_name=None,
            liquidity_tier=None,
        ),
        business_date=business_date,
    )


def _identity_fx() -> ResolvedFxRate:
    return ResolvedFxRate(
        value=Decimal("1"),
        effective_as_of_date=None,
        from_currency="USD",
        to_currency="USD",
    )


def _resolve(
    *rows: CoreSnapshotPositionSource,
    requested_as_of_date: date = date(2026, 2, 27),
    use_snapshot: bool = True,
    reporting_fx: ResolvedFxRate | None = None,
    projected_market_data: tuple[MarketDataObservation, ...] = (),
):
    return resolve_core_snapshot_source_provenance(
        portfolio_id="PORT_001",
        requested_as_of_date=requested_as_of_date,
        position_rows=tuple(rows),
        use_snapshot=use_snapshot,
        portfolio_source_hash="a" * 64,
        reporting_fx=reporting_fx or _identity_fx(),
        projected_market_data=projected_market_data,
    )


def test_source_provenance_is_ready_only_for_coherent_exact_date_evidence() -> None:
    first = _row("SEC_B")
    second = _row("SEC_A")

    resolution = _resolve(first, second)
    reordered = _resolve(second, first)

    assert resolution.supportability is CoreSnapshotValuationSupportability.READY
    assert resolution.reason_code is CoreSnapshotValuationReason.SOURCE_EVIDENCE_READY
    assert resolution.effective_as_of_date == date(2026, 2, 27)
    assert resolution.source_provenance.portfolio.as_of == date(2026, 2, 27)
    assert resolution.source_provenance.market_data.as_of == date(2026, 2, 27)
    assert len(resolution.source_provenance.market_data.source_hash) == 64
    assert resolution.source_provenance.market_data.source_hash == (
        reordered.source_provenance.market_data.source_hash
    )
    assert resolution.source_provenance.market_data.source_id == (
        reordered.source_provenance.market_data.source_id
    )


def test_source_provenance_rejects_mixed_portfolio_business_dates() -> None:
    resolution = _resolve(
        _row("SEC_A"),
        _row("SEC_B", business_date=date(2026, 2, 26)),
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.PORTFOLIO_AS_OF_CONFLICT
    assert resolution.effective_as_of_date is None
    assert resolution.source_provenance.portfolio.as_of is None
    assert resolution.source_provenance.portfolio.freshness_status == "PARTIAL"


def test_source_provenance_rejects_history_cost_basis_as_market_evidence() -> None:
    resolution = _resolve(_row("SEC_A"), use_snapshot=False)

    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.source_provenance.portfolio.as_of == date(2026, 2, 27)
    assert resolution.source_provenance.market_data.as_of is None


def test_source_provenance_rejects_carried_forward_fx_date() -> None:
    resolution = _resolve(
        _row("SEC_A"),
        reporting_fx=ResolvedFxRate(
            value=Decimal("1.1"),
            effective_as_of_date=date(2026, 2, 26),
            from_currency="EUR",
            to_currency="USD",
        ),
    )

    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_CONFLICT
    assert resolution.source_provenance.market_data.as_of is None
    assert resolution.source_provenance.market_data.freshness_status == "PARTIAL"


def test_source_provenance_exposes_matching_stale_date_without_claiming_readiness() -> None:
    stale_date = date(2026, 2, 26)
    resolution = _resolve(
        _row("SEC_A", business_date=stale_date),
        requested_as_of_date=date(2026, 2, 27),
    )

    assert resolution.effective_as_of_date == stale_date
    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.SOURCE_AS_OF_STALE
    assert resolution.source_provenance.portfolio.freshness_status == "STALE"
    assert resolution.source_provenance.market_data.freshness_status == "STALE"


def test_source_provenance_rejects_partially_valued_snapshot() -> None:
    resolution = _resolve(
        _row("SEC_A"),
        _row("SEC_B", market_value=None),
    )

    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.source_provenance.market_data.as_of is None
