"""Prove derived-state repository behavior against PostgreSQL."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TypeVar
from unittest.mock import MagicMock, patch

import pytest
from portfolio_common.database_models import (
    Cashflow,
    CashflowRule,
    DailyPositionSnapshot,
    FinancialReconciliationFinding,
    Instrument,
    OutboxEvent,
    PipelineStageState,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
    PositionHistory,
    PositionState,
    PositionTimeseries,
    Transaction,
)
from portfolio_common.reconciliation_quality import FINANCIAL_RECONCILIATION_STAGE
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from src.services.financial_reconciliation_service.app.consumers import (
    reconciliation_requested_consumer,
)
from src.services.portfolio_derived_state_service.app.application.portfolio_timeseries import (
    MaterializePortfolioTimeseries,
    MaterializePortfolioTimeseriesCommand,
    PortfolioTimeseriesMaterializationStatus,
)
from src.services.portfolio_derived_state_service.app.application.position_timeseries import (
    MaterializePositionTimeseries,
    MaterializePositionTimeseriesCommand,
)
from src.services.portfolio_derived_state_service.app.domain.aggregation_jobs.models import (
    AggregationJobLeaseClaim,
)
from src.services.portfolio_derived_state_service.app.domain.position_timeseries.calculator import (
    calculate_position_timeseries,
)
from src.services.portfolio_derived_state_service.app.infrastructure import (
    portfolio_aggregation_repository,
    portfolio_timeseries_unit_of_work_provider,
    timeseries_generation_repository,
)
from src.services.portfolio_derived_state_service.app.ports.position_timeseries import (
    PositionTimeseriesRepository,
)
from tests.test_support.async_task_coordination import (
    cancel_pending_tasks,
    wait_for_postgres_advisory_lock_wait,
    wait_for_task_signal,
)
from tests.test_support.postgres_query_plan import plan_index_names, plan_node_types
from tests.test_support.tenant import TEST_TENANT_ID

TimeseriesGenerationRepository = timeseries_generation_repository.TimeseriesGenerationRepository

PortfolioAggregationRepository = portfolio_aggregation_repository.PortfolioAggregationRepository

pytestmark = pytest.mark.asyncio
T = TypeVar("T")


class _SessionPositionTimeseriesRepositoryProvider:
    """Run integration materialization against the fixture-owned database session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def run_in_transaction(
        self,
        operation: Callable[[PositionTimeseriesRepository], Awaitable[T]],
    ) -> T:
        async with self._session.begin():
            return await operation(TimeseriesGenerationRepository(self._session))


def _lease(identity: str) -> AggregationJobLeaseClaim:
    """Build one durable claim identity for a repository integration scenario."""

    return AggregationJobLeaseClaim(
        owner=f"integration-runtime-{identity}",
        token=f"integration-lease-{identity}",
        duration_seconds=300,
    )


@pytest.mark.lifecycle
async def test_aggregation_staging_preserves_authoritative_legacy_portfolio_identity(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    stored_portfolio_id = " PORT-AGG-LEGACY-ID "
    aggregation_date = date(2026, 9, 11)
    async_db_session.add(
        Portfolio(
            tenant_id=TEST_TENANT_ID,
            portfolio_id=stored_portfolio_id,
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="balanced",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="SG_BOOKING",
            client_id="CLIENT-AGG-LEGACY-ID",
            status="ACTIVE",
        )
    )
    await async_db_session.flush()
    repository = TimeseriesGenerationRepository(async_db_session)

    await repository.stage_aggregation_jobs(
        stored_portfolio_id.strip(),
        [aggregation_date],
        3,
        "corr-aggregation-legacy-id",
    )
    await async_db_session.commit()

    staged_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.tenant_id == TEST_TENANT_ID,
            PortfolioAggregationJob.portfolio_id == stored_portfolio_id,
            PortfolioAggregationJob.aggregation_date == aggregation_date,
        )
    )
    assert staged_job is not None
    assert staged_job.source_revision == 1
    staged_job.status = "COMPLETE"
    await async_db_session.commit()

    restaged_dates = await repository.restage_aggregation_jobs_in_carry_forward_interval(
        stored_portfolio_id.strip(),
        start_date=aggregation_date,
        end_date_exclusive=aggregation_date + timedelta(days=1),
        excluded_dates=[],
        target_epoch=4,
        correlation_id="corr-aggregation-legacy-id-restage",
    )
    await async_db_session.commit()

    restaged_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.tenant_id == TEST_TENANT_ID,
            PortfolioAggregationJob.portfolio_id == stored_portfolio_id,
            PortfolioAggregationJob.aggregation_date == aggregation_date,
        )
    )
    assert restaged_dates == [aggregation_date]
    assert restaged_job is not None
    assert restaged_job.status == "PENDING"
    assert restaged_job.target_epoch == 4
    assert restaged_job.source_revision == 2


