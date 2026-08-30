"""Prove generated transaction ownership against real PostgreSQL conflicts."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import Cashflow, OutboxEvent, Portfolio, PositionState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from portfolio_common.infrastructure.persistence.transaction_identity_guard import (
    GeneratedTransactionIdentityCollisionError,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
)
from tests.test_support.tenant import TEST_TENANT_ID

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


def _source_event(transaction_id: str, *, portfolio_id: str = "PORT-OWNER-A") -> TransactionEvent:
    return TransactionEvent(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id="SEC-OWNER-1",
        security_id="SEC-OWNER-1",
        transaction_date=datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )


def _generated_event(
    family: str,
    *,
    portfolio_id: str = "PORT-OWNER-A",
    amount: Decimal = Decimal("1000"),
) -> TransactionEvent:
    if family == "cash":
        return TransactionEvent(
            transaction_id="ROOT-OWNER-1-CASHLEG",
            portfolio_id=portfolio_id,
            instrument_id="CASH-USD",
            security_id="CASH-USD",
            transaction_date=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
            transaction_type="ADJUSTMENT",
            quantity=Decimal(0),
            price=Decimal(0),
            gross_transaction_amount=amount,
            trade_currency="USD",
            currency="USD",
            cash_entry_mode="AUTO_GENERATE",
            originating_transaction_id="ROOT-OWNER-1",
            originating_transaction_type="BUY",
            link_type="BUY_TO_CASH",
        )
    return TransactionEvent(
        transaction_id="ROOT-OWNER-1-ACCRUED-INTEREST",
        portfolio_id=portfolio_id,
        instrument_id="SEC-OWNER-1",
        security_id="SEC-OWNER-1",
        transaction_date=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
        transaction_type="INTEREST",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=amount,
        trade_currency="USD",
        currency="USD",
        component_type="REDEMPTION_ACCRUED_INTEREST",
        component_id="ROOT-OWNER-1-ACCRUED-INTEREST:v1",
        originating_transaction_id="ROOT-OWNER-1",
        originating_transaction_type="MATURITY_REDEMPTION",
        link_type="REDEMPTION_TO_ACCRUED_INTEREST",
    )


def _incomplete_generated_shape_event(family: str) -> TransactionEvent:
    """Build suffix-shaped metadata that remains source-owned because it is incomplete."""

    generated = _generated_event(family)
    if family == "cash":
        return generated.model_copy(update={"component_id": "UPSTREAM-COMPONENT-1"})
    return generated.model_copy(update={"link_type": None})


async def _persist(
    session_factory: async_sessionmaker[AsyncSession],
    event: TransactionEvent,
) -> str:
    async with session_factory() as session:
        try:
            await TransactionDBRepository(session).create_or_update_transaction(event)
            await session.commit()
            return "persisted"
        except GeneratedTransactionIdentityCollisionError:
            await session.rollback()
            return "generated_transaction_identity_collision"


async def _seed_portfolios(session: AsyncSession) -> None:
    session.add_all(
        [
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2026, 1, 1),
                risk_exposure="MEDIUM",
                investment_time_horizon="LONG_TERM",
                portfolio_type="ADVISORY",
                booking_center_code="SG",
                client_id=f"CLIENT-{portfolio_id}",
                status="ACTIVE",
            )
            for portfolio_id in ("PORT-OWNER-A", "PORT-OWNER-B")
        ]
    )
    await session.commit()


@pytest.mark.parametrize("family", ["cash", "interest"])
@pytest.mark.parametrize("first_owner", ["source", "generated"])
async def test_first_owner_wins_without_hybrid_or_downstream_evidence(
    clean_db,
    async_db_session: AsyncSession,
    family: str,
    first_owner: str,
) -> None:
    await _seed_portfolios(async_db_session)
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    generated = _generated_event(family)
    source = _source_event(generated.transaction_id)
    first, second = (source, generated) if first_owner == "source" else (generated, source)

    assert await _persist(factory, first) == "persisted"
    assert await _persist(factory, second) == "generated_transaction_identity_collision"

    async_db_session.expire_all()
    row = (
        await async_db_session.execute(
            select(DBTransaction).where(DBTransaction.transaction_id == generated.transaction_id)
        )
    ).scalar_one()
    assert row.transaction_type == first.transaction_type
    assert row.portfolio_id == first.portfolio_id
    assert row.originating_transaction_id == first.originating_transaction_id
    for model in (Cashflow, PositionState, OutboxEvent):
        assert (await async_db_session.scalar(select(func.count()).select_from(model))) == 0


@pytest.mark.parametrize("family", ["cash", "interest"])
async def test_concurrent_source_and_generated_creators_produce_one_owner(
    clean_db,
    async_db_session: AsyncSession,
    family: str,
) -> None:
    await _seed_portfolios(async_db_session)
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    generated = _generated_event(family)
    source = _source_event(generated.transaction_id)

    outcomes = await asyncio.gather(
        _persist(factory, source),
        _persist(factory, generated),
    )

    assert sorted(outcomes) == ["generated_transaction_identity_collision", "persisted"]
    assert (
        await async_db_session.scalar(
            select(func.count()).where(DBTransaction.transaction_id == generated.transaction_id)
        )
    ) == 1


@pytest.mark.parametrize("family", ["cash", "interest"])
async def test_same_owner_replay_updates_but_cross_portfolio_reclaim_fails(
    clean_db,
    async_db_session: AsyncSession,
    family: str,
) -> None:
    await _seed_portfolios(async_db_session)
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    generated = _generated_event(family)

    assert await _persist(factory, generated) == "persisted"
    corrected = generated.model_copy(update={"gross_transaction_amount": Decimal("875")})
    foreign_portfolio = generated.model_copy(update={"portfolio_id": "PORT-OWNER-B"})
    assert await _persist(factory, corrected) == "persisted"
    assert await _persist(factory, foreign_portfolio) == (
        "generated_transaction_identity_collision"
    )

    async_db_session.expire_all()
    row = (
        await async_db_session.execute(
            select(DBTransaction).where(DBTransaction.transaction_id == generated.transaction_id)
        )
    ).scalar_one()
    assert row.portfolio_id == "PORT-OWNER-A"
    assert row.gross_transaction_amount == Decimal("875")


@pytest.mark.parametrize("family", ["cash", "interest"])
async def test_padded_generated_identity_replays_against_canonical_row(
    clean_db,
    async_db_session: AsyncSession,
    family: str,
) -> None:
    await _seed_portfolios(async_db_session)
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    generated = _generated_event(family)

    assert await _persist(factory, generated) == "persisted"
    padded = generated.model_copy(
        update={
            "transaction_id": f"  {generated.transaction_id}  ",
            "portfolio_id": f"  {generated.portfolio_id}  ",
            "originating_transaction_id": (f"  {generated.originating_transaction_id}  "),
            "gross_transaction_amount": Decimal("875"),
        }
    )
    assert await _persist(factory, padded) == "persisted"

    async_db_session.expire_all()
    rows = (
        (
            await async_db_session.execute(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == generated.transaction_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].portfolio_id == generated.portfolio_id
    assert rows[0].originating_transaction_id == generated.originating_transaction_id
    assert rows[0].gross_transaction_amount == Decimal("875")


@pytest.mark.parametrize("family", ["cash", "interest"])
async def test_generated_owner_rejects_origin_type_reclassification(
    clean_db,
    async_db_session: AsyncSession,
    family: str,
) -> None:
    await _seed_portfolios(async_db_session)
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    generated = _generated_event(family)
    replacement_type = "DIVIDEND" if family == "cash" else "CALL_REDEMPTION"
    update = {"originating_transaction_type": replacement_type}
    if family == "cash":
        update["link_type"] = "DIVIDEND_TO_CASH"
    reclassified = generated.model_copy(update=update)

    assert await _persist(factory, generated) == "persisted"
    assert await _persist(factory, reclassified) == "generated_transaction_identity_collision"

    async_db_session.expire_all()
    row = (
        await async_db_session.execute(
            select(DBTransaction).where(DBTransaction.transaction_id == generated.transaction_id)
        )
    ).scalar_one()
    assert row.originating_transaction_type == generated.originating_transaction_type


@pytest.mark.parametrize("family", ["cash", "interest"])
async def test_incomplete_generated_shape_replays_as_source_owned(
    clean_db,
    async_db_session: AsyncSession,
    family: str,
) -> None:
    await _seed_portfolios(async_db_session)
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    source = _incomplete_generated_shape_event(family)

    assert await _persist(factory, source) == "persisted"
    corrected = source.model_copy(update={"gross_transaction_amount": Decimal("875")})
    assert await _persist(factory, corrected) == "persisted"

    async_db_session.expire_all()
    row = (
        await async_db_session.execute(
            select(DBTransaction).where(DBTransaction.transaction_id == source.transaction_id)
        )
    ).scalar_one()
    assert row.gross_transaction_amount == Decimal("875")


@pytest.mark.parametrize("family", ["cash", "interest"])
async def test_sparse_source_update_cannot_merge_into_generated_ownership(
    clean_db,
    async_db_session: AsyncSession,
    family: str,
) -> None:
    await _seed_portfolios(async_db_session)
    factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    generated = _generated_event(family)
    if family == "cash":
        incomplete = generated.model_copy(update={"cash_entry_mode": None})
        sparse_update = generated.model_copy(
            update={
                "originating_transaction_id": None,
                "originating_transaction_type": None,
                "link_type": None,
            }
        )
    else:
        incomplete = generated.model_copy(update={"link_type": None})
        sparse_update = generated.model_copy(
            update={
                "originating_transaction_id": None,
                "originating_transaction_type": None,
                "component_type": None,
                "component_id": None,
            }
        )

    assert await _persist(factory, incomplete) == "persisted"
    assert await _persist(factory, sparse_update) == "generated_transaction_identity_collision"

    async_db_session.expire_all()
    row = (
        await async_db_session.execute(
            select(DBTransaction).where(DBTransaction.transaction_id == generated.transaction_id)
        )
    ).scalar_one()
    if family == "cash":
        assert row.cash_entry_mode is None
        assert row.originating_transaction_id == generated.originating_transaction_id
    else:
        assert row.link_type is None
        assert row.component_id == generated.component_id
