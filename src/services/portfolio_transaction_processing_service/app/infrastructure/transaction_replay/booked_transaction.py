"""Replay one booked transaction through the canonical transaction publisher."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from itertools import product
from types import SimpleNamespace
from typing import Any, Protocol

from portfolio_common.database_models import ProcessedEvent
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.transaction import transaction_payload_fingerprint
from portfolio_common.domain.transaction.fee_components import TRANSACTION_FEE_COMPONENT_FIELDS
from portfolio_common.events import TransactionEvent
from portfolio_common.reprocessing_replay import (
    TRANSACTION_REPLAY_SOURCE_FIELD_NAMES,
    TRANSACTION_REPLAY_SOURCE_INVALID,
    ReprocessingReplayError,
)
from portfolio_common.reprocessing_repository import (
    load_transaction_fee_facts,
    load_transaction_replay_rows,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ...application import (
    BookedTransactionReplayDependencyUnavailable,
    BookedTransactionReplayInvariantViolation,
)
from ...domain import build_transaction_semantic_identity
from ...domain.transaction.semantic_identity import build_transaction_correction_identity
from ..transaction_mapping.booked_transaction import (
    to_booked_transaction,
    to_booked_transaction_from_record,
)


class CanonicalTransactionReplayer(Protocol):
    """Describe the canonical publisher used by the replay adapter."""

    async def reprocess_transactions_by_ids(
        self,
        transaction_ids: list[str],
        *,
        correlation_id: str | None = None,
        repair_delivery_id: str | None = None,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class SqlAlchemyBookedTransactionReplayAdapter:
    """Replay one transaction using a fresh SQLAlchemy session."""

    session_factory: Callable[[], AsyncSession]
    replayer_factory: Callable[[AsyncSession], CanonicalTransactionReplayer]

    async def replay_booked_transaction(
        self,
        *,
        transaction_id: str,
        correlation_id: str | None,
        repair_delivery_id: str | None = None,
    ) -> bool:
        try:
            async with self.session_factory() as session:
                replayer = self.replayer_factory(session)
                if repair_delivery_id is None:
                    replayed_count = await replayer.reprocess_transactions_by_ids(
                        [transaction_id],
                        correlation_id=correlation_id,
                    )
                else:
                    replayed_count = await replayer.reprocess_transactions_by_ids(
                        [transaction_id],
                        correlation_id=correlation_id,
                        repair_delivery_id=repair_delivery_id,
                    )
        except (DBAPIError, ReprocessingReplayError) as exc:
            raise BookedTransactionReplayDependencyUnavailable(
                "Canonical booked transaction replay dependency unavailable"
            ) from exc
        if replayed_count not in {0, 1}:
            raise BookedTransactionReplayInvariantViolation(
                "Canonical booked transaction replay must publish zero or one record; "
                f"transaction_id={transaction_id}, replayed_count={replayed_count}"
            )
        return replayed_count == 1


def qualify_transaction_fee_source(
    canonical: Mapping[str, Any],
    costs: Sequence[Mapping[str, Any]],
    raw_sources: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]] = (),
    *,
    allow_retained_receipt: bool = False,
    derived_financial: bool = False,
) -> dict[str, Decimal | None]:
    """Recover exact fee presence only from original-fingerprint-qualified source facts."""
    transaction_id = str(canonical["transaction_id"])
    tenant_id = str(canonical.get("tenant_id") or "")
    fingerprint: str | None = canonical.get("payload_fingerprint")
    if not tenant_id.strip() or not fingerprint:
        raise ValueError("Original transaction fee authority is unavailable")
    payload = {
        key: value
        for key, value in canonical.items()
        if key in TRANSACTION_REPLAY_SOURCE_FIELD_NAMES
    }
    currency = normalize_currency_code(payload.get("trade_currency") or payload["currency"])
    positive = {}
    for cost in costs:
        name = str(cost["fee_type"]).strip().lower()
        amount = Decimal(cost["amount"])
        if (
            name not in TRANSACTION_FEE_COMPONENT_FIELDS
            or name in positive
            or normalize_currency_code(cost["currency"]) != currency
            or not amount.is_finite()
            or amount <= 0
        ):
            raise ValueError("Conflicting canonical named fee rows")
        positive[name] = amount

    def qualifies(original: Mapping[str, Any]) -> bool:
        if (
            str(original.get("transaction_id")) != transaction_id
            or original.get("portfolio_id") != canonical["portfolio_id"]
            or original.get("tenant_id") not in {None, tenant_id}
        ):
            return False
        event = TransactionEvent.model_validate(original)
        original_fingerprint: str = transaction_payload_fingerprint(event.model_dump(mode="python"))
        return original_fingerprint == fingerprint

    # These are the existing aggregate-only and complete named-row representations.
    # A matching original hash establishes presence; an unmatched candidate supplies no facts.
    candidates = [
        payload | dict.fromkeys(TRANSACTION_FEE_COMPONENT_FIELDS),
        payload
        | {name: positive.get(name, Decimal(0)) for name in TRANSACTION_FEE_COMPONENT_FIELDS},
    ]
    if derived_financial:
        candidates = [
            payload | fees
            for fees in _fee_presence_hypotheses(positive, canonical.get("trade_fee"))
        ]
    qualified = [candidate for candidate in candidates if qualifies(candidate)]
    for raw in raw_sources:
        original = raw["payload"]
        if raw["aggregate_id"] != canonical["portfolio_id"] or not qualifies(original):
            raise ValueError("Conflicting retained raw transaction authority")
        qualified.append(original)
    if not qualified and allow_retained_receipt:
        return _qualify_retained_fee_presence(
            canonical, positive, receipts, derived_financial=derived_financial
        )
    if not qualified:
        raise ValueError("Original named fee presence cannot be recovered")
    projections = []
    for original in qualified:
        event = TransactionEvent.model_validate(original)
        fees = {name: getattr(event, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS}
        actual_positive = {
            name: amount for name, amount in fees.items() if amount is not None and amount > 0
        }
        # The existing cost engine represents an aggregate-only fee as one brokerage row.
        # It remains a derived allocation; the qualified original still carries five Nones.
        aggregate_allocation = (
            all(amount is None for amount in fees.values())
            and event.trade_fee is not None
            and positive == {"brokerage": event.trade_fee}
        )
        if (
            (actual_positive != positive and not aggregate_allocation)
            or normalize_currency_code(event.trade_currency or event.currency) != currency
            or (not derived_financial and event.trade_fee != canonical.get("trade_fee"))
        ):
            raise ValueError("Original fee amounts conflict with canonical ledger")
        projection = fees | {"trade_fee": event.trade_fee}
        if projection not in projections:
            projections.append(projection)
    if len(projections) != 1:
        raise ValueError("Ambiguous original named fee presence")
    return projections[0]


def _receipt_scope_keys(canonical: Mapping[str, Any]) -> tuple[str, str]:
    booked = to_booked_transaction_from_record(canonical)
    identity = build_transaction_semantic_identity(
        replace(booked, transaction_fx_rate_origin="SOURCE_BOOKED")
    )
    return identity.legacy_semantic_key, identity.semantic_key


def _fee_presence_hypotheses(
    positive: Mapping[str, Decimal], aggregate: Decimal | None
) -> list[dict[str, Decimal | None]]:
    """Bound presence candidates; none supplies authority before exact evidence matches."""
    missing = [name for name in TRANSACTION_FEE_COMPONENT_FIELDS if name not in positive]
    candidates = [
        dict(positive) | dict(zip(missing, values, strict=True))
        for values in product((None, Decimal(0)), repeat=len(missing))
    ]
    if positive == {"brokerage": aggregate} and aggregate is not None and aggregate > 0:
        candidates.append(dict.fromkeys(TRANSACTION_FEE_COMPONENT_FIELDS))
    return candidates


def _qualify_retained_fee_presence(
    canonical: Mapping[str, Any],
    positive: Mapping[str, Decimal],
    receipts: Sequence[Mapping[str, Any]],
    *,
    derived_financial: bool = False,
) -> dict[str, Decimal | None]:
    """Verify bounded hypotheses against independent committed processing evidence."""
    tenant = canonical.get("tenant_id")
    portfolio = canonical["portfolio_id"]
    v1_key, v2_key = _receipt_scope_keys(canonical)
    admissible = [
        receipt
        for receipt in receipts
        if receipt["tenant_id"] == tenant
        and receipt["portfolio_id"] == portfolio
        and receipt["service_name"] == "portfolio-transaction-processing"
        and receipt["semantic_key"] in {v1_key, v2_key}
    ]
    if not admissible:
        raise ValueError("Exact retained material receipt is unavailable")
    if any(not receipt["payload_fingerprint"] for receipt in admissible):
        raise ValueError("Retained material receipt is incomplete")
    source_booked = canonical.get("transaction_fx_rate_origin") == "SOURCE_BOOKED"
    has_v2 = any(receipt["semantic_key"] == v2_key for receipt in admissible)
    if has_v2 != source_booked:
        raise ValueError("Retained source FX version cannot be downgraded or inferred")
    if derived_financial:
        corrected = _qualified_correction_fee_presence(canonical, positive, receipts)
        if corrected is not None:
            return corrected
    aggregate = canonical.get("trade_fee")
    component_candidates = _fee_presence_hypotheses(positive, aggregate)
    aggregates: tuple[Decimal | None, ...] = (aggregate,)
    if not positive and aggregate in {None, Decimal(0)}:
        aggregates = (None, Decimal(0))
    qualified = []
    payload = {
        key: value
        for key, value in canonical.items()
        if key in TRANSACTION_REPLAY_SOURCE_FIELD_NAMES
    }
    for fees in component_candidates:
        for trade_fee in aggregates:
            # Preserve the exact aggregate hypothesis rather than event-validator coercion.
            event = TransactionEvent.model_validate(payload | fees | {"trade_fee": trade_fee})
            if not derived_financial and event.trade_fee != trade_fee:
                continue
            identity = build_transaction_semantic_identity(to_booked_transaction(event))
            fingerprints = {
                identity.semantic_key: identity.payload_fingerprint,
                identity.legacy_semantic_key: identity.legacy_payload_fingerprint,
            }
            if all(
                fingerprints.get(receipt["semantic_key"]) == receipt["payload_fingerprint"]
                for receipt in admissible
            ):
                projection = fees | {"trade_fee": event.trade_fee}
                if projection not in qualified:
                    qualified.append(projection)
    if len(qualified) != 1:
        raise ValueError("Retained fee presence is absent, conflicting or ambiguous")
    return qualified[0]


def _correction_fee_hypotheses(
    canonical: Mapping[str, Any], positive: Mapping[str, Decimal]
) -> list[tuple[str, str, dict[str, Decimal | None]]]:
    """Compute exact current correction keys; hypotheses alone confer no authority."""
    aggregate = canonical.get("trade_fee")
    aggregates = (
        (None, Decimal(0)) if not positive and aggregate in {None, Decimal(0)} else (aggregate,)
    )
    payload = {
        key: value
        for key, value in canonical.items()
        if key in TRANSACTION_REPLAY_SOURCE_FIELD_NAMES
    }
    candidates = []
    for fees in _fee_presence_hypotheses(positive, aggregate):
        for trade_fee in aggregates:
            event = TransactionEvent.model_validate(payload | fees | {"trade_fee": trade_fee})
            identity = build_transaction_correction_identity(to_booked_transaction(event))
            candidate = (
                identity.semantic_key,
                identity.payload_fingerprint,
                fees | {"trade_fee": event.trade_fee},
            )
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _qualified_correction_fee_presence(
    canonical: Mapping[str, Any],
    positive: Mapping[str, Decimal],
    receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Decimal | None] | None:
    """A unique exact committed correction binds this historical derived material cut."""
    qualified = []
    for key, fingerprint, projection in _correction_fee_hypotheses(canonical, positive):
        matches = [
            receipt
            for receipt in receipts
            if receipt["tenant_id"] == canonical["tenant_id"]
            and receipt["portfolio_id"] == canonical["portfolio_id"]
            and receipt["service_name"] == "portfolio-transaction-processing"
            and receipt["semantic_key"] == key
        ]
        if matches:
            if len(matches) != 1 or matches[0]["payload_fingerprint"] != fingerprint:
                raise ValueError("Conflicting committed correction authority")
            if projection not in qualified:
                qualified.append(projection)
    if len(qualified) > 1:
        raise ValueError("Ambiguous committed correction fee presence")
    return qualified[0] if qualified else None


async def _load_correction_fee_receipts(
    session: AsyncSession,
    canonical_rows: Sequence[Mapping[str, Any]],
    costs_by_id: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    lock_sources: bool,
) -> list[Mapping[str, Any]]:
    """One additional bounded batch after fee rows make exact correction keys computable."""
    scopes = [
        and_(
            ProcessedEvent.tenant_id == row["tenant_id"],
            ProcessedEvent.service_name == "portfolio-transaction-processing",
            ProcessedEvent.portfolio_id == row["portfolio_id"],
            ProcessedEvent.semantic_key == key,
        )
        for row in canonical_rows
        for key, _, _ in _correction_fee_hypotheses(
            row,
            {
                str(cost["fee_type"]).strip().lower(): Decimal(cost["amount"])
                for cost in costs_by_id.get(str(row["transaction_id"]), [])
            },
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
    return list((await session.execute(statement)).mappings().all())


async def load_qualified_transaction_fee_sources(
    session: AsyncSession,
    canonical_rows: Sequence[Mapping[str, Any]],
    *,
    lock_sources: bool = False,
    allow_retained_receipt: bool = False,
    derived_financial: bool = False,
) -> dict[str, dict[str, Decimal | None]]:
    """Qualify the complete bounded batch before its first publication."""
    scopes = (
        [
            (
                str(row["tenant_id"]),
                "portfolio-transaction-processing",
                str(row["portfolio_id"]),
                key,
            )
            for row in canonical_rows
            for key in _receipt_scope_keys(row)
        ]
        if allow_retained_receipt
        else []
    )
    costs, raw, receipts = await load_transaction_fee_facts(
        session, canonical_rows, lock_sources=lock_sources, receipt_scopes=scopes
    )
    costs_by_id: dict[str, list[Mapping[str, Any]]] = {}
    raw_by_id: dict[str, list[Mapping[str, Any]]] = {}
    receipts_by_scope: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for cost in costs:
        costs_by_id.setdefault(str(cost["transaction_id"]), []).append(cost)
    if allow_retained_receipt and derived_financial:
        receipts.extend(
            await _load_correction_fee_receipts(
                session, canonical_rows, costs_by_id, lock_sources=lock_sources
            )
        )
    for source in raw:
        raw_by_id.setdefault(str(source["payload"]["transaction_id"]), []).append(source)
    for receipt in receipts:
        scope = (
            receipt["tenant_id"],
            receipt["service_name"],
            receipt["portfolio_id"],
            receipt["semantic_key"],
        )
        receipts_by_scope.setdefault(scope, []).append(receipt)
    projections = {}
    for canonical in canonical_rows:
        key = str(canonical["transaction_id"])
        try:
            projections[key] = qualify_transaction_fee_source(
                canonical,
                costs_by_id.get(key, []),
                raw_by_id.get(key, []),
                [
                    receipt
                    for semantic_key in (
                        _receipt_scope_keys(canonical)
                        + tuple(
                            correction_key
                            for correction_key, _, _ in _correction_fee_hypotheses(
                                canonical,
                                {
                                    str(cost["fee_type"]).strip().lower(): Decimal(cost["amount"])
                                    for cost in costs_by_id.get(key, [])
                                },
                            )
                        )
                        if derived_financial
                        else _receipt_scope_keys(canonical)
                    )
                    for receipt in receipts_by_scope.get(
                        (
                            canonical["tenant_id"],
                            "portfolio-transaction-processing",
                            canonical["portfolio_id"],
                            semantic_key,
                        ),
                        [],
                    )
                ]
                if allow_retained_receipt
                else [],
                allow_retained_receipt=allow_retained_receipt,
                derived_financial=derived_financial,
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise ReprocessingReplayError(
                "Canonical transaction fee source is unavailable or conflicting",
                failed_transaction_ids=[key],
                reason_code=TRANSACTION_REPLAY_SOURCE_INVALID,
            ) from exc
    return projections


@dataclass(frozen=True, slots=True)
class SqlAlchemyQualifiedTransactionReplayReader:
    """Own typed material qualification while shared SQL stays policy-neutral."""

    session: AsyncSession

    async def list_transactions_to_replay(self, transaction_ids: list[str]) -> list[Any]:
        rows = await load_transaction_replay_rows(self.session, transaction_ids, lock_sources=True)
        projections = await load_qualified_transaction_fee_sources(
            self.session, rows, lock_sources=True, allow_retained_receipt=True
        )
        return [
            SimpleNamespace(
                **{
                    key: value
                    for key, value in (dict(row) | projections[row["transaction_id"]]).items()
                    if key in TRANSACTION_REPLAY_SOURCE_FIELD_NAMES
                }
            )
            for row in rows
        ]