@pytest.mark.lifecycle
async def test_portfolio_aggregation_mutation_fence_serializes_same_portfolio(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Hold shared portfolio effects behind one cross-session transaction fence."""

    del clean_db
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    first_acquired = asyncio.Event()
    release_first = asyncio.Event()
    second_attempted = asyncio.Event()
    second_acquired = asyncio.Event()
    second_backend_pid: int | None = None

    async def hold_first_fence() -> None:
        async with session_factory() as session, session.begin():
            await TimeseriesGenerationRepository(
                session
            ).acquire_portfolio_aggregation_mutation_fence("PORT-AGG-FENCE-001")
            first_acquired.set()
            await release_first.wait()

    async def await_second_fence() -> None:
        nonlocal second_backend_pid
        await first_acquired.wait()
        async with session_factory() as session, session.begin():
            second_backend_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            second_attempted.set()
            await TimeseriesGenerationRepository(
                session
            ).acquire_portfolio_aggregation_mutation_fence("PORT-AGG-FENCE-001")
            second_acquired.set()

    first_task = asyncio.create_task(hold_first_fence())
    second_task: asyncio.Task[None] | None = None
    try:
        await wait_for_task_signal(first_task, first_acquired, timeout=2)
        second_task = asyncio.create_task(await_second_fence())
        await wait_for_task_signal(second_task, second_attempted, timeout=2)
        assert second_backend_pid is not None
        await wait_for_postgres_advisory_lock_wait(
            second_task,
            session_factory,
            backend_pid=second_backend_pid,
            timeout=2,
        )
        assert second_acquired.is_set() is False

        release_first.set()
        await asyncio.wait_for(
            asyncio.gather(first_task, second_task),
            timeout=5,
        )
        assert second_acquired.is_set() is True
    finally:
        release_first.set()
        await cancel_pending_tasks(first_task, second_task)


@pytest.mark.lifecycle
async def test_later_epoch_materialization_promotes_only_selected_historical_business_days(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """A later cash epoch must rearm an older selected holding's exact control day."""

    portfolio_id = "HISTORICAL_EPOCH_PORT"
    other_portfolio_id = "HISTORICAL_EPOCH_OTHER"
    old_day = date(2025, 4, 20)
    closed_day = date(2025, 6, 1)
    new_day = date(2026, 4, 10)
    with Session(db_engine) as session:
        for selected_portfolio_id in (portfolio_id, other_portfolio_id):
            session.add(
                Portfolio(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=selected_portfolio_id,
                    base_currency="USD",
                    open_date=date(2024, 1, 1),
                    risk_exposure="balanced",
                    investment_time_horizon="long_term",
                    portfolio_type="discretionary",
                    booking_center_code="SG",
                    client_id=f"CLIENT-{selected_portfolio_id}",
                    status="ACTIVE",
                )
            )
        for security_id in ("HIST_OLD", "HIST_CLOSED", "HIST_CASH"):
            session.add(
                Instrument(
                    security_id=security_id,
                    name=security_id,
                    isin=f"ISIN-{security_id}",
                    currency="USD",
                    product_type="Equity",
                )
            )
        session.flush()
        for transaction_id, security_id, transaction_day, transaction_type, quantity in (
            ("HIST-T-OLD", "HIST_OLD", old_day, "BUY", Decimal("10")),
            (
                "HIST-T-CLOSED-OPEN",
                "HIST_CLOSED",
                closed_day - timedelta(days=1),
                "BUY",
                Decimal("5"),
            ),
            ("HIST-T-CLOSED-END", "HIST_CLOSED", closed_day, "SELL", Decimal("5")),
            ("HIST-T-CASH", "HIST_CASH", new_day, "BUY", Decimal("10")),
        ):
            transaction = _transaction(
                transaction_id,
                portfolio_id,
                security_id,
                transaction_day,
                transaction_type=transaction_type,
            )
            transaction.quantity = quantity
            transaction.price = Decimal("10")
            transaction.gross_transaction_amount = quantity * 10
            session.add(transaction)
        session.flush()
        for transaction in session.query(Transaction).filter(
            Transaction.portfolio_id == portfolio_id
        ):
            rule = session.get(CashflowRule, transaction.transaction_type)
            assert rule is not None
            transaction_day = transaction.transaction_date
            cashflow_date = (
                transaction_day.date() if isinstance(transaction_day, datetime) else transaction_day
            )
            session.add(
                Cashflow(
                    transaction_id=transaction.transaction_id,
                    portfolio_id=portfolio_id,
                    security_id=transaction.security_id,
                    cashflow_date=cashflow_date,
                    epoch=1 if transaction.transaction_id == "HIST-T-CASH" else 0,
                    amount=(
                        -transaction.gross_transaction_amount
                        if transaction.transaction_type == "BUY"
                        else transaction.gross_transaction_amount
                    ),
                    currency="USD",
                    classification=rule.classification,
                    timing=rule.timing,
                    calculation_type="TRANSACTION",
                    is_position_flow=rule.is_position_flow,
                    is_portfolio_flow=rule.is_portfolio_flow,
                )
            )
        for transaction_id, security_id, business_day, epoch, quantity in (
            ("HIST-T-OLD", "HIST_OLD", old_day, 0, Decimal("10")),
            (
                "HIST-T-CLOSED-OPEN",
                "HIST_CLOSED",
                closed_day - timedelta(days=1),
                0,
                Decimal("5"),
            ),
            ("HIST-T-CLOSED-END", "HIST_CLOSED", closed_day, 0, Decimal("0")),
            ("HIST-T-CASH", "HIST_CASH", new_day, 1, Decimal("10")),
        ):
            session.add(
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    transaction_id=transaction_id,
                    position_date=business_day,
                    epoch=epoch,
                    quantity=quantity,
                    cost_basis=quantity * 10,
                    cost_basis_local=quantity * 10,
                )
            )
        cash_snapshot = _snapshot(portfolio_id, "HIST_CASH", new_day, epoch=1)
        old_position_timeseries = _position_ts(portfolio_id, "HIST_OLD", old_day)
        old_position_timeseries.bod_market_value = Decimal("0")
        old_position_timeseries.bod_cashflow_position = Decimal("100")
        old_position_timeseries.cost = Decimal("10")
        session.add_all(
            [cash_snapshot, _snapshot(portfolio_id, "HIST_OLD", old_day), old_position_timeseries]
        )
        session.add_all(
            [
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=selected_portfolio_id,
                    aggregation_date=old_day,
                    status="COMPLETE",
                    target_epoch=0,
                    source_revision=1,
                )
                for selected_portfolio_id in (portfolio_id, other_portfolio_id)
            ]
        )
        session.commit()
        snapshot_id = cash_snapshot.id

    result = await MaterializePositionTimeseries(
        repository_provider=_SessionPositionTimeseriesRepositoryProvider(async_db_session)
    ).execute(
        MaterializePositionTimeseriesCommand(
            snapshot_id=snapshot_id,
            portfolio_id=portfolio_id,
            security_id="HIST_CASH",
            valuation_date=new_day,
            epoch=1,
            correlation_id="corr-historical-epoch",
        )
    )
    assert result.current_day_changed is True

    async def job(selected_portfolio_id: str, business_day: date):
        return await async_db_session.scalar(
            select(PortfolioAggregationJob).where(
                PortfolioAggregationJob.portfolio_id == selected_portfolio_id,
                PortfolioAggregationJob.aggregation_date == business_day,
            )
        )

    old_job = await job(portfolio_id, old_day)
    current_job = await job(portfolio_id, new_day)
    other_job = await job(other_portfolio_id, old_day)
    assert old_job is not None
    assert (old_job.status, old_job.target_epoch, old_job.source_revision) == (
        "PENDING",
        1,
        2,
    )
    assert current_job is not None and current_job.target_epoch == 1
    assert other_job is not None
    assert (other_job.status, other_job.target_epoch, other_job.source_revision) == (
        "COMPLETE",
        0,
        1,
    )
    assert await job(portfolio_id, closed_day) is None
    old_history = await async_db_session.scalar(
        select(PositionHistory).where(PositionHistory.transaction_id == "HIST-T-OLD")
    )
    assert old_history is not None
    assert (old_history.position_date, old_history.epoch, old_history.quantity) == (
        old_day,
        0,
        Decimal("10"),
    )
    await async_db_session.rollback()

    claimed = await PortfolioAggregationRepository(async_db_session).claim_eligible_jobs(
        batch_size=1,
        lease=_lease("historical-control"),
    )
    assert len(claimed) == 1
    historical_claim = claimed[0]
    assert (historical_claim.aggregation_date, historical_claim.target_epoch) == (old_day, 1)
    await async_db_session.commit()

    async def override_session():
        session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
        async with session_factory() as session:
            yield session

    with patch(
        "src.services.portfolio_derived_state_service.app.infrastructure."
        "portfolio_timeseries_unit_of_work_provider.get_async_db_session",
        new=override_session,
    ):
        aggregation_result = await MaterializePortfolioTimeseries(
            unit_of_work_provider=(
                portfolio_timeseries_unit_of_work_provider.SqlAlchemyPortfolioTimeseriesUnitOfWorkProvider()
            )
        ).execute(
            MaterializePortfolioTimeseriesCommand(
                job_id=historical_claim.id,
                lease_token=historical_claim.lease.token,
                tenant_id=historical_claim.tenant_id,
                portfolio_id=portfolio_id,
                aggregation_date=old_day,
                aggregation_revision=historical_claim.aggregation_revision,
                target_epoch=historical_claim.target_epoch,
                source_revision=historical_claim.source_revision,
                correlation_id=historical_claim.correlation_id,
            )
        )
    assert aggregation_result.status is PortfolioTimeseriesMaterializationStatus.COMPLETE
    historical_output = await async_db_session.scalar(
        select(PortfolioTimeseries).where(
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date == old_day,
            PortfolioTimeseries.epoch == 1,
        )
    )
    requested_event = await async_db_session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.event_type == "FinancialReconciliationRequested",
            OutboxEvent.aggregate_id == f"{portfolio_id}:{old_day}:1",
        )
    )
    assert historical_output is not None
    assert historical_output.eod_market_value == Decimal("100")
    assert requested_event is not None
    assert requested_event.payload["business_date"] == old_day.isoformat()
    assert requested_event.payload["epoch"] == 1
    requested_payload = requested_event.payload
    requested_topic = requested_event.topic
    await async_db_session.rollback()

    message = MagicMock()
    message.value.return_value = json.dumps(requested_payload).encode("utf-8")
    message.key.return_value = portfolio_id.encode("utf-8")
    message.topic.return_value = requested_topic
    message.partition.return_value = 0
    message.offset.return_value = 1
    message.headers.return_value = []
    consumer = reconciliation_requested_consumer.ReconciliationRequestedConsumer(
        bootstrap_servers="mock_server",
        topic=requested_topic,
        group_id="historical-control-test",
    )
    with patch(
        "src.services.financial_reconciliation_service.app.consumers."
        "reconciliation_requested_consumer.get_async_db_session",
        new=override_session,
    ):
        await consumer.process_message(message)
    completed_control = await async_db_session.scalar(
        select(PipelineStageState).where(
            PipelineStageState.stage_name == FINANCIAL_RECONCILIATION_STAGE,
            PipelineStageState.portfolio_id == portfolio_id,
            PipelineStageState.business_date == old_day,
            PipelineStageState.epoch == 1,
        )
    )
    assert completed_control is not None
    findings = (
        (
            await async_db_session.execute(
                select(FinancialReconciliationFinding).where(
                    FinancialReconciliationFinding.portfolio_id == portfolio_id,
                    FinancialReconciliationFinding.business_date == old_day,
                )
            )
        )
        .scalars()
        .all()
    )
    assert completed_control.status == "COMPLETED", [
        (finding.reconciliation_type, finding.finding_type, finding.severity)
        for finding in findings
    ]
    await async_db_session.rollback()

    repository = TimeseriesGenerationRepository(async_db_session)
    await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
    assert (
        await repository.promote_selected_history_aggregation_jobs(
            portfolio_id,
            security_id="HIST_CASH",
            as_of_date=new_day,
            target_epoch=1,
            correlation_id="corr-historical-epoch",
        )
        == 0
    )
    assert (
        await repository.promote_selected_history_aggregation_jobs(
            portfolio_id,
            security_id="HIST_CASH",
            as_of_date=new_day,
            target_epoch=0,
            correlation_id="corr-late-writer",
        )
        == 0
    )
    await async_db_session.commit()
    unchanged_job = await job(portfolio_id, old_day)
    assert unchanged_job is not None
    assert (unchanged_job.target_epoch, unchanged_job.source_revision) == (1, 2)

    lease_expiry = datetime.now(UTC) + timedelta(minutes=5)
    unchanged_job.status = "PROCESSING"
    unchanged_job.lease_owner = "historical-epoch-worker"
    unchanged_job.lease_token = "historical-epoch-lease"
    unchanged_job.lease_expires_at = lease_expiry
    next_day = new_day + timedelta(days=1)
    async_db_session.add(_transaction("HIST-T-CASH-NEXT", portfolio_id, "HIST_CASH", next_day))
    await async_db_session.flush()
    async_db_session.add(
        PositionHistory(
            portfolio_id=portfolio_id,
            security_id="HIST_CASH",
            transaction_id="HIST-T-CASH-NEXT",
            position_date=next_day,
            epoch=2,
            quantity=Decimal("11"),
            cost_basis=Decimal("110"),
            cost_basis_local=Decimal("110"),
        )
    )
    await async_db_session.commit()

    # Even a late epoch-0 caller observes the authoritative selected epoch 2.
    await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
    await repository.stage_aggregation_jobs(
        portfolio_id, [next_day], 0, "corr-historical-epoch-next"
    )
    promoted_count = await repository.promote_selected_history_aggregation_jobs(
        portfolio_id,
        security_id="HIST_CASH",
        as_of_date=next_day,
        target_epoch=0,
        correlation_id="corr-historical-epoch-next",
    )
    await async_db_session.commit()
    processing_job = await job(portfolio_id, old_day)
    assert promoted_count == 2  # Old control plus the newly selected cash business day.
    assert processing_job is not None
    await async_db_session.refresh(processing_job)
    assert (
        processing_job.status,
        processing_job.target_epoch,
        processing_job.source_revision,
        processing_job.failure_reason,
    ) == ("PROCESSING", 2, 3, "REPROCESS_REQUESTED")
    assert (processing_job.lease_owner, processing_job.lease_token) == (
        "historical-epoch-worker",
        "historical-epoch-lease",
    )
    assert processing_job.lease_expires_at == lease_expiry

    await async_db_session.rollback()
    with pytest.raises(RuntimeError, match="roll back historical promotion"):
        async with async_db_session.begin():
            await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
            assert (
                await repository.promote_selected_history_aggregation_jobs(
                    portfolio_id,
                    security_id="HIST_CASH",
                    as_of_date=next_day,
                    target_epoch=3,
                    correlation_id="corr-historical-epoch-rollback",
                )
                > 0
            )
            raise RuntimeError("roll back historical promotion")
    rolled_back_job = await job(portfolio_id, old_day)
    assert rolled_back_job is not None
    await async_db_session.refresh(rolled_back_job)
    assert (rolled_back_job.target_epoch, rolled_back_job.source_revision) == (2, 3)


