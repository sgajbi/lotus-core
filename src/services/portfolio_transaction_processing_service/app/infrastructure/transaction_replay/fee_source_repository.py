"""Load and freeze fee-source evidence across caller-owned database awaits."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import ProcessedEvent
from portfolio_common.reprocessing_replay import (
    TRANSACTION_REPLAY_SOURCE_INVALID,
    ReprocessingReplayError,
)
from portfolio_common.reprocessing_repository import (
    load_transaction_fee_facts,
    load_transaction_fee_receipts,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .fee_authority import (
    _fee_correction_hypotheses,
    _FeeAuthorityPreparation,
    _OriginalFeeQualification,
    _qualify_original_fee_source,
    _qualify_retained_fee_presence,
)


@dataclass(frozen=True, slots=True)
class _PendingFeeAuthority:
    canonical: Mapping[str, Any]
    original: _OriginalFeeQualification
    preparation: _FeeAuthorityPreparation


async def _load_correction_fee_receipts(
    session: AsyncSession,
    pending: Sequence[_PendingFeeAuthority],
    *,
    lock_sources: bool,
) -> list[Mapping[str, Any]]:
    """One bounded batch of exact correction keys for unresolved original sources."""
    scopes = [
        and_(
            ProcessedEvent.tenant_id == item.canonical["tenant_id"],
            ProcessedEvent.service_name == "portfolio-transaction-processing",
            ProcessedEvent.portfolio_id == item.canonical["portfolio_id"],
            ProcessedEvent.semantic_key == key,
        )
        for item in pending
        for key, _, _ in _fee_correction_hypotheses(
            item.canonical, item.original.positive, item.preparation
        )
    ]
    if not scopes:
        return []
    statement = (
        select(
            ProcessedEvent.tenant_id,
            ProcessedEvent.service_name,
            ProcessedEvent.portfolio_id,
            ProcessedEvent.semantic_key,
            ProcessedEvent.payload_fingerprint,
        )
        .where(or_(*scopes))
        .order_by(ProcessedEvent.id)
    )
    if lock_sources:
        statement = statement.with_for_update(read=True, of=ProcessedEvent)
    return [dict(receipt) for receipt in (await session.execute(statement)).mappings().all()]


def _fee_source_invalid(transaction_id: str) -> ReprocessingReplayError:
    return ReprocessingReplayError(
        "Canonical transaction fee source is unavailable or conflicting",
        failed_transaction_ids=[transaction_id],
        reason_code=TRANSACTION_REPLAY_SOURCE_INVALID,
    )


@dataclass(frozen=True, slots=True)
class _FeeSourceCapture:
    canonical: Mapping[str, Any]
    costs: Sequence[Mapping[str, Any]]
    raw: Sequence[Mapping[str, Any]]


def _assert_unchanged_fee_facts(
    canonical_rows: Sequence[Mapping[str, Any]],
    costs_by_id: Mapping[str, Sequence[Mapping[str, Any]]],
    raw_by_id: Mapping[str, Sequence[Mapping[str, Any]]],
    captured: Sequence[_FeeSourceCapture],
) -> None:
    for canonical, source in zip(canonical_rows, captured, strict=True):
        key = str(source.canonical["transaction_id"])
        if (
            canonical != source.canonical
            or costs_by_id.get(key, []) != source.costs
            or raw_by_id.get(key, []) != source.raw
        ):
            raise _fee_source_invalid(key)


async def load_qualified_transaction_fee_sources(
    session: AsyncSession,
    canonical_rows: Sequence[Mapping[str, Any]],
    *,
    lock_sources: bool = False,
    allow_retained_receipt: bool = False,
    derived_financial: bool = False,
    source_facts: tuple[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, dict[str, Decimal | None]]:
    """Examine all original facts before requesting authority for unresolved rows."""
    costs: Sequence[Mapping[str, Any]]
    raw: Sequence[Mapping[str, Any]]
    if source_facts is None:
        costs, raw, _ = await load_transaction_fee_facts(
            session, canonical_rows, lock_sources=lock_sources
        )
    else:
        costs, raw = source_facts
    costs_by_id: dict[str, list[Mapping[str, Any]]] = {}
    raw_by_id: dict[str, list[Mapping[str, Any]]] = {}
    for cost in costs:
        costs_by_id.setdefault(str(cost["transaction_id"]), []).append(cost)
    for source in raw:
        raw_by_id.setdefault(str(source["payload"]["transaction_id"]), []).append(source)
    projections: dict[str, dict[str, Decimal | None]] = {}
    pending = []
    # Detect changed inputs across receipt awaits without repeating original validation.
    captured = [
        _FeeSourceCapture(
            deepcopy(dict(row)),
            deepcopy(costs_by_id.get(str(row["transaction_id"]), [])),
            deepcopy(raw_by_id.get(str(row["transaction_id"]), [])),
        )
        for row in canonical_rows
    ]
    for canonical in canonical_rows:
        key = str(canonical["transaction_id"])
        try:
            original = _qualify_original_fee_source(
                canonical, costs_by_id.get(key, []), raw_by_id.get(key, []), derived_financial
            )
            if original.projection is not None:
                projections[key] = dict(original.projection)
            elif allow_retained_receipt:
                pending.append(
                    _PendingFeeAuthority(canonical, original, _FeeAuthorityPreparation())
                )
            else:
                raise ValueError("Original named fee presence cannot be recovered")
        except (ValueError, TypeError, KeyError) as exc:
            raise _fee_source_invalid(key) from exc
    if not pending:
        return projections
    scopes = [
        (
            str(item.canonical["tenant_id"]),
            "portfolio-transaction-processing",
            str(item.canonical["portfolio_id"]),
            key,
        )
        for item in pending
        for key in item.preparation.scope_keys(item.canonical)
    ]
    receipts = await load_transaction_fee_receipts(session, scopes, lock_sources=lock_sources)
    _assert_unchanged_fee_facts(canonical_rows, costs_by_id, raw_by_id, captured)
    if derived_financial:
        receipts.extend(
            await _load_correction_fee_receipts(session, pending, lock_sources=lock_sources)
        )
        _assert_unchanged_fee_facts(canonical_rows, costs_by_id, raw_by_id, captured)
    for item in pending:
        key = str(item.canonical["transaction_id"])
        try:
            projections[key] = _qualify_retained_fee_presence(
                item.canonical,
                item.original.positive,
                receipts,
                derived_financial=derived_financial,
                preparation=item.preparation,
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise _fee_source_invalid(key) from exc
    return projections
