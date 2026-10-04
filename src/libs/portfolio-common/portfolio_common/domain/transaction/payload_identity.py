"""Deterministic durable identity for one source transaction payload."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any, Mapping

from .fx_source_admission import FX_SOURCE_ADMISSION_TYPES

TRANSACTION_PAYLOAD_IDENTITY_VERSION = "v1"
TRANSACTION_PAYLOAD_SOURCE_BOOKED_IDENTITY_VERSION = "v2"
TRANSACTION_PAYLOAD_UPSTREAM_FX_IDENTITY_VERSION = "v3"
_SOURCE_BOOKED_FX_ORIGIN = "SOURCE_BOOKED"
FX_UPSTREAM_PNL_FIELDS = tuple(
    f"realized_{component}_pnl_{basis}"
    for basis in ("local", "base")
    for component in ("capital", "fx", "total")
)

# Every TransactionEvent field must be classified by the contract test.  These fields
# are source economic or source-identity facts whose change requires an explicit
# correction command; they are intentionally independent of transport metadata and
# processor-owned calculation outputs.
TRANSACTION_PAYLOAD_MATERIAL_FIELDS = frozenset(
    {
        "accrued_interest_proceeds_local",
        "adjustment_reason",
        "brokerage",
        "buy_amount",
        "buy_currency",
        "calculation_policy_id",
        "calculation_policy_version",
        "cash_entry_mode",
        "child_role",
        "child_sequence_hint",
        "component_id",
        "component_type",
        "contract_rate",
        "currency",
        "dependency_reference_ids",
        "economic_event_id",
        "embedded_fee_amount_local",
        "embedded_tax_amount_local",
        "exchange_fee",
        "external_cash_transaction_id",
        "external_destination_reference",
        "far_leg_group_id",
        "fx_cash_leg_role",
        "fx_contract_close_transaction_id",
        "fx_contract_id",
        "fx_contract_open_transaction_id",
        "fx_rate_quote_convention",
        "fx_realized_pnl_mode",
        "gross_transaction_amount",
        "gst",
        "has_synthetic_flow",
        "instrument_id",
        "interest_direction",
        "link_type",
        "linked_cash_transaction_id",
        "linked_component_ids",
        "linked_fx_cash_leg_id",
        "linked_parent_event_id",
        "linked_transaction_group_id",
        "movement_direction",
        "near_leg_group_id",
        "net_interest_amount",
        "new_factor",
        "old_factor",
        "originating_transaction_id",
        "originating_transaction_type",
        "other_fees",
        "other_interest_deductions_amount",
        "pair_base_currency",
        "pair_quote_currency",
        "parent_event_reference",
        "parent_transaction_reference",
        "portfolio_id",
        "price",
        "principal_proceeds_local",
        "quantity",
        "reconciliation_key",
        "redemption_price_type",
        "security_id",
        "sell_amount",
        "sell_currency",
        "settlement_cash_account_id",
        "settlement_cash_instrument_id",
        "settlement_date",
        "settlement_of_fx_contract_id",
        "settlement_status",
        "source_instrument_id",
        "source_system",
        "source_transaction_reference",
        "spot_exposure_model",
        "stamp_duty",
        "swap_event_id",
        "synthetic_flow_amount_base",
        "synthetic_flow_amount_local",
        "synthetic_flow_classification",
        "synthetic_flow_currency",
        "synthetic_flow_effective_date",
        "synthetic_flow_fx_rate_to_base",
        "synthetic_flow_fx_source",
        "synthetic_flow_price_source",
        "synthetic_flow_price_used",
        "synthetic_flow_quantity_used",
        "synthetic_flow_source",
        "synthetic_flow_valuation_method",
        "target_instrument_id",
        "target_transaction_reference",
        "trade_currency",
        "trade_fee",
        "transaction_date",
        "transaction_id",
        "transaction_type",
        "withholding_tax_amount",
    }
)

TRANSACTION_PAYLOAD_NON_MATERIAL_FIELDS = frozenset(
    {
        # Governed event/transport metadata.
        "correlation_id",
        "event_type",
        "schema_version",
        "traceparent",
        # Tenant is part of the semantic key, not the economic payload.
        "tenant_id",
        # Attempt/serving chronology, not source economics.
        "created_at",
        "epoch",
        # Processor-owned outputs may be written after raw source acceptance.
        "allocated_cost_basis_base",
        "allocated_cost_basis_local",
        "gross_cost",
        "net_cost",
        "net_cost_local",
        "realized_capital_pnl_base",
        "realized_capital_pnl_local",
        "realized_fx_pnl_base",
        "realized_fx_pnl_local",
        "realized_gain_loss",
        "realized_gain_loss_local",
        "realized_total_pnl_base",
        "realized_total_pnl_local",
        "transaction_fx_rate",
        "transaction_fx_rate_origin",
        # Database-only technical/output fields used by migration backfill.
        "calculation_lineage",
        "id",
        "payload_fingerprint",
        "updated_at",
    }
)

_TRANSACTION_PAYLOAD_CLASSIFIED_FIELDS = (
    TRANSACTION_PAYLOAD_MATERIAL_FIELDS | TRANSACTION_PAYLOAD_NON_MATERIAL_FIELDS
)


@dataclass(frozen=True, slots=True)
class TransactionPayloadIdentity:
    """Tenant-scoped semantic key plus stable economic payload fingerprint."""

    semantic_key: str
    payload_fingerprint: str
    legacy_payload_fingerprint: str


def build_transaction_payload_identity(
    payload: Mapping[str, Any],
    *,
    tenant_id: str,
) -> TransactionPayloadIdentity:
    """Build the durable identity for one admitted source transaction."""

    normalized_tenant_id = tenant_id.strip()
    transaction_id = str(payload.get("transaction_id") or "").strip()
    if not normalized_tenant_id:
        raise ValueError("tenant_id is required for transaction payload identity")
    if not transaction_id:
        raise ValueError("transaction_id is required for transaction payload identity")
    origin = str(payload.get("transaction_fx_rate_origin") or "").strip().upper()
    identity_version = (
        TRANSACTION_PAYLOAD_UPSTREAM_FX_IDENTITY_VERSION
        if has_upstream_fx_pnl_authority(payload)
        else (
            TRANSACTION_PAYLOAD_SOURCE_BOOKED_IDENTITY_VERSION
            if origin == _SOURCE_BOOKED_FX_ORIGIN
            else TRANSACTION_PAYLOAD_IDENTITY_VERSION
        )
    )
    return TransactionPayloadIdentity(
        semantic_key=(
            f"transaction-persistence:{identity_version}:{normalized_tenant_id}:{transaction_id}"
        ),
        payload_fingerprint=transaction_payload_fingerprint(payload),
        legacy_payload_fingerprint=transaction_payload_legacy_fingerprint(payload),
    )


def transaction_payload_fingerprint(payload: Mapping[str, Any]) -> str:
    """Hash source facts using the governed provenance-aware identity version."""

    include_source_booked_fx = (
        str(payload.get("transaction_fx_rate_origin") or "").strip().upper()
        == _SOURCE_BOOKED_FX_ORIGIN
    )
    return _transaction_payload_fingerprint(
        payload,
        include_source_booked_fx=include_source_booked_fx,
        include_upstream_fx_pnl=has_upstream_fx_pnl_authority(payload),
    )


def has_upstream_fx_pnl_authority(payload: Mapping[str, Any]) -> bool:
    """Classify raw upstream source amounts, never infer authority from a receipt."""
    return (
        str(payload.get("transaction_type") or "").strip().upper() in FX_SOURCE_ADMISSION_TYPES
        and str(payload.get("fx_realized_pnl_mode") or "").strip().upper() == "UPSTREAM_PROVIDED"
    )


def transaction_payload_pre_upstream_fingerprint(payload: Mapping[str, Any]) -> str:
    """Retain the exact pre-v3 hash for refusal/compatibility tests, not promotion."""
    return _transaction_payload_fingerprint(
        payload,
        include_source_booked_fx=str(payload.get("transaction_fx_rate_origin") or "")
        .strip()
        .upper()
        == _SOURCE_BOOKED_FX_ORIGIN,
    )


def transaction_payload_legacy_fingerprint(payload: Mapping[str, Any]) -> str:
    """Build the pre-c175 v1 fingerprint for a qualified legacy replay only."""

    return _transaction_payload_fingerprint(payload, include_source_booked_fx=False)


def _transaction_payload_fingerprint(
    payload: Mapping[str, Any],
    *,
    include_source_booked_fx: bool,
    include_upstream_fx_pnl: bool = False,
) -> str:
    """Hash the complete classified payload under an explicit compatibility policy."""

    unknown_fields = set(payload).difference(_TRANSACTION_PAYLOAD_CLASSIFIED_FIELDS)
    if unknown_fields:
        names = ", ".join(sorted(unknown_fields))
        raise ValueError(f"Unclassified transaction payload fields: {names}")
    material_payload = {
        field_name: _canonical_value(payload.get(field_name))
        for field_name in sorted(TRANSACTION_PAYLOAD_MATERIAL_FIELDS)
    }
    if include_source_booked_fx:
        material_payload["transaction_fx_rate"] = _canonical_value(
            payload.get("transaction_fx_rate")
        )
    if include_upstream_fx_pnl:
        # This boundary hashes original raw source only. Derived/enriched ledger
        # amounts and caller calculation receipts cannot reconstruct missing source.
        material_payload.update(
            {name: _canonical_value(payload.get(name)) for name in FX_UPSTREAM_PNL_FIELDS}
        )
    canonical = json.dumps(
        material_payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def transaction_payload_fingerprint_default(context: Any) -> str:
    """Fingerprint legacy ORM-created ledger fixtures and internal records."""

    try:
        parameters = context.get_current_parameters()
    except KeyError as isolation_error:
        # SQLAlchemy 2.0 can expose table-qualified compile-state keys while an
        # ORM ``insert(Model).values([row, ...])`` stores the flattened bind
        # parameters under unqualified ``<field>_m<index>`` keys.  Its built-in
        # per-row isolation then raises before calling the default.  Recover the
        # same row from the documented unisolated parameter view; do not hash
        # the complete flattened batch as one transaction.
        parameters = _multi_values_default_parameters(context)
        if not parameters:
            raise isolation_error
    return transaction_payload_fingerprint(_classified_default_parameters(parameters))


def _classified_default_parameters(parameters: Mapping[Any, Any]) -> dict[str, Any]:
    """Project SQLAlchemy execution parameters onto transaction model fields.

    Context-sensitive defaults receive every bind parameter compiled into the
    statement. PostgreSQL upsert predicates therefore contribute technical
    names such as ``trim_1`` and ``coalesce_1`` which are not source payload
    fields. Keep the public fingerprint function fail-closed for callers while
    isolating this ORM adapter from compiler-owned binds.
    """

    classified_parameters: dict[str, Any] = {}
    for parameter_key, value in parameters.items():
        field_name = str(getattr(parameter_key, "key", parameter_key)).rsplit(".", maxsplit=1)[-1]
        if field_name in _TRANSACTION_PAYLOAD_CLASSIFIED_FIELDS:
            classified_parameters[field_name] = value
    return classified_parameters


def _multi_values_default_parameters(context: Any) -> dict[str, Any]:
    parameters = context.get_current_parameters(isolate_multiinsert_groups=False)
    current_column_key = str(getattr(context.current_column, "key", ""))
    _, row_separator, row_suffix = current_column_key.rpartition("_m")
    row_index = int(row_suffix) if row_separator and row_suffix.isdigit() else 0
    suffix = f"_m{row_index}"
    current_row: dict[str, Any] = {}
    for parameter_key, value in parameters.items():
        key = str(getattr(parameter_key, "key", parameter_key))
        if not key.endswith(suffix):
            continue
        field_name = key[: -len(suffix)].rsplit(".", maxsplit=1)[-1]
        if field_name in _TRANSACTION_PAYLOAD_CLASSIFIED_FIELDS:
            current_row[field_name] = value
    return current_row


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        normalized = value
        if normalized.tzinfo is not None:
            normalized = normalized.astimezone(timezone.utc).replace(tzinfo=None)
        return normalized.isoformat(timespec="microseconds") + "Z"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value
