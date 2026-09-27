"""Fence immutable transaction payload conflicts at the durable ledger row.

Revision ID: c173b2c3d534
Revises: c172b2c3d533
Create Date: 2026-09-27

The backfill contract is deliberately frozen in this revision.  Runtime fields added
later require an explicit material/non-material decision and, when material, a new
corrective migration rather than changing this applied migration.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "c173b2c3d534"
down_revision: str | Sequence[str] | None = "c172b2c3d533"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK = "ck_transactions_payload_fingerprint"
_BATCH_SIZE = 1000
_STAGED_SOURCE_TABLE = "c173_raw_transaction_sources"
_GENERATED_CASH_LEG_ORIGIN_TYPES = frozenset(
    {
        "BUY",
        "CALL_REDEMPTION",
        "DIVIDEND",
        "INTEREST",
        "MATURITY_REDEMPTION",
        "PARTIAL_REDEMPTION",
        "SELL",
    }
)
_REDEMPTION_TRANSACTION_TYPES = frozenset(
    {"CALL_REDEMPTION", "MATURITY_REDEMPTION", "PARTIAL_REDEMPTION"}
)
_DECIMAL_FIELDS = frozenset(
    {
        "accrued_interest_proceeds_local",
        "brokerage",
        "buy_amount",
        "contract_rate",
        "embedded_fee_amount_local",
        "embedded_tax_amount_local",
        "exchange_fee",
        "gross_transaction_amount",
        "gst",
        "net_interest_amount",
        "new_factor",
        "old_factor",
        "other_fees",
        "other_interest_deductions_amount",
        "price",
        "principal_proceeds_local",
        "quantity",
        "sell_amount",
        "stamp_duty",
        "synthetic_flow_amount_base",
        "synthetic_flow_amount_local",
        "synthetic_flow_fx_rate_to_base",
        "synthetic_flow_price_used",
        "synthetic_flow_quantity_used",
        "trade_fee",
        "withholding_tax_amount",
    }
)
_DATETIME_FIELDS = frozenset({"settlement_date", "transaction_date"})
_DATE_FIELDS = frozenset({"synthetic_flow_effective_date"})
_MATERIAL_FIELDS = frozenset(
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


def upgrade() -> None:
    connection = op.get_bind()
    op.add_column(
        "transactions",
        sa.Column("payload_fingerprint", sa.String(length=71), nullable=True),
    )

    # The preceding ALTER already holds an ACCESS EXCLUSIVE lock until migration
    # commit.  The explicit locks preserve one atomic view of immutable source
    # outbox evidence and transient idempotency evidence as well.
    connection.execute(
        sa.text(
            "LOCK TABLE transactions, processed_events, outbox_events IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    _backfill_transaction_fingerprints(connection)
    _backfill_persistence_semantic_claims(connection)

    op.create_check_constraint(
        _CHECK,
        "transactions",
        "payload_fingerprint ~ '^sha256:[0-9a-f]{64}$'",
        postgresql_not_valid=True,
    )
    op.execute(sa.text(f'ALTER TABLE transactions VALIDATE CONSTRAINT "{_CHECK}"'))
    op.alter_column(
        "transactions",
        "payload_fingerprint",
        existing_type=sa.String(length=71),
        nullable=False,
    )


def downgrade() -> None:
    # Preserve processed-event semantic evidence; old runtimes ignore it, and
    # deleting durable conflict history would make downgrade less safe.
    op.drop_constraint(_CHECK, "transactions", type_="check")
    op.drop_column("transactions", "payload_fingerprint")


def _backfill_transaction_fingerprints(connection: Any) -> None:
    last_id = 0
    rows = _load_transaction_fingerprint_batch(connection, last_id=last_id)
    if not rows:
        return

    _stage_transaction_source_evidence(connection)
    try:
        while rows:
            _backfill_transaction_fingerprint_batch(connection, rows)
            last_id = int(rows[-1]["id"])
            rows = _load_transaction_fingerprint_batch(connection, last_id=last_id)
    finally:
        connection.execute(sa.text(f"DROP TABLE IF EXISTS pg_temp.{_STAGED_SOURCE_TABLE}"))


def _load_transaction_fingerprint_batch(connection: Any, *, last_id: int) -> list[Any]:
    rows = (
        connection.execute(
            sa.text(
                "SELECT * FROM transactions "
                "WHERE payload_fingerprint IS NULL AND id > :last_id "
                "ORDER BY id LIMIT :batch_size"
            ),
            {"last_id": last_id, "batch_size": _BATCH_SIZE},
        )
        .mappings()
        .all()
    )
    return list(rows)


def _backfill_transaction_fingerprint_batch(
    connection: Any, rows: Sequence[Mapping[str, Any]]
) -> None:
    transaction_ids = [str(row["transaction_id"]) for row in rows]
    transaction_rows = {str(row["transaction_id"]): row for row in rows}
    source_rows = (
        connection.execute(
            sa.text(
                f"SELECT id, payload FROM {_STAGED_SOURCE_TABLE} "
                "WHERE transaction_id = ANY(:transaction_ids) "
                "ORDER BY id"
            ),
            {"transaction_ids": transaction_ids},
        )
        .mappings()
        .all()
    )
    source_payloads: dict[str, Mapping[str, Any]] = {}
    source_fingerprints: dict[str, str] = {}
    for source_row in source_rows:
        payload = source_row["payload"]
        if not isinstance(payload, Mapping):
            raise RuntimeError(
                "transaction payload fingerprint migration found malformed immutable "
                f"source evidence in outbox row {source_row['id']}"
            )
        transaction_id = str(payload.get("transaction_id") or "").strip()
        transaction = transaction_rows.get(transaction_id)
        if transaction is None:
            continue
        if str(payload.get("portfolio_id") or "").strip() != str(transaction["portfolio_id"]):
            raise RuntimeError(
                "transaction payload fingerprint migration found immutable source "
                f"portfolio mismatch for transaction {transaction_id}"
            )
        fingerprint = _payload_fingerprint(payload)
        existing_fingerprint = source_fingerprints.get(transaction_id)
        if existing_fingerprint is not None and existing_fingerprint != fingerprint:
            raise RuntimeError(
                "transaction payload fingerprint migration found conflicting immutable "
                f"source evidence for transaction {transaction_id}"
            )
        source_payloads[transaction_id] = payload
        source_fingerprints[transaction_id] = fingerprint

    # Processor-generated settlement and accrued-interest children do not pass
    # through RawTransactionPersisted. Their canonical generated ownership makes
    # the current row the durable source for this one-time migration; subsequent
    # generated upserts refresh the fingerprint atomically with the row.
    for transaction_id, transaction in transaction_rows.items():
        if transaction_id in source_payloads:
            continue
        if _is_canonical_generated_transaction(transaction):
            source_payloads[transaction_id] = transaction
            source_fingerprints[transaction_id] = _payload_fingerprint(transaction)

    missing_source_ids = sorted(set(transaction_ids).difference(source_payloads))
    if missing_source_ids:
        preview = ", ".join(missing_source_ids[:5])
        raise RuntimeError(
            "transaction payload fingerprint migration requires immutable "
            f"RawTransactionPersisted source evidence; missing for {preview}"
        )

    updates = [
        {
            "row_id": row["id"],
            "payload_fingerprint": source_fingerprints[str(row["transaction_id"])],
        }
        for row in rows
    ]
    connection.execute(
        sa.text(
            "UPDATE transactions SET payload_fingerprint = :payload_fingerprint "
            "WHERE id = :row_id AND payload_fingerprint IS NULL"
        ),
        updates,
    )


def _stage_transaction_source_evidence(connection: Any) -> None:
    connection.execute(
        sa.text(
            f"CREATE TEMPORARY TABLE {_STAGED_SOURCE_TABLE} ON COMMIT DROP AS "
            "WITH raw_source AS MATERIALIZED ("
            "SELECT id, payload, payload ->> 'transaction_id' AS transaction_id "
            "FROM outbox_events "
            "WHERE aggregate_type = 'RawTransaction' "
            "AND event_type = 'RawTransactionPersisted'"
            ") "
            "SELECT source.id, source.payload, source.transaction_id "
            "FROM raw_source AS source "
            "JOIN transactions AS txn "
            "ON txn.payload_fingerprint IS NULL "
            "AND txn.transaction_id = source.transaction_id"
        )
    )
    connection.execute(
        sa.text(
            "CREATE INDEX c173_raw_transaction_sources_transaction_id_idx "
            f"ON {_STAGED_SOURCE_TABLE} (transaction_id)"
        )
    )
    connection.execute(sa.text(f"ANALYZE {_STAGED_SOURCE_TABLE}"))


def _backfill_persistence_semantic_claims(connection: Any) -> None:
    conflict_count = connection.scalar(
        sa.text(
            """
            SELECT count(*)
            FROM processed_events AS processed
            JOIN transactions AS txn
              ON txn.transaction_id = processed.event_id
             AND txn.portfolio_id = processed.portfolio_id
            WHERE processed.service_name = 'persistence-transactions'
              AND processed.tenant_id IS NOT NULL
              AND (
                (processed.payload_fingerprint IS NOT NULL
                 AND processed.payload_fingerprint <> txn.payload_fingerprint)
                OR
                (processed.semantic_key IS NOT NULL
                 AND processed.semantic_key <>
                     'transaction-persistence:v1:' || processed.tenant_id || ':' ||
                     txn.transaction_id)
              )
            """
        )
    )
    if conflict_count:
        raise RuntimeError(
            "transaction payload fingerprint migration found inconsistent persistence fences"
        )
    connection.execute(
        sa.text(
            """
            UPDATE processed_events AS processed
               SET semantic_key =
                     'transaction-persistence:v1:' || processed.tenant_id || ':' ||
                     txn.transaction_id,
                   payload_fingerprint = txn.payload_fingerprint
              FROM transactions AS txn
             WHERE processed.service_name = 'persistence-transactions'
               AND processed.tenant_id IS NOT NULL
               AND txn.transaction_id = processed.event_id
               AND txn.portfolio_id = processed.portfolio_id
               AND (processed.semantic_key IS NULL OR processed.payload_fingerprint IS NULL)
            """
        )
    )


def _payload_fingerprint(payload: Mapping[str, Any]) -> str:
    material = {
        field_name: _canonical_material_value(field_name, payload.get(field_name))
        for field_name in sorted(_MATERIAL_FIELDS)
    }
    canonical = json.dumps(
        material,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_material_value(field_name: str, value: Any) -> Any:
    if value is None:
        return None
    if field_name in _DECIMAL_FIELDS:
        return _canonical_value(Decimal(str(value)))
    if field_name in _DATETIME_FIELDS and isinstance(value, str):
        return _canonical_value(datetime.fromisoformat(value.replace("Z", "+00:00")))
    if field_name in _DATE_FIELDS and isinstance(value, str):
        return _canonical_value(date.fromisoformat(value))
    return _canonical_value(value)


def _is_canonical_generated_transaction(payload: Mapping[str, Any]) -> bool:
    transaction_id = str(payload.get("transaction_id") or "").strip()
    transaction_type = _control_code(payload.get("transaction_type"))
    originating_transaction_id = str(payload.get("originating_transaction_id") or "").strip()
    originating_transaction_type = _control_code(payload.get("originating_transaction_type"))
    if not originating_transaction_id:
        return False
    if (
        transaction_id == f"{originating_transaction_id}-CASHLEG"
        and transaction_type == "ADJUSTMENT"
        and _control_code(payload.get("cash_entry_mode")) == "AUTO_GENERATE"
        and originating_transaction_type in _GENERATED_CASH_LEG_ORIGIN_TYPES
        and _control_code(payload.get("link_type")) == f"{originating_transaction_type}_TO_CASH"
        and not _control_code(payload.get("component_type"))
        and not str(payload.get("component_id") or "").strip()
    ):
        return True
    expected_id = f"{originating_transaction_id}-ACCRUED-INTEREST"
    return (
        transaction_id == expected_id
        and transaction_type == "INTEREST"
        and _control_code(payload.get("component_type")) == "REDEMPTION_ACCRUED_INTEREST"
        and payload.get("component_id") == f"{expected_id}:v1"
        and originating_transaction_type in _REDEMPTION_TRANSACTION_TYPES
        and _control_code(payload.get("link_type")) == "REDEMPTION_TO_ACCRUED_INTEREST"
    )


def _control_code(value: Any) -> str:
    return str(value or "").strip().upper()


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