@pytest.mark.lifecycle
@pytest.mark.parametrize("ready_epoch", [1, 2])
async def test_late_valuation_rearms_preobserved_historical_fact(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
    ready_epoch: int,
) -> None:
    """An observed history fact is not proof that its later valuation was materialized."""

    portfolio_id = f"HISTORICAL_LATE_VALUATION_{ready_epoch}"
    old_day = date(2025, 4, 20)
    as_of_date = date(2026, 4, 10)
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="balanced",
                investment_time_horizon="long_term",
                portfolio_type="discretionary",
                booking_center_code="SG",
                client_id="CLIENT-HIST-LATE-VALUATION",
                status="ACTIVE",
            )
        )
        for security_id in ("HIST_READY", "HIST_LATE"):
            session.add(
                Instrument(
                    security_id=security_id,
                    name=security_id,
                    isin=f"ISIN-{security_id}",
                    currency="USD",
                    product_type="Equity",
                )
            )
        session.flush()
        session.add_all(
            [
                _transaction("HIST-READY-T", portfolio_id, "HIST_READY", as_of_date),
                _transaction("HIST-LATE-T", portfolio_id, "HIST_LATE", old_day),
            ]
        )
        session.flush()
        session.add_all(
            [
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id="HIST_READY",
                    transaction_id="HIST-READY-T",
                    position_date=as_of_date,
                    epoch=ready_epoch,
                    quantity=Decimal("10"),
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                ),
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id="HIST_LATE",
                    transaction_id="HIST-LATE-T",
                    position_date=old_day,
                    epoch=2,
                    quantity=Decimal("10"),
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                ),
                _snapshot(portfolio_id, "HIST_LATE", old_day, epoch=0),
                _position_ts(portfolio_id, "HIST_LATE", old_day, epoch=0),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=old_day,
                    status="COMPLETE",
                    target_epoch=1,
                    source_revision=1,
                ),
            ]
        )
        ready_snapshot = _snapshot(portfolio_id, "HIST_READY", as_of_date, epoch=ready_epoch)
        session.add(ready_snapshot)
        session.commit()
        ready_snapshot_id = ready_snapshot.id

    materializer = MaterializePositionTimeseries(
        repository_provider=_SessionPositionTimeseriesRepositoryProvider(async_db_session)
    )
    assert (
        await materializer.execute(
            MaterializePositionTimeseriesCommand(
                snapshot_id=ready_snapshot_id,
                portfolio_id=portfolio_id,
                security_id="HIST_READY",
                valuation_date=as_of_date,
                epoch=ready_epoch,
                correlation_id="corr-hist-ready",
            )
        )
    ).current_day_changed

    old_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == old_day,
        )
    )
    assert old_job is not None
    assert (old_job.status, old_job.target_epoch) == ("PENDING", 2)
    assert (
        await async_db_session.scalar(
            text(
                "SELECT count(*) FROM portfolio_selected_history_valuation_states "
                "WHERE portfolio_id = :portfolio_id "
                "AND security_id = 'HIST_LATE'"
            ),
            {"portfolio_id": portfolio_id},
        )
        == 0
    )
    await async_db_session.rollback()

    claimed = await PortfolioAggregationRepository(async_db_session).claim_eligible_jobs(
        batch_size=1,
        lease=_lease("prevaluation-history"),
    )
    assert [(job.aggregation_date, job.target_epoch) for job in claimed] == [(old_day, 2)]
    await async_db_session.commit()
    old_job.status = "COMPLETE"  # The claim used the only valued, epoch-0 row.
    await async_db_session.commit()
    previous_revision = old_job.source_revision

    # This older valuation delivery must not certify the already-selected
    # epoch-2 history fact for the same security.
    with Session(db_engine) as session:
        stale_snapshot = _snapshot(portfolio_id, "HIST_LATE", as_of_date, epoch=0)
        session.add(stale_snapshot)
        session.commit()
        stale_snapshot_id = stale_snapshot.id
    assert (
        await materializer.execute(
            MaterializePositionTimeseriesCommand(
                snapshot_id=stale_snapshot_id,
                portfolio_id=portfolio_id,
                security_id="HIST_LATE",
                valuation_date=as_of_date,
                epoch=0,
                correlation_id="corr-hist-stale-delivery",
            )
        )
    ).current_day_changed
    assert (
        await async_db_session.scalar(
            text(
                "SELECT count(*) FROM portfolio_selected_history_valuation_states "
                "WHERE portfolio_id = :portfolio_id AND security_id = 'HIST_LATE'"
            ),
            {"portfolio_id": portfolio_id},
        )
        == 0
    )
    await async_db_session.refresh(old_job)
    assert (old_job.status, old_job.source_revision) == ("COMPLETE", previous_revision)
    await async_db_session.rollback()

    with Session(db_engine) as session:
        late_snapshot = _snapshot(portfolio_id, "HIST_LATE", as_of_date, epoch=2)
        late_snapshot.market_value_local = None
        late_snapshot.valuation_status = "FAILED"
        session.add(late_snapshot)
        session.commit()
        late_snapshot_id = late_snapshot.id

    command = MaterializePositionTimeseriesCommand(
        snapshot_id=late_snapshot_id,
        portfolio_id=portfolio_id,
        security_id="HIST_LATE",
        valuation_date=as_of_date,
        epoch=2,
        correlation_id="corr-hist-late",
    )
    assert not (await materializer.execute(command)).current_day_changed
    await async_db_session.refresh(old_job)
    assert (old_job.status, old_job.target_epoch, old_job.source_revision) == (
        "PENDING",
        2,
        previous_revision + 1,
    )
    assert (
        await async_db_session.scalar(
            text(
                "SELECT valuation_outcome FROM portfolio_selected_history_valuation_states "
                "WHERE portfolio_id = :portfolio_id "
                "AND security_id = 'HIST_LATE'"
            ),
            {"portfolio_id": portfolio_id},
        )
        == "UNAVAILABLE"
    )
    await async_db_session.rollback()
    assert not (await materializer.execute(command)).current_day_changed
    await async_db_session.refresh(old_job)
    assert old_job.source_revision == previous_revision + 1

    old_job.status = "COMPLETE"
    await async_db_session.commit()
    with Session(db_engine) as session:
        recovered_snapshot = session.get(DailyPositionSnapshot, late_snapshot_id)
        assert recovered_snapshot is not None
        recovered_snapshot.market_value_local = Decimal("100")
        recovered_snapshot.valuation_status = "VALUED_CURRENT"
        session.commit()

    assert (await materializer.execute(command)).current_day_changed
    await async_db_session.refresh(old_job)
    assert (old_job.status, old_job.target_epoch, old_job.source_revision) == (
        "PENDING",
        2,
        previous_revision + 2,
    )
    assert (
        await async_db_session.scalar(
            text(
                "SELECT valuation_outcome FROM portfolio_selected_history_valuation_states "
                "WHERE portfolio_id = :portfolio_id AND security_id = 'HIST_LATE'"
            ),
            {"portfolio_id": portfolio_id},
        )
        == "READY"
    )
    await async_db_session.rollback()
    assert not (await materializer.execute(command)).current_day_changed
    await async_db_session.refresh(old_job)
    assert old_job.source_revision == previous_revision + 2

    # A later ordinary valuation of this already-observed security must not
    # reopen the same historical day forever at an unchanged source epoch.
    old_job.status = "COMPLETE"
    await async_db_session.commit()
    stable_revision = old_job.source_revision
    next_day = as_of_date + timedelta(days=1)
    with Session(db_engine) as session:
        next_snapshot = _snapshot(portfolio_id, "HIST_LATE", next_day, epoch=2)
        session.add(next_snapshot)
        session.commit()
        next_snapshot_id = next_snapshot.id
    assert (
        await materializer.execute(
            MaterializePositionTimeseriesCommand(
                snapshot_id=next_snapshot_id,
                portfolio_id=portfolio_id,
                security_id="HIST_LATE",
                valuation_date=next_day,
                epoch=2,
                correlation_id="corr-hist-next-day",
            )
        )
    ).current_day_changed
    await async_db_session.refresh(old_job)
    assert (old_job.status, old_job.source_revision) == ("COMPLETE", stable_revision)
    assert (
        await async_db_session.scalar(
            text(
                "SELECT valuation_date FROM portfolio_selected_history_valuation_states "
                "WHERE portfolio_id = :portfolio_id AND security_id = 'HIST_LATE'"
            ),
            {"portfolio_id": portfolio_id},
        )
        == next_day
    )
    await async_db_session.rollback()

    # An older failed delivery for that same selected security must not
    # overwrite the newer READY observation or reopen its historical control.
    stale_day = as_of_date - timedelta(days=1)
    with Session(db_engine) as session:
        stale_failed_snapshot = _snapshot(portfolio_id, "HIST_LATE", stale_day, epoch=2)
        stale_failed_snapshot.market_value_local = None
        stale_failed_snapshot.valuation_status = "FAILED"
        session.add(stale_failed_snapshot)
        session.commit()
        stale_failed_snapshot_id = stale_failed_snapshot.id
    assert not (
        await materializer.execute(
            MaterializePositionTimeseriesCommand(
                snapshot_id=stale_failed_snapshot_id,
                portfolio_id=portfolio_id,
                security_id="HIST_LATE",
                valuation_date=stale_day,
                epoch=2,
                correlation_id="corr-hist-stale-failure",
            )
        )
    ).current_day_changed
    await async_db_session.refresh(old_job)
    assert (old_job.status, old_job.source_revision) == ("COMPLETE", stable_revision)
    assert (
        await async_db_session.scalar(
            text(
                "SELECT valuation_outcome FROM portfolio_selected_history_valuation_states "
                "WHERE portfolio_id = :portfolio_id AND security_id = 'HIST_LATE'"
            ),
            {"portfolio_id": portfolio_id},
        )
        == "READY"
    )


@pytest.mark.lifecycle
async def test_history_sweep_rearms_first_fact_and_later_full_sweep_close(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """First sweep and later closure both rearm the exact old business-day control."""

    portfolio_id = "HISTORICAL_FIRST_SWEEP_EQUAL_EPOCH"
    security_id = "HIST_FIRST_SWEEP"
    old_day = date(2025, 4, 20)
    as_of_date = date(2026, 4, 10)
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="balanced",
                investment_time_horizon="long_term",
                portfolio_type="discretionary",
                booking_center_code="SG",
                client_id="CLIENT-HIST-FIRST-SWEEP",
                status="ACTIVE",
            )
        )
        session.add(
            Instrument(
                security_id=security_id,
                name=security_id,
                isin="ISIN-HIST-FIRST-SWEEP",
                currency="USD",
                product_type="Equity",
            )
        )
        session.flush()
        session.add(_transaction("HIST-FIRST-SWEEP-T", portfolio_id, security_id, old_day))
        session.flush()
        session.add(
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id=security_id,
                transaction_id="HIST-FIRST-SWEEP-T",
                position_date=old_day,
                epoch=1,
                quantity=Decimal("10"),
                cost_basis=Decimal("100"),
                cost_basis_local=Decimal("100"),
            )
        )
        session.add_all(
            [
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=old_day,
                    status="COMPLETE",
                    target_epoch=1,
                    source_revision=1,
                ),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=as_of_date,
                    status="PENDING",
                    target_epoch=1,
                    source_revision=1,
                ),
            ]
        )
        session.commit()

    repository = TimeseriesGenerationRepository(async_db_session)
    await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
    assert (
        await repository.promote_selected_history_aggregation_jobs(
            portfolio_id,
            security_id=security_id,
            as_of_date=as_of_date,
            target_epoch=1,
            correlation_id="corr-historical-first-sweep",
        )
        == 1
    )
    await async_db_session.commit()

    old_control = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == old_day,
        )
    )
    as_of_control = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == as_of_date,
        )
    )
    assert old_control is not None and as_of_control is not None
    assert (old_control.status, old_control.target_epoch, old_control.source_revision) == (
        "PENDING",
        1,
        2,
    )

    assert as_of_control.selected_history_sweep_epoch == 1

    await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
    assert (
        await repository.promote_selected_history_aggregation_jobs(
            portfolio_id,
            security_id=security_id,
            as_of_date=as_of_date,
            target_epoch=1,
            correlation_id="corr-historical-first-sweep-replay",
        )
        == 0
    )
    await async_db_session.commit()
    await async_db_session.refresh(old_control)
    assert (old_control.status, old_control.target_epoch, old_control.source_revision) == (
        "PENDING",
        1,
        2,
    )

    # A later as-of boundary must reuse the observed source fact, rather than
    # rearming the completed historical day on every new day's first sweep.
    old_control.status = "COMPLETE"
    await async_db_session.commit()
    next_as_of_date = as_of_date + timedelta(days=1)
    await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
    await repository.stage_aggregation_jobs(
        portfolio_id,
        [next_as_of_date],
        1,
        "corr-historical-next-day",
    )
    assert (
        await repository.promote_selected_history_aggregation_jobs(
            portfolio_id,
            security_id=security_id,
            as_of_date=next_as_of_date,
            target_epoch=1,
            correlation_id="corr-historical-next-day",
        )
        == 0
    )
    await async_db_session.commit()
    await async_db_session.refresh(old_control)
    assert (old_control.status, old_control.target_epoch, old_control.source_revision) == (
        "COMPLETE",
        1,
        2,
    )

    # A different boundary can already have advanced the old date to epoch 2.
    # Closing the selected holding in a later full sweep must still rearm that
    # equal-epoch completed control using its previously observed business date.
    old_control.target_epoch = 2
    await async_db_session.commit()
    with Session(db_engine) as session:
        session.add(
            _transaction(
                "HIST-FIRST-SWEEP-CLOSE-T",
                portfolio_id,
                security_id,
                as_of_date,
                transaction_type="SELL",
            )
        )
        session.flush()
        session.add(
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id=security_id,
                transaction_id="HIST-FIRST-SWEEP-CLOSE-T",
                position_date=as_of_date,
                epoch=2,
                quantity=Decimal("0"),
                cost_basis=Decimal("0"),
                cost_basis_local=Decimal("0"),
            )
        )
        session.commit()

    await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
    await repository.stage_aggregation_jobs(
        portfolio_id,
        [as_of_date],
        2,
        "corr-historical-full-sweep-close",
    )
    assert (
        await repository.promote_selected_history_aggregation_jobs(
            portfolio_id,
            security_id=security_id,
            as_of_date=as_of_date,
            target_epoch=2,
            correlation_id="corr-historical-full-sweep-close",
        )
        == 1
    )
    await async_db_session.commit()
    await async_db_session.refresh(old_control)
    assert (old_control.status, old_control.target_epoch, old_control.source_revision) == (
        "PENDING",
        2,
        3,
    )
    assert (
        await async_db_session.scalar(
            text(
                "SELECT selected_nonzero FROM portfolio_selected_history_observations "
                "WHERE portfolio_id = :portfolio_id AND as_of_date = :as_of_date "
                "AND security_id = :security_id"
            ),
            {
                "portfolio_id": portfolio_id,
                "as_of_date": as_of_date,
                "security_id": security_id,
            },
        )
        is False
    )
    await async_db_session.commit()
    await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
    assert (
        await repository.promote_selected_history_aggregation_jobs(
            portfolio_id,
            security_id=security_id,
            as_of_date=as_of_date,
            target_epoch=2,
            correlation_id="corr-historical-full-sweep-close-replay",
        )
        == 0
    )
    await async_db_session.commit()
    await async_db_session.refresh(old_control)
    assert (old_control.status, old_control.target_epoch, old_control.source_revision) == (
        "PENDING",
        2,
        3,
    )


