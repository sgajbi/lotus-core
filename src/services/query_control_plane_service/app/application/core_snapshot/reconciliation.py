"""Extract exact reconciliation scopes from Core snapshot source records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.holdings_reconciliation import (
    FinancialReconciliationControl,
    HoldingsReconciliationScope,
    HoldingsReconciliationScopes,
    holdings_reconciliation_status,
)

from ...domain.core_snapshot import CoreSnapshotPositionSource


@dataclass(frozen=True, slots=True)
class CoreSnapshotReconciliationEvidence:
    """Deterministic exact-scope reconciliation proof for snapshot assembly."""

    status: str
    scope_content_hash: str
    control_content_hash: str
    latest_evidence_timestamp: datetime | None


def core_snapshot_reconciliation_scopes(
    rows: list[CoreSnapshotPositionSource],
) -> HoldingsReconciliationScopes:
    """Coalesce selected baseline rows by exact business date and epoch."""

    grouped: dict[tuple[date, int], tuple[datetime | None, int]] = {}
    unscoped_count = 0
    for row in rows:
        if row.business_date is None or row.epoch < 0:
            unscoped_count += 1
            continue
        key = (row.business_date, row.epoch)
        prior_timestamp, prior_count = grouped.get(key, (None, 0))
        grouped[key] = (
            _latest_timestamp(
                prior_timestamp,
                row.source_created_at,
                row.source_updated_at,
                row.state_created_at,
                row.state_updated_at,
            ),
            prior_count + 1,
        )
    return HoldingsReconciliationScopes(
        items=tuple(
            HoldingsReconciliationScope(
                business_date=business_date,
                epoch=epoch,
                latest_evidence_timestamp=latest_timestamp,
                source_row_count=row_count,
            )
            for (business_date, epoch), (latest_timestamp, row_count) in sorted(grouped.items())
        ),
        unscoped_source_row_count=unscoped_count,
    )


def core_snapshot_source_content_hash(rows: list[CoreSnapshotPositionSource]) -> str:
    """Hash the normalized source facts selected for baseline assembly."""

    payloads = [_core_snapshot_source_row_payload(row) for row in rows]
    return cast(
        str,
        canonical_content_hash(
            {
                "positions": sorted(payloads, key=canonical_content_hash),
            }
        ),
    )


def _core_snapshot_source_row_payload(row: CoreSnapshotPositionSource) -> dict[str, object]:
    return {
        "security_id": row.security_id,
        "quantity": row.quantity,
        "market_value": row.market_value,
        "market_value_local": row.market_value_local,
        "cost_basis": row.cost_basis,
        "cost_basis_local": row.cost_basis_local,
        "business_date": row.business_date,
        "epoch": row.epoch,
        "source_created_at": row.source_created_at,
        "source_updated_at": row.source_updated_at,
        "state_created_at": row.state_created_at,
        "state_updated_at": row.state_updated_at,
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
            "ultimate_parent_issuer_id": row.instrument.ultimate_parent_issuer_id,
            "ultimate_parent_issuer_name": row.instrument.ultimate_parent_issuer_name,
            "liquidity_tier": row.instrument.liquidity_tier,
        },
    }


def core_snapshot_reconciliation_evidence(
    *,
    scopes: HoldingsReconciliationScopes,
    controls: list[FinancialReconciliationControl],
) -> CoreSnapshotReconciliationEvidence:
    """Bind selected source scopes to their durable reconciliation controls."""

    ordered_controls = sorted(
        controls,
        key=lambda control: (control.business_date, control.epoch),
    )
    return CoreSnapshotReconciliationEvidence(
        status=holdings_reconciliation_status(scopes=scopes, controls=ordered_controls),
        scope_content_hash=scopes.content_hash(),
        control_content_hash=canonical_content_hash(
            {
                "controls": [
                    {
                        "business_date": control.business_date,
                        "epoch": control.epoch,
                        "status": control.status.strip().upper(),
                        "updated_at": control.updated_at,
                    }
                    for control in ordered_controls
                ]
            }
        ),
        latest_evidence_timestamp=_latest_timestamp(
            *(scope.latest_evidence_timestamp for scope in scopes.items),
            *(control.updated_at for control in ordered_controls),
        ),
    )


def _latest_timestamp(*values: datetime | None) -> datetime | None:
    return max((_as_utc(value) for value in values if value is not None), default=None)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
