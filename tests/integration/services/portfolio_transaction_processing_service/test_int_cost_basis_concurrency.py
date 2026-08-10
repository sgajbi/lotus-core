from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import CostBasisProcessingState, PositionLotState
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    PreparedCostProcessingUseCase,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BUY_DEFAULT_POLICY_ID,
    BUY_DEFAULT_POLICY_VERSION,
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    redemption as redemption_domain,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    CostBasisProcessingAdapter,
    SqlAlchemyAverageCostPoolRepository,
    SqlAlchemyCorporateActionReconciliationRepository,
    SqlAlchemyCostBasisFxRateRepository,
    SqlAlchemyCostBasisLotBasisTransferRepository,
    SqlAlchemyCostBasisLotDisposalRepository,
    SqlAlchemyCostBasisLotRepository,
    SqlAlchemyCostBasisProcessingStateRepository,
    SqlAlchemyCostBasisReferenceDataRepository,
    SqlAlchemyCostBasisTransactionRepository,
    SqlAlchemyInitialOpeningCostStateRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.fixed_income_book_cost import (  # noqa: E501
    SqlAlchemyLotAmortizedCostProfileRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.income import (
    SqlAlchemyAccruedIncomeOffsetRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_mapping.booked_transaction import (  # noqa: E501
    to_booked_transaction,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostProcessingEffectStagingPort,
)
from tests.test_support.async_task_coordination import (
    cancel_pending_tasks,
    wait_for_postgres_advisory_lock_wait,
    wait_for_task_signal,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
    portfolio_record,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
    pytest.mark.resilience,
]


class _HeldHistoryCostRepository(SqlAlchemyCostBasisTransactionRepository):
    def __init__(
        self,
        db: AsyncSession,
        *,
        history_read: asyncio.Event,
        release_history: asyncio.Event,
    ) -> None:
        super().__init__(db)
        self._history_read = history_read
        self._release_history = release_history

    async def get_transaction_history(
        self,
        portfolio_id: str,
        security_id: str,
        exclude_id: str | None = None,
    ):
        history = await super().get_transaction_history(portfolio_id, security_id, exclude_id)
        self._history_read.set()
        await self._release_history.wait()
        return history


class _ObservedProcessingStateRepository(SqlAlchemyCostBasisProcessingStateRepository):
    def __init__(
        self,
        db: AsyncSession,
        *,
        lock_attempted: asyncio.Event,
        backend_pid: list[int],
    ) -> None:
        super().__init__(db)
        self._lock_attempted = lock_attempted
        self._backend_pid = backend_pid

    async def acquire_cost_basis_processing_lock(
        self,
        portfolio_id: str,
        security_id: str,
    ) -> None:
        self._backend_pid.append(await self._session.scalar(text("SELECT pg_backend_pid()")))
        self._lock_attempted.set()
        await super().acquire_cost_basis_processing_lock(portfolio_id, security_id)


class _HeldLinkedGroupCostRepository(SqlAlchemyCostBasisTransactionRepository):
    def __init__(
        self,
        db: AsyncSession,
        *,
        group_read: asyncio.Event,
        release_group_read: asyncio.Event,
    ) -> None:
        super().__init__(db)
        self._group_read = group_read
        self._release_group_read = release_group_read

    async def get_linked_transaction_group(
        self,
        portfolio_id: str,
        linked_transaction_group_id: str,
        exclude_id: str | None = None,
    ) -> list[BookedTransaction]:
        history = await super().get_linked_transaction_group(
            portfolio_id,
            linked_transaction_group_id,
            exclude_id,
        )
        self._group_read.set()
        await self._release_group_read.wait()
        return history


class _ObservedLinkedGroupProcessingStateRepository(SqlAlchemyCostBasisProcessingStateRepository):
    def __init__(
        self,
        db: AsyncSession,
        *,
        group_lock_attempted: asyncio.Event,
        backend_pid: list[int],
    ) -> None:
        super().__init__(db)
        self._group_lock_attempted = group_lock_attempted
        self._backend_pid = backend_pid

    async def acquire_linked_redemption_group_lock(
        self,
        portfolio_id: str,
        linked_transaction_group_id: str,
    ) -> None:
        self._backend_pid.append(await self._session.scalar(text("SELECT pg_backend_pid()")))
        self._group_lock_attempted.set()
        await super().acquire_linked_redemption_group_lock(
            portfolio_id,
            linked_transaction_group_id,
        )


async def _stage_cost_calculation(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    event,
    repository_factory,
    processing_state_factory=SqlAlchemyCostBasisProcessingStateRepository,
) -> None:
    async with session_factory() as session, session.begin():
        await CostBasisProcessingAdapter(
            processor=PreparedCostProcessingUseCase(),
            repository=repository_factory(session),
            average_cost_pools=SqlAlchemyAverageCostPoolRepository(session),
            lot_disposals=SqlAlchemyCostBasisLotDisposalRepository(session),
            lot_basis_transfers=SqlAlchemyCostBasisLotBasisTransferRepository(session),
            lot_states=SqlAlchemyCostBasisLotRepository(session),
            amortized_cost_profiles=SqlAlchemyLotAmortizedCostProfileRepository(session),
            income_offsets=SqlAlchemyAccruedIncomeOffsetRepository(session),
            initial_opening_state=SqlAlchemyInitialOpeningCostStateRepository(session),
            reference_data=SqlAlchemyCostBasisReferenceDataRepository(session),
            fx_rates=SqlAlchemyCostBasisFxRateRepository(session),
            processing_state=processing_state_factory(session),
            reconciliation_repository=SqlAlchemyCorporateActionReconciliationRepository(session),
            effect_stager=AsyncMock(spec=CostProcessingEffectStagingPort),
        ).process(
            to_booked_transaction(event),
            correlation_id=f"corr-{event.transaction_id}",
            traceparent=None,
        )


async def test_same_key_buy_sell_and_replay_serialize_to_deterministic_fifo_lot_state(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COST-LOCK-01"
    security_id = "SEC-COST-LOCK-01"
    buy = booked_transaction_event(
        transaction_id="BUY-COST-LOCK-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    sell = booked_transaction_event(
        transaction_id="SELL-COST-LOCK-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="60",
        price="15",
        gross_amount="900",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name="Cost Lock Proof Equity",
                isin="SG0000000484",
                currency="USD",
            ),
            canonical_transaction_record(buy),
        ]
    )
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    buy_history_read = asyncio.Event()
    release_buy_history = asyncio.Event()
    sell_lock_attempted = asyncio.Event()
    replay_lock_attempted = asyncio.Event()
    sell_backend_pid: list[int] = []
    replay_backend_pid: list[int] = []

    buy_task = asyncio.create_task(
        _stage_cost_calculation(
            session_factory=session_factory,
            event=buy,
            repository_factory=lambda session: _HeldHistoryCostRepository(
                session,
                history_read=buy_history_read,
                release_history=release_buy_history,
            ),
        )
    )
    sell_task: asyncio.Task[None] | None = None
    replay_task: asyncio.Task[None] | None = None
    try:
        await wait_for_task_signal(buy_task, buy_history_read, timeout=2)

        async with session_factory() as insert_session, insert_session.begin():
            insert_session.add(canonical_transaction_record(sell))

        sell_task = asyncio.create_task(
            _stage_cost_calculation(
                session_factory=session_factory,
                event=sell,
                repository_factory=SqlAlchemyCostBasisTransactionRepository,
                processing_state_factory=lambda session: _ObservedProcessingStateRepository(
                    session,
                    lock_attempted=sell_lock_attempted,
                    backend_pid=sell_backend_pid,
                ),
            )
        )
        replay_task = asyncio.create_task(
            _stage_cost_calculation(
                session_factory=session_factory,
                event=sell,
                repository_factory=SqlAlchemyCostBasisTransactionRepository,
                processing_state_factory=lambda session: _ObservedProcessingStateRepository(
                    session,
                    lock_attempted=replay_lock_attempted,
                    backend_pid=replay_backend_pid,
                ),
            )
        )
        await wait_for_task_signal(sell_task, sell_lock_attempted, timeout=2)
        await wait_for_task_signal(replay_task, replay_lock_attempted, timeout=2)
        assert len(sell_backend_pid) == 1
        assert len(replay_backend_pid) == 1
        await wait_for_postgres_advisory_lock_wait(
            sell_task,
            session_factory,
            backend_pid=sell_backend_pid[0],
            timeout=2,
        )
        await wait_for_postgres_advisory_lock_wait(
            replay_task,
            session_factory,
            backend_pid=replay_backend_pid[0],
            timeout=2,
        )

        release_buy_history.set()
        await asyncio.wait_for(
            asyncio.gather(buy_task, sell_task, replay_task),
            timeout=8,
        )
    finally:
        release_buy_history.set()
        await cancel_pending_tasks(buy_task, sell_task, replay_task)

    async with session_factory() as verification_session:
        lots = list(
            (
                await verification_session.scalars(
                    select(PositionLotState).where(
                        PositionLotState.portfolio_id == portfolio_id,
                        PositionLotState.security_id == security_id,
                    )
                )
            ).all()
        )
        checkpoint = (
            await verification_session.scalars(
                select(CostBasisProcessingState).where(
                    CostBasisProcessingState.portfolio_id == portfolio_id,
                    CostBasisProcessingState.security_id == security_id,
                )
            )
        ).one()

    assert len(lots) == 1
    assert lots[0].source_transaction_id == buy.transaction_id
    assert lots[0].open_quantity == Decimal("40")
    assert lots[0].lot_cost_local == Decimal("400")
    assert lots[0].lot_cost_base == Decimal("400")
    assert lots[0].calculation_policy_id == BUY_DEFAULT_POLICY_ID
    assert lots[0].calculation_policy_version == BUY_DEFAULT_POLICY_VERSION
    assert checkpoint.cost_basis_method == "FIFO"
    assert checkpoint.latest_transaction_id == sell.transaction_id
    assert checkpoint.engine_state_version == "open-lot-v1"


async def test_cost_basis_processing_lock_does_not_serialize_other_security_keys(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async with (
        session_factory() as owning_session,
        owning_session.begin(),
        session_factory() as other_security_session,
        other_security_session.begin(),
    ):
        await SqlAlchemyCostBasisProcessingStateRepository(
            owning_session
        ).acquire_cost_basis_processing_lock(
            "PORT-COST-LOCK-02",
            "SEC-COST-LOCK-01",
        )
        await asyncio.wait_for(
            SqlAlchemyCostBasisProcessingStateRepository(
                other_security_session
            ).acquire_cost_basis_processing_lock(
                "PORT-COST-LOCK-02",
                "SEC-COST-LOCK-02",
            ),
            timeout=1,
        )


async def test_linked_redemption_group_lock_does_not_serialize_other_groups(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async with (
        session_factory() as owning_session,
        owning_session.begin(),
        session_factory() as other_group_session,
        other_group_session.begin(),
    ):
        await SqlAlchemyCostBasisProcessingStateRepository(
            owning_session
        ).acquire_linked_redemption_group_lock(
            "PORT-COST-LOCK-03",
            "GROUP-REDEMPTION-01",
        )
        await asyncio.wait_for(
            SqlAlchemyCostBasisProcessingStateRepository(
                other_group_session
            ).acquire_linked_redemption_group_lock(
                "PORT-COST-LOCK-03",
                "GROUP-REDEMPTION-02",
            ),
            timeout=1,
        )


@pytest.mark.parametrize("first_is_redemption", [True, False])
async def test_linked_redemption_interest_group_serializes_cross_security_authority(
    clean_db,
    async_db_session: AsyncSession,
    first_is_redemption: bool,
) -> None:
    portfolio_id = "PORT-REDEMPTION-GROUP-LOCK-01"
    bond_security_id = "FO_FI_REDEMPTION_GROUP_LOCK_01"
    interest_security_id = "FO_FI_INTEREST_GROUP_LOCK_01"
    group_id = "GROUP-REDEMPTION-LOCK-01"
    acquisition = booked_transaction_event(
        transaction_id="BUY-REDEMPTION-GROUP-LOCK-01",
        portfolio_id=portfolio_id,
        security_id=bond_security_id,
        transaction_date=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="0.97",
        gross_amount="97",
    )
    redemption = booked_transaction_event(
        transaction_id="MATURITY-REDEMPTION-GROUP-LOCK-01",
        portfolio_id=portfolio_id,
        security_id=bond_security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc),
        transaction_type="MATURITY_REDEMPTION",
        quantity="100",
        price="1",
        gross_amount="100",
        redemption_price_type="PAR",
        principal_proceeds_local=Decimal("100"),
        accrued_interest_proceeds_local=Decimal("5"),
        economic_event_id="EVENT-REDEMPTION-LOCK-01",
        linked_transaction_group_id=group_id,
        settlement_cash_account_id="CASH-USD-REDEMPTION-LOCK-01",
        settlement_cash_instrument_id="CASH-USD",
    )
    independent_interest = booked_transaction_event(
        transaction_id="INTEREST-REDEMPTION-GROUP-LOCK-01",
        portfolio_id=portfolio_id,
        security_id=interest_security_id,
        transaction_date=datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc),
        transaction_type="INTEREST",
        quantity="0",
        price="0",
        gross_amount="5",
        interest_direction="INCOME",
        economic_event_id="EVENT-REDEMPTION-LOCK-01",
        linked_transaction_group_id=group_id,
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                bond_security_id,
                name="Linked Group Redemption Note",
                isin="SG0000000517",
                currency="USD",
                product_type="BOND",
                asset_class="FIXED_INCOME",
            ),
            instrument_record(
                interest_security_id,
                name="Linked Group Interest Authority",
                isin="SG0000000525",
                currency="USD",
                product_type="BOND",
                asset_class="FIXED_INCOME",
            ),
            canonical_transaction_record(acquisition),
        ]
    )
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    await _stage_cost_calculation(
        session_factory=session_factory,
        event=acquisition,
        repository_factory=SqlAlchemyCostBasisTransactionRepository,
    )

    first, second = (
        (redemption, independent_interest)
        if first_is_redemption
        else (independent_interest, redemption)
    )
    async with session_factory() as insert_session, insert_session.begin():
        insert_session.add(canonical_transaction_record(first))

    group_read = asyncio.Event()
    release_group_read = asyncio.Event()
    second_group_lock_attempted = asyncio.Event()
    second_backend_pid: list[int] = []
    first_task = asyncio.create_task(
        _stage_cost_calculation(
            session_factory=session_factory,
            event=first,
            repository_factory=lambda session: _HeldLinkedGroupCostRepository(
                session,
                group_read=group_read,
                release_group_read=release_group_read,
            ),
        )
    )
    second_task: asyncio.Task[None] | None = None
    try:
        await wait_for_task_signal(first_task, group_read, timeout=2)
        async with session_factory() as insert_session, insert_session.begin():
            insert_session.add(canonical_transaction_record(second))

        second_task = asyncio.create_task(
            _stage_cost_calculation(
                session_factory=session_factory,
                event=second,
                repository_factory=SqlAlchemyCostBasisTransactionRepository,
                processing_state_factory=lambda session: (
                    _ObservedLinkedGroupProcessingStateRepository(
                        session,
                        group_lock_attempted=second_group_lock_attempted,
                        backend_pid=second_backend_pid,
                    )
                ),
            )
        )
        await wait_for_task_signal(second_task, second_group_lock_attempted, timeout=2)
        assert len(second_backend_pid) == 1
        await wait_for_postgres_advisory_lock_wait(
            second_task,
            session_factory,
            backend_pid=second_backend_pid[0],
            timeout=2,
        )

        release_group_read.set()
        await asyncio.wait_for(first_task, timeout=8)
        with pytest.raises(redemption_domain.RedemptionLinkedEventValidationError):
            await asyncio.wait_for(second_task, timeout=8)
    finally:
        release_group_read.set()
        await cancel_pending_tasks(first_task, second_task)

    async with session_factory() as verification_session:
        persisted = list(
            (
                await verification_session.scalars(
                    select(DBTransaction).where(
                        DBTransaction.transaction_id.in_(
                            (redemption.transaction_id, independent_interest.transaction_id)
                        )
                    )
                )
            ).all()
        )

    calculated_ids = {
        transaction.transaction_id
        for transaction in persisted
        if transaction.calculation_lineage is not None
    }
    assert calculated_ids == {first.transaction_id}


