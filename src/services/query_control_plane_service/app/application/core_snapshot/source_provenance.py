"""Resolve authoritative effective dates and identities for Core snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, cast

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.valuation import is_quote_independent_flat_position

from ...contracts.core_snapshot import (
    CoreSnapshotSourceProvenance,
    CoreSnapshotSourceProvenanceRecord,
    CoreSnapshotValuationReason,
    CoreSnapshotValuationSupportability,
)
from ...domain.core_snapshot import CoreSnapshotPositionSource
from .market_data import MarketDataObservation, ResolvedFxRate


@dataclass(frozen=True, slots=True)
class CoreSnapshotSourceProvenanceResolution:
    source_provenance: CoreSnapshotSourceProvenance
    effective_as_of_date: date | None
    supportability: CoreSnapshotValuationSupportability
    reason_code: CoreSnapshotValuationReason


@dataclass(frozen=True, slots=True)
class _SourceFamilyDate:
    as_of: date | None
    freshness_status: Literal["CURRENT", "STALE", "PARTIAL", "UNAVAILABLE"]
    unavailable: bool
    conflict: bool


def resolve_core_snapshot_source_provenance(
    *,
    portfolio_id: str,
    requested_as_of_date: date,
    position_rows: tuple[CoreSnapshotPositionSource, ...],
    use_snapshot: bool,
    portfolio_currency: str,
    portfolio_created_at: datetime | None = None,
    portfolio_updated_at: datetime | None = None,
    reporting_fx: ResolvedFxRate,
    projected_market_data: tuple[MarketDataObservation, ...],
) -> CoreSnapshotSourceProvenanceResolution:
    """Build source-owned dates without substituting the caller's requested date."""

    portfolio_dates = tuple(
        row.business_date if use_snapshot else row.portfolio_business_date for row in position_rows
    )
    portfolio_date = _resolve_family_date(
        dates=portfolio_dates,
        requested_as_of_date=requested_as_of_date,
        evidence_expected=len(position_rows),
    )

    valued_rows = tuple(
        row
        for row in position_rows
        if use_snapshot
        and row.market_value is not None
        and row.business_date is not None
        and row.valuation_status == "VALUED_CURRENT"
        and _has_required_baseline_market_evidence(
            row,
            portfolio_currency=portfolio_currency,
        )
    )
    market_observations = _market_observations(
        reporting_fx=reporting_fx,
        projected_market_data=projected_market_data,
    )
    baseline_market_dates = tuple(
        source_date
        for row in valued_rows
        for source_date in _baseline_market_dates(
            row=row,
            portfolio_currency=portfolio_currency,
        )
    )
    market_dates = baseline_market_dates + tuple(
        observation.effective_as_of_date for observation in market_observations
    )
    market_evidence_expected = (
        len(position_rows)
        + sum(
            int(_requires_baseline_fx_evidence(row, portfolio_currency=portfolio_currency))
            for row in position_rows
        )
        + len(market_observations)
    )
    market_date = _resolve_family_date(
        dates=market_dates,
        requested_as_of_date=requested_as_of_date,
        evidence_expected=market_evidence_expected,
    )

    portfolio_source_hash = _portfolio_source_hash(
        position_rows,
        portfolio_currency=portfolio_currency,
        use_snapshot=use_snapshot,
    )
    market_source_hash = cast(
        str,
        canonical_content_hash(
            {
                "baseline_price_evidence": [
                    {
                        "security_id": row.security_id,
                        "market_price": row.market_price,
                        "market_price_currency": row.valuation_source_currency,
                        "valuation_reporting_currency": row.valuation_reporting_currency,
                        "market_price_date": row.business_date,
                        "valuation_status": row.valuation_status,
                        "valuation_fx_rate_date": row.valuation_fx_rate_date,
                        "valuation_fx_rate": row.valuation_fx_rate,
                    }
                    for row in sorted(position_rows, key=lambda item: item.security_id)
                ],
                "market_observations": [
                    observation.lineage_payload()
                    for observation in sorted(
                        market_observations,
                        key=lambda item: (
                            item.observation_type,
                            item.source_key,
                            item.effective_as_of_date,
                        ),
                    )
                ],
                "reporting_conversion": reporting_fx.lineage_payload(),
            }
        ),
    )
    portfolio_timestamp = _latest_portfolio_timestamp(
        position_rows,
        portfolio_created_at=portfolio_created_at,
        portfolio_updated_at=portfolio_updated_at,
    )
    market_timestamp = _latest_market_timestamp(
        position_rows=position_rows,
        use_snapshot=use_snapshot,
        market_observations=market_observations,
    )
    provenance = CoreSnapshotSourceProvenance(
        portfolio=_source_record(
            source_kind="PORTFOLIO",
            portfolio_id=portfolio_id,
            source_hash=portfolio_source_hash,
            source_date=portfolio_date,
            valuation_timestamp=portfolio_timestamp,
        ),
        market_data=_source_record(
            source_kind="MARKET_DATA",
            portfolio_id=portfolio_id,
            source_hash=market_source_hash,
            source_date=market_date,
            valuation_timestamp=market_timestamp,
        ),
    )
    effective_date, supportability, reason = _valuation_readiness(
        requested_as_of_date=requested_as_of_date,
        portfolio_date=portfolio_date,
        market_date=market_date,
    )
    return CoreSnapshotSourceProvenanceResolution(
        source_provenance=provenance,
        effective_as_of_date=effective_date,
        supportability=supportability,
        reason_code=reason,
    )