@pytest.mark.lifecycle
async def test_selected_history_sweep_normalizes_legacy_security_boundary_whitespace(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "HISTORICAL_LEGACY_SECURITY"
    security_id = "HIST_LEGACY_SECURITY"
    legacy_security_id = f"\t{security_id}\u00a0"
    old_day = date(2025, 4, 20)
    as_of_date = date(2026, 4, 10)
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="balanced",
                investment_time_horizon="long_term",
                portfolio_type="discretionary",
                booking_center_code="SG",
                client_id="CLIENT-HIST-LEGACY-SECURITY",
                status="ACTIVE",
            )
        )
        session.add(
            Instrument(
                security_id=security_id,
                name=security_id,
                isin="ISIN-HIST-LEGACY-SECURITY",
                currency="USD",
                product_type="Equity",
            )
        )
        session.flush()
        session.add(_transaction("HIST-LEGACY-SECURITY-T1", portfolio_id, security_id, old_day))
        session.flush()
        session.add(
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id=legacy_security_id,
                transaction_id="HIST-LEGACY-SECURITY-T1",
                position_date=old_day,
                epoch=1,
                quantity=Decimal("10"),
                cost_basis=Decimal("100"),
                cost_basis_local=Decimal("100"),
            )
        )
        session.add_all(
            [
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=old_day,
                    status="COMPLETE",
                    target_epoch=0,
                    source_revision=1,
                ),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=as_of_date,
                    status="PENDING",
                    target_epoch=1,
                    source_revision=1,
                ),
            ]
        )
        session.commit()

    repository = TimeseriesGenerationRepository(async_db_session)
    await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
    assert (
        await repository.promote_selected_history_aggregation_jobs(
            portfolio_id,
            security_id=security_id,
            as_of_date=as_of_date,
            target_epoch=1,
            correlation_id="corr-hist-legacy-security-first",
        )
        == 1
    )
    await async_db_session.commit()
    observed_security_id = await async_db_session.scalar(
        text(
            "SELECT security_id FROM portfolio_selected_history_observations "
            "WHERE portfolio_id = :portfolio_id AND as_of_date = :as_of_date"
        ),
        {"portfolio_id": portfolio_id, "as_of_date": as_of_date},
    )
    assert observed_security_id == security_id

    old_control = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == old_day,
        )
    )
    assert old_control is not None
    old_control.status = "COMPLETE"
    await async_db_session.commit()
    with Session(db_engine) as session:
        session.add(_transaction("HIST-LEGACY-SECURITY-T2", portfolio_id, security_id, old_day))
        session.flush()
        session.add(
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id=legacy_security_id,
                transaction_id="HIST-LEGACY-SECURITY-T2",
                position_date=old_day,
                epoch=1,
                quantity=Decimal("12"),
                cost_basis=Decimal("120"),
                cost_basis_local=Decimal("120"),
            )
        )
        session.commit()

    await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
    assert (
        await repository.promote_selected_history_aggregation_jobs(
            portfolio_id,
            security_id=security_id,
            as_of_date=as_of_date,
            target_epoch=1,
            correlation_id="corr-hist-legacy-security-restated",
        )
        == 1
    )
    await async_db_session.commit()
    await async_db_session.refresh(old_control)
    assert (old_control.status, old_control.target_epoch, old_control.source_revision) == (
        "PENDING",
        1,
        3,
    )


@pytest.mark.lifecycle
async def test_failed_valuation_rearms_each_selected_boundary_once_per_epoch(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "HISTORICAL_FAILED_VALUATION"
    old_day = date(2025, 4, 20)
    closing_open_day = old_day + timedelta(days=1)
    failed_day = date(2026, 4, 10)
    closed_day = failed_day + timedelta(days=1)
    future_day = failed_day + timedelta(days=2)
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="balanced",
                investment_time_horizon="long_term",
                portfolio_type="discretionary",
                booking_center_code="SG",
                client_id="CLIENT-HISTORICAL-FAILED",
                status="ACTIVE",
            )
        )
        for security_id in ("HIST_OLD", "HIST_CLOSED", "HIST_FAILED"):
            session.add(
                Instrument(
                    security_id=security_id,
                    name=security_id,
                    isin=f"ISIN-{portfolio_id}-{security_id}",
                    currency="USD",
                    product_type="Equity",
                )
            )
        session.flush()
        for transaction_id, security_id, business_day, transaction_type in (
            ("HIST-FAILED-OLD-T", "HIST_OLD", old_day, "BUY"),
            ("HIST-FAILED-CLOSED-OPEN-T", "HIST_CLOSED", closing_open_day, "BUY"),
            ("HIST-FAILED-CLOSED-END-T", "HIST_CLOSED", closed_day, "SELL"),
            ("HIST-FAILED-NEW-T", "HIST_FAILED", failed_day, "BUY"),
        ):
            session.add(
                _transaction(
                    transaction_id,
                    portfolio_id,
                    security_id,
                    business_day,
                    transaction_type=transaction_type,
                )
            )
        session.flush()
        for transaction_id, security_id, business_day, epoch, quantity in (
            ("HIST-FAILED-OLD-T", "HIST_OLD", old_day, 0, Decimal("10")),
            (
                "HIST-FAILED-CLOSED-OPEN-T",
                "HIST_CLOSED",
                closing_open_day,
                0,
                Decimal("10"),
            ),
            ("HIST-FAILED-CLOSED-END-T", "HIST_CLOSED", closed_day, 0, Decimal("0")),
            ("HIST-FAILED-NEW-T", "HIST_FAILED", failed_day, 1, Decimal("10")),
        ):
            session.add(
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    transaction_id=transaction_id,
                    position_date=business_day,
                    epoch=epoch,
                    quantity=quantity,
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                )
            )
        failed_snapshot = _snapshot(portfolio_id, "HIST_FAILED", failed_day, epoch=1)
        failed_snapshot.market_value_local = None
        failed_snapshot.valuation_status = "FAILED"
        session.add(failed_snapshot)
        session.add(_snapshot(portfolio_id, "HIST_FAILED", future_day, epoch=1))
        session.add(_position_ts(portfolio_id, "HIST_FAILED", future_day, epoch=1))
        session.add_all(
            PortfolioAggregationJob(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                aggregation_date=business_day,
                status="COMPLETE",
                target_epoch=0,
                source_revision=1,
            )
            for business_day in (old_day, closing_open_day)
        )
        session.commit()
        snapshot_id = failed_snapshot.id

    command = MaterializePositionTimeseriesCommand(
        snapshot_id=snapshot_id,
        portfolio_id=portfolio_id,
        security_id="HIST_FAILED",
        valuation_date=failed_day,
        epoch=1,
        correlation_id="corr-historical-failed",
    )
    materializer = MaterializePositionTimeseries(
        repository_provider=_SessionPositionTimeseriesRepositoryProvider(async_db_session)
    )
    full_sweep_statements: list[str] = []

    def capture_full_sweep(_connection, _cursor, statement, _parameters, _context, _many):
        if "INSERT INTO _lotus_selected_history_batch" in statement:
            full_sweep_statements.append(statement)

    sync_engine = async_db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", capture_full_sweep)
    try:
        first = await materializer.execute(command)
        first_sweep_count = len(full_sweep_statements)
        await async_db_session.rollback()
        second = await materializer.execute(command)
        for _ in range(16):
            await materializer.execute(command)

        late_day = old_day + timedelta(days=2)
        with Session(db_engine) as session:
            session.add(
                Instrument(
                    security_id="HIST_LATE",
                    name="HIST_LATE",
                    isin=f"ISIN-{portfolio_id}-HIST_LATE",
                    currency="USD",
                    product_type="Equity",
                )
            )
            session.add(_transaction("HIST-FAILED-LATE-T", portfolio_id, "HIST_LATE", late_day))
            session.flush()
            session.add(
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id="HIST_LATE",
                    transaction_id="HIST-FAILED-LATE-T",
                    position_date=late_day,
                    epoch=1,
                    quantity=Decimal("10"),
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                )
            )
            session.add(
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=late_day,
                    status="COMPLETE",
                    target_epoch=1,
                    source_revision=1,
                )
            )
            late_snapshot = _snapshot(portfolio_id, "HIST_LATE", failed_day, epoch=1)
            late_snapshot.market_value_local = None
            late_snapshot.valuation_status = "FAILED"
            session.add(late_snapshot)
            session.commit()
            late_snapshot_id = late_snapshot.id
        late_command = MaterializePositionTimeseriesCommand(
            snapshot_id=late_snapshot_id,
            portfolio_id=portfolio_id,
            security_id="HIST_LATE",
            valuation_date=failed_day,
            epoch=1,
            correlation_id="corr-historical-late-security",
        )
        await materializer.execute(late_command)
        await materializer.execute(late_command)
        second_sweep_count = len(full_sweep_statements)
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture_full_sweep)

    assert first.current_day_changed is False
    assert second.current_day_changed is False
    assert first.dependent_days_changed == 1
    assert first_sweep_count == 1  # Two affected days share one bounded source selection.
    assert second_sweep_count == first_sweep_count
    late_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == late_day,
        )
    )
    assert late_job is not None
    assert (late_job.status, late_job.target_epoch, late_job.source_revision) == (
        "PENDING",
        1,
        2,
    )
    closing_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == closing_open_day,
        )
    )
    assert closing_job is not None
    assert (closing_job.target_epoch, closing_job.source_revision) == (1, 2)
    old_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == old_day,
        )
    )
    failed_day_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == failed_day,
        )
    )
    assert old_job is not None
    assert (old_job.target_epoch, old_job.source_revision) == (1, 2)
    assert failed_day_job is not None
    assert (
        failed_day_job.selected_history_sweep_epoch,
        failed_day_job.selected_history_collective_epoch,
    ) == (1, 1)
    future_day_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == future_day,
        )
    )
    assert future_day_job is not None and future_day_job.selected_history_sweep_epoch == 1
    assert (
        await async_db_session.scalar(
            select(PositionTimeseries).where(
                PositionTimeseries.portfolio_id == portfolio_id,
                PositionTimeseries.security_id == "HIST_FAILED",
                PositionTimeseries.date == failed_day,
            )
        )
        is None
    )

    # A new source fact for a security already seen by the sweep must rearm an
    # equal-epoch COMPLETE historical job; replay of that same snapshot must not.
    old_job.status = "COMPLETE"
    await async_db_session.commit()
    with Session(db_engine) as session:
        session.add(_transaction("HIST-FAILED-OLD-RESTATE-T", portfolio_id, "HIST_OLD", old_day))
        session.flush()
        session.add(
            PositionHistory(
                portfolio_id=portfolio_id,
                security_id="HIST_OLD",
                transaction_id="HIST-FAILED-OLD-RESTATE-T",
                position_date=old_day,
                epoch=1,
                quantity=Decimal("12"),
                cost_basis=Decimal("120"),
                cost_basis_local=Decimal("120"),
            )
        )
        restated_snapshot = _snapshot(portfolio_id, "HIST_OLD", failed_day, epoch=1)
        restated_snapshot.market_value_local = None
        restated_snapshot.valuation_status = "FAILED"
        session.add(restated_snapshot)
        session.commit()
        restated_snapshot_id = restated_snapshot.id
    restated_command = MaterializePositionTimeseriesCommand(
        snapshot_id=restated_snapshot_id,
        portfolio_id=portfolio_id,
        security_id="HIST_OLD",
        valuation_date=failed_day,
        epoch=1,
        correlation_id="corr-historical-same-epoch-restatement",
    )
    await materializer.execute(restated_command)
    await materializer.execute(restated_command)
    await async_db_session.refresh(old_job)
    assert (old_job.status, old_job.target_epoch, old_job.source_revision) == (
        "PENDING",
        1,
        3,
    )


