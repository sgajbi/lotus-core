from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

from src.services.query_control_plane_service.app.application.core_snapshot.market_data import (
    MarketDataObservation,
    ResolvedFxRate,
)
from src.services.query_control_plane_service.app.application.core_snapshot.reconciliation import (
    core_snapshot_source_content_hash,
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

_USE_MARKET_VALUE = object()
_USE_INSTRUMENT_CURRENCY = object()


def _row(
    security_id: str,
    *,
    business_date: date | None = date(2026, 2, 27),
    portfolio_business_date: date | None = date(2026, 2, 27),
    quantity: Decimal = Decimal("10"),
    market_price: Decimal | None = Decimal("10"),
    market_value: Decimal | None = Decimal("100"),
    market_value_local: Decimal | None | object = _USE_MARKET_VALUE,
    cost_basis: Decimal = Decimal("80"),
    cost_basis_local: Decimal = Decimal("80"),
    epoch: int = 7,
    valuation_status: str | None = "VALUED_CURRENT",
    instrument_currency: str = "USD",
    valuation_fx_rate_date: date | None = None,
    valuation_fx_rate: Decimal | None = None,
    valuation_source_currency: str | None | object = _USE_INSTRUMENT_CURRENCY,
    valuation_reporting_currency: str | None = "USD",
    market_evidence_timestamp: datetime | None = None,
    portfolio_evidence_timestamp: datetime | None = None,
    instrument_evidence_timestamp: datetime | None = None,
) -> CoreSnapshotPositionSource:
    evidence_timestamp = datetime(2026, 2, 27, 10, tzinfo=UTC)
    market_timestamp = market_evidence_timestamp or evidence_timestamp
    portfolio_timestamp = portfolio_evidence_timestamp or evidence_timestamp
    instrument_timestamp = instrument_evidence_timestamp or portfolio_timestamp
    return CoreSnapshotPositionSource(
        security_id=security_id,
        quantity=quantity,
        market_price=market_price,
        market_value=market_value,
        market_value_local=(
            market_value
            if market_value_local is _USE_MARKET_VALUE
            else cast(Decimal | None, market_value_local)
        ),
        cost_basis=cost_basis,
        cost_basis_local=cost_basis_local,
        epoch=epoch,
        source_created_at=market_timestamp,
        source_updated_at=market_timestamp,
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
            created_at=instrument_timestamp,
            updated_at=instrument_timestamp,
        ),
        business_date=business_date,
        valuation_status=valuation_status,
        valuation_source_currency=(
            instrument_currency
            if valuation_source_currency is _USE_INSTRUMENT_CURRENCY
            else cast(str | None, valuation_source_currency)
        ),
        valuation_reporting_currency=valuation_reporting_currency,
        valuation_fx_rate_date=valuation_fx_rate_date,
        valuation_fx_rate=valuation_fx_rate,
        portfolio_fact_created_at=portfolio_timestamp,
        portfolio_fact_updated_at=portfolio_timestamp,
        portfolio_business_date=portfolio_business_date,
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
    portfolio_created_at: datetime | None = None,
    portfolio_updated_at: datetime | None = None,
    reporting_fx: ResolvedFxRate | None = None,
    projected_market_data: tuple[MarketDataObservation, ...] = (),
):
    return resolve_core_snapshot_source_provenance(
        portfolio_id="PORT_001",
        requested_as_of_date=requested_as_of_date,
        position_rows=tuple(rows),
        use_snapshot=use_snapshot,
        portfolio_currency=portfolio_currency,
        portfolio_created_at=portfolio_created_at,
        portfolio_updated_at=portfolio_updated_at,
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
        _row("SEC_B", portfolio_business_date=date(2026, 2, 26)),
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.PORTFOLIO_AS_OF_CONFLICT
    assert resolution.effective_as_of_date is None
    assert resolution.source_provenance.portfolio.as_of is None
    assert resolution.source_provenance.portfolio.freshness_status == "PARTIAL"


def test_source_provenance_preserves_history_date_when_snapshot_date_is_older() -> None:
    resolution = _resolve(
        _row(
            "SEC_A",
            business_date=date(2026, 2, 26),
            portfolio_business_date=date(2026, 2, 27),
        )
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.SOURCE_AS_OF_MISMATCH
    assert resolution.source_provenance.portfolio.as_of == date(2026, 2, 27)
    assert resolution.source_provenance.market_data.as_of == date(2026, 2, 26)


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


def test_market_value_correction_changes_aggregate_not_source_family_identities() -> None:
    original_row = _row("SEC_A", market_value=Decimal("100"))
    corrected_row = _row("SEC_A", market_value=Decimal("105"))
    original = _resolve(original_row)
    corrected = _resolve(corrected_row)

    assert original.source_provenance.portfolio.source_hash == (
        corrected.source_provenance.portfolio.source_hash
    )
    assert original.source_provenance.portfolio.source_id == (
        corrected.source_provenance.portfolio.source_id
    )
    assert original.source_provenance.market_data.source_hash == (
        corrected.source_provenance.market_data.source_hash
    )
    assert original.source_provenance.market_data.source_id == (
        corrected.source_provenance.market_data.source_id
    )
    assert core_snapshot_source_content_hash([original_row]) != core_snapshot_source_content_hash(
        [corrected_row]
    )


def test_holdings_change_does_not_restate_market_source_identity() -> None:
    original = _resolve(_row("SEC_A", quantity=Decimal("10"), market_value=Decimal("100"), epoch=7))
    increased = _resolve(
        _row("SEC_A", quantity=Decimal("12"), market_value=Decimal("120"), epoch=8)
    )

    assert original.source_provenance.portfolio.source_hash != (
        increased.source_provenance.portfolio.source_hash
    )
    assert original.source_provenance.market_data.source_hash == (
        increased.source_provenance.market_data.source_hash
    )
    assert original.source_provenance.market_data.source_id == (
        increased.source_provenance.market_data.source_id
    )


def test_split_revaluation_changes_market_source_identity() -> None:
    original = _resolve(
        _row(
            "SEC_A",
            quantity=Decimal("10"),
            market_price=Decimal("10"),
            market_value=Decimal("100"),
        )
    )
    split_adjusted = _resolve(
        _row(
            "SEC_A",
            quantity=Decimal("20"),
            market_price=Decimal("5"),
            market_value=Decimal("100"),
        )
    )

    assert original.source_provenance.market_data.source_hash != (
        split_adjusted.source_provenance.market_data.source_hash
    )
    assert original.source_provenance.market_data.source_id != (
        split_adjusted.source_provenance.market_data.source_id
    )


def test_source_provenance_exposes_matching_stale_date_without_claiming_readiness() -> None:
    stale_date = date(2026, 2, 26)
    resolution = _resolve(
        _row(
            "SEC_A",
            business_date=stale_date,
            portfolio_business_date=stale_date,
        ),
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


def test_source_provenance_rejects_nonflat_snapshot_without_market_price() -> None:
    resolution = _resolve(_row("SEC_A", market_price=None))

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.effective_as_of_date is None
    assert resolution.source_provenance.market_data.as_of is None
    assert resolution.source_provenance.market_data.freshness_status == "UNAVAILABLE"


def test_source_provenance_rejects_nonflat_snapshot_without_local_market_value() -> None:
    resolution = _resolve(_row("SEC_A", market_value_local=None))

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.effective_as_of_date is None
    assert resolution.source_provenance.market_data.as_of is None
    assert resolution.source_provenance.market_data.freshness_status == "UNAVAILABLE"


def test_source_family_timestamps_follow_their_own_authoritative_evidence() -> None:
    portfolio_timestamp = datetime(2026, 2, 27, 8, tzinfo=UTC)
    market_timestamp = datetime(2026, 2, 27, 11, tzinfo=UTC)

    resolution = _resolve(
        _row(
            "SEC_A",
            market_evidence_timestamp=market_timestamp,
            portfolio_evidence_timestamp=portfolio_timestamp,
        )
    )

    assert resolution.source_provenance.portfolio.valuation_timestamp == portfolio_timestamp
    assert resolution.source_provenance.market_data.valuation_timestamp == market_timestamp


def test_portfolio_timestamp_includes_mutable_instrument_evidence() -> None:
    original_timestamp = datetime(2026, 2, 27, 8, tzinfo=UTC)
    corrected_timestamp = datetime(2026, 2, 27, 12, tzinfo=UTC)
    original = _resolve(
        _row(
            "SEC_A",
            portfolio_evidence_timestamp=original_timestamp,
            instrument_evidence_timestamp=original_timestamp,
        )
    )
    corrected_row = _row(
        "SEC_A",
        portfolio_evidence_timestamp=original_timestamp,
        instrument_evidence_timestamp=corrected_timestamp,
    )
    corrected_row = replace(
        corrected_row,
        instrument=replace(corrected_row.instrument, sector="FINANCIALS"),
    )
    corrected = _resolve(corrected_row)

    assert original.source_provenance.portfolio.source_hash != (
        corrected.source_provenance.portfolio.source_hash
    )
    assert corrected.source_provenance.portfolio.valuation_timestamp == corrected_timestamp


def test_portfolio_currency_correction_changes_portfolio_identity_and_timestamp() -> None:
    corrected_timestamp = datetime(2026, 2, 27, 12, tzinfo=UTC)
    row = _row("SEC_A")

    original = _resolve(row, portfolio_currency="USD")
    corrected = _resolve(
        row,
        portfolio_currency="GBP",
        portfolio_updated_at=corrected_timestamp,
        reporting_fx=ResolvedFxRate(
            value=Decimal("1"),
            effective_as_of_date=None,
            from_currency="GBP",
            to_currency="GBP",
        ),
    )

    assert original.source_provenance.portfolio.source_hash != (
        corrected.source_provenance.portfolio.source_hash
    )
    assert corrected.source_provenance.portfolio.valuation_timestamp == corrected_timestamp


def test_market_reobservation_advances_only_market_timestamp_not_source_identity() -> None:
    portfolio_timestamp = datetime(2026, 2, 27, 8, tzinfo=UTC)
    original = _resolve(
        _row(
            "SEC_A",
            market_evidence_timestamp=datetime(2026, 2, 27, 10, tzinfo=UTC),
            portfolio_evidence_timestamp=portfolio_timestamp,
        )
    )
    reobserved = _resolve(
        _row(
            "SEC_A",
            market_evidence_timestamp=datetime(2026, 2, 27, 12, tzinfo=UTC),
            portfolio_evidence_timestamp=portfolio_timestamp,
        )
    )

    assert original.source_provenance.portfolio == reobserved.source_provenance.portfolio
    assert original.source_provenance.market_data.source_id == (
        reobserved.source_provenance.market_data.source_id
    )
    assert original.source_provenance.market_data.source_hash == (
        reobserved.source_provenance.market_data.source_hash
    )
    assert original.source_provenance.market_data.valuation_timestamp < (
        reobserved.source_provenance.market_data.valuation_timestamp
    )


def test_projected_market_observation_advances_market_timestamp() -> None:
    observation_timestamp = datetime(2026, 2, 27, 13, tzinfo=UTC)
    resolution = _resolve(
        _row("SEC_A"),
        projected_market_data=(
            MarketDataObservation(
                observation_type="MARKET_PRICE",
                source_key="SEC_A",
                value=Decimal("11"),
                effective_as_of_date=date(2026, 2, 27),
                currency="USD",
                evidence_timestamp=observation_timestamp,
            ),
        ),
    )

    assert resolution.source_provenance.market_data.valuation_timestamp == observation_timestamp


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
            valuation_fx_rate=Decimal("1.35"),
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


def test_source_provenance_rejects_baseline_fx_date_without_exact_rate() -> None:
    resolution = _resolve(
        _row(
            "SEC_EUR",
            instrument_currency="EUR",
            valuation_fx_rate_date=date(2026, 2, 27),
        ),
        portfolio_currency="USD",
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.effective_as_of_date is None
    assert resolution.source_provenance.market_data.as_of is None


def test_source_provenance_accepts_exact_date_baseline_fx() -> None:
    resolution = _resolve(
        _row(
            "SEC_EUR",
            instrument_currency="EUR",
            valuation_fx_rate_date=date(2026, 2, 27),
            valuation_fx_rate=Decimal("1.35"),
        ),
        portfolio_currency="USD",
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.READY
    assert resolution.reason_code is CoreSnapshotValuationReason.SOURCE_EVIDENCE_READY
    assert resolution.effective_as_of_date == date(2026, 2, 27)


def test_source_provenance_uses_persisted_currency_pair_after_master_data_correction() -> None:
    original = _resolve(
        _row(
            "SEC_EUR",
            instrument_currency="EUR",
            valuation_fx_rate_date=date(2026, 2, 27),
            valuation_fx_rate=Decimal("1.35"),
        ),
        portfolio_currency="USD",
    )
    relabeled_master = _resolve(
        _row(
            "SEC_EUR",
            instrument_currency="GBP",
            valuation_source_currency="EUR",
            valuation_fx_rate_date=date(2026, 2, 27),
            valuation_fx_rate=Decimal("1.35"),
        ),
        portfolio_currency="USD",
    )

    assert relabeled_master.supportability is CoreSnapshotValuationSupportability.READY
    assert original.source_provenance.market_data.source_hash == (
        relabeled_master.source_provenance.market_data.source_hash
    )
    assert original.source_provenance.market_data.source_id == (
        relabeled_master.source_provenance.market_data.source_id
    )


def test_source_provenance_rejects_missing_valuation_currency_pair() -> None:
    resolution = _resolve(
        _row(
            "SEC_A",
            valuation_source_currency=None,
            valuation_reporting_currency=None,
        )
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.source_provenance.market_data.as_of is None


def test_source_provenance_rejects_changed_portfolio_reporting_currency() -> None:
    resolution = _resolve(
        _row(
            "SEC_A",
            valuation_source_currency="USD",
            valuation_reporting_currency="EUR",
        ),
        portfolio_currency="USD",
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.source_provenance.market_data.as_of is None


def test_market_source_identity_changes_with_same_date_baseline_fx_correction() -> None:
    original = _resolve(
        _row(
            "SEC_EUR",
            instrument_currency="EUR",
            valuation_fx_rate_date=date(2026, 2, 27),
            valuation_fx_rate=Decimal("1.35"),
        ),
        portfolio_currency="USD",
    )
    corrected = _resolve(
        _row(
            "SEC_EUR",
            instrument_currency="EUR",
            valuation_fx_rate_date=date(2026, 2, 27),
            valuation_fx_rate=Decimal("1.36"),
        ),
        portfolio_currency="USD",
    )

    assert original.source_provenance.portfolio.source_hash == (
        corrected.source_provenance.portfolio.source_hash
    )
    assert original.source_provenance.market_data.source_hash != (
        corrected.source_provenance.market_data.source_hash
    )
    assert original.source_provenance.market_data.source_id != (
        corrected.source_provenance.market_data.source_id
    )


def test_source_provenance_does_not_fabricate_fx_for_flat_position() -> None:
    resolution = _resolve(
        _row(
            "SEC_EUR",
            instrument_currency="EUR",
            quantity=Decimal("0"),
            market_price=None,
            cost_basis=Decimal("0"),
            cost_basis_local=Decimal("0"),
            market_value=Decimal("0"),
        ),
        portfolio_currency="USD",
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.READY
    assert resolution.reason_code is CoreSnapshotValuationReason.SOURCE_EVIDENCE_READY
    assert resolution.effective_as_of_date == date(2026, 2, 27)


def test_source_provenance_rejects_unpriced_flat_position_with_nonzero_value() -> None:
    resolution = _resolve(
        _row(
            "SEC_ZERO_INVALID",
            quantity=Decimal("0"),
            market_price=None,
            cost_basis=Decimal("0"),
            cost_basis_local=Decimal("0"),
            market_value=Decimal("1"),
        )
    )

    assert resolution.supportability is CoreSnapshotValuationSupportability.UNAVAILABLE
    assert resolution.reason_code is CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    assert resolution.source_provenance.market_data.as_of is None
