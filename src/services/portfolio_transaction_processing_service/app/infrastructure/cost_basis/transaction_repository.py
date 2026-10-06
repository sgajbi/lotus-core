"""SQLAlchemy persistence for transaction cost-basis processing."""

from collections.abc import Mapping, Sequence
from dataclasses import fields, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import OutboxEvent, Portfolio, TransactionCost
from portfolio_common.database_models import (
    Transaction as DBTransaction,
)
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    calculation_lineage_from_payload,
    canonical_content_hash,
)
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.transaction import (
    TRANSACTION_PAYLOAD_MATERIAL_FIELDS,
    TransactionIdentityOwnership,
    canonical_transaction_identity_record_values,
    require_generated_transaction_identity,
    transaction_identity_ownership,
    transaction_payload_fingerprint,
)
from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code
from portfolio_common.events import TransactionEvent
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.infrastructure.persistence.transaction_identity_guard import (
    GeneratedTransactionIdentityCollisionError,
    transaction_identity_update_allowed,
)
from portfolio_common.reprocessing_replay import ReprocessingReplayError
from portfolio_common.reprocessing_repository import load_transaction_fee_facts
from portfolio_common.utils import async_timed
from sqlalchemy import delete, func, select, true, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from ...application.errors import TransactionProcessingRejected
from ...domain.cost_basis import CostBasisTransaction
from ...domain.transaction import BookedTransaction, enrich_booking_metadata
from ...domain.transaction.fx import FX_BUSINESS_TRANSACTION_TYPES
from ...domain.transaction.fx.persisted_return import (
    FxCanonicalSourceLoad,
    FxPersistenceWitness,
    qualify_fx_raw_source,
)
from ...domain.transaction.redemption import (
    REDEMPTION_CORRECTION_OWNED_OPTIONAL_FIELDS,
    REDEMPTION_TRANSACTION_TYPES,
)
from ..transaction_mapping.booked_transaction import (
    to_booked_transaction_from_record,
    to_transaction_event,
)
from ..transaction_replay.booked_transaction import load_qualified_transaction_fee_sources

TRANSACTION_METADATA_FIELDS = (
    "economic_event_id",
    "linked_transaction_group_id",
    "calculation_policy_id",
    "calculation_policy_version",
    "source_system",
    "cash_entry_mode",
    "external_cash_transaction_id",
    "settlement_cash_account_id",
    "settlement_cash_instrument_id",
    "movement_direction",
    "originating_transaction_id",
    "originating_transaction_type",
    "adjustment_reason",
    "link_type",
    "reconciliation_key",
    "interest_direction",
    "withholding_tax_amount",
    "other_interest_deductions_amount",
    "net_interest_amount",
    "component_type",
    "component_id",
    "linked_component_ids",
    "fx_cash_leg_role",
    "linked_fx_cash_leg_id",
    "settlement_status",
    "pair_base_currency",
    "pair_quote_currency",
    "fx_rate_quote_convention",
    "buy_currency",
    "sell_currency",
    "buy_amount",
    "sell_amount",
    "contract_rate",
    "fx_contract_id",
    "fx_contract_open_transaction_id",
    "fx_contract_close_transaction_id",
    "settlement_of_fx_contract_id",
    "swap_event_id",
    "near_leg_group_id",
    "far_leg_group_id",
    "spot_exposure_model",
    "fx_realized_pnl_mode",
    "allocated_cost_basis_local",
    "allocated_cost_basis_base",
    "realized_capital_pnl_local",
    "realized_fx_pnl_local",
    "realized_total_pnl_local",
    "realized_capital_pnl_base",
    "realized_fx_pnl_base",
    "realized_total_pnl_base",
    "parent_transaction_reference",
    "linked_parent_event_id",
    "parent_event_reference",
    "child_role",
    "child_sequence_hint",
    "dependency_reference_ids",
    "source_instrument_id",
    "target_instrument_id",
    "source_transaction_reference",
    "target_transaction_reference",
    "external_destination_reference",
    "linked_cash_transaction_id",
    "redemption_price_type",
    "old_factor",
    "new_factor",
    "principal_proceeds_local",
    "accrued_interest_proceeds_local",
    "embedded_fee_amount_local",
    "embedded_tax_amount_local",
    "has_synthetic_flow",
    "synthetic_flow_effective_date",
    "synthetic_flow_amount_local",
    "synthetic_flow_currency",
    "synthetic_flow_amount_base",
    "synthetic_flow_fx_rate_to_base",
    "synthetic_flow_price_used",
    "synthetic_flow_quantity_used",
    "synthetic_flow_valuation_method",
    "synthetic_flow_classification",
    "synthetic_flow_price_source",
    "synthetic_flow_fx_source",
    "synthetic_flow_source",
)

