from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from portfolio_common.database_models import (
    CashAccountMaster,
    Instrument,
    Portfolio,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.transaction import build_transaction_payload_identity
from portfolio_common.events import TransactionEvent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.persistence_service.app.adapters.event_record_mapper import (
    transaction_event_fee_component_values,
    transaction_event_to_record_values,
)
from src.services.portfolio_transaction_processing_service.app.application import (
    ProcessTransactionResult,
    ProcessTransactionUseCase,
    TransactionProcessingIntent,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    map_transaction_event,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_tenant_authority import (  # noqa: E501
    SqlAlchemyTransactionTenantAuthority,
)
from src.services.portfolio_transaction_processing_service.app.runtime.dependency_composition import (  # noqa: E501
    build_process_transaction_use_case,
)
from tests.test_support.tenant import TEST_TENANT_ID


@dataclass(frozen=True, slots=True)
class TransactionProcessingTestContext:
    session_factory: async_sessionmaker[AsyncSession]
    use_case: ProcessTransactionUseCase


def transaction_processing_test_context(
    session: AsyncSession,
) -> TransactionProcessingTestContext:
    session_factory = async_sessionmaker(session.bind, expire_on_commit=False)
    return TransactionProcessingTestContext(
        session_factory=session_factory,
        use_case=build_process_transaction_use_case(session_factory=session_factory),
    )


def portfolio_record(
    portfolio_id: str,
    *,
    base_currency: str = "USD",
    client_id: str = "CLIENT-COMBINED-01",
    cost_basis_method: str = "FIFO",
    legal_book_id: str | None = None,
) -> Portfolio:
    return Portfolio(
        tenant_id=TEST_TENANT_ID,
        legal_book_id=legal_book_id,
        portfolio_id=portfolio_id,
        base_currency=base_currency,
        open_date=date(2025, 1, 1),
        risk_exposure="MODERATE",
        investment_time_horizon="MEDIUM_TERM",
        portfolio_type="DISCRETIONARY",
        booking_center_code="SG",
        client_id=client_id,
        is_leverage_allowed=False,
        status="ACTIVE",
        cost_basis_method=cost_basis_method,
    )


def instrument_record(
    security_id: str,
    *,
    name: str,
    isin: str,
    currency: str,
    product_type: str = "EQUITY",
    asset_class: str = "Equity",
) -> Instrument:
    return Instrument(
        security_id=security_id,
        name=name,
        isin=isin,
        currency=currency,
        product_type=product_type,
        asset_class=asset_class,
    )


def cash_account_record(
    cash_account_id: str,
    *,
    portfolio_id: str,
    security_id: str,
    account_currency: str,
    opened_on: date = date(2025, 1, 1),
) -> CashAccountMaster:
    """Build an active portfolio-owned settlement cash-account mapping."""

    return CashAccountMaster(
        cash_account_id=cash_account_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        display_name=f"Settlement cash {cash_account_id}",
        account_currency=account_currency,
        lifecycle_status="ACTIVE",
        opened_on=opened_on,
    )


def booked_transaction_event(
    *,
    transaction_id: str,
    portfolio_id: str,
    security_id: str,
    transaction_date: datetime,
    transaction_type: str,
    quantity: str,
    price: str,
    gross_amount: str,
    trade_fee: str = "0",
    trade_currency: str = "USD",
    **domain_fields: object,
) -> TransactionEvent:
    if (
        domain_fields.get("transaction_fx_rate") is not None
        and "transaction_fx_rate_origin" not in domain_fields
    ):
        domain_fields["transaction_fx_rate_origin"] = "SOURCE_BOOKED"
    return TransactionEvent(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        tenant_id=TEST_TENANT_ID,
        instrument_id=security_id,
        security_id=security_id,
        transaction_date=transaction_date,
        transaction_type=transaction_type,
        quantity=Decimal(quantity),
        price=Decimal(price),
        gross_transaction_amount=Decimal(gross_amount),
        trade_fee=Decimal(trade_fee),
        trade_currency=trade_currency,
        currency=trade_currency,
        **domain_fields,
    )


def canonical_transaction_record(event: TransactionEvent) -> DBTransaction:
    identity = build_transaction_payload_identity(
        event.model_dump(mode="python"), tenant_id=event.tenant_id
    )
    return DBTransaction(
        **transaction_event_to_record_values(event),
        payload_fingerprint=identity.payload_fingerprint,
        costs=[TransactionCost(**row) for row in transaction_event_fee_component_values(event)],
    )


async def persist_and_process_booked_transaction(
    *,
    session: AsyncSession,
    context: TransactionProcessingTestContext,
    event: TransactionEvent,
    event_id: str,
    correlation_id: str,
) -> ProcessTransactionResult:
    session.add(canonical_transaction_record(event))
    await session.commit()
    return await process_booked_transaction(
        context=context,
        event=event,
        event_id=event_id,
        correlation_id=correlation_id,
    )


async def process_booked_transaction(
    *,
    context: TransactionProcessingTestContext,
    event: TransactionEvent,
    event_id: str,
    correlation_id: str,
    processing_intent: TransactionProcessingIntent = TransactionProcessingIntent.STANDARD,
    repair_delivery_id: str | None = None,
) -> ProcessTransactionResult:
    if event.tenant_id is None:
        tenant_id = await SqlAlchemyTransactionTenantAuthority(context.session_factory).resolve(
            portfolio_id=event.portfolio_id,
            asserted_tenant_id=None,
        )
        event = event.model_copy(update={"tenant_id": tenant_id})
    return await context.use_case.execute(
        map_transaction_event(
            event,
            event_id=event_id,
            correlation_id=correlation_id,
            processing_intent=processing_intent,
            repair_delivery_id=repair_delivery_id,
        )
    )
