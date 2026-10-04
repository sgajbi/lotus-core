"""Prove source-lot admission and receipt failures through native PostgreSQL processing.

Raw source rows use the canonical event mapper, not a broker or HTTP ingress. Native combined
composition executes PreparedCostProcessingUseCase and its real repositories/UOW. No test
creates PositionLotState, checkpoints, calculated economics, or completed controls to conceal
the missing-prefix dependency. This is database proof, not live-worker batch certification.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    Cashflow,
    CostBasisProcessingState,
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    OutboxEvent,
    PipelineStageState,
    Portfolio,
    PositionHistory,
    PositionLotState,
    ProcessedEvent,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    ProcessTransactionResult,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction,
    LotDisposalReceiptStatus,
    build_cost_basis_engine_input,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.lot_disposal_repository import (  # noqa: E501
    ConflictingLotDisposalReceiptError,
    MissingSourceLotDisposalDependencyError,
    SqlAlchemyCostBasisLotDisposalRepository,
    _verified_state,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.lot_state_repository import (  # noqa: E501
    SqlAlchemyCostBasisLotRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.transaction_repository import (  # noqa: E501
    SqlAlchemyCostBasisTransactionRepository,
)
from tests.test_support.async_task_coordination import cancel_pending_tasks, wait_for_task_signal
from tests.test_support.transaction_processing import (
    TransactionProcessingTestContext,
    booked_transaction_event,
    canonical_transaction_record,
    cash_account_record,
    instrument_record,
    portfolio_record,
    process_booked_transaction,
    transaction_processing_test_context,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]


async def _admit_raw_sources(
    session: AsyncSession, *, suffix: str, include_sell: bool
) -> tuple[TransactionProcessingTestContext, TransactionEvent, TransactionEvent]:
    portfolio_id = f"PORT-LOT-ADMISSION-{suffix}"
    security_id = f"SEC-LOT-ADMISSION-{suffix}"
    cash_id = f"CASH-LOT-ADMISSION-{suffix}"
    common = {
        "portfolio_id": portfolio_id,
        "security_id": security_id,
        "cash_entry_mode": "AUTO_GENERATE",
        "settlement_cash_account_id": cash_id,
        "settlement_cash_instrument_id": cash_id,
    }
    buy = booked_transaction_event(
        **common,
        transaction_id=f"BUY-LOT-ADMISSION-{suffix}",
        transaction_date=datetime(2026, 4, 9, 10, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="100",
        gross_amount="1000",
    )
    sell = booked_transaction_event(
        **common,
        transaction_id=f"SELL-LOT-ADMISSION-{suffix}",
        transaction_date=datetime(2026, 4, 10, 10, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="6",
        price="120",
        gross_amount="720",
    )
    session.add(portfolio_record(portfolio_id))
    await session.flush()
    session.add_all(
        [
            instrument_record(
                security_id, name="Admission equity", isin=security_id, currency="USD"
            ),
            instrument_record(
                cash_id,
                name="Admission USD cash",
                isin=cash_id,
                currency="USD",
                product_type="CASH",
                asset_class="Cash",
            ),
            cash_account_record(
                cash_id, portfolio_id=portfolio_id, security_id=cash_id, account_currency="USD"
            ),
            canonical_transaction_record(buy),
        ]
    )
    if include_sell:
        session.add(canonical_transaction_record(sell))
    await session.commit()
    return transaction_processing_test_context(session), buy, sell


async def _process(
    context: TransactionProcessingTestContext, source: TransactionEvent, *, delivery: str = "first"
) -> ProcessTransactionResult:
    return await process_booked_transaction(
        context=context,
        event=source,
        event_id=f"transactions.persisted-{source.transaction_id}-{delivery}",
        correlation_id=f"corr-{source.transaction_id}",
    )


async def _durable_cut(context: TransactionProcessingTestContext, portfolio_id: str) -> dict:
    """Compare actual durable rows across failure, not session-cached calculated objects."""
    tables = (
        DBTransaction,
        PositionLotState,
        CostBasisProcessingState,
        AccruedIncomeOffsetState,
        ProcessedEvent,
        PipelineStageState,
        LotDisposalReceiptRecord,
        LotDisposalAllocationRecord,
        Cashflow,
        PositionHistory,
    )
    async with context.session_factory() as session:
        cut = {
            model.__tablename__: list(
                (
                    await session.execute(
                        select(model.__table__)
                        .where(model.portfolio_id == portfolio_id)
                        .order_by(*model.__table__.primary_key.columns)
                    )
                )
                .mappings()
                .all()
            )
            for model in tables
        }
        cut["transaction_costs"] = list(
            (
                await session.execute(
                    select(TransactionCost.__table__)
                    .join(
                        DBTransaction,
                        DBTransaction.transaction_id == TransactionCost.transaction_id,
                    )
                    .where(DBTransaction.portfolio_id == portfolio_id)
                    .order_by(TransactionCost.id)
                )
            )
            .mappings()
            .all()
        )
        cut["outbox_events"] = list(
            (
                await session.execute(
                    select(OutboxEvent.__table__)
                    .where(
                        or_(
                            OutboxEvent.aggregate_id == portfolio_id,
                            OutboxEvent.aggregate_id.startswith(
                                f"{portfolio_id}:", autoescape=True
                            ),
                            OutboxEvent.aggregate_id.in_(
                                {row["security_id"] for row in cut["transactions"]}
                            ),
                            OutboxEvent.correlation_id.in_(
                                {f"corr-{row['transaction_id']}" for row in cut["transactions"]}
                            ),
                        )
                    )
                    .order_by(OutboxEvent.id)
                )
            )
            .mappings()
            .all()
        )
    return cut


def _postgres_error_identity(error: BaseException) -> tuple[str | None, str | None]:
    """Inspect SQLSTATE/constraint from the actual asyncpg exception chain."""
    current: BaseException | None = error
    sqlstate = constraint = None
    while current is not None:
        sqlstate = getattr(current, "sqlstate", None) or sqlstate
        constraint = getattr(current, "constraint_name", None) or constraint
        current = current.__cause__
    return sqlstate, constraint


@pytest.mark.parametrize("repetition", [1, 2])
async def test_missing_prefix_buy_lot_is_admitted_before_sell_receipt(
    clean_db, async_db_session: AsyncSession, repetition: int
) -> None:
    context, buy, sell = await _admit_raw_sources(
        async_db_session, suffix=f"PREFIX-{repetition}", include_sell=True
    )
    before = await _durable_cut(context, sell.portfolio_id)
    assert len(before["transactions"]) == 2
    assert before["position_lot_state"] == before["cost_basis_processing_state"] == []
    assert before["processed_events"] == before["accrued_income_offset_state"] == []
    assert all(row["calculation_lineage"] is None for row in before["transactions"])
    result = await _process(context, sell)
    assert result.status is TransactionProcessingStatus.PROCESSED
    await _assert_sell_economics(context, buy, sell)
    after = await _durable_cut(context, sell.portfolio_id)
    assert not any(
        row["transaction_id"] == buy.transaction_id for row in after["accrued_income_offset_state"]
    )
    assert not any(
        row["transaction_id"] == f"{buy.transaction_id}-CASHLEG" for row in after["transactions"]
    )
    assert not any(buy.transaction_id in row["event_id"] for row in after["processed_events"])
    assert any(row["aggregate_type"] == "PipelineStage" for row in after["outbox_events"])
    assert any(row["aggregate_type"] == "ValuationReadiness" for row in after["outbox_events"])
    retry_cut = after
    assert (
        await _process(context, sell, delivery="retry")
    ).status is TransactionProcessingStatus.DUPLICATE
    assert await _durable_cut(context, sell.portfolio_id) == retry_cut


async def test_removing_parent_admission_exposes_actual_dependency_fk_and_atomic_rollback(
    clean_db, async_db_session: AsyncSession, monkeypatch
) -> None:
    context, _buy, sell = await _admit_raw_sources(
        async_db_session, suffix="REMOVE-FIX", include_sell=True
    )
    before = await _durable_cut(context, sell.portfolio_id)

    async def omit_parent(self, transaction, *, tenant_id):
        pass

    monkeypatch.setattr(
        SqlAlchemyCostBasisLotRepository, "ensure_acquisition_lot_parent", omit_parent
    )
    with pytest.raises(MissingSourceLotDisposalDependencyError) as failure:
        await _process(context, sell)
    assert _postgres_error_identity(failure.value) == (
        "23503",
        "fk_lot_disposal_allocation_lot_scope",
    )
    assert await _durable_cut(context, sell.portfolio_id) == before


async def _source_candidate(session: AsyncSession, buy: TransactionEvent) -> CostBasisTransaction:
    history = await SqlAlchemyCostBasisTransactionRepository(session).get_transaction_history(
        buy.portfolio_id, buy.security_id
    )
    source = next(row for row in history if row.transaction_id == buy.transaction_id)
    base_currency = await session.scalar(
        select(Portfolio.base_currency).where(Portfolio.portfolio_id == source.portfolio_id)
    )
    return CostBasisTransaction(
        **build_cost_basis_engine_input(source), portfolio_base_currency=base_currency
    )


async def test_present_parent_admission_preserves_entire_residual_lot_and_durable_cut(
    clean_db, async_db_session: AsyncSession
) -> None:
    context, buy, sell = await _process_existing_lot(async_db_session, "PRESENT")
    before = await _durable_cut(context, buy.portfolio_id)
    async with context.session_factory() as session, session.begin():
        candidate = await _source_candidate(session, buy)
        repository = SqlAlchemyCostBasisLotRepository(session)
        await repository.ensure_acquisition_lot_parent(candidate, tenant_id=buy.tenant_id)
        await repository.ensure_acquisition_lot_parent(candidate, tenant_id=buy.tenant_id)
    assert await _durable_cut(context, buy.portfolio_id) == before
    await _assert_sell_economics(context, buy, sell)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "FOREIGN"),
        ("portfolio_id", "FOREIGN"),
        ("security_id", "FOREIGN"),
        ("instrument_id", "FOREIGN"),
        ("transaction_id", "MISSING-SOURCE"),
        ("quantity", Decimal("11")),
        ("transaction_type", "TRANSFER_IN"),
        ("transaction_date", datetime(2026, 4, 8, tzinfo=timezone.utc)),
    ],
)
async def test_parent_source_scope_refusal_preserves_actual_durable_rows(
    clean_db, async_db_session: AsyncSession, field: str, value: object
) -> None:
    context, buy, _sell = await _admit_raw_sources(
        async_db_session, suffix="REFUSE", include_sell=False
    )
    before = await _durable_cut(context, buy.portfolio_id)
    with pytest.raises(ValueError, match="Acquisition lot parent"):
        async with context.session_factory() as session, session.begin():
            candidate = await _source_candidate(session, buy)
            tenant_id = buy.tenant_id
            if field == "tenant_id":
                tenant_id = str(value)
            else:
                setattr(candidate, field, value)
            await SqlAlchemyCostBasisLotRepository(session).ensure_acquisition_lot_parent(
                candidate, tenant_id=tenant_id
            )
    assert await _durable_cut(context, buy.portfolio_id) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("lot_id", "FOREIGN-LOT"),
        ("security_id", "FOREIGN-SEC"),
        ("instrument_id", "FOREIGN-INST"),
    ],
)
async def test_conflicting_present_parent_is_not_silently_accepted_or_repaired(
    clean_db, async_db_session: AsyncSession, field: str, value: str
) -> None:
    context, buy, _sell = await _admit_raw_sources(
        async_db_session, suffix="COLLISION", include_sell=False
    )
    assert (await _process(context, buy)).status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as session, session.begin():
        await session.execute(
            update(PositionLotState)
            .where(PositionLotState.source_transaction_id == buy.transaction_id)
            .values(**{field: value})
        )
    before = await _durable_cut(context, buy.portfolio_id)
    with pytest.raises(ValueError, match="durable source identity"):
        async with context.session_factory() as session, session.begin():
            await SqlAlchemyCostBasisLotRepository(session).ensure_acquisition_lot_parent(
                await _source_candidate(session, buy), tenant_id=buy.tenant_id
            )
    assert await _durable_cut(context, buy.portfolio_id) == before


async def test_parent_admission_then_refusal_rolls_back_earlier_insert(
    clean_db, async_db_session: AsyncSession
) -> None:
    context, buy, _sell = await _admit_raw_sources(
        async_db_session, suffix="PARTIAL", include_sell=False
    )
    before = await _durable_cut(context, buy.portfolio_id)
    with pytest.raises(ValueError, match="durable source scope"):
        async with context.session_factory() as session, session.begin():
            candidate = await _source_candidate(session, buy)
            repository = SqlAlchemyCostBasisLotRepository(session)
            await repository.ensure_acquisition_lot_parent(candidate, tenant_id=buy.tenant_id)
            candidate.security_id = "FOREIGN-SEC"
            await repository.ensure_acquisition_lot_parent(candidate, tenant_id=buy.tenant_id)
    assert await _durable_cut(context, buy.portfolio_id) == before


async def test_initial_opening_buy_creates_lot_and_settlement_cash(
    clean_db, async_db_session: AsyncSession
) -> None:
    context, buy, _sell = await _admit_raw_sources(
        async_db_session, suffix="OPENING", include_sell=False
    )
    result = await _process(context, buy)
    assert result.status is TransactionProcessingStatus.PROCESSED
    async with context.session_factory() as session:
        lot = (
            await session.scalars(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == buy.transaction_id
                )
            )
        ).one()
        cash = (
            await session.scalars(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == f"{buy.transaction_id}-CASHLEG"
                )
            )
        ).one()
        checkpoint = (
            await session.scalars(
                select(CostBasisProcessingState).where(
                    CostBasisProcessingState.portfolio_id == buy.portfolio_id
                )
            )
        ).one()
    assert (lot.original_quantity, lot.open_quantity, lot.lot_cost_base) == (
        Decimal("10"),
        Decimal("10"),
        Decimal("1000"),
    )
    assert cash.gross_transaction_amount == Decimal("1000")
    assert checkpoint.latest_transaction_id == buy.transaction_id
    assert cash.economic_event_id == f"EVT-BUY-{buy.portfolio_id}-{buy.transaction_id}"
    assert cash.linked_transaction_group_id == f"LTG-BUY-{buy.portfolio_id}-{buy.transaction_id}"


async def _process_existing_lot(
    session: AsyncSession, suffix: str
) -> tuple[TransactionProcessingTestContext, TransactionEvent, TransactionEvent]:
    context, buy, sell = await _admit_raw_sources(session, suffix=suffix, include_sell=False)
    assert (await _process(context, buy)).status is TransactionProcessingStatus.PROCESSED
    session.add(canonical_transaction_record(sell))
    await session.commit()
    assert (await _process(context, sell)).status is TransactionProcessingStatus.PROCESSED
    await _assert_sell_economics(context, buy, sell)
    return context, buy, sell


async def _assert_sell_economics(
    context: TransactionProcessingTestContext, buy: TransactionEvent, sell: TransactionEvent
) -> None:
    async with context.session_factory() as session:
        lot = (
            await session.scalars(
                select(PositionLotState).where(
                    PositionLotState.source_transaction_id == buy.transaction_id
                )
            )
        ).one()
        persisted_sell = (
            await session.scalars(
                select(DBTransaction).where(DBTransaction.transaction_id == sell.transaction_id)
            )
        ).one()
        cash = (
            await session.scalars(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == f"{sell.transaction_id}-CASHLEG"
                )
            )
        ).one()
        receipt = (
            await session.scalars(
                select(LotDisposalReceiptRecord).where(
                    LotDisposalReceiptRecord.disposal_transaction_id == sell.transaction_id
                )
            )
        ).one()
        allocation = (
            await session.scalars(
                select(LotDisposalAllocationRecord).where(
                    LotDisposalAllocationRecord.receipt_id == receipt.receipt_id
                )
            )
        ).one()
    assert (lot.open_quantity, lot.lot_cost_local, lot.lot_cost_base) == (
        Decimal("4"),
        Decimal("400"),
        Decimal("400"),
    )
    assert (persisted_sell.net_cost, persisted_sell.realized_gain_loss) == (
        Decimal("-600"),
        Decimal("120"),
    )
    assert (
        receipt.receipt_version,
        receipt.status,
        receipt.consumed_quantity,
        receipt.consumed_cost_base,
    ) == (1, "ACTIVE", Decimal("6"), Decimal("600"))
    assert (
        allocation.source_lot_id,
        allocation.source_transaction_id,
        allocation.consumed_cost_base,
    ) == (lot.lot_id, buy.transaction_id, Decimal("600"))
    assert cash.gross_transaction_amount == Decimal("720")
    assert cash.economic_event_id == persisted_sell.economic_event_id
    assert cash.linked_transaction_group_id == persisted_sell.linked_transaction_group_id


async def test_existing_lot_incremental_sell_and_delivery_retry_are_neutral(
    clean_db, async_db_session: AsyncSession
) -> None:
    context, buy, sell = await _process_existing_lot(async_db_session, "EXISTING")
    before = await _durable_cut(context, sell.portfolio_id)
    result = await _process(context, sell, delivery="retry")
    assert result.status is TransactionProcessingStatus.DUPLICATE
    assert await _durable_cut(context, sell.portfolio_id) == before
    await _assert_sell_economics(context, buy, sell)


class _HeldReceiptReadRepository(SqlAlchemyCostBasisLotDisposalRepository):
    def __init__(self, session: AsyncSession, read: asyncio.Event, release: asyncio.Event) -> None:
        super().__init__(session)
        self._read = read
        self._release = release

    async def _load_receipt_chains(
        self, transaction_ids: tuple[str, ...]
    ) -> dict[str, tuple[LotDisposalReceiptRecord, ...]]:
        chains = await super()._load_receipt_chains(transaction_ids)
        self._read.set()
        await self._release.wait()
        return chains


async def test_actual_receipt_version_collision_remains_distinct_from_missing_lot_fk(
    clean_db, async_db_session: AsyncSession
) -> None:
    context, _buy, sell = await _process_existing_lot(async_db_session, "VERSION")
    async with context.session_factory() as session:
        header = (
            await session.scalars(
                select(LotDisposalReceiptRecord).where(
                    LotDisposalReceiptRecord.disposal_transaction_id == sell.transaction_id
                )
            )
        ).one()
        allocations = tuple(
            (
                await session.scalars(
                    select(LotDisposalAllocationRecord).where(
                        LotDisposalAllocationRecord.receipt_id == header.receipt_id
                    )
                )
            ).all()
        )
        active = _verified_state(header, allocations=allocations, previous_record=None)
    voided = replace(
        active,
        status=LotDisposalReceiptStatus.VOIDED,
        consumed_quantity=Decimal(0),
        consumed_cost_local=Decimal(0),
        consumed_cost_base=Decimal(0),
        allocations=(),
        disposal_calculation_lineage=None,
        void_reason="RECALCULATED_WITHOUT_LOT_DISPOSAL",
    )
    read, release = asyncio.Event(), asyncio.Event()

    async def append_stale_version() -> None:
        async with context.session_factory() as session, session.begin():
            await _HeldReceiptReadRepository(session, read, release).reconcile_disposal_receipts(
                receipt_states=(voided,)
            )

    task = asyncio.create_task(append_stale_version())
    try:
        await wait_for_task_signal(task, read, timeout=5)
        async with context.session_factory() as session, session.begin():
            await SqlAlchemyCostBasisLotDisposalRepository(session).reconcile_disposal_receipts(
                receipt_states=(voided,)
            )
        release.set()
        with pytest.raises(ConflictingLotDisposalReceiptError) as failure:
            await asyncio.wait_for(task, timeout=5)
        sqlstate, constraint = _postgres_error_identity(failure.value)
        assert sqlstate == "23505"
        assert constraint in {
            "uq_lot_disposal_receipt_version",
            "uq_lot_disposal_transaction_version",
            "uq_lot_disposal_receipt_scope_version",
        }
        async with context.session_factory() as session:
            headers = (
                await session.scalars(
                    select(LotDisposalReceiptRecord)
                    .where(LotDisposalReceiptRecord.disposal_transaction_id == sell.transaction_id)
                    .order_by(LotDisposalReceiptRecord.receipt_version)
                )
            ).all()
        assert [(row.receipt_version, row.status) for row in headers] == [
            (1, "ACTIVE"),
            (2, "VOIDED"),
        ]
        assert headers[1].previous_receipt_content_hash == headers[0].receipt_content_hash
    finally:
        release.set()
        await cancel_pending_tasks(task)
