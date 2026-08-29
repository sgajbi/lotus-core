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
    quantity: Decimal = Decimal("10"),
    market_value: Decimal | None = Decimal("100"),
    cost_basis: Decimal = Decimal("80"),
    cost_basis_local: Decimal = Decimal("80"),
    valuation_status: str | None = "VALUED_CURRENT",
    instrument_currency: str = "USD",
    valuation_fx_rate_date: date | None = None,
) -> CoreSnapshotPositionSource:
    evidence_timestamp = datetime(2026, 2, 27, 10, tzinfo=UTC)
    return CoreSnapshotPositionSource(
        security_id=security_id,
        quantity=quantity,
        market_value=market_value,
        market_value_local=market_value,
        cost_basis=cost_basis,
        cost_basis_local=cost_basis_local,
        epoch=7,
        source_created_at=evidence_timestamp,
        source_updated_at=evidence_timestamp,
        state_created_at=evidence_timestamp,
        state_updated_at=evidence_timestamp,
        instrument=CoreSnapshotInstrument(
            security_id=security_id,
            name=security_id,
            currency=instrument_currency,
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
        valuation_status=valuation_status,
        valuation_fx_rate_date=valuation_fx_rate_date,
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
    portfolio_currency: str = "USD",
    reporting_fx: ResolvedFxRate | None = None,
    projected_market_data: tuple[MarketDataObservation, ...] = (),
):
    return resolve_core_snapshot_source_provenance(
        portfolio_id="PORT_001",
        requested_as_of_date=requested_as_of_date,
        position_rows=tuple(rows),
        use_snapshot=use_snapshot,
        portfolio_currency=portfolio_currency,
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


def test_market_source_identity_changes_with_authoritative_fx_fact() -> None:
    first = _resolve(
        _row("SEC_A"),
        reporting_fx=ResolvedFxRate(
            value=Decimal("1.1"),
            effective_as_of_date=date(2026, 2, 27),
            from_currency="EUR",
            to_currency="USD",
        ),
    )
    revised = _resolve(
        _row("SEC_A"),
        reporting_fx=ResolvedFxRate(
            value=Decimal("1.2"),
            effective_as_of_date=date(2026, 2, 27),
            from_currency="EUR",
            to_currency="USD",
        ),
    )

    assert first.source_provenance.market_data.source_hash != (
        revised.source_provenance.market_data.source_hash
    )
    assert first.source_provenance.market_data.source_id != (
        revised.source_provenance.market_data.source_id
    )


def test_market_value_correction_does_not_restate_portfolio_source_identity() -> None:
    original = _resolve(_row("SEC_A", market_value=Decimal("100")))
    corrected = _resolve(_row("SEC_A", market_value=Decimal("105")))

    assert original.source_provenance.portfolio.source_hash == (
        corrected.source_provenance.portfolio.source_hash
    )
    assert original.source_provenance.portfolio.source_id == (
        corrected.source_provenance.portfolio.source_id
    )
    assert original.source_provenance.market_data.source_hash != (
        corrected.source_provenance.market_data.source_hash
    )
    assert original.source_provenance.market_data.source_id != (
        corrected.source_provenance.market_data.source_id
    )


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
    complete = _resolve(_row("SEC_A"))
    resolution = _resolve(
        _row("SEC_A"),
        _row("SEC_B", market_value=None),
    )

    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.source_provenance.market_data.as_of is None
    assert resolution.source_provenance.market_data.source_hash != (
        complete.source_provenance.market_data.source_hash
    )


def test_source_provenance_rejects_carried_forward_baseline_price() -> None:
    current = _resolve(_row("SEC_A"))
    resolution = _resolve(_row("SEC_A", valuation_status="VALUED_STALE"))

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.effective_as_of_date is None
    assert resolution.source_provenance.market_data.as_of is None
    assert resolution.source_provenance.market_data.freshness_status == "UNAVAILABLE"
    assert resolution.source_provenance.market_data.source_hash != (
        current.source_provenance.market_data.source_hash
    )


def test_source_provenance_rejects_carried_forward_baseline_fx() -> None:
    resolution = _resolve(
        _row(
            "SEC_EUR",
            instrument_currency="EUR",
            valuation_fx_rate_date=date(2026, 2, 26),
        ),
        portfolio_currency="USD",
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_CONFLICT
    assert resolution.effective_as_of_date is None
    assert resolution.source_provenance.market_data.as_of is None
    assert resolution.source_provenance.market_data.freshness_status == "PARTIAL"


def test_source_provenance_rejects_missing_baseline_fx_lineage() -> None:
    resolution = _resolve(
        _row("SEC_EUR", instrument_currency="EUR"),
        portfolio_currency="USD",
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.effective_as_of_date is None
    assert resolution.source_provenance.market_data.as_of is None
    assert resolution.source_provenance.market_data.freshness_status == "UNAVAILABLE"


def test_source_provenance_accepts_exact_date_baseline_fx() -> None:
    resolution = _resolve(
        _row(
            "SEC_EUR",
            instrument_currency="EUR",
            valuation_fx_rate_date=date(2026, 2, 27),
        ),
        portfolio_currency="USD",
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.READY
    assert resolution.reason_code is CoreSnapshotValuationReason.SOURCE_EVIDENCE_READY
    assert resolution.effective_as_of_date == date(2026, 2, 27)


def test_source_provenance_does_not_fabricate_fx_for_flat_position() -> None:
    resolution = _resolve(
        _row(
            "SEC_EUR",
            instrument_currency="EUR",
            quantity=Decimal("0"),
            cost_basis=Decimal("0"),
            cost_basis_local=Decimal("0"),
            market_value=Decimal("0"),
        ),
        portfolio_currency="USD",
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.READY
    assert resolution.reason_code is CoreSnapshotValuationReason.SOURCE_EVIDENCE_READY
    assert resolution.effective_as_of_date == date(2026, 2, 27)
