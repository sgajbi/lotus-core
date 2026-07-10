from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from portfolio_common.database_models import Instrument, Portfolio
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.persistence_service.app.adapters.event_record_mapper import (
    transaction_event_to_record_values,
)
from src.services.portfolio_transaction_processing_service.app.application import (
    ProcessTransactionResult,
    ProcessTransactionUseCase,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    map_transaction_event,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    build_process_transaction_use_case,
)


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
) -> Portfolio:
    return Portfolio(
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
) -> Instrument:
    return Instrument(
        security_id=security_id,
        name=name,
        isin=isin,
        currency=currency,
        product_type="EQUITY",
        asset_class="Equity",
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
    return TransactionEvent(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
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
    return DBTransaction(**transaction_event_to_record_values(event))


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
) -> ProcessTransactionResult:
    return await context.use_case.execute(
        map_transaction_event(
            event,
            event_id=event_id,
            correlation_id=correlation_id,
        )
    )
