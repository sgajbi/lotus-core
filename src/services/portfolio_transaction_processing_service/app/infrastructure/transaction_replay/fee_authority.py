"""Qualify original and retained financial facts without database I/O."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from decimal import Decimal
from itertools import product
from types import MappingProxyType
from typing import Any

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.transaction import transaction_payload_fingerprint
from portfolio_common.domain.transaction.fee_components import TRANSACTION_FEE_COMPONENT_FIELDS
from portfolio_common.events import TransactionEvent
from portfolio_common.reprocessing_replay import TRANSACTION_REPLAY_SOURCE_FIELD_NAMES

from ...domain import build_transaction_semantic_identity
from ...domain.transaction.semantic_identity import build_transaction_correction_identity
from ..transaction_mapping.booked_transaction import (
    to_booked_transaction,
    to_booked_transaction_from_record,
)


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


def _original_positive_fee_rows(
    costs: Sequence[Mapping[str, Any]], currency: str
) -> dict[str, Decimal]:
    """Validate canonical positive named costs before selecting any original authority."""
    positive: dict[str, Decimal] = {}
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
    return positive


def _original_fee_event(
    original: Mapping[str, Any],
    canonical: Mapping[str, Any],
    transaction_id: str,
    tenant_id: str,
    fingerprint: str,
) -> TransactionEvent | None:
    """Carry the model only after exact original identity and fingerprint qualification."""
    if (
        str(original.get("transaction_id")) != transaction_id
        or original.get("portfolio_id") != canonical["portfolio_id"]
        or original.get("tenant_id") not in {None, tenant_id}
    ):
        return None
    event = TransactionEvent.model_validate(original)
    original_fingerprint: str = transaction_payload_fingerprint(event.model_dump(mode="python"))
    return event if original_fingerprint == fingerprint else None


def _original_fee_projection(
    events: Sequence[TransactionEvent],
    positive: Mapping[str, Decimal],
    currency: str,
    trade_fee: Any,
    derived_financial: bool,
) -> Mapping[str, Decimal | None] | None:
    """Require a unique original presence projection consistent with the canonical ledger."""
    projections = []
    for event in events:
        fees = {name: getattr(event, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS}
        actual_positive = {
            name: amount for name, amount in fees.items() if amount is not None and amount > 0
        }
        aggregate_allocation = (
            all(amount is None for amount in fees.values())
            and event.trade_fee is not None
            and positive == {"brokerage": event.trade_fee}
        )
        if (
            (actual_positive != positive and not aggregate_allocation)
            or normalize_currency_code(event.trade_currency or event.currency) != currency
            or (not derived_financial and event.trade_fee != trade_fee)
        ):
            raise ValueError("Original fee amounts conflict with canonical ledger")
        projection = fees | {"trade_fee": event.trade_fee}
        if projection not in projections:
            projections.append(projection)
    if not projections:
        return None
    if len(projections) != 1:
        raise ValueError("Ambiguous original named fee presence")
    return MappingProxyType(projections[0])


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
    positive = _original_positive_fee_rows(costs, currency)
    candidates = [
        payload | dict.fromkeys(TRANSACTION_FEE_COMPONENT_FIELDS),
        payload
        | {name: positive.get(name, Decimal(0)) for name in TRANSACTION_FEE_COMPONENT_FIELDS},
    ]
    # Retained raw facts decide exact presence; keep canonical validation and every raw
    # conflict check, but enumerate historical hypotheses only when raw is absent.
    if derived_financial and not raw_sources:
        candidates = [
            payload | fees
            for fees in _fee_presence_hypotheses(positive, canonical.get("trade_fee"))
        ]
    qualified = []
    for candidate in candidates:
        event = _original_fee_event(candidate, canonical, transaction_id, tenant_id, fingerprint)
        if event is not None:
            qualified.append(event)
    for raw in raw_sources:
        original = raw["payload"]
        if raw["aggregate_id"] != canonical["portfolio_id"]:
            raise ValueError("Conflicting retained raw transaction authority")
        event = _original_fee_event(original, canonical, transaction_id, tenant_id, fingerprint)
        if event is None:
            raise ValueError("Conflicting retained raw transaction authority")
        qualified.append(event)
    projection = _original_fee_projection(
        qualified, positive, currency, canonical.get("trade_fee"), derived_financial
    )
    return _OriginalFeeQualification(MappingProxyType(positive), projection)


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