TRANSACTION_TABLE_FIELDS = frozenset(DBTransaction.__table__.columns.keys())
BOOKED_TRANSACTION_FIELD_NAMES = tuple(field.name for field in fields(BookedTransaction))
BOOKED_TRANSACTION_PERSISTENCE_EXCLUDE_FIELDS = frozenset(
    {"id", "epoch", "brokerage", "stamp_duty", "exchange_fee", "gst", "other_fees"}
)
BOOKED_TRANSACTION_EXPLICIT_NULL_FIELDS = frozenset(
    {"calculation_lineage", "external_cash_transaction_id", "linked_component_ids"}
)


def _booked_transaction_payload(
    transaction: BookedTransaction,
    *,
    fields_to_clear: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    unsupported_clear_fields = fields_to_clear - BOOKED_TRANSACTION_EXPLICIT_NULL_FIELDS
    if unsupported_clear_fields:
        raise ValueError(
            "Unsupported booked-transaction clear fields: "
            f"{', '.join(sorted(unsupported_clear_fields))}."
        )
    payload = {
        field_name: value
        for field_name in BOOKED_TRANSACTION_FIELD_NAMES
        if (value := getattr(transaction, field_name)) is not None
        and field_name in TRANSACTION_TABLE_FIELDS
        and field_name not in BOOKED_TRANSACTION_PERSISTENCE_EXCLUDE_FIELDS
    }
    calculation_lineage = payload.get("calculation_lineage")
    if isinstance(calculation_lineage, CalculationLineage):
        payload["calculation_lineage"] = calculation_lineage.lineage_payload()
    payload.update(dict.fromkeys(fields_to_clear))
    return payload


def _persisted_transaction_payload_fingerprint(transaction: DBTransaction) -> str:
    """Hash the final ledger values after PostgreSQL has merged an upsert."""

    return str(
        transaction_payload_fingerprint(
            {
                field_name: getattr(transaction, field_name)
                for field_name in TRANSACTION_PAYLOAD_MATERIAL_FIELDS
                if field_name in TRANSACTION_TABLE_FIELDS
            }
            | {
                "transaction_fx_rate": transaction.transaction_fx_rate,
                "transaction_fx_rate_origin": transaction.transaction_fx_rate_origin,
            }
        )
    )


def _to_persisted_booked_transaction(
    transaction: DBTransaction,
    *,
    fee_components: dict[str, Decimal] | None = None,
    tenant_id: str | None = None,
) -> BookedTransaction:
    """Rehydrate the internal calculation receipt excluded from the public event contract."""

    booked = to_booked_transaction_from_record(transaction)
    booked = replace(
        booked,
        calculation_lineage=calculation_lineage_from_payload(transaction.calculation_lineage),
        tenant_id=tenant_id,
    )
    if fee_components is None:
        return booked
    return replace(
        booked,
        brokerage=fee_components["brokerage"],
        stamp_duty=fee_components["stamp_duty"],
        exchange_fee=fee_components["exchange_fee"],
        gst=fee_components["gst"],
        other_fees=fee_components["other_fees"],
    )


FEE_COMPONENT_FIELDS = (
    "brokerage",
    "stamp_duty",
    "exchange_fee",
    "gst",
    "other_fees",
)
FEE_COMPONENT_FIELD_SET = frozenset(FEE_COMPONENT_FIELDS)


def _rehydrate_transaction_fee_components(
    transaction: DBTransaction,
) -> dict[str, Decimal] | None:
    """Return lossless named fee authority from eagerly loaded canonical rows."""

    if not transaction.costs:
        return None

    expected_currency = normalize_currency_code(transaction.trade_currency or transaction.currency)
    components = dict.fromkeys(FEE_COMPONENT_FIELDS, Decimal(0))
    observed_types: set[str] = set()
    for cost in transaction.costs:
        fee_type = str(cost.fee_type).strip().lower()
        if fee_type not in FEE_COMPONENT_FIELD_SET:
            raise ValueError("Persisted transaction cost has an unsupported fee type.")
        if fee_type in observed_types:
            raise ValueError("Persisted transaction cost has duplicate fee-type authority.")
        if normalize_currency_code(cost.currency) != expected_currency:
            raise ValueError(
                "Persisted transaction cost currency conflicts with the trade currency."
            )
        amount = Decimal(cost.amount)
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Persisted transaction cost amount must be finite and positive.")
        observed_types.add(fee_type)
        components[fee_type] = amount
    return components


def project_derived_financial_transaction(
    transaction: DBTransaction,
    *,
    tenant_id: str,
    cost_basis_method: str,
    qualified_fees: Mapping[str, Decimal | None] | None = None,
) -> BookedTransaction:
    """Project qualified cost facts and governed metadata without changing original source."""
    financial = _to_persisted_booked_transaction(
        transaction,
        fee_components=_rehydrate_transaction_fee_components(transaction),
        tenant_id=tenant_id,
    )
    financial = _with_qualified_fees(financial, qualified_fees)
    return enrich_booking_metadata(financial, cost_basis_method=cost_basis_method)


def _with_qualified_fees(
    transaction: BookedTransaction, fees: Mapping[str, Decimal | None] | None
) -> BookedTransaction:
    if fees is None:
        return transaction
    return replace(
        transaction,
        brokerage=fees["brokerage"],
        stamp_duty=fees["stamp_duty"],
        exchange_fee=fees["exchange_fee"],
        gst=fees["gst"],
        other_fees=fees["other_fees"],
        trade_fee=fees["trade_fee"],
    )


async def load_derived_financial_transactions(
    session: AsyncSession,
    rows: Sequence[tuple[DBTransaction, str, str]],
    *,
    enrich_metadata: bool = True,
) -> tuple[BookedTransaction, ...]:
    """Reuse bounded original fee authority before projecting derived financial effects."""
    canonical_sources = [
        to_transaction_event(
            _to_persisted_booked_transaction(row, tenant_id=tenant_id),
            correlation_id=None,
            traceparent=None,
        ).model_dump(mode="python")
        | {"payload_fingerprint": row.payload_fingerprint}
        for row, tenant_id, _method in rows
        if row.payload_fingerprint
    ]
    qualified = (
        await load_qualified_transaction_fee_sources(
            session,
            canonical_sources,
            lock_sources=True,
            allow_retained_receipt=True,
            derived_financial=True,
        )
        if canonical_sources
        else {}
    )
    projections = []
    for row, tenant_id, method in rows:
        fees = qualified.get(str(row.transaction_id))
        if enrich_metadata:
            projected = project_derived_financial_transaction(
                row, tenant_id=tenant_id, cost_basis_method=method, qualified_fees=fees
            )
        else:
            projected = _to_persisted_booked_transaction(
                row, fee_components=_rehydrate_transaction_fee_components(row)
            )
            projected = _with_qualified_fees(projected, fees)
        projections.append(projected)
    return tuple(projections)


def _positive_fee_components(fees: object | None) -> dict[str, Decimal]:
    if fees is None:
        return {}
    return {
        field_name: amount
        for field_name in FEE_COMPONENT_FIELDS
        if (amount := getattr(fees, field_name, None) or Decimal(0)) > 0
    }


def _transaction_metadata_update_values(
    transaction_result: CostBasisTransaction,
) -> dict[str, object | None]:
    """Project metadata and enforce redemption-only field ownership on correction."""

    transaction_type = normalize_transaction_control_code(transaction_result.transaction_type)
    metadata_values = {
        field_name: field_value
        for field_name in TRANSACTION_METADATA_FIELDS
        if (
            (field_value := getattr(transaction_result, field_name, None)) is not None
            or field_name in REDEMPTION_CORRECTION_OWNED_OPTIONAL_FIELDS
        )
    }
    if transaction_type not in REDEMPTION_TRANSACTION_TYPES:
        metadata_values.update(dict.fromkeys(REDEMPTION_CORRECTION_OWNED_OPTIONAL_FIELDS))
    return metadata_values


def _transaction_cost_rows(
    *,
    transaction_result: CostBasisTransaction,
    db_txn: DBTransaction,
) -> list[TransactionCost]:
    currency = normalize_currency_code(db_txn.trade_currency or db_txn.currency)
    return [
        TransactionCost(
            transaction_id=transaction_result.transaction_id,
            fee_type=fee_type,
            amount=amount,
            currency=currency,
        )
        for fee_type, amount in _positive_fee_components(transaction_result.fees).items()
    ]


class SqlAlchemyCostBasisTransactionRepository:
    """Persist canonical transaction economics and load cost-basis history."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def load_fx_creation_timestamp(self) -> datetime:
        """Use the same PostgreSQL transaction clock as the ledger's server default."""
        timestamp = (await self.db.execute(select(func.transaction_timestamp()))).scalar_one()
        if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
            raise ValueError("FX server creation timestamp must be an aware datetime")
        return timestamp.astimezone(UTC)

    async def load_fx_retention_witness(
        self, transaction: BookedTransaction
    ) -> FxPersistenceWitness | None:
        """Reuse locked source facts, otherwise take only the target upsert's row lock."""
        row = (
            await self.db.execute(
                select(DBTransaction)
                .join(Portfolio, Portfolio.portfolio_id == DBTransaction.portfolio_id)
                .where(
                    DBTransaction.transaction_id == transaction.transaction_id,
                    DBTransaction.portfolio_id == transaction.portfolio_id,
                    DBTransaction.security_id == transaction.security_id,
                    Portfolio.tenant_id == transaction.tenant_id,
                )
                .with_for_update(of=DBTransaction)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        before = _to_persisted_booked_transaction(row, tenant_id=transaction.tenant_id)
        sources = []
        if (
            normalize_transaction_control_code(transaction.fx_realized_pnl_mode)
            == "UPSTREAM_PROVIDED"
        ):
            sources = [
                dict(source)
                for source in (
                    await self.db.execute(
                        select(OutboxEvent.id, OutboxEvent.aggregate_id, OutboxEvent.payload)
                        .where(
                            OutboxEvent.aggregate_type == "RawTransaction",
                            OutboxEvent.event_type == "RawTransactionPersisted",
                            OutboxEvent.aggregate_id == transaction.portfolio_id,
                            OutboxEvent.payload["portfolio_id"].as_string()
                            == transaction.portfolio_id,
                            OutboxEvent.payload["transaction_id"].as_string()
                            == transaction.transaction_id,
                        )
                        .order_by(OutboxEvent.id)
                    )
                )
                .mappings()
                .all()
            ]
        return self._qualify_fx_witness(
            before, str(row.payload_fingerprint or ""), sources, transaction.epoch
        )

    @staticmethod
    def _qualify_fx_witness(
        before: BookedTransaction,
        fingerprint: str,
        sources: Sequence[Mapping[str, Any]],
        admitted_epoch: int | None = None,
    ) -> FxPersistenceWitness:
        if normalize_transaction_control_code(before.fx_realized_pnl_mode) != "UPSTREAM_PROVIDED":
            return FxPersistenceWitness(before, None, None, admitted_epoch)
        if len(sources) != 1 or sources[0]["aggregate_id"] != before.portfolio_id:
            raise ValueError("FX original raw source cut is unavailable or ambiguous")
        source = sources[0]
        original = source["payload"]
        event = TransactionEvent.model_validate(original)
        identity_source = dict(original)
        for name in ("transaction_date", "settlement_date"):
            if name in identity_source:
                identity_source[name] = getattr(event, name)
        raw = qualify_fx_raw_source(
            raw=original,
            transaction=before,
            stored_fingerprint=fingerprint,
            raw_event_id=int(source["id"]),
            raw_payload_hash=canonical_content_hash(original),
            identity_source=identity_source,
        )
        return FxPersistenceWitness(before, raw.original_pnl, raw, admitted_epoch)

    @async_timed(repository="CostBasisTransactionRepository", method="get_transaction_history")
    async def get_transaction_history(
        self, portfolio_id: str, security_id: str, exclude_id: str | None = None
    ) -> list[BookedTransaction]:
        """
        Fetches all transactions for a given security in a portfolio,
        optionally excluding one by its transaction_id.
        """
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = (
            select(DBTransaction, Portfolio.tenant_id, Portfolio.cost_basis_method)
            .join(Portfolio, Portfolio.portfolio_id == DBTransaction.portfolio_id)
            .options(joinedload(DBTransaction.costs))
            .where(
                func.trim(DBTransaction.portfolio_id) == normalized_portfolio_id,
                func.trim(DBTransaction.security_id) == normalized_security_id,
            )
        )

        if exclude_id:
            normalized_exclude_id = normalize_lookup_identifier(exclude_id)
            stmt = stmt.where(func.trim(DBTransaction.transaction_id) != normalized_exclude_id)

        stmt = stmt.order_by(
            DBTransaction.transaction_date.asc(),
            DBTransaction.transaction_id.asc(),
        )

        result = await self.db.execute(stmt)
        return list(
            await load_derived_financial_transactions(
                self.db, result.unique().all(), enrich_metadata=False
            )
        )

    async def get_derived_financial_transaction(
        self, transaction: BookedTransaction
    ) -> BookedTransaction | None:
        """Retain one exact owned row and project the same financial facts as a rebuild."""
        if not transaction.tenant_id:
            return None
        statement = (
            select(DBTransaction, Portfolio.tenant_id, Portfolio.cost_basis_method)
            .join(Portfolio, Portfolio.portfolio_id == DBTransaction.portfolio_id)
            .options(joinedload(DBTransaction.costs))
            .where(
                Portfolio.tenant_id == transaction.tenant_id,
                DBTransaction.portfolio_id == transaction.portfolio_id,
                DBTransaction.security_id == transaction.security_id,
                DBTransaction.transaction_id == transaction.transaction_id,
            )
            .with_for_update(read=True, of=DBTransaction)
        )
        row = (await self.db.execute(statement)).unique().one_or_none()
        if row is None:
            return None
        booked, tenant_id, cost_basis_method = row
        if not booked.payload_fingerprint:
            # Legacy history remains readable, but cannot certify original fee presence.
            return None
        return (
            await load_derived_financial_transactions(
                self.db, [(booked, tenant_id, cost_basis_method)]
            )
        )[0]

    @async_timed(repository="CostBasisTransactionRepository", method="get_linked_transaction_group")
    async def get_linked_transaction_group(
        self,
        portfolio_id: str,
        linked_transaction_group_id: str,
        exclude_id: str | None = None,
    ) -> list[BookedTransaction]:
        """Load one portfolio-owned linked group across instrument and security boundaries."""

        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_group_id = normalize_lookup_identifier(linked_transaction_group_id)
        stmt = select(DBTransaction).where(
            DBTransaction.portfolio_id == normalized_portfolio_id,
            DBTransaction.linked_transaction_group_id == normalized_group_id,
        )
        if exclude_id:
            normalized_exclude_id = normalize_lookup_identifier(exclude_id)
            stmt = stmt.where(DBTransaction.transaction_id != normalized_exclude_id)
        stmt = stmt.order_by(
            DBTransaction.transaction_date.asc(),
            DBTransaction.transaction_id.asc(),
        )
        result = await self.db.execute(stmt)
        return [_to_persisted_booked_transaction(row) for row in result.scalars().all()]

    @async_timed(
        repository="CostBasisTransactionRepository",
        method="apply_transaction_costs_and_replace_breakdown",
    )
    async def apply_transaction_costs_and_replace_breakdown(
        self, transaction_result: CostBasisTransaction
    ) -> BookedTransaction | None:
        """Apply economics and replace fee components without rereading the canonical row."""

        calculation_lineage = getattr(transaction_result, "calculation_lineage", None)
        if not isinstance(calculation_lineage, CalculationLineage):
            raise ValueError(
                "Calculated transaction is missing governed calculation lineage: "
                f"{transaction_result.transaction_id}"
            )
        update_values = {
            "net_cost": transaction_result.net_cost,
            "gross_cost": transaction_result.gross_cost,
            "realized_gain_loss": transaction_result.realized_gain_loss,
            "transaction_fx_rate": transaction_result.transaction_fx_rate,
            "transaction_fx_rate_origin": getattr(
                transaction_result, "transaction_fx_rate_origin", None
            ),
            "net_cost_local": transaction_result.net_cost_local,
            "realized_gain_loss_local": transaction_result.realized_gain_loss_local,
            "calculation_lineage": calculation_lineage.lineage_payload(),
            **_transaction_metadata_update_values(transaction_result),
        }
        update_statement = (
            update(DBTransaction)
            .where(DBTransaction.transaction_id == transaction_result.transaction_id)
            .values(**update_values)
            .returning(DBTransaction)
        )
        updated_transaction = update_statement.cte("updated_transaction")
        updated_transaction_row = aliased(DBTransaction, updated_transaction)
        deleted_costs = (
            delete(TransactionCost)
            .where(TransactionCost.transaction_id == updated_transaction.c.transaction_id)
            .returning(TransactionCost.id)
            .cte("deleted_transaction_costs")
        )
        statement = (
            select(updated_transaction_row)
            .select_from(updated_transaction_row)
            .outerjoin(deleted_costs, true())
            .limit(1)
        )
        db_transaction = (await self.db.execute(statement)).scalars().first()
        if db_transaction is None:
            return None
        self.db.add_all(
            _transaction_cost_rows(
                transaction_result=transaction_result,
                db_txn=db_transaction,
            )
        )
        return _to_persisted_booked_transaction(
            db_transaction,
            tenant_id=getattr(transaction_result, "tenant_id", None),
        )

    @async_timed(repository="CostBasisTransactionRepository", method="get_booked_transaction")
    async def get_booked_transaction(
        self,
        transaction_id: str,
        *,
        portfolio_id: str | None = None,
        repair_tenant_id: str | None = None,
        repair_security_id: str | None = None,
    ) -> BookedTransaction | None:
        result = await self._get_booked_transaction(
            transaction_id,
            portfolio_id=portfolio_id,
            repair_tenant_id=repair_tenant_id,
            repair_security_id=repair_security_id,
        )
        if isinstance(result, FxCanonicalSourceLoad):
            raise TypeError("Canonical transaction lookup returned an unexpected FX source load")
        return result

    async def load_booked_transaction_with_fx_witness(
        self,
        transaction: BookedTransaction,
    ) -> FxCanonicalSourceLoad:
        result = await self._get_booked_transaction(
            transaction.transaction_id,
            portfolio_id=transaction.portfolio_id,
            repair_tenant_id=transaction.tenant_id or "",
            repair_security_id=transaction.security_id,
            include_fx_witness=True,
        )
        return (
            result
            if isinstance(result, FxCanonicalSourceLoad)
            else FxCanonicalSourceLoad(result, None)
        )

    async def _get_booked_transaction(
        self,
        transaction_id: str,
        *,
        portfolio_id: str | None = None,
        repair_tenant_id: str | None = None,
        repair_security_id: str | None = None,
        include_fx_witness: bool = False,
    ) -> BookedTransaction | FxCanonicalSourceLoad | None:
        """Load one persisted transaction as an immutable domain transaction."""

        repair_source = repair_tenant_id is not None
        if repair_source:
            # Acquire the strongest Portfolio lock needed by later acquisition-lot persistence
            # at entry, not via a shared-to-exclusive upgrade after transaction writes.
            owner = (
                await self.db.execute(
                    select(Portfolio.tenant_id)
                    .where(Portfolio.portfolio_id == portfolio_id)
                    .with_for_update(of=Portfolio)
                )
            ).scalar_one_or_none()
            if not repair_tenant_id or owner != repair_tenant_id:
                raise TransactionProcessingRejected(
                    reason_code="repair_source_owner_mismatch",
                    detail={"portfolio_id": portfolio_id, "transaction_id": transaction_id},
                    retryable=False,
                )
        stmt = select(DBTransaction).where(DBTransaction.transaction_id == transaction_id)
        if portfolio_id:
            stmt = stmt.where(DBTransaction.portfolio_id == portfolio_id)
        if repair_source:
            stmt = stmt.options(joinedload(DBTransaction.costs)).with_for_update(of=DBTransaction)
            stmt = stmt.execution_options(populate_existing=True)
        result = await self.db.execute(stmt)
        transaction = (
            result.unique().scalars().first() if repair_source else result.scalars().first()
        )
        if transaction is None:
            return None
        if repair_source:
            if (
                transaction.portfolio_id != portfolio_id
                or transaction.security_id != repair_security_id
                or not str(transaction.payload_fingerprint or "").strip()
            ):
                raise TransactionProcessingRejected(
                    reason_code="repair_source_authority_mismatch",
                    detail={"portfolio_id": portfolio_id, "transaction_id": transaction_id},
                    retryable=False,
                )
            source = _to_persisted_booked_transaction(
                transaction,
                tenant_id=repair_tenant_id,
            )
            source_payload = to_transaction_event(
                source, correlation_id=None, traceparent=None
            ).model_dump(mode="python")
            witness = None
            try:
                source_facts = None
                if (
                    normalize_transaction_control_code(source.transaction_type)
                    in FX_BUSINESS_TRANSACTION_TYPES
                ):
                    costs, raw, _ = await load_transaction_fee_facts(
                        self.db,
                        [source_payload | {"payload_fingerprint": transaction.payload_fingerprint}],
                        lock_sources=True,
                    )
                    source_facts = (costs, raw)
                    if include_fx_witness:
                        witness = self._qualify_fx_witness(
                            source,
                            str(transaction.payload_fingerprint),
                            raw,
                        )
                fee_sources = await load_qualified_transaction_fee_sources(
                    self.db,
                    [
                        source_payload
                        | {
                            "payload_fingerprint": transaction.payload_fingerprint,
                        }
                    ],
                    lock_sources=True,
                    source_facts=source_facts,
                )
            except ReprocessingReplayError as exc:
                if include_fx_witness:
                    return FxCanonicalSourceLoad(None, witness)
                raise TransactionProcessingRejected(
                    reason_code="repair_original_source_unavailable",
                    detail={"portfolio_id": portfolio_id, "transaction_id": transaction_id},
                    retryable=False,
                ) from exc
            fees = fee_sources[source.transaction_id]
            source = replace(
                source,
                brokerage=fees["brokerage"],
                stamp_duty=fees["stamp_duty"],
                exchange_fee=fees["exchange_fee"],
                gst=fees["gst"],
                other_fees=fees["other_fees"],
                trade_fee=fees["trade_fee"],
            )
            source_payload.update(fee_sources[source.transaction_id])
            if transaction.payload_fingerprint != transaction_payload_fingerprint(source_payload):
                if include_fx_witness:
                    return FxCanonicalSourceLoad(None, witness)
                raise TransactionProcessingRejected(
                    reason_code="repair_original_source_unavailable",
                    detail={"portfolio_id": portfolio_id, "transaction_id": transaction_id},
                    retryable=False,
                )
            return FxCanonicalSourceLoad(source, witness) if include_fx_witness else source
        return _to_persisted_booked_transaction(transaction)

    @async_timed(repository="CostBasisTransactionRepository", method="upsert_booked_transaction")
    async def upsert_booked_transaction(
        self,
        transaction: BookedTransaction,
        *,
        fields_to_clear: frozenset[str] = frozenset(),
    ) -> BookedTransaction:
        """Upsert and return the final canonical booked transaction row."""

        return await self._upsert_booked_transaction(
            transaction,
            ownership=transaction_identity_ownership(transaction),
            fields_to_clear=fields_to_clear,
            refresh_payload_fingerprint=False,
        )

    @async_timed(
        repository="CostBasisTransactionRepository",
        method="upsert_generated_booked_transaction",
    )
    async def upsert_generated_booked_transaction(
        self,
        transaction: BookedTransaction,
        *,
        fields_to_clear: frozenset[str] = frozenset(),
    ) -> BookedTransaction:
        """Atomically upsert one canonical generated child within its existing ownership."""

        return await self._upsert_booked_transaction(
            transaction,
            ownership=require_generated_transaction_identity(transaction),
            fields_to_clear=fields_to_clear,
            refresh_payload_fingerprint=True,
        )

    async def _upsert_booked_transaction(
        self,
        transaction: BookedTransaction,
        *,
        ownership: TransactionIdentityOwnership,
        fields_to_clear: frozenset[str],
        refresh_payload_fingerprint: bool,
    ) -> BookedTransaction:
        transaction_values = canonical_transaction_identity_record_values(
            _booked_transaction_payload(
                transaction,
                fields_to_clear=fields_to_clear,
            ),
            ownership,
        )
        if refresh_payload_fingerprint:
            transaction_values["payload_fingerprint"] = transaction_payload_fingerprint(
                transaction_values
            )
        stmt = pg_insert(DBTransaction).values(**transaction_values)
        update_fields = [
            field_name
            for field_name in transaction_values
            if field_name not in {"id", "transaction_id"}
        ]
        update_dict = {field: getattr(stmt.excluded, field) for field in update_fields}
        upsert_statement = stmt.on_conflict_do_update(
            index_elements=["transaction_id"],
            set_=update_dict,
            where=transaction_identity_update_allowed(
                DBTransaction,
                ownership,
                excluded=stmt.excluded,
                updated_fields=transaction_values,
            ),
        )
        if not refresh_payload_fingerprint:
            persisted = (
                (await self.db.execute(upsert_statement.returning(DBTransaction)))
                .scalars()
                .one_or_none()
            )
            if persisted is None:
                raise GeneratedTransactionIdentityCollisionError(transaction.transaction_id)
            return _to_persisted_booked_transaction(
                persisted,
                tenant_id=transaction.tenant_id,
            )
        persisted_transaction_id = (
            await self.db.execute(upsert_statement.returning(DBTransaction.transaction_id))
        ).scalar_one_or_none()
        if persisted_transaction_id is None:
            raise GeneratedTransactionIdentityCollisionError(transaction.transaction_id)
        persisted_row = (
            (
                await self.db.execute(
                    select(*DBTransaction.__table__.columns).where(
                        DBTransaction.transaction_id == persisted_transaction_id
                    )
                )
            )
            .mappings()
            .one()
        )
        persisted = DBTransaction(**dict(persisted_row))
        final_payload_fingerprint = _persisted_transaction_payload_fingerprint(persisted)
        if persisted.payload_fingerprint != final_payload_fingerprint:
            await self.db.execute(
                update(DBTransaction)
                .where(DBTransaction.transaction_id == persisted.transaction_id)
                .values(payload_fingerprint=final_payload_fingerprint)
            )
            persisted.payload_fingerprint = final_payload_fingerprint
        return _to_persisted_booked_transaction(
            persisted,
            tenant_id=transaction.tenant_id,
        )