@pytest.mark.lifecycle
async def test_same_epoch_earlier_valuation_cannot_certify_later_history_fact(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """One replay epoch can cover multiple dated facts, but a snapshot cannot time travel."""

    portfolio_id = "HISTORICAL_SAME_EPOCH_DATES"
    security_id = "HIST_SAME_EPOCH"
    earlier_day, later_day = date(2026, 4, 10), date(2026, 4, 12)
    future_day = later_day + timedelta(days=1)
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="balanced",
                investment_time_horizon="long_term",
                portfolio_type="discretionary",
                booking_center_code="SG",
                client_id="CLIENT-HIST-SAME-EPOCH",
                status="ACTIVE",
            )
        )
        session.add(
            Instrument(
                security_id=security_id,
                name=security_id,
                isin="ISIN-HIST-SAME-EPOCH",
                currency="USD",
                product_type="Equity",
            )
        )
        session.flush()
        for transaction_id, business_day, quantity in (
            ("HIST-SAME-EPOCH-EARLY-T", earlier_day, Decimal("10")),
            ("HIST-SAME-EPOCH-LATER-T", later_day, Decimal("12")),
        ):
            session.add(_transaction(transaction_id, portfolio_id, security_id, business_day))
            session.flush()
            session.add(
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    transaction_id=transaction_id,
                    position_date=business_day,
                    epoch=2,
                    quantity=quantity,
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                )
            )
            session.add(
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=business_day,
                    status="COMPLETE",
                    target_epoch=2,
                    source_revision=1,
                )
            )
        session.add(
            PortfolioAggregationJob(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                aggregation_date=future_day,
                status="COMPLETE",
                target_epoch=2,
                source_revision=1,
            )
        )
        session.commit()

    async with async_db_session.begin():
        repository = TimeseriesGenerationRepository(async_db_session)
        await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
        await repository.promote_selected_history_aggregation_jobs_for_dates(
            portfolio_id,
            security_id=security_id,
            as_of_dates=[earlier_day, later_day, future_day],
            target_epoch=2,
            correlation_id="corr-hist-same-epoch-early",
            valuation_outcome="READY",
            valuation_date=earlier_day,
        )
    states = (
        await async_db_session.execute(
            text(
                "SELECT selected_business_date, valuation_date "
                "FROM portfolio_selected_history_valuation_states "
                "WHERE portfolio_id = :portfolio_id ORDER BY selected_business_date"
            ),
            {"portfolio_id": portfolio_id},
        )
    ).all()
    assert states == [(earlier_day, earlier_day)]
    await async_db_session.execute(
        text(
            "UPDATE portfolio_aggregation_jobs SET status = 'COMPLETE' "
            "WHERE portfolio_id = :portfolio_id AND aggregation_date = :later_day"
        ),
        {"portfolio_id": portfolio_id, "later_day": later_day},
    )
    await async_db_session.commit()

    async with async_db_session.begin():
        repository = TimeseriesGenerationRepository(async_db_session)
        await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
        affected = await repository.promote_selected_history_aggregation_jobs(
            portfolio_id,
            security_id=security_id,
            as_of_date=future_day,
            target_epoch=2,
            correlation_id="corr-hist-same-epoch-later",
            valuation_outcome="READY",
            valuation_date=later_day,
        )
        job = await async_db_session.execute(
            text(
                "SELECT status, target_epoch, source_revision, selected_history_sweep_epoch, "
                "selected_history_collective_epoch FROM portfolio_aggregation_jobs "
                "WHERE portfolio_id = :portfolio_id AND aggregation_date = :later_day"
            ),
            {"portfolio_id": portfolio_id, "later_day": later_day},
        )
        assert affected == 1, job.one()
    assert (
        await async_db_session.execute(
            text(
                "SELECT selected_business_date, valuation_date "
                "FROM portfolio_selected_history_valuation_states "
                "WHERE portfolio_id = :portfolio_id ORDER BY selected_business_date"
            ),
            {"portfolio_id": portfolio_id},
        )
    ).all() == [(earlier_day, earlier_day), (later_day, later_day)]
    await async_db_session.rollback()