async def test_single_buy_cost_stage_avoids_duplicate_canonical_transaction_reads(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COST-SHAPE-01"
    security_id = "SEC-COST-SHAPE-01"
    buy = booked_transaction_event(
        transaction_id="BUY-COST-SHAPE-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name="Cost Shape Equity",
                isin="SG0000000499",
                currency="USD",
            ),
            canonical_transaction_record(buy),
        ]
    )
    await async_db_session.commit()
    statements: list[str] = []

    def capture_statement(
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(" ".join(statement.split()))

    sync_engine = async_db_session.bind.sync_engine
    sqlalchemy_event.listen(sync_engine, "before_cursor_execute", capture_statement)
    try:
        await _stage_cost_calculation(
            session_factory=async_sessionmaker(async_db_session.bind, expire_on_commit=False),
            event=buy,
            repository_factory=SqlAlchemyCostBasisTransactionRepository,
        )
    finally:
        sqlalchemy_event.remove(sync_engine, "before_cursor_execute", capture_statement)

    # The initial BUY aggregate replaces the separate lot, accrued-income-offset,
    # and checkpoint statements with one atomic statement.
    assert len(statements) == 8
    initial_opening_writes = [
        statement
        for statement in statements
        if "persist_initial_opening_lot" in statement
        and "persist_initial_income_offset" in statement
        and "INSERT INTO cost_basis_processing_state" in statement
    ]
    assert len(initial_opening_writes) == 1
    canonical_transaction_writes = [
        statement
        for statement in statements
        if statement.startswith("WITH updated_transaction AS")
        and "UPDATE transactions SET" in statement
    ]
    canonical_transaction_reads = [
        statement
        for statement in statements
        if statement.startswith("SELECT transactions.id")
        and "transactions.transaction_id =" in statement
    ]
    assert len(canonical_transaction_writes) == 1
    assert "RETURNING transactions.id" in canonical_transaction_writes[0]
    assert "DELETE FROM transaction_costs" in canonical_transaction_writes[0]
    assert canonical_transaction_reads == []
    opening_lot_snapshot_reads = [
        statement
        for statement in statements
        if statement.startswith("SELECT position_lot_state.lot_id")
    ]
    assert opening_lot_snapshot_reads == []
    disposal_receipt_reads = [
        statement
        for statement in statements
        if statement.startswith("SELECT lot_disposal_receipts.id")
    ]
    assert len(disposal_receipt_reads) == 1
    basis_transfer_receipt_reads = [
        statement
        for statement in statements
        if statement.startswith("SELECT lot_basis_transfer_receipts.id")
    ]
    assert len(basis_transfer_receipt_reads) == 1