def _baseline_market_dates(
    *,
    row: CoreSnapshotPositionSource,
    portfolio_currency: str,
) -> tuple[date | None, ...]:
    dates: tuple[date | None, ...] = (row.business_date,)
    if _requires_baseline_fx_evidence(row, portfolio_currency=portfolio_currency):
        return dates + (row.valuation_fx_rate_date,)
    return dates


def _requires_baseline_fx_evidence(
    row: CoreSnapshotPositionSource,
    *,
    portfolio_currency: str,
) -> bool:
    is_cross_currency = row.valuation_source_currency != portfolio_currency.strip().upper()
    return is_cross_currency and not _is_quote_independent_flat_position(row)


def _has_required_baseline_price_evidence(row: CoreSnapshotPositionSource) -> bool:
    if _is_quote_independent_flat_position(row):
        return bool(row.market_value == 0 and row.market_value_local == 0)
    return row.market_price is not None


def _has_required_baseline_market_evidence(
    row: CoreSnapshotPositionSource,
    *,
    portfolio_currency: str,
) -> bool:
    if row.market_value_local is None:
        return False
    if not _has_required_baseline_currency_evidence(
        row,
        portfolio_currency=portfolio_currency,
    ):
        return False
    if not _has_required_baseline_price_evidence(row):
        return False
    if _requires_baseline_fx_evidence(row, portfolio_currency=portfolio_currency):
        return bool(
            row.valuation_fx_rate_date is not None
            and row.valuation_fx_rate is not None
            and row.valuation_fx_rate > 0
        )
    return row.valuation_fx_rate_date is None and row.valuation_fx_rate is None


def _has_required_baseline_currency_evidence(
    row: CoreSnapshotPositionSource,
    *,
    portfolio_currency: str,
) -> bool:
    source_currency = str(row.valuation_source_currency or "").strip().upper()
    reporting_currency = str(row.valuation_reporting_currency or "").strip().upper()
    return bool(
        len(source_currency) == 3
        and len(reporting_currency) == 3
        and reporting_currency == portfolio_currency.strip().upper()
    )


def _is_quote_independent_flat_position(row: CoreSnapshotPositionSource) -> bool:
    return bool(
        is_quote_independent_flat_position(
            quantity=row.quantity,
            cost_basis_reporting=row.cost_basis,
            cost_basis_local=row.cost_basis_local,
        )
    )


def _portfolio_source_hash(
    position_rows: tuple[CoreSnapshotPositionSource, ...],
    *,
    portfolio_currency: str,
    use_snapshot: bool,
) -> str:
    return cast(
        str,
        canonical_content_hash(
            {
                "portfolio_currency": portfolio_currency.strip().upper(),
                "positions": [
                    {
                        "security_id": row.security_id,
                        "quantity": row.quantity,
                        "cost_basis": row.cost_basis,
                        "cost_basis_local": row.cost_basis_local,
                        "snapshot_business_date": row.business_date if use_snapshot else None,
                        "portfolio_business_date": row.portfolio_business_date,
                        "epoch": row.epoch,
                        "instrument": {
                            "security_id": row.instrument.security_id,
                            "name": row.instrument.name,
                            "currency": row.instrument.currency,
                            "asset_class": row.instrument.asset_class,
                            "sector": row.instrument.sector,
                            "country_of_risk": row.instrument.country_of_risk,
                            "isin": row.instrument.isin,
                            "issuer_id": row.instrument.issuer_id,
                            "issuer_name": row.instrument.issuer_name,
                            "ultimate_parent_issuer_id": (row.instrument.ultimate_parent_issuer_id),
                            "ultimate_parent_issuer_name": (
                                row.instrument.ultimate_parent_issuer_name
                            ),
                            "liquidity_tier": row.instrument.liquidity_tier,
                        },
                    }
                    for row in sorted(position_rows, key=lambda item: item.security_id)
                ],
            }
        ),
    )