@pytest.mark.lifecycle
async def test_selected_history_batch_bounds_source_scans_across_sixty_four_days(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Many affected days reuse one baseline/change selection without losing closures."""

    portfolio_id = "HISTORICAL_BATCH_64_DAYS"
    old_day = date(2025, 4, 20)
    affected_dates = [date(2026, 4, 10) + timedelta(days=offset) for offset in range(64)]
    opening_day, closing_day = affected_dates[20], affected_dates[40]
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="balanced",
                investment_time_horizon="long_term",
                portfolio_type="discretionary",
                booking_center_code="SG",
                client_id="CLIENT-HISTORICAL-BATCH",
                status="ACTIVE",
            )
        )
        for security_id in ("HIST_BATCH_OLD", "HIST_BATCH_CHANGE", "HIST_BATCH_CHURN"):
            session.add(
                Instrument(
                    security_id=security_id,
                    name=security_id,
                    isin=f"ISIN-{security_id}",
                    currency="USD",
                    product_type="Equity",
                )
            )
        session.flush()
        for transaction_id, security_id, business_day, transaction_type in (
            ("HIST-BATCH-OLD-T", "HIST_BATCH_OLD", old_day, "BUY"),
            ("HIST-BATCH-OPEN-T", "HIST_BATCH_CHANGE", opening_day, "BUY"),
            ("HIST-BATCH-CLOSE-T", "HIST_BATCH_CHANGE", closing_day, "SELL"),
        ):
            session.add(
                _transaction(
                    transaction_id,
                    portfolio_id,
                    security_id,
                    business_day,
                    transaction_type=transaction_type,
                )
            )
        session.flush()
        for transaction_id, security_id, business_day, quantity in (
            ("HIST-BATCH-OLD-T", "HIST_BATCH_OLD", old_day, Decimal("10")),
            ("HIST-BATCH-OPEN-T", "HIST_BATCH_CHANGE", opening_day, Decimal("10")),
            ("HIST-BATCH-CLOSE-T", "HIST_BATCH_CHANGE", closing_day, Decimal("0")),
        ):
            session.add(
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    transaction_id=transaction_id,
                    position_date=business_day,
                    epoch=2,
                    quantity=quantity,
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                )
            )
        for offset, business_day in enumerate(affected_dates):
            transaction_id = f"HIST-BATCH-CHURN-{offset}"
            session.add(
                _transaction(transaction_id, portfolio_id, "HIST_BATCH_CHURN", business_day)
            )
            session.flush()
            session.add(
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id="HIST_BATCH_CHURN",
                    transaction_id=transaction_id,
                    position_date=business_day,
                    epoch=2,
                    quantity=Decimal(offset + 1),
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                )
            )
        session.add_all(
            PortfolioAggregationJob(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                aggregation_date=business_day,
                status="COMPLETE",
                target_epoch=2,
                source_revision=1,
            )
            for business_day in [old_day, *affected_dates]
        )
        session.commit()

    batch_statements: list[str] = []
    portfolio_wide_per_day: list[str] = []

    def capture_source_work(_connection, _cursor, statement, _parameters, _context, _many):
        if "INSERT INTO _lotus_selected_history_batch" in statement:
            batch_statements.append(statement)
        if "FROM position_history" in statement and (
            "ranked_position_history" in statement
            or "batch_sequenced_position_history" in statement
        ):
            portfolio_wide_per_day.append(statement)

    sync_engine = async_db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", capture_source_work)
    try:
        async with async_db_session.begin():
            repository = TimeseriesGenerationRepository(async_db_session)
            await repository.acquire_portfolio_aggregation_mutation_fence(portfolio_id)
            affected = await repository.promote_selected_history_aggregation_jobs_for_dates(
                portfolio_id,
                security_id="HIST_BATCH_OLD",
                as_of_dates=affected_dates,
                target_epoch=2,
                correlation_id="corr-historical-batch",
                valuation_outcome="READY",
                valuation_date=affected_dates[0],
            )
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture_source_work)

    assert affected == 1
    assert len(batch_statements) == 1
    assert batch_statements[0].count("FROM position_history") == 2
    assert "lead(" in batch_statements[0].lower()
    assert "row_number() OVER (PARTITION BY affected_dates" not in batch_statements[0]
    assert portfolio_wide_per_day == [batch_statements[0]]
    assert (
        await async_db_session.scalar(
            text(
                "SELECT count(*) FROM portfolio_selected_history_valuation_states "
                "WHERE portfolio_id = :portfolio_id AND security_id = 'HIST_BATCH_OLD' "
                "AND valuation_outcome = 'READY' AND valuation_epoch = 2"
            ),
            {"portfolio_id": portfolio_id},
        )
        == 1
    )
    assert (
        await async_db_session.scalar(
            text(
                "SELECT count(*) FROM portfolio_selected_history_observations "
                "WHERE portfolio_id = :portfolio_id"
            ),
            {"portfolio_id": portfolio_id},
        )
        == 172
    )
    assert (
        await async_db_session.execute(
            text(
                "SELECT as_of_date, selected_business_date "
                "FROM portfolio_selected_history_observations "
                "WHERE portfolio_id = :portfolio_id AND security_id = 'HIST_BATCH_CHURN' "
                "ORDER BY as_of_date"
            ),
            {"portfolio_id": portfolio_id},
        )
    ).all() == [(business_day, business_day) for business_day in affected_dates]
    assert (
        await async_db_session.execute(
            text(
                "SELECT as_of_date, selected_nonzero FROM portfolio_selected_history_observations "
                "WHERE portfolio_id = :portfolio_id AND security_id = 'HIST_BATCH_CHANGE' "
                "AND as_of_date IN (:before_close, :at_close) ORDER BY as_of_date"
            ),
            {
                "portfolio_id": portfolio_id,
                "before_close": affected_dates[39],
                "at_close": closing_day,
            },
        )
    ).all() == [(affected_dates[39], True), (closing_day, False)]
    old_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == old_day,
        )
    )
    assert old_job is not None
    assert (old_job.status, old_job.target_epoch, old_job.source_revision) == (
        "PENDING",
        2,
        2,
    )
    assert (
        await async_db_session.scalar(
            text(
                "SELECT count(*) FROM portfolio_aggregation_jobs "
                "WHERE portfolio_id = :portfolio_id AND selected_history_sweep_epoch = 2"
            ),
            {"portfolio_id": portfolio_id},
        )
        == 64
    )
    await async_db_session.rollback()


@pytest.mark.lifecycle
async def test_failed_valuation_promotes_history_selected_only_at_intermediate_job_day(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "HISTORICAL_INTERMEDIATE_CARRY"
    failed_security_id = "HIST_INTERMEDIATE_FAILED"
    intermediate_security_id = "HIST_INTERMEDIATE_OPEN"
    failed_day = date(2026, 4, 10)
    opening_day = failed_day + timedelta(days=1)
    intermediate_day = failed_day + timedelta(days=2)
    closing_day = failed_day + timedelta(days=3)
    explicit_future_day = failed_day + timedelta(days=4)
    convergence_day = failed_day + timedelta(days=5)
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="balanced",
                investment_time_horizon="long_term",
                portfolio_type="discretionary",
                booking_center_code="SG",
                client_id="CLIENT-HIST-INTERMEDIATE",
                status="ACTIVE",
            )
        )
        for security_id in (failed_security_id, intermediate_security_id):
            session.add(
                Instrument(
                    security_id=security_id,
                    name=security_id,
                    isin=f"ISIN-{security_id}",
                    currency="USD",
                    product_type="Equity",
                )
            )
        session.flush()
        session.add_all(
            [
                _transaction(
                    "HIST-INTERMEDIATE-OPEN-T", portfolio_id, intermediate_security_id, opening_day
                ),
                _transaction(
                    "HIST-INTERMEDIATE-CLOSE-T",
                    portfolio_id,
                    intermediate_security_id,
                    closing_day,
                    transaction_type="SELL",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id=intermediate_security_id,
                    transaction_id="HIST-INTERMEDIATE-OPEN-T",
                    position_date=opening_day,
                    epoch=0,
                    quantity=Decimal("10"),
                    cost_basis=Decimal("100"),
                    cost_basis_local=Decimal("100"),
                ),
                PositionHistory(
                    portfolio_id=portfolio_id,
                    security_id=intermediate_security_id,
                    transaction_id="HIST-INTERMEDIATE-CLOSE-T",
                    position_date=closing_day,
                    epoch=0,
                    quantity=Decimal("0"),
                    cost_basis=Decimal("0"),
                    cost_basis_local=Decimal("0"),
                ),
            ]
        )
        failed_snapshot = _snapshot(portfolio_id, failed_security_id, failed_day, epoch=1)
        failed_snapshot.market_value_local = None
        failed_snapshot.valuation_status = "FAILED"
        session.add_all(
            [
                failed_snapshot,
                _snapshot(portfolio_id, failed_security_id, explicit_future_day, epoch=1),
                _snapshot(portfolio_id, failed_security_id, convergence_day, epoch=1),
                _position_ts(portfolio_id, failed_security_id, explicit_future_day, epoch=1),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=intermediate_day,
                    status="COMPLETE",
                    target_epoch=0,
                    source_revision=1,
                ),
            ]
        )
        session.commit()
        snapshot_id = failed_snapshot.id

    await MaterializePositionTimeseries(
        repository_provider=_SessionPositionTimeseriesRepositoryProvider(async_db_session)
    ).execute(
        MaterializePositionTimeseriesCommand(
            snapshot_id=snapshot_id,
            portfolio_id=portfolio_id,
            security_id=failed_security_id,
            valuation_date=failed_day,
            epoch=1,
            correlation_id="corr-hist-intermediate",
        )
    )
    intermediate_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == intermediate_day,
        )
    )
    opening_control = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == opening_day,
        )
    )
    assert intermediate_job is not None
    assert (
        intermediate_job.status,
        intermediate_job.target_epoch,
        intermediate_job.source_revision,
    ) == (
        "PENDING",
        1,
        2,
    )
    assert opening_control is not None
    assert (opening_control.status, opening_control.target_epoch) == ("PENDING", 1)
    assert (
        await async_db_session.scalar(
            select(PositionTimeseries).where(
                PositionTimeseries.portfolio_id == portfolio_id,
                PositionTimeseries.security_id == failed_security_id,
                PositionTimeseries.date == failed_day,
            )
        )
        is None
    )


def _snapshot(
    portfolio_id: str, security_id: str, a_date: date, *, epoch: int = 0
) -> DailyPositionSnapshot:
    return DailyPositionSnapshot(
        portfolio_id=portfolio_id,
        security_id=security_id,
        date=a_date,
        epoch=epoch,
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
        market_price=Decimal("10"),
        market_value=Decimal("100"),
        market_value_local=Decimal("100"),
        unrealized_gain_loss=Decimal("0"),
        unrealized_gain_loss_local=Decimal("0"),
        valuation_status="VALUED_CURRENT",
    )


def _position_ts(
    portfolio_id: str, security_id: str, a_date: date, *, epoch: int = 0
) -> PositionTimeseries:
    return PositionTimeseries(
        portfolio_id=portfolio_id,
        security_id=security_id,
        date=a_date,
        epoch=epoch,
        bod_market_value=Decimal("100"),
        bod_cashflow_position=Decimal("0"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=Decimal("0"),
        eod_cashflow_portfolio=Decimal("0"),
        eod_market_value=Decimal("100"),
        fees=Decimal("0"),
        quantity=Decimal("10"),
        cost=Decimal("100"),
    )


def _portfolio_ts(portfolio_id: str, a_date: date, *, epoch: int = 0) -> PortfolioTimeseries:
    return PortfolioTimeseries(
        portfolio_id=portfolio_id,
        date=a_date,
        epoch=epoch,
        bod_market_value=Decimal("100"),
        bod_cashflow=Decimal("0"),
        eod_cashflow=Decimal("0"),
        eod_market_value=Decimal("100"),
        fees=Decimal("0"),
    )


def _transaction(
    transaction_id: str,
    portfolio_id: str,
    security_id: str,
    transaction_date: date,
    *,
    transaction_type: str = "BUY",
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=security_id,
        security_id=security_id,
        transaction_date=transaction_date,
        transaction_type=transaction_type,
        quantity=Decimal("1"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("1"),
        trade_currency="USD",
        currency="USD",
    )


async def test_newer_snapshot_refreshes_evidence_and_rearms_portfolio_day_once(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
):
    portfolio_id = "FX_REFRESH_PORT"
    security_id = "FX_REFRESH_EUR"
    valuation_date = date(2026, 7, 9)
    snapshot_updated_at = datetime.now(UTC)
    original_materialized_at = snapshot_updated_at - timedelta(hours=1)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="ACTIVE",
            )
        )
        session.add(
            Instrument(
                security_id=security_id,
                name="EUR refresh instrument",
                isin="FX_REFRESH_EUR_ISIN",
                currency="EUR",
                product_type="Equity",
            )
        )
        session.flush()
        snapshot = _snapshot(portfolio_id, security_id, valuation_date)
        snapshot.updated_at = snapshot_updated_at
        session.add(snapshot)
        session.add(
            PositionTimeseries(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=valuation_date,
                epoch=0,
                bod_market_value=Decimal("0"),
                bod_cashflow_position=Decimal("0"),
                eod_cashflow_position=Decimal("0"),
                bod_cashflow_portfolio=Decimal("0"),
                eod_cashflow_portfolio=Decimal("0"),
                eod_market_value=Decimal("100"),
                fees=Decimal("0"),
                quantity=Decimal("10"),
                cost=Decimal("10"),
                updated_at=original_materialized_at,
            )
        )
        carry_forward_date = valuation_date + timedelta(days=1)
        session.add(
            PortfolioAggregationJob(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                aggregation_date=carry_forward_date,
                status="COMPLETE",
                target_epoch=0,
                source_revision=2,
            )
        )
        session.commit()
        snapshot_id = snapshot.id

    materializer = MaterializePositionTimeseries(
        repository_provider=_SessionPositionTimeseriesRepositoryProvider(async_db_session)
    )
    command = MaterializePositionTimeseriesCommand(
        snapshot_id=snapshot_id,
        portfolio_id=portfolio_id,
        security_id=security_id,
        valuation_date=valuation_date,
        epoch=0,
        correlation_id="corr-fx-refresh",
    )

    first_result = await materializer.execute(command)
    refreshed_series = await async_db_session.scalar(
        select(PositionTimeseries).where(
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.security_id == security_id,
            PositionTimeseries.date == valuation_date,
            PositionTimeseries.epoch == 0,
        )
    )
    aggregation_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == valuation_date,
        )
    )
    assert refreshed_series is not None
    assert aggregation_job is not None
    first_materialized_at = refreshed_series.updated_at
    assert first_result.current_day_changed is False
    assert first_result.dependent_days_changed == 0
    assert first_materialized_at > original_materialized_at
    assert refreshed_series.calculation_lineage is not None
    assert refreshed_series.calculation_lineage["numeric_output_policy"]["name"] == (
        "position-timeseries-ledger-output"
    )
    first_lineage = refreshed_series.calculation_lineage
    assert aggregation_job.status == "PENDING"
    assert aggregation_job.tenant_id == TEST_TENANT_ID
    carry_forward_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == carry_forward_date,
        )
    )
    assert carry_forward_job is not None
    assert carry_forward_job.tenant_id == TEST_TENANT_ID
    assert carry_forward_job.status == "PENDING"
    assert carry_forward_job.target_epoch == 0
    assert carry_forward_job.source_revision == 3
    await async_db_session.rollback()

    duplicate_result = await materializer.execute(command)
    duplicate_series = await async_db_session.scalar(
        select(PositionTimeseries).where(
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.security_id == security_id,
            PositionTimeseries.date == valuation_date,
            PositionTimeseries.epoch == 0,
        )
    )

    assert duplicate_series is not None
    assert duplicate_result.current_day_changed is False
    assert duplicate_series.updated_at == first_materialized_at
    assert duplicate_series.calculation_lineage == first_lineage
    duplicate_carry_forward_job = await async_db_session.scalar(
        select(PortfolioAggregationJob).where(
            PortfolioAggregationJob.portfolio_id == portfolio_id,
            PortfolioAggregationJob.aggregation_date == carry_forward_date,
        )
    )
    assert duplicate_carry_forward_job is not None
    assert duplicate_carry_forward_job.tenant_id == TEST_TENANT_ID
    assert duplicate_carry_forward_job.source_revision == 3


async def test_unavailable_valuation_invalidates_stale_carry_forward_portfolio_rows(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "UNAVAILABLE_CARRY_FORWARD_PORT"
    security_id = "UNAVAILABLE_CARRY_FORWARD_SEC"
    unavailable_day = date(2026, 7, 10)
    first_future_day = date(2026, 7, 11)
    carry_forward_day = date(2026, 7, 12)
    convergence_day = date(2026, 7, 13)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="ACTIVE",
            )
        )
        session.add(
            Instrument(
                security_id=security_id,
                name="Unavailable carry-forward instrument",
                isin="UNAVAILABLE_CARRY_FORWARD_ISIN",
                currency="USD",
                product_type="Equity",
            )
        )
        session.flush()
        unavailable_snapshot = _snapshot(portfolio_id, security_id, unavailable_day, epoch=3)
        unavailable_snapshot.market_value_local = None
        unavailable_snapshot.valuation_status = "FAILED"
        session.add_all(
            [
                unavailable_snapshot,
                _snapshot(portfolio_id, security_id, first_future_day, epoch=3),
                _snapshot(portfolio_id, security_id, convergence_day, epoch=3),
            ]
        )
        session.add_all(
            [
                _position_ts(portfolio_id, security_id, unavailable_day, epoch=3),
                _position_ts(portfolio_id, security_id, first_future_day, epoch=3),
            ]
        )
        session.add_all(
            [
                _portfolio_ts(portfolio_id, unavailable_day, epoch=3),
                _portfolio_ts(portfolio_id, first_future_day, epoch=3),
                _portfolio_ts(portfolio_id, carry_forward_day, epoch=2),
                _portfolio_ts(portfolio_id, carry_forward_day, epoch=3),
                _portfolio_ts(portfolio_id, convergence_day, epoch=3),
            ]
        )
        session.add_all(
            [
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=a_date,
                    status="COMPLETE",
                    target_epoch=3,
                    source_revision=1,
                )
                for a_date in (
                    unavailable_day,
                    first_future_day,
                    carry_forward_day,
                    convergence_day,
                )
            ]
        )
        session.commit()
        snapshot_id = unavailable_snapshot.id

    result = await MaterializePositionTimeseries(
        repository_provider=_SessionPositionTimeseriesRepositoryProvider(async_db_session)
    ).execute(
        MaterializePositionTimeseriesCommand(
            snapshot_id=snapshot_id,
            portfolio_id=portfolio_id,
            security_id=security_id,
            valuation_date=unavailable_day,
            epoch=3,
            correlation_id="corr-unavailable-carry-forward",
        )
    )

    portfolio_rows = (
        (
            await async_db_session.execute(
                select(PortfolioTimeseries)
                .where(PortfolioTimeseries.portfolio_id == portfolio_id)
                .order_by(PortfolioTimeseries.date, PortfolioTimeseries.epoch)
            )
        )
        .scalars()
        .all()
    )
    aggregation_rows = (
        (
            await async_db_session.execute(
                select(PortfolioAggregationJob)
                .where(PortfolioAggregationJob.portfolio_id == portfolio_id)
                .order_by(PortfolioAggregationJob.aggregation_date)
            )
        )
        .scalars()
        .all()
    )

    assert result.current_day_changed is True
    assert result.dependent_days_changed == 1
    assert [(row.date, row.epoch) for row in portfolio_rows] == [
        (carry_forward_day, 2),
        (convergence_day, 3),
    ]
    assert [
        (row.aggregation_date, row.status, row.source_revision) for row in aggregation_rows
    ] == [
        (unavailable_day, "PENDING", 2),
        (first_future_day, "PENDING", 2),
        (carry_forward_day, "PENDING", 2),
        (convergence_day, "COMPLETE", 1),
    ]
    await async_db_session.rollback()


async def test_materialization_restages_carry_forward_days_before_convergence(
    db_engine,
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "TERMINAL_CARRY_FORWARD_PORT"
    security_id = "TERMINAL_CARRY_FORWARD_SEC"
    changed_day = date(2026, 7, 10)
    complete_carry_day = date(2026, 7, 11)
    failed_carry_day = date(2026, 7, 12)
    pending_carry_day = date(2026, 7, 13)
    processing_carry_day = date(2026, 7, 14)
    convergence_day = date(2026, 7, 15)
    lease_expiry = datetime.now(UTC) + timedelta(minutes=5)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="ACTIVE",
            )
        )
        session.add(
            Instrument(
                security_id=security_id,
                name="Carry-forward instrument",
                isin="TERMINAL_CARRY_FORWARD_ISIN",
                currency="USD",
                product_type="Equity",
            )
        )
        session.flush()
        changed_snapshot = _snapshot(portfolio_id, security_id, changed_day, epoch=2)
        convergence_snapshot = _snapshot(portfolio_id, security_id, convergence_day, epoch=2)
        session.add_all([changed_snapshot, convergence_snapshot])
        session.flush()
        # Prove convergence against PostgreSQL-normalized NUMERIC inputs, not
        # transient Decimal representations that persistence will reshape.
        session.expire_all()
        convergence_record = calculate_position_timeseries(
            current_snapshot=timeseries_generation_repository.to_position_snapshot_record(
                convergence_snapshot
            ),
            previous_snapshot=timeseries_generation_repository.to_position_snapshot_record(
                changed_snapshot
            ),
            cashflows=[],
            epoch=2,
        )
        assert convergence_record.calculation_lineage is not None
        session.add(
            PositionTimeseries(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=convergence_day,
                epoch=2,
                bod_market_value=convergence_record.bod_market_value,
                bod_cashflow_position=convergence_record.bod_cashflow_position,
                eod_cashflow_position=convergence_record.eod_cashflow_position,
                bod_cashflow_portfolio=convergence_record.bod_cashflow_portfolio,
                eod_cashflow_portfolio=convergence_record.eod_cashflow_portfolio,
                eod_market_value=convergence_record.eod_market_value,
                fees=convergence_record.fees,
                quantity=convergence_record.quantity,
                cost=convergence_record.cost,
                calculation_lineage=convergence_record.calculation_lineage.lineage_payload(),
            )
        )
        session.add_all(
            [
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=changed_day,
                    status="COMPLETE",
                    target_epoch=0,
                    source_revision=1,
                ),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=complete_carry_day,
                    status="COMPLETE",
                    target_epoch=0,
                    source_revision=3,
                ),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=failed_carry_day,
                    status="FAILED",
                    failure_reason="POISON_EVENT",
                    target_epoch=1,
                    source_revision=4,
                ),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=pending_carry_day,
                    status="PENDING",
                    target_epoch=0,
                    source_revision=5,
                ),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=processing_carry_day,
                    status="PROCESSING",
                    target_epoch=1,
                    source_revision=6,
                    lease_owner="existing-owner",
                    lease_token="existing-token",
                    lease_expires_at=lease_expiry,
                ),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=convergence_day,
                    status="COMPLETE",
                    target_epoch=0,
                    source_revision=7,
                ),
            ]
        )
        noise_portfolio_id = "TERMINAL_CARRY_FORWARD_PLAN_NOISE"
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=noise_portfolio_id,
                base_currency="USD",
                open_date=date(2018, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="noise",
                status="ACTIVE",
            )
        )
        session.flush()
        noise_start = date(2018, 1, 1)
        session.execute(
            PortfolioAggregationJob.__table__.insert(),
            [
                {
                    "tenant_id": TEST_TENANT_ID,
                    "portfolio_id": noise_portfolio_id,
                    "aggregation_date": noise_start + timedelta(days=offset),
                    "status": "COMPLETE",
                    "target_epoch": 0,
                    "source_revision": 1,
                }
                for offset in range(2_000)
            ],
        )
        session.commit()
        snapshot_id = changed_snapshot.id

    materializer = MaterializePositionTimeseries(
        repository_provider=_SessionPositionTimeseriesRepositoryProvider(async_db_session)
    )
    result = await materializer.execute(
        MaterializePositionTimeseriesCommand(
            snapshot_id=snapshot_id,
            portfolio_id=portfolio_id,
            security_id=security_id,
            valuation_date=changed_day,
            epoch=2,
            correlation_id="corr-terminal-carry-forward",
        )
    )
    rows = (
        (
            await async_db_session.execute(
                select(PortfolioAggregationJob)
                .where(PortfolioAggregationJob.portfolio_id == portfolio_id)
                .order_by(PortfolioAggregationJob.aggregation_date)
            )
        )
        .scalars()
        .all()
    )

    assert result.current_day_changed is True
    assert result.dependent_days_changed == 0
    assert [
        (row.aggregation_date, row.status, row.target_epoch, row.source_revision) for row in rows
    ] == [
        (changed_day, "PENDING", 2, 2),
        (complete_carry_day, "PENDING", 2, 4),
        (failed_carry_day, "PENDING", 2, 5),
        (pending_carry_day, "PENDING", 2, 6),
        (processing_carry_day, "PROCESSING", 2, 7),
        (convergence_day, "COMPLETE", 0, 7),
    ]
    assert rows[2].failure_reason is None
    assert rows[4].lease_owner == "existing-owner"
    assert rows[4].lease_token == "existing-token"
    assert rows[4].lease_expires_at == lease_expiry
    assert rows[4].failure_reason == "REPROCESS_REQUESTED"

    await async_db_session.execute(text("ANALYZE portfolio_aggregation_jobs"))
    plan = await async_db_session.scalar(
        text(
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            UPDATE portfolio_aggregation_jobs
               SET target_epoch = greatest(target_epoch, :target_epoch),
                   source_revision = source_revision + 1,
                   status = 'PENDING',
                   failure_reason = NULL,
                   updated_at = now()
             WHERE portfolio_id = :portfolio_id
               AND aggregation_date >= :start_date
               AND aggregation_date < :end_date_exclusive
               AND status IN ('PENDING', 'PROCESSING', 'COMPLETE', 'FAILED')
            """
        ),
        {
            "portfolio_id": "TERMINAL_CARRY_FORWARD_PLAN_NOISE",
            "start_date": noise_start + timedelta(days=500),
            "end_date_exclusive": noise_start + timedelta(days=530),
            "target_epoch": 2,
        },
    )
    assert plan_index_names(plan) & {
        "_portfolio_date_uc",
        "ix_portfolio_aggregation_jobs_aggregation_date",
    }
    assert "Seq Scan" not in plan_node_types(plan)
    await async_db_session.rollback()


