"""Resolve authoritative effective dates and identities for Core snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, cast

from portfolio_common.domain.calculation_lineage import canonical_content_hash

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
    portfolio_source_hash: str,
    reporting_fx: ResolvedFxRate,
    projected_market_data: tuple[MarketDataObservation, ...],
) -> CoreSnapshotSourceProvenanceResolution:
    """Build source-owned dates without substituting the caller's requested date."""

    portfolio_dates = tuple(row.business_date for row in position_rows)
    portfolio_date = _resolve_family_date(
        dates=portfolio_dates,
        requested_as_of_date=requested_as_of_date,
        evidence_expected=len(position_rows),
    )

    valued_rows = tuple(
        row
        for row in position_rows
        if use_snapshot and row.market_value is not None and row.business_date is not None
    )
    market_observations = _market_observations(
        reporting_fx=reporting_fx,
        projected_market_data=projected_market_data,
    )
    market_dates = tuple(row.business_date for row in valued_rows) + tuple(
        observation.effective_as_of_date for observation in market_observations
    )
    market_evidence_expected = len(position_rows) + len(market_observations)
    market_date = _resolve_family_date(
        dates=market_dates,
        requested_as_of_date=requested_as_of_date,
        evidence_expected=market_evidence_expected,
    )

    market_source_hash = cast(
        str,
        canonical_content_hash(
            {
                "position_valuations": [
                    {
                        "security_id": row.security_id,
                        "business_date": row.business_date,
                        "epoch": row.epoch,
                        "market_value": row.market_value,
                        "market_value_local": row.market_value_local,
                    }
                    for row in sorted(valued_rows, key=lambda item: item.security_id)
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
    valuation_timestamp = _latest_position_timestamp(position_rows)
    provenance = CoreSnapshotSourceProvenance(
        portfolio=_source_record(
            source_kind="PORTFOLIO",
            portfolio_id=portfolio_id,
            source_hash=portfolio_source_hash,
            source_date=portfolio_date,
            valuation_timestamp=valuation_timestamp,
        ),
        market_data=_source_record(
            source_kind="MARKET_DATA",
            portfolio_id=portfolio_id,
            source_hash=market_source_hash,
            source_date=market_date,
            valuation_timestamp=valuation_timestamp,
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


def _latest_position_timestamp(
    rows: tuple[CoreSnapshotPositionSource, ...],
) -> datetime | None:
    timestamps = (
        timestamp
        for row in rows
        for timestamp in (
            row.source_created_at,
            row.source_updated_at,
            row.state_created_at,
            row.state_updated_at,
        )
        if timestamp is not None
    )
    return max(timestamps, default=None)
