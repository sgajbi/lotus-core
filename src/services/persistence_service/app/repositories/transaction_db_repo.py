# services/persistence_service/app/repositories/transaction_db_repo.py
import logging
from dataclasses import dataclass
from datetime import date

from portfolio_common.database_models import (
    CashAccountMaster,
    Instrument,
    Portfolio,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.tenant import TenantId
from portfolio_common.domain.transaction import (
    TransactionIdentityFamily,
    TransactionIdentityOwnership,
    TransactionPayloadIdentity,
    build_transaction_payload_identity,
    canonical_transaction_identity_record_values,
    transaction_identity_ownership,
)
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import TransactionSemanticConflictError
from portfolio_common.infrastructure.persistence.transaction_identity_guard import (
    GeneratedTransactionIdentityCollisionError,
)
from sqlalchemy import exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.event_record_mapper import (
    transaction_event_fee_component_values,
    transaction_event_has_named_fee_authority,
    transaction_event_to_record_values,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TransactionReferenceAvailability:
    """Reference state required to accept one transaction into the raw ledger."""

    portfolio_exists: bool
    instrument_exists: bool
    cash_account_exists: bool | None


@dataclass(frozen=True, slots=True)
class TransactionWriteOutcome:
    """Result of staging one immutable raw-ledger transaction."""

    transaction: DBTransaction
    inserted: bool


class TransactionDBRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_portfolio_tenant(self, portfolio_id: str) -> str | None:
        """Return normalized source-owned tenant authority for one portfolio."""

        tenant_id = (
            await self.db.execute(
                select(Portfolio.tenant_id).where(Portfolio.portfolio_id == portfolio_id)
            )
        ).scalar_one_or_none()
        return TenantId(tenant_id).value if tenant_id is not None else None

    async def resolve_transaction_reference_availability(
        self,
        *,
        portfolio_id: str,
        tenant_id: str,
        security_id: str,
        cash_account_id: str | None,
        cash_security_id: str | None,
        as_of_date: date,
    ) -> TransactionReferenceAvailability:
        """Resolve portfolio, instrument, and optional cash-account state in one database read."""
        normalized_security_id = security_id.strip()
        normalized_cash_account_id = (cash_account_id or "").strip()
        normalized_cash_security_id = (cash_security_id or "").strip()

        instrument_exists = (
            exists().where(func.trim(Instrument.security_id) == normalized_security_id)
            if normalized_security_id
            else literal(False)
        )
        cash_account_exists = literal(None)
        if normalized_cash_account_id:
            cash_account_conditions = [
                CashAccountMaster.portfolio_id == portfolio_id,
                CashAccountMaster.cash_account_id == normalized_cash_account_id,
                func.upper(func.trim(CashAccountMaster.lifecycle_status)) == "ACTIVE",
                or_(
                    CashAccountMaster.opened_on.is_(None),
                    CashAccountMaster.opened_on <= as_of_date,
                ),
                or_(
                    CashAccountMaster.closed_on.is_(None),
                    CashAccountMaster.closed_on >= as_of_date,
                ),
            ]
            if normalized_cash_security_id:
                cash_account_conditions.append(
                    func.trim(CashAccountMaster.security_id) == normalized_cash_security_id
                )
            cash_account_exists = exists().where(*cash_account_conditions)

        statement = select(
            exists().where(
                Portfolio.portfolio_id == portfolio_id,
                Portfolio.tenant_id == tenant_id,
            ),
            instrument_exists,
            cash_account_exists,
        )
        result = await self.db.execute(statement)
        portfolio_available, instrument_available, cash_account_available = result.one()
        return TransactionReferenceAvailability(
            portfolio_exists=bool(portfolio_available),
            instrument_exists=bool(instrument_available),
            cash_account_exists=(
                bool(cash_account_available) if cash_account_available is not None else None
            ),
        )

    async def _require_identical_durable_replay(
        self,
        *,
        existing: DBTransaction,
        incoming_ownership: TransactionIdentityOwnership,
        incoming_tenant_id: str,
        incoming_payload_identity: TransactionPayloadIdentity,
    ) -> None:
        existing_ownership = transaction_identity_ownership(existing)
        if existing_ownership != incoming_ownership:
            same_tenant_source_replay = (
                existing_ownership.family is TransactionIdentityFamily.SOURCE
                and incoming_ownership.family is TransactionIdentityFamily.SOURCE
                and await self.resolve_portfolio_tenant(existing.portfolio_id)
                == TenantId(incoming_tenant_id).value
            )
            if not same_tenant_source_replay:
                raise GeneratedTransactionIdentityCollisionError(incoming_ownership.transaction_id)
        if existing.payload_fingerprint != incoming_payload_identity.payload_fingerprint:
            raise TransactionSemanticConflictError(
                semantic_key=incoming_payload_identity.semantic_key,
                existing_payload_fingerprint=existing.payload_fingerprint,
                incoming_payload_fingerprint=incoming_payload_identity.payload_fingerprint,
            )

    async def create_or_update_transaction(
        self,
        event: TransactionEvent,
    ) -> TransactionWriteOutcome:
        """
        Insert one immutable source transaction or prove an identical durable replay.

        A materially changed payload is never an upsert. Approved correction commands are
        intentionally owned by #452 and do not pass through this raw persistence method.
        """
        try:
            ownership = transaction_identity_ownership(event)
            if event.tenant_id is None:
                raise ValueError("Transaction persistence requires an admitted tenant")
            payload_identity = build_transaction_payload_identity(
                event.model_dump(mode="python"),
                tenant_id=event.tenant_id,
            )
            event_dict = canonical_transaction_identity_record_values(
                transaction_event_to_record_values(event),
                ownership,
            )
            event_dict["payload_fingerprint"] = payload_identity.payload_fingerprint

            insert_stmt = (
                pg_insert(DBTransaction)
                .values(**event_dict)
                .on_conflict_do_nothing(index_elements=["transaction_id"])
                .returning(DBTransaction.transaction_id)
            )
            persisted_id = (await self.db.execute(insert_stmt)).scalar_one_or_none()
            inserted = persisted_id is not None
            persisted_transaction: DBTransaction
            if not inserted:
                existing = (
                    await self.db.execute(
                        select(DBTransaction)
                        .where(DBTransaction.transaction_id == ownership.transaction_id)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if existing is None:
                    raise GeneratedTransactionIdentityCollisionError(ownership.transaction_id)
                await self._require_identical_durable_replay(
                    existing=existing,
                    incoming_ownership=ownership,
                    incoming_tenant_id=event.tenant_id,
                    incoming_payload_identity=payload_identity,
                )
                persisted_id = existing.transaction_id
                persisted_transaction = existing
            else:
                persisted_transaction = DBTransaction(**event_dict)
            fee_components = transaction_event_fee_component_values(event)
            if inserted and transaction_event_has_named_fee_authority(event) and fee_components:
                await self.db.execute(
                    pg_insert(TransactionCost).values(fee_components).on_conflict_do_nothing()
                )
            logger.debug(
                "Transaction insert or identical replay staged.",
                extra={"transaction_id": ownership.transaction_id, "inserted": inserted},
            )

            return TransactionWriteOutcome(
                transaction=persisted_transaction,
                inserted=inserted,
            )

        except Exception:
            logger.error(
                "Failed to stage transaction insert or replay.",
                extra={"transaction_id": event.transaction_id},
                exc_info=True,
            )
            raise