@pytest.fixture(scope="function")
def setup_sequential_jobs_with_snapshot_completeness(db_engine, clean_db):
    portfolio_id = "SEQ_JOB_TEST_01"
    day1 = date(2025, 8, 18)
    day2 = date(2025, 8, 19)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.add_all(
            [
                Instrument(
                    security_id="SEC_A",
                    name="Sec A",
                    isin="ISIN_A",
                    currency="USD",
                    product_type="EQ",
                ),
                Instrument(
                    security_id="SEC_B",
                    name="Sec B",
                    isin="ISIN_B",
                    currency="USD",
                    product_type="EQ",
                ),
            ]
        )
        session.add_all(
            [
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    epoch=0,
                    watermark_date=date(2024, 1, 1),
                ),
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    epoch=0,
                    watermark_date=date(2024, 1, 1),
                ),
            ]
        )
        session.add_all(
            [
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=day1,
                    status="PENDING",
                ),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=day2,
                    status="PENDING",
                ),
            ]
        )
        session.flush()

        # Day1 inputs: 2 expected snapshots, only 1 produced position-timeseries (incomplete).
        session.add_all(
            [
                _snapshot(portfolio_id, "SEC_A", day1),
                _snapshot(portfolio_id, "SEC_B", day1),
                _position_ts(portfolio_id, "SEC_A", day1),
            ]
        )
        # Day2 inputs: complete latest-per-security input set. Portfolio aggregation
        # no longer depends on a previous portfolio row, so complete days can be
        # claimed in the same batch and processed in parallel by Kafka consumers.
        session.add_all(
            [
                _snapshot(portfolio_id, "SEC_A", day2),
                _snapshot(portfolio_id, "SEC_B", day2),
                _position_ts(portfolio_id, "SEC_A", day2),
                _position_ts(portfolio_id, "SEC_B", day2),
            ]
        )
        session.commit()

    return {"portfolio_id": portfolio_id, "day1": day1, "day2": day2}


async def test_claim_eligible_jobs_enforces_snapshot_completeness_gate(
    setup_sequential_jobs_with_snapshot_completeness,
    async_db_session: AsyncSession,
    db_engine,
):
    repo = PortfolioAggregationRepository(async_db_session)
    portfolio_id = setup_sequential_jobs_with_snapshot_completeness["portfolio_id"]
    day1 = setup_sequential_jobs_with_snapshot_completeness["day1"]
    day2 = setup_sequential_jobs_with_snapshot_completeness["day2"]

    # Day1 should not claim while input set is incomplete, but complete later
    # dates are independently eligible because portfolio aggregation does not
    # carry prior portfolio rows forward.
    claimed_jobs_1 = await repo.claim_eligible_jobs(
        batch_size=5,
        lease=_lease("completeness-first"),
    )
    await async_db_session.commit()
    assert [job.aggregation_date for job in claimed_jobs_1] == [day2]

    # Complete day1 input set.
    with Session(db_engine) as session:
        session.add(_position_ts(portfolio_id, "SEC_B", day1))
        session.commit()
    await async_db_session.rollback()

    claimed_jobs_2 = await repo.claim_eligible_jobs(
        batch_size=5,
        lease=_lease("completeness-second"),
    )
    await async_db_session.commit()
    assert [job.aggregation_date for job in claimed_jobs_2] == [day1]


