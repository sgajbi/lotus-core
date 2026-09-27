"""PostgreSQL behavior proof for immutable source-transaction payloads."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import Portfolio, ProcessedEvent, TransactionCost
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.transaction import build_transaction_payload_identity
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import (
    TransactionSemanticConflictError,
)
from portfolio_common.idempotency_repository import (
    IdempotencyRepository,
    SemanticEventClaimOutcome,
)
from portfolio_common.infrastructure.persistence.transaction_identity_guard import (
    GeneratedTransactionIdentityCollisionError,
)
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
)

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.asyncio]


def _event(*, tenant_id: str, portfolio_id: str, quantity: str = "10") -> TransactionEvent:
    amount = Decimal(quantity) * Decimal("125.50")
    return TransactionEvent(
        transaction_id="TX-DURABLE-CONFLICT-001",
        portfolio_id=portfolio_id,
        tenant_id=tenant_id,
        instrument_id="INST-DURABLE-001",
        security_id="SEC-DURABLE-001",
        transaction_date=datetime(2026, 9, 27, 10, 15, tzinfo=UTC),
        settlement_date=datetime(2026, 9, 29, 0, 0, tzinfo=UTC),
        transaction_type="BUY",
        quantity=Decimal(quantity),
        price=Decimal("125.50"),
        gross_transaction_amount=amount,
        trade_currency="USD",
        currency="USD",
        brokerage=Decimal("2.50"),
        source_system="BOOKING_SOURCE",
        source_transaction_reference="BOOKING-001",
    )


async def test_transaction_conflict_survives_transient_fence_purge_and_preserves_financial_state(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    tenant_a = "tenant-durable-a"
    tenant_b = "tenant-durable-b"
    portfolio_a = "PORT-DURABLE-A"
    portfolio_a_alternate = "PORT-DURABLE-A-ALTERNATE"
    portfolio_b = "PORT-DURABLE-B"
    for tenant_id, portfolio_id in (
        (tenant_a, portfolio_a),
        (tenant_a, portfolio_a_alternate),
        (tenant_b, portfolio_b),
    ):
        async_db_session.add(
            Portfolio(
                tenant_id=tenant_id,
                portfolio_id=portfolio_id,
                legal_book_id=f"BOOK-{portfolio_id}",
                base_currency="USD",
                open_date=date(2026, 1, 1),
                risk_exposure="Balanced",
                investment_time_horizon="Long",
                portfolio_type="Discretionary",
                booking_center_code="SG",
                client_id=f"CLIENT-{tenant_id}",
                status="ACTIVE",
            )
        )
    await async_db_session.commit()

    original = _event(tenant_id=tenant_a, portfolio_id=portfolio_a)
    identity = build_transaction_payload_identity(
        original.model_dump(mode="python"), tenant_id=tenant_a
    )
    idempotency = IdempotencyRepository(async_db_session)
    repository = TransactionDBRepository(async_db_session)

    assert (
        await idempotency.claim_semantic_event_processing(
            event_id=original.transaction_id,
            portfolio_id=original.portfolio_id,
            service_name="persistence-transactions",
            semantic_key=identity.semantic_key,
            payload_fingerprint=identity.payload_fingerprint,
            correlation_id="corr-original",
            tenant_id=tenant_a,
        )
        is SemanticEventClaimOutcome.CLAIMED
    )
    await repository.create_or_update_transaction(original)
    await async_db_session.commit()

    # A new transport observation of identical economics is a no-op.
    replay = original.model_copy(
        update={
            "correlation_id": "corr-replay",
            "created_at": datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
            "epoch": 42,
        }
    )
    replay_identity = build_transaction_payload_identity(
        replay.model_dump(mode="python"), tenant_id=tenant_a
    )
    assert replay_identity.payload_fingerprint == identity.payload_fingerprint
    assert (
        await idempotency.claim_semantic_event_processing(
            event_id=replay.transaction_id,
            portfolio_id=replay.portfolio_id,
            service_name="persistence-transactions",
            semantic_key=replay_identity.semantic_key,
            payload_fingerprint=replay_identity.payload_fingerprint,
            correlation_id="corr-replay",
            tenant_id=tenant_a,
        )
        is SemanticEventClaimOutcome.PHYSICAL_DUPLICATE
    )
    await async_db_session.rollback()

    changed = _event(tenant_id=tenant_a, portfolio_id=portfolio_a, quantity="11")
    changed_identity = build_transaction_payload_identity(
        changed.model_dump(mode="python"), tenant_id=tenant_a
    )
    assert (
        await idempotency.claim_semantic_event_processing(
            event_id=changed.transaction_id,
            portfolio_id=changed.portfolio_id,
            service_name="persistence-transactions",
            semantic_key=changed_identity.semantic_key,
            payload_fingerprint=changed_identity.payload_fingerprint,
            correlation_id="corr-changed",
            tenant_id=tenant_a,
        )
        is SemanticEventClaimOutcome.SEMANTIC_CONFLICT
    )
    await async_db_session.rollback()

    # Simulate retention expiry. The ledger fingerprint remains the final write fence.
    await async_db_session.execute(
        delete(ProcessedEvent).where(
            ProcessedEvent.tenant_id == tenant_a,
            ProcessedEvent.service_name == "persistence-transactions",
            ProcessedEvent.event_id == original.transaction_id,
        )
    )
    await async_db_session.commit()
    with pytest.raises(TransactionSemanticConflictError):
        await repository.create_or_update_transaction(changed)
    await async_db_session.rollback()

    persisted = await async_db_session.scalar(
        select(DBTransaction).where(DBTransaction.transaction_id == original.transaction_id)
    )
    assert persisted is not None
    assert persisted.portfolio_id == portfolio_a
    assert persisted.quantity == Decimal("10")
    assert persisted.gross_transaction_amount == Decimal("1255")
    assert persisted.payload_fingerprint == identity.payload_fingerprint
    costs = list(
        (
            await async_db_session.scalars(
                select(TransactionCost).where(
                    TransactionCost.transaction_id == original.transaction_id
                )
            )
        ).all()
    )
    assert [(cost.fee_type, cost.amount, cost.currency) for cost in costs] == [
        ("brokerage", Decimal("2.50"), "USD")
    ]

    same_tenant_portfolio_change = _event(
        tenant_id=tenant_a,
        portfolio_id=portfolio_a_alternate,
    )
    with pytest.raises(TransactionSemanticConflictError):
        await repository.create_or_update_transaction(same_tenant_portfolio_change)
    await async_db_session.rollback()

    # The existing global transaction-id contract also fails closed across tenants;
    # composite transaction identity remains a separate #798 tranche.
    foreign_tenant_replay = _event(tenant_id=tenant_b, portfolio_id=portfolio_b)
    with pytest.raises(GeneratedTransactionIdentityCollisionError):
        await repository.create_or_update_transaction(foreign_tenant_replay)
    await async_db_session.rollback()
    assert (
        await async_db_session.scalar(
            select(DBTransaction.portfolio_id).where(
                DBTransaction.transaction_id == original.transaction_id
            )
        )
        == portfolio_a
    )


async def test_concurrent_changed_replay_waits_then_fails_closed(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    tenant_id = "tenant-concurrent"
    portfolio_id = "PORT-CONCURRENT"
    async_db_session.add(
        Portfolio(
            tenant_id=tenant_id,
            portfolio_id=portfolio_id,
            legal_book_id="BOOK-CONCURRENT",
            base_currency="USD",
            open_date=date(2026, 1, 1),
            risk_exposure="Balanced",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id="CLIENT-CONCURRENT",
            status="ACTIVE",
        )
    )
    await async_db_session.commit()

    original = _event(tenant_id=tenant_id, portfolio_id=portfolio_id)
    changed = _event(tenant_id=tenant_id, portfolio_id=portfolio_id, quantity="11")
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with session_factory() as first_session, session_factory() as second_session:
        await TransactionDBRepository(first_session).create_or_update_transaction(original)
        second_pid = await second_session.scalar(text("SELECT pg_backend_pid()"))
        changed_write = asyncio.create_task(
            TransactionDBRepository(second_session).create_or_update_transaction(changed)
        )

        blocked = False
        for _ in range(40):
            blockers = await async_db_session.scalar(
                text("SELECT pg_blocking_pids(:pid)"), {"pid": second_pid}
            )
            if blockers:
                blocked = True
                break
            await asyncio.sleep(0.05)
        assert blocked, "changed replay did not reach the PostgreSQL unique-index wait"

        await first_session.commit()
        with pytest.raises(TransactionSemanticConflictError):
            await changed_write
        await second_session.rollback()

    persisted = await async_db_session.scalar(
        select(DBTransaction).where(DBTransaction.transaction_id == original.transaction_id)
    )
    assert persisted is not None
    assert persisted.quantity == Decimal("10")
    assert persisted.gross_transaction_amount == Decimal("1255")


async def test_rolled_back_claim_and_ledger_write_retry_atomically_in_a_fresh_session(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    tenant_id = "tenant-atomic-restart"
    portfolio_id = "PORT-ATOMIC-RESTART"
    async_db_session.add(
        Portfolio(
            tenant_id=tenant_id,
            portfolio_id=portfolio_id,
            legal_book_id="BOOK-ATOMIC-RESTART",
            base_currency="USD",
            open_date=date(2026, 1, 1),
            risk_exposure="Balanced",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center_code="SG",
            client_id="CLIENT-ATOMIC-RESTART",
            status="ACTIVE",
        )
    )
    await async_db_session.commit()

    event = _event(tenant_id=tenant_id, portfolio_id=portfolio_id)
    identity = build_transaction_payload_identity(
        event.model_dump(mode="python"), tenant_id=tenant_id
    )
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async with session_factory() as interrupted_session:
        idempotency = IdempotencyRepository(interrupted_session)
        assert (
            await idempotency.claim_semantic_event_processing(
                event_id=event.transaction_id,
                portfolio_id=event.portfolio_id,
                service_name="persistence-transactions",
                semantic_key=identity.semantic_key,
                payload_fingerprint=identity.payload_fingerprint,
                correlation_id="corr-interrupted",
                tenant_id=tenant_id,
            )
            is SemanticEventClaimOutcome.CLAIMED
        )
        await TransactionDBRepository(interrupted_session).create_or_update_transaction(event)
        assert (
            await interrupted_session.scalar(
                select(DBTransaction.transaction_id).where(
                    DBTransaction.transaction_id == event.transaction_id
                )
            )
            == event.transaction_id
        )
        await interrupted_session.rollback()

    async with session_factory() as verification_session:
        assert (
            await verification_session.scalar(
                select(DBTransaction.transaction_id).where(
                    DBTransaction.transaction_id == event.transaction_id
                )
            )
            is None
        )
        assert (
            await verification_session.scalar(
                select(ProcessedEvent.event_id).where(
                    ProcessedEvent.tenant_id == tenant_id,
                    ProcessedEvent.service_name == "persistence-transactions",
                    ProcessedEvent.event_id == event.transaction_id,
                )
            )
            is None
        )

    async with session_factory() as retry_session:
        retry_idempotency = IdempotencyRepository(retry_session)
        assert (
            await retry_idempotency.claim_semantic_event_processing(
                event_id=event.transaction_id,
                portfolio_id=event.portfolio_id,
                service_name="persistence-transactions",
                semantic_key=identity.semantic_key,
                payload_fingerprint=identity.payload_fingerprint,
                correlation_id="corr-retry",
                tenant_id=tenant_id,
            )
            is SemanticEventClaimOutcome.CLAIMED
        )
        await TransactionDBRepository(retry_session).create_or_update_transaction(event)
        await retry_session.commit()

    async with session_factory() as final_session:
        persisted = await final_session.scalar(
            select(DBTransaction).where(DBTransaction.transaction_id == event.transaction_id)
        )
        assert persisted is not None
        assert persisted.quantity == Decimal("10")
        assert persisted.gross_transaction_amount == Decimal("1255")
        assert persisted.payload_fingerprint == identity.payload_fingerprint
        assert (
            await final_session.scalar(
                select(ProcessedEvent.payload_fingerprint).where(
                    ProcessedEvent.tenant_id == tenant_id,
                    ProcessedEvent.service_name == "persistence-transactions",
                    ProcessedEvent.event_id == event.transaction_id,
                )
            )
            == identity.payload_fingerprint
        )
