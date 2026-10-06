"""Replay one booked transaction through the canonical transaction publisher."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from decimal import Decimal
from itertools import product
from types import MappingProxyType, SimpleNamespace
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
    load_transaction_fee_receipts,
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
    return _qualify_transaction_fee_source(
        canonical,
        costs,
        raw_sources,
        receipts,
        allow_retained_receipt=allow_retained_receipt,
        derived_financial=derived_financial,
    )


def _qualify_transaction_fee_source(
    canonical: Mapping[str, Any],
    costs: Sequence[Mapping[str, Any]],
    raw_sources: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
    *,
    allow_retained_receipt: bool,
    derived_financial: bool,
    preparation: _FeeAuthorityPreparation | None = None,
) -> dict[str, Decimal | None]:
    original = _qualify_original_fee_source(canonical, costs, raw_sources, derived_financial)
    if original.projection is not None:
        return dict(original.projection)
    if allow_retained_receipt:
        return _qualify_retained_fee_presence(
            canonical,
            original.positive,
            receipts,
            derived_financial=derived_financial,
            preparation=preparation,
        )
    raise ValueError("Original named fee presence cannot be recovered")


@dataclass(frozen=True, slots=True)
class _OriginalFeeQualification:
    """Complete original-source examination; absence alone permits receipt lookup."""

    positive: Mapping[str, Decimal]
    projection: Mapping[str, Decimal | None] | None


def _qualify_original_fee_source(
    canonical: Mapping[str, Any],
    costs: Sequence[Mapping[str, Any]],
    raw_sources: Sequence[Mapping[str, Any]],
    derived_financial: bool,
) -> _OriginalFeeQualification:
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
    if not qualified:
        return _OriginalFeeQualification(MappingProxyType(positive), None)
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
    return _OriginalFeeQualification(MappingProxyType(positive), MappingProxyType(projections[0]))


def _receipt_scope_keys(canonical: Mapping[str, Any]) -> tuple[str, str]:
    booked = to_booked_transaction_from_record(canonical)
    identity = build_transaction_semantic_identity(
        replace(booked, transaction_fx_rate_origin="SOURCE_BOOKED")
    )
    return identity.legacy_semantic_key, identity.semantic_key


class _FeeAuthorityPreparation:
    """Reuse one row's exact hypotheses within a batch, never its financial authority."""

    def __init__(self) -> None:
        self._canonical: dict[str, Any] | None = None
        self._positive: dict[str, Decimal] | None = None
        self._scopes: tuple[str, str] | None = None
        self._corrections: tuple[tuple[str, str, Mapping[str, Decimal | None]], ...] | None = None

    def _sync(self, canonical: Mapping[str, Any]) -> None:
        if self._canonical != canonical:
            self._canonical = deepcopy(dict(canonical))
            self._positive = None
            self._scopes = None
            self._corrections = None

    def scope_keys(self, canonical: Mapping[str, Any]) -> tuple[str, str]:
        self._sync(canonical)
        if self._scopes is None:
            self._scopes = _receipt_scope_keys(canonical)
        return self._scopes

    def correction_hypotheses(
        self, canonical: Mapping[str, Any], positive: Mapping[str, Decimal]
    ) -> tuple[tuple[str, str, Mapping[str, Decimal | None]], ...]:
        self._sync(canonical)
        if self._positive != positive or self._corrections is None:
            self._positive = dict(positive)
            self._corrections = tuple(
                (key, fingerprint, MappingProxyType(dict(projection)))
                for key, fingerprint, projection in _correction_fee_hypotheses(canonical, positive)
            )
        return self._corrections


def _fee_receipt_scope_keys(
    canonical: Mapping[str, Any], preparation: _FeeAuthorityPreparation | None
) -> tuple[str, str]:
    return preparation.scope_keys(canonical) if preparation else _receipt_scope_keys(canonical)


def _fee_correction_hypotheses(
    canonical: Mapping[str, Any],
    positive: Mapping[str, Decimal],
    preparation: _FeeAuthorityPreparation | None,
) -> Sequence[tuple[str, str, Mapping[str, Decimal | None]]]:
    return (
        preparation.correction_hypotheses(canonical, positive)
        if preparation
        else _correction_fee_hypotheses(canonical, positive)
    )


def _fee_presence_hypotheses(
    positive: Mapping[str, Decimal], aggregate: Decimal | None
) -> list[dict[str, Decimal | None]]:
    """Bound presence candidates; none supplies authority before exact evidence matches."""
    missing = [name for name in TRANSACTION_FEE_COMPONENT_FIELDS if name not in positive]
    candidates = [
        dict[str, Decimal | None](positive) | dict(zip(missing, values, strict=True))
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
    preparation: _FeeAuthorityPreparation | None = None,
) -> dict[str, Decimal | None]:
    """Verify bounded hypotheses against independent committed processing evidence."""
    tenant = canonical.get("tenant_id")
    portfolio = canonical["portfolio_id"]
    v1_key, v2_key = _fee_receipt_scope_keys(canonical, preparation)
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
        corrected = _qualified_correction_fee_presence(
            canonical, positive, receipts, preparation=preparation
        )
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
    *,
    preparation: _FeeAuthorityPreparation | None = None,
) -> dict[str, Decimal | None] | None:
    """A unique exact committed correction binds this historical derived material cut."""
    qualified = []
    for key, fingerprint, projection in _fee_correction_hypotheses(
        canonical, positive, preparation
    ):
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
                qualified.append(dict(projection))
    if len(qualified) > 1:
        raise ValueError("Ambiguous committed correction fee presence")
    return qualified[0] if qualified else None


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
) -> dict[str, dict[str, Decimal | None]]:
    """Examine all original facts before requesting authority for unresolved rows."""
    costs, raw, _ = await load_transaction_fee_facts(
        session, canonical_rows, lock_sources=lock_sources
    )
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