async def test_claim_eligible_jobs_claims_first_day_without_portfolio_history(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "FIRST_DAY_PORTFOLIO"
    first_day = date(2025, 8, 19)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.flush()
        session.add(
            Instrument(
                security_id="CASH_USD_FIRST",
                name="Cash USD",
                isin="CASH_USD_FIRST",
                currency="USD",
                product_type="Cash",
            )
        )
        session.add(
            PositionState(
                portfolio_id=portfolio_id,
                security_id="CASH_USD_FIRST",
                epoch=0,
                watermark_date=date(1970, 1, 1),
            )
        )
        session.add(
            PortfolioAggregationJob(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                aggregation_date=first_day,
                status="PENDING",
            )
        )
        session.add(_snapshot(portfolio_id, "CASH_USD_FIRST", first_day, epoch=0))
        session.add(_position_ts(portfolio_id, "CASH_USD_FIRST", first_day, epoch=0))
        session.commit()
    await async_db_session.rollback()

    repo = PortfolioAggregationRepository(async_db_session)
    claimed_jobs = await repo.claim_eligible_jobs(
        batch_size=5,
        lease=_lease("first-day"),
    )
    await async_db_session.commit()

    assert len(claimed_jobs) == 1
    assert claimed_jobs[0].aggregation_date == first_day


async def test_claim_eligible_jobs_accepts_mixed_latest_epochs_per_security(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "MIXED_EPOCH_PORT"
    a_date = date(2025, 8, 23)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.flush()
        session.add_all(
            [
                Instrument(
                    security_id="SEC_A",
                    name="Sec A",
                    isin="ISIN_A",
                    currency="USD",
                    product_type="EQ",
                ),
                Instrument(
                    security_id="SEC_B",
                    name="Sec B",
                    isin="ISIN_B",
                    currency="USD",
                    product_type="EQ",
                ),
            ]
        )
        session.add_all(
            [
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    epoch=1,
                    watermark_date=a_date,
                ),
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    epoch=0,
                    watermark_date=date(1970, 1, 1),
                ),
            ]
        )
        session.add(
            PortfolioAggregationJob(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                aggregation_date=a_date,
                status="PENDING",
                target_epoch=1,
            )
        )
        session.add(
            PortfolioTimeseries(
                portfolio_id=portfolio_id,
                date=date(2025, 8, 22),
                epoch=1,
                bod_market_value=Decimal("0"),
                bod_cashflow=Decimal("0"),
                eod_cashflow=Decimal("0"),
                eod_market_value=Decimal("100"),
                fees=Decimal("0"),
            )
        )
        session.add_all(
            [
                _snapshot(portfolio_id, "SEC_A", a_date, epoch=1),
                _snapshot(portfolio_id, "SEC_B", a_date, epoch=0),
                _position_ts(portfolio_id, "SEC_A", a_date, epoch=1),
                _position_ts(portfolio_id, "SEC_B", a_date, epoch=0),
            ]
        )
        session.commit()

    repo = PortfolioAggregationRepository(async_db_session)
    claimed_jobs = await repo.claim_eligible_jobs(
        batch_size=5,
        lease=_lease("mixed-epochs"),
    )
    await async_db_session.commit()

    assert len(claimed_jobs) == 1
    assert claimed_jobs[0].aggregation_date == a_date
    assert claimed_jobs[0].target_epoch == 1


async def test_claim_eligible_jobs_claims_all_complete_days_without_history_dependency(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "STRANDED_BOOTSTRAP_PORT"
    early_day = date(2025, 4, 1)
    later_day = date(2025, 7, 2)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.flush()
        session.add(
            Instrument(
                security_id="CASH_USD_BOOT",
                name="Cash USD",
                isin="CASH_USD_BOOT",
                currency="USD",
                product_type="Cash",
            )
        )
        session.add(
            PositionState(
                portfolio_id=portfolio_id,
                security_id="CASH_USD_BOOT",
                epoch=0,
                watermark_date=date(1970, 1, 1),
            )
        )
        session.add_all(
            [
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=early_day,
                    status="PENDING",
                ),
                PortfolioAggregationJob(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    aggregation_date=later_day,
                    status="PENDING",
                ),
            ]
        )
        session.add_all(
            [
                _snapshot(portfolio_id, "CASH_USD_BOOT", early_day, epoch=0),
                _position_ts(portfolio_id, "CASH_USD_BOOT", early_day, epoch=0),
                _snapshot(portfolio_id, "CASH_USD_BOOT", later_day, epoch=0),
                _position_ts(portfolio_id, "CASH_USD_BOOT", later_day, epoch=0),
                PortfolioTimeseries(
                    portfolio_id=portfolio_id,
                    date=later_day,
                    epoch=0,
                    bod_market_value=Decimal("0"),
                    bod_cashflow=Decimal("0"),
                    eod_cashflow=Decimal("0"),
                    eod_market_value=Decimal("100"),
                    fees=Decimal("0"),
                ),
            ]
        )
        session.commit()

    repo = PortfolioAggregationRepository(async_db_session)
    claimed_jobs = await repo.claim_eligible_jobs(
        batch_size=5,
        lease=_lease("complete-days"),
    )
    await async_db_session.commit()

    assert [job.aggregation_date for job in claimed_jobs] == [early_day, later_day]


async def test_claim_eligible_jobs_does_not_need_prior_day_when_current_epoch_has_advanced(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "PRIOR_DAY_MIXED_EPOCH"
    prior_day = date(2025, 8, 22)
    target_day = date(2025, 8, 23)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.flush()
        session.add_all(
            [
                Instrument(
                    security_id="SEC_A",
                    name="Sec A",
                    isin="ISIN_A",
                    currency="USD",
                    product_type="EQ",
                ),
                Instrument(
                    security_id="SEC_B",
                    name="Sec B",
                    isin="ISIN_B",
                    currency="USD",
                    product_type="EQ",
                ),
            ]
        )
        session.add_all(
            [
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    epoch=1,
                    watermark_date=target_day,
                ),
                PositionState(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    epoch=0,
                    watermark_date=date(1970, 1, 1),
                ),
            ]
        )
        session.add(
            PortfolioAggregationJob(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                aggregation_date=target_day,
                status="PENDING",
                target_epoch=1,
            )
        )
        session.add(
            PortfolioTimeseries(
                portfolio_id=portfolio_id,
                date=prior_day,
                epoch=0,
                bod_market_value=Decimal("0"),
                bod_cashflow=Decimal("0"),
                eod_cashflow=Decimal("0"),
                eod_market_value=Decimal("170"),
                fees=Decimal("0"),
            )
        )
        session.add_all(
            [
                _snapshot(portfolio_id, "SEC_A", target_day, epoch=1),
                _snapshot(portfolio_id, "SEC_B", target_day, epoch=0),
                _position_ts(portfolio_id, "SEC_A", target_day, epoch=1),
                _position_ts(portfolio_id, "SEC_B", target_day, epoch=0),
            ]
        )
        session.commit()

    repo = PortfolioAggregationRepository(async_db_session)
    claimed_jobs = await repo.claim_eligible_jobs(
        batch_size=5,
        lease=_lease("advanced-epoch"),
    )
    await async_db_session.commit()

    assert len(claimed_jobs) == 1
    assert claimed_jobs[0].aggregation_date == target_day
    assert claimed_jobs[0].target_epoch == 1


async def test_get_all_position_timeseries_for_date_returns_one_authoritative_asof_row_per_security(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "PTS_ASOF_PORT"
    target_date = date(2025, 8, 20)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.add_all(
            [
                Instrument(
                    security_id="SEC_A",
                    name="Sec A",
                    isin="ISIN_A",
                    currency="USD",
                    product_type="EQ",
                ),
                Instrument(
                    security_id="SEC_B",
                    name="Sec B",
                    isin="ISIN_B",
                    currency="USD",
                    product_type="EQ",
                ),
            ]
        )
        session.add_all(
            [
                PositionTimeseries(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    date=date(2025, 8, 18),
                    epoch=1,
                    bod_market_value=Decimal("10"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    eod_market_value=Decimal("11"),
                    fees=Decimal("0"),
                    quantity=Decimal("1"),
                    cost=Decimal("10"),
                ),
                PositionTimeseries(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    date=date(2025, 8, 19),
                    epoch=1,
                    bod_market_value=Decimal("20"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    eod_market_value=Decimal("21"),
                    fees=Decimal("0"),
                    quantity=Decimal("2"),
                    cost=Decimal("20"),
                ),
                PositionTimeseries(
                    portfolio_id=portfolio_id,
                    security_id="SEC_A",
                    date=date(2025, 8, 19),
                    epoch=2,
                    bod_market_value=Decimal("30"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    eod_market_value=Decimal("31"),
                    fees=Decimal("0"),
                    quantity=Decimal("3"),
                    cost=Decimal("30"),
                ),
                PositionTimeseries(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    date=date(2025, 8, 17),
                    epoch=4,
                    bod_market_value=Decimal("40"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    eod_market_value=Decimal("41"),
                    fees=Decimal("0"),
                    quantity=Decimal("4"),
                    cost=Decimal("40"),
                ),
                PositionTimeseries(
                    portfolio_id=portfolio_id,
                    security_id="SEC_B",
                    date=date(2025, 8, 21),
                    epoch=1,
                    bod_market_value=Decimal("50"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    eod_market_value=Decimal("51"),
                    fees=Decimal("0"),
                    quantity=Decimal("5"),
                    cost=Decimal("50"),
                ),
            ]
        )
        session.commit()
    await async_db_session.rollback()

    repo = PortfolioAggregationRepository(async_db_session)

    rows = await repo.get_all_position_timeseries_for_date(portfolio_id, target_date, 4)

    assert [(row.security_id, row.date, row.epoch) for row in rows] == [
        ("SEC_A", date(2025, 8, 19), 2),
        ("SEC_B", date(2025, 8, 17), 4),
    ]
    assert len(rows) == 2


async def test_get_all_cashflows_for_security_date_returns_latest_restatement_per_transaction_id(
    db_engine, clean_db, async_db_session: AsyncSession
):
    portfolio_id = "CF_ASOF_PORT"
    security_id = "CASH_USD"
    cashflow_date = date(2025, 8, 20)

    with Session(db_engine) as session:
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.add(
            Instrument(
                security_id=security_id,
                name="Cash USD",
                isin="CASH_USD",
                currency="USD",
                product_type="Cash",
            )
        )
        session.add_all(
            [
                _transaction("TXN_RESTATED", portfolio_id, security_id, cashflow_date),
                _transaction("TXN_SECOND", portfolio_id, security_id, cashflow_date),
                _transaction("TXN_FUTURE", portfolio_id, security_id, cashflow_date),
            ]
        )
        session.add_all(
            [
                Cashflow(
                    transaction_id="TXN_RESTATED",
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    cashflow_date=cashflow_date,
                    epoch=1,
                    amount=Decimal("100"),
                    currency="USD",
                    classification="CASHFLOW_OUT",
                    timing="BOD",
                    calculation_type="NET",
                    is_position_flow=False,
                    is_portfolio_flow=True,
                ),
                Cashflow(
                    transaction_id="TXN_RESTATED",
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    cashflow_date=cashflow_date,
                    epoch=2,
                    amount=Decimal("100"),
                    currency="USD",
                    classification="EXPENSE",
                    timing="EOD",
                    calculation_type="NET",
                    is_position_flow=False,
                    is_portfolio_flow=False,
                ),
                Cashflow(
                    transaction_id="TXN_SECOND",
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    cashflow_date=cashflow_date,
                    epoch=1,
                    amount=Decimal("250"),
                    currency="USD",
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    calculation_type="NET",
                    is_position_flow=False,
                    is_portfolio_flow=True,
                ),
                Cashflow(
                    transaction_id="TXN_FUTURE",
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    cashflow_date=cashflow_date,
                    epoch=3,
                    amount=Decimal("999"),
                    currency="USD",
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    calculation_type="NET",
                    is_position_flow=False,
                    is_portfolio_flow=True,
                ),
            ]
        )
        session.commit()
    await async_db_session.rollback()

    repo = TimeseriesGenerationRepository(async_db_session)

    rows = await repo.get_all_cashflows_for_security_date(
        portfolio_id, security_id, cashflow_date, 2
    )

    assert [(row.transaction_id, row.epoch) for row in rows] == [
        ("TXN_SECOND", 1),
        ("TXN_RESTATED", 2),
    ]
    restated_row = next(row for row in rows if row.transaction_id == "TXN_RESTATED")
    assert restated_row.classification == "EXPENSE"
    assert restated_row.timing == "EOD"
    assert restated_row.is_portfolio_flow is False
    assert all(row.transaction_id != "TXN_FUTURE" for row in rows)