def _market_observations(
    *,
    reporting_fx: ResolvedFxRate,
    projected_market_data: tuple[MarketDataObservation, ...],
) -> tuple[MarketDataObservation, ...]:
    reporting_observation = reporting_fx.observation()
    if reporting_observation is None:
        return projected_market_data
    return projected_market_data + (reporting_observation,)


def _resolve_family_date(
    *,
    dates: tuple[date | None, ...],
    requested_as_of_date: date,
    evidence_expected: int,
) -> _SourceFamilyDate:
    available_dates = {value for value in dates if value is not None}
    if (
        evidence_expected == 0
        or len(dates) != evidence_expected
        or len(available_dates) == 0
        or any(value is None for value in dates)
    ):
        return _SourceFamilyDate(None, "UNAVAILABLE", unavailable=True, conflict=False)
    if len(available_dates) != 1:
        return _SourceFamilyDate(None, "PARTIAL", unavailable=False, conflict=True)
    resolved = next(iter(available_dates))
    return _SourceFamilyDate(
        as_of=resolved,
        freshness_status="CURRENT" if resolved == requested_as_of_date else "STALE",
        unavailable=False,
        conflict=False,
    )


def _valuation_readiness(
    *,
    requested_as_of_date: date,
    portfolio_date: _SourceFamilyDate,
    market_date: _SourceFamilyDate,
) -> tuple[
    date | None,
    CoreSnapshotValuationSupportability,
    CoreSnapshotValuationReason,
]:
    unavailable = CoreSnapshotValuationSupportability.UNAVAILABLE
    if portfolio_date.unavailable:
        return None, unavailable, CoreSnapshotValuationReason.PORTFOLIO_AS_OF_UNAVAILABLE
    if portfolio_date.conflict:
        return None, unavailable, CoreSnapshotValuationReason.PORTFOLIO_AS_OF_CONFLICT
    if market_date.unavailable:
        return None, unavailable, CoreSnapshotValuationReason.MARKET_DATA_AS_OF_UNAVAILABLE
    if market_date.conflict:
        return None, unavailable, CoreSnapshotValuationReason.MARKET_DATA_AS_OF_CONFLICT
    if portfolio_date.as_of != market_date.as_of:
        return None, unavailable, CoreSnapshotValuationReason.SOURCE_AS_OF_MISMATCH
    effective_date = portfolio_date.as_of
    if effective_date != requested_as_of_date:
        return effective_date, unavailable, CoreSnapshotValuationReason.SOURCE_AS_OF_STALE
    return (
        effective_date,
        CoreSnapshotValuationSupportability.READY,
        CoreSnapshotValuationReason.SOURCE_EVIDENCE_READY,
    )


def _source_record(
    *,
    source_kind: Literal["PORTFOLIO", "MARKET_DATA"],
    portfolio_id: str,
    source_hash: str,
    source_date: _SourceFamilyDate,
    valuation_timestamp: datetime | None,
) -> CoreSnapshotSourceProvenanceRecord:
    return CoreSnapshotSourceProvenanceRecord(
        source_kind=source_kind,
        source_id=(
            f"lotus-core:portfolio-state-snapshot:{source_kind.lower()}:"
            f"{portfolio_id}:{source_hash[:24]}"
        ),
        as_of=source_date.as_of,
        source_hash=source_hash,
        valuation_timestamp=valuation_timestamp,
        freshness_status=source_date.freshness_status,
    )


def _latest_portfolio_timestamp(
    rows: tuple[CoreSnapshotPositionSource, ...],
    *,
    portfolio_created_at: datetime | None,
    portfolio_updated_at: datetime | None,
) -> datetime | None:
    row_timestamps = (
        timestamp
        for row in rows
        for timestamp in (
            row.portfolio_fact_created_at,
            row.portfolio_fact_updated_at,
            row.instrument.created_at,
            row.instrument.updated_at,
        )
        if timestamp is not None
    )
    return max(
        (
            timestamp
            for timestamp in (*row_timestamps, portfolio_created_at, portfolio_updated_at)
            if timestamp is not None
        ),
        default=None,
    )


def _latest_market_timestamp(
    *,
    position_rows: tuple[CoreSnapshotPositionSource, ...],
    use_snapshot: bool,
    market_observations: tuple[MarketDataObservation, ...],
) -> datetime | None:
    baseline_timestamps = (
        timestamp
        for row in position_rows
        for timestamp in (row.source_created_at, row.source_updated_at)
        if use_snapshot and timestamp is not None
    )
    observation_timestamps = (
        observation.evidence_timestamp
        for observation in market_observations
        if observation.evidence_timestamp is not None
    )
    return max((*baseline_timestamps, *observation_timestamps), default=None)
