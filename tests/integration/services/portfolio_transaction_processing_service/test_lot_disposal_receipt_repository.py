"""PostgreSQL proof for immutable lot-disposal receipt version chains."""

from __future__ import annotations

import runpy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import (
    Cashflow,
    CostBasisProcessingState,
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    OutboxEvent,
    PositionHistory,
    PositionLotState,
    PositionState,
    ProcessedEvent,
    Transaction,
)
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.domain.cost_basis_receipt_integrity import (
    LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
    LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
    lot_disposal_allocation_payload,
    lot_disposal_lineage_input_payload,
    lot_disposal_lineage_output_payload,
    receipt_version_content_hash,
    verify_cost_basis_receipt_version_chain,
)
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1
from sqlalchemy import event, func, inspect, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LotDisposalReceiptState,
    LotDisposalReceiptStatus,
    SourceLotDisposalAllocation,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    CorruptLotDisposalReceiptError,
    SqlAlchemyCostBasisLotDisposalRepository,
)
from src.services.query_service.app.repositories.lot_disposal_repository import (
    CorruptLotDisposalReadModelError,
)
from src.services.query_service.app.repositories.lot_disposal_repository import (
    LotDisposalRepository as QueryLotDisposalRepository,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
    portfolio_record,
)
from tools.front_office_portfolio_seed import build_portfolio_seed_cleanup_sql

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c141b2c3d50e_feat_add_lot_disposal_receipts.py"
)
CARRY_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c144b2c3d511_fix_separate_amortized_book_carry.py"
)


@pytest.fixture
def disposal_receipt_schema(clean_db, db_engine) -> None:
    """Apply the branch migration when the cached integration image predates it."""

    with db_engine.begin() as connection:
        inspector = inspect(connection)
        operations = Operations(MigrationContext.configure(connection))
        if not inspector.has_table("lot_disposal_receipts"):
            lot_constraints = {
                item["name"] for item in inspector.get_unique_constraints("position_lot_state")
            }
            if "uq_position_lot_scope_identity" not in lot_constraints:
                operations.create_unique_constraint(
                    "uq_position_lot_scope_identity",
                    "position_lot_state",
                    ["lot_id", "portfolio_id", "security_id"],
                )
            migration = runpy.run_path(str(MIGRATION))
            migration["upgrade"].__globals__["op"] = operations
            migration["upgrade"]()
        lot_columns = {
            item["name"] for item in inspect(connection).get_columns("position_lot_state")
        }
        if "amortized_book_carrying_local" not in lot_columns:
            carry_migration = runpy.run_path(str(CARRY_MIGRATION))
            carry_migration["upgrade"].__globals__["op"] = operations
            carry_migration["upgrade"]()


async def test_repository_preserves_active_correction_void_and_reactivation_history(
    clean_db,
    disposal_receipt_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyCostBasisLotDisposalRepository(async_db_session)
    first = _active_state(cost_local="10")
    corrected = _active_state(cost_local="11")
    voided = _void_state()

    await repository.reconcile_disposal_receipts(receipt_states=(first,))
    await repository.reconcile_disposal_receipts(receipt_states=(first,))
    await repository.reconcile_disposal_receipts(receipt_states=(corrected,))
    await repository.reconcile_disposal_receipts(receipt_states=(voided,))
    await repository.reconcile_disposal_receipts(receipt_states=(corrected,))
    await async_db_session.commit()

    receipts = list(
        (
            await async_db_session.scalars(
                select(LotDisposalReceiptRecord).order_by(LotDisposalReceiptRecord.receipt_version)
            )
        ).all()
    )
    allocations = list(
        (
            await async_db_session.scalars(
                select(LotDisposalAllocationRecord).order_by(
                    LotDisposalAllocationRecord.receipt_version
                )
            )
        ).all()
    )
    assert [receipt.receipt_version for receipt in receipts] == [1, 2, 3, 4]
    assert [receipt.status for receipt in receipts] == [
        "ACTIVE",
        "ACTIVE",
        "VOIDED",
        "ACTIVE",
    ]
    assert [allocation.receipt_version for allocation in allocations] == [1, 2, 4]
    assert receipts[0].previous_receipt_content_hash is None
    assert receipts[1].previous_receipt_content_hash == receipts[0].receipt_content_hash
    assert receipts[2].previous_receipt_content_hash == receipts[1].receipt_content_hash
    assert receipts[3].previous_receipt_content_hash == receipts[2].receipt_content_hash


async def test_portfolio_reseed_cleanup_removes_disposal_evidence_and_preserves_other_lots(
    clean_db,
    disposal_receipt_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    await _seed_unrelated_source_lot(async_db_session)
    await SqlAlchemyCostBasisLotDisposalRepository(async_db_session).reconcile_disposal_receipts(
        receipt_states=(_active_state(cost_local="10"),)
    )
    await async_db_session.commit()

    cleanup_sql = build_portfolio_seed_cleanup_sql(portfolio_id="PORT-RECEIPT-DB-01")
    for statement in cleanup_sql.split(";"):
        if statement.strip():
            await async_db_session.execute(text(statement))
    await async_db_session.commit()

    allocation_count = await async_db_session.scalar(
        select(func.count()).select_from(LotDisposalAllocationRecord)
    )
    receipt_count = await async_db_session.scalar(
        select(func.count()).select_from(LotDisposalReceiptRecord)
    )
    remaining_lot_ids = set((await async_db_session.scalars(select(PositionLotState.lot_id))).all())
    assert allocation_count == 0
    assert receipt_count == 0
    assert remaining_lot_ids == {"LOT-RECEIPT-DB-OTHER"}


async def test_repository_detects_tampered_child_after_restart(
    clean_db,
    disposal_receipt_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    state = _active_state(cost_local="10")
    await SqlAlchemyCostBasisLotDisposalRepository(async_db_session).reconcile_disposal_receipts(
        receipt_states=(state,)
    )
    await async_db_session.commit()
    await async_db_session.execute(
        update(LotDisposalAllocationRecord).values(allocation_content_hash="0" * 64)
    )
    await async_db_session.commit()

    with pytest.raises(
        CorruptLotDisposalReceiptError,
        match="persisted lot-disposal receipt is corrupt",
    ):
        await SqlAlchemyCostBasisLotDisposalRepository(
            async_db_session
        ).reconcile_disposal_receipts(receipt_states=(state,))


@pytest.mark.lifecycle
async def test_repository_verifies_sixty_four_versions_with_two_bounded_reads(
    clean_db,
    disposal_receipt_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyCostBasisLotDisposalRepository(async_db_session)
    states = tuple(_active_state(cost_local=f"10.{version:02}") for version in range(1, 65))
    for state in states:
        await repository.reconcile_disposal_receipts(receipt_states=(state,))
    await async_db_session.commit()

    statements: list[str] = []

    def record_statement(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT") and "lot_disposal_" in statement:
            statements.append(statement)

    assert async_db_session.bind is not None
    sync_engine = async_db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", record_statement)
    try:
        await repository.reconcile_disposal_receipts(receipt_states=(states[-1],))
    finally:
        event.remove(sync_engine, "before_cursor_execute", record_statement)

    assert len(statements) == 2
    assert "lot_disposal_receipts" in statements[0]
    assert "lot_disposal_allocations" in statements[1]
    assert (
        await async_db_session.scalar(select(func.count()).select_from(LotDisposalReceiptRecord))
        == 64
    )

    statements.clear()
    event.listen(sync_engine, "before_cursor_execute", record_statement)
    try:
        receipt = await QueryLotDisposalRepository(async_db_session).get_latest_receipt(
            portfolio_id=states[-1].portfolio_id,
            transaction_id=states[-1].disposal_transaction_id,
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", record_statement)
    assert receipt is not None
    assert receipt[0].receipt_version == 64
    assert len(statements) == 2

    await async_db_session.execute(
        update(LotDisposalAllocationRecord)
        .where(LotDisposalAllocationRecord.receipt_version == 32)
        .values(allocation_content_hash="0" * 64)
    )
    await async_db_session.commit()
    with pytest.raises(CorruptLotDisposalReceiptError, match="receipt is corrupt"):
        await repository.reconcile_disposal_receipts(receipt_states=(states[-1],))
    with pytest.raises(CorruptLotDisposalReadModelError, match="chain is corrupt"):
        await QueryLotDisposalRepository(async_db_session).get_latest_receipt(
            portfolio_id=states[-1].portfolio_id,
            transaction_id=states[-1].disposal_transaction_id,
        )


async def test_initial_void_state_remains_database_neutral(
    clean_db,
    disposal_receipt_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)

    await SqlAlchemyCostBasisLotDisposalRepository(async_db_session).reconcile_disposal_receipts(
        receipt_states=(_void_state(),)
    )

    assert (
        await async_db_session.scalar(select(func.count()).select_from(LotDisposalReceiptRecord))
        == 0
    )


async def _disposal_durable_snapshot(session_factory) -> dict[str, tuple]:
    """Observe complete financial, receipt, fence and outbox rows through a fresh session."""
    snapshot = {}
    async with session_factory() as session:
        for model in (
            Transaction,
            Cashflow,
            PositionHistory,
            PositionLotState,
            PositionState,
            CostBasisProcessingState,
            LotDisposalReceiptRecord,
            LotDisposalAllocationRecord,
            ProcessedEvent,
            OutboxEvent,
        ):
            table = model.__table__
            rows = await session.execute(select(table).order_by(*table.primary_key.columns))
            snapshot[table.name] = tuple(tuple(row) for row in rows.all())
    return snapshot


def _numerical_disposal_state(
    quantity: int, *, violation: str = "valid"
) -> LotDisposalReceiptState:
    """Independent 10-local/12-base unit basis, with conserved persisted allocations."""
    template = _active_state(cost_local=str(quantity * 10))
    allocation = replace(
        template.allocations[0],
        consumed_quantity=Decimal(quantity),
        consumed_cost_base=Decimal(quantity * 12),
    )
    state = replace(
        template,
        consumed_quantity=Decimal(quantity),
        consumed_cost_base=Decimal(quantity * 12),
        allocations=(allocation,),
    )
    lineage = build_calculation_lineage(
        algorithm_id=("foreign" if violation == "algorithm" else LOT_DISPOSAL_LINEAGE_ALGORITHM_ID),
        algorithm_version=LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=(
            {"unrelated_source": "BUY-OTHER"}
            if violation == "input"
            else lot_disposal_lineage_input_payload([lot_disposal_allocation_payload(allocation)])
        ),
        output_payload=lot_disposal_lineage_output_payload(
            consumed_cost_base=state.consumed_cost_base,
            consumed_cost_local=state.consumed_cost_local,
            consumed_quantity=Decimal(99) if violation == "output" else state.consumed_quantity,
        ),
        numeric_output_policy=(
            None if violation == "policy" else COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity()
        ),
    )
    return replace(state, disposal_calculation_lineage=lineage)


def _assert_lineage_refusal(error: ValueError, violation: str) -> None:
    reason = {
        "algorithm": "algorithm identity is unsupported",
        "policy": "numeric policy is unsupported",
        "input": "lineage does not bind persisted inputs",
        "output": "lineage does not bind persisted outputs",
    }[violation]
    cause: BaseException = error
    while cause.__cause__ is not None:
        cause = cause.__cause__
    assert reason in str(cause)


@pytest.mark.parametrize("violation", ["algorithm", "policy", "input", "output"])
@pytest.mark.parametrize("bad_version", [1, 2])
async def test_reloaded_rehashed_lineage_refuses_retry_correction_and_query_without_writes(
    clean_db,
    disposal_receipt_schema,
    async_db_session: AsyncSession,
    violation: str,
    bad_version: int,
) -> None:
    await _seed_source_lot(async_db_session)
    await _seed_unrelated_source_lot(async_db_session)
    assert async_db_session.bind is not None
    # The fixture owns its engine; each proof phase owns/closes only its session.
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    states = tuple(_numerical_disposal_state(quantity) for quantity in (1, 2, 3))
    async with session_factory() as writer:
        repository = SqlAlchemyCostBasisLotDisposalRepository(writer)
        for state in states:
            await repository.reconcile_disposal_receipts(receipt_states=(state,))
        await writer.commit()

    async with session_factory() as adversary:
        records = list(
            (
                await adversary.scalars(
                    select(LotDisposalReceiptRecord).order_by(
                        LotDisposalReceiptRecord.receipt_version
                    )
                )
            ).all()
        )
        bad = _numerical_disposal_state(bad_version, violation=violation)
        assert bad.disposal_calculation_lineage is not None
        records[
            bad_version - 1
        ].disposal_calculation_lineage = bad.disposal_calculation_lineage.lineage_payload()
        records[bad_version - 1].semantic_content_hash = bad.semantic_content_hash
        # Rehash every successor so neither stale outer hashes nor broken pointers
        # can explain refusal. Only governed lineage admission remains violated.
        previous_hash = None
        for record in records:
            record.previous_receipt_content_hash = previous_hash
            record.receipt_content_hash = receipt_version_content_hash(
                receipt_id=record.receipt_id,
                semantic_content_hash=record.semantic_content_hash,
                receipt_version=record.receipt_version,
                previous_receipt_content_hash=previous_hash,
            )
            previous_hash = record.receipt_content_hash
        verify_cost_basis_receipt_version_chain(records)
        await adversary.commit()

    before = await _disposal_durable_snapshot(session_factory)
    statements = []

    def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lstrip().split()[0].upper())

    engine = async_db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", observe)
    try:
        for candidate in (states[-1], _numerical_disposal_state(4)):
            async with session_factory() as restarted:
                with pytest.raises(
                    CorruptLotDisposalReceiptError, match="receipt is corrupt"
                ) as rejected:
                    await SqlAlchemyCostBasisLotDisposalRepository(
                        restarted
                    ).reconcile_disposal_receipts(receipt_states=(candidate,))
                _assert_lineage_refusal(rejected.value, violation)
                await restarted.commit()
        async with session_factory() as reader:
            with pytest.raises(
                CorruptLotDisposalReadModelError, match="chain is corrupt"
            ) as rejected_read:
                await QueryLotDisposalRepository(reader).get_latest_receipt(
                    portfolio_id=states[-1].portfolio_id,
                    transaction_id=states[-1].disposal_transaction_id,
                )
            _assert_lineage_refusal(rejected_read.value, violation)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert statements and set(statements) == {"SELECT"}
    assert await _disposal_durable_snapshot(session_factory) == before


async def test_governed_history_survives_session_restart_and_replays_without_writes(
    clean_db,
    disposal_receipt_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    await _seed_unrelated_source_lot(async_db_session)
    assert async_db_session.bind is not None
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    original, corrected = _numerical_disposal_state(2), _numerical_disposal_state(3)
    for state in (original, corrected, _void_state(), corrected):
        async with session_factory() as writer:
            await SqlAlchemyCostBasisLotDisposalRepository(writer).reconcile_disposal_receipts(
                receipt_states=(state,)
            )
            await writer.commit()
    before = await _disposal_durable_snapshot(session_factory)
    async with session_factory() as restarted:
        await SqlAlchemyCostBasisLotDisposalRepository(restarted).reconcile_disposal_receipts(
            receipt_states=(corrected,)
        )
        await restarted.commit()
    async with session_factory() as reader:
        records = list(
            (
                await reader.scalars(
                    select(LotDisposalReceiptRecord).order_by(
                        LotDisposalReceiptRecord.receipt_version
                    )
                )
            ).all()
        )
        assert [row.status for row in records] == ["ACTIVE", "ACTIVE", "VOIDED", "ACTIVE"]
        assert [row.receipt_version for row in records] == [1, 2, 3, 4]
        assert (
            records[0].consumed_quantity,
            records[0].consumed_cost_local,
            records[0].consumed_cost_base,
        ) == (Decimal(2), Decimal(20), Decimal(24))
        receipt = await QueryLotDisposalRepository(reader).get_latest_receipt(
            portfolio_id=corrected.portfolio_id,
            transaction_id=corrected.disposal_transaction_id,
        )
        assert receipt is not None
        assert receipt[0].receipt_version == 4
        assert (
            receipt[0].consumed_quantity,
            receipt[0].consumed_cost_local,
            receipt[0].consumed_cost_base,
        ) == (Decimal(3), Decimal(30), Decimal(36))
    assert await _disposal_durable_snapshot(session_factory) == before


async def _seed_source_lot(session: AsyncSession) -> None:
    portfolio_id = "PORT-RECEIPT-DB-01"
    security_id = "SEC-RECEIPT-DB-01"
    buy = booked_transaction_event(
        transaction_id="BUY-RECEIPT-DB-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="10",
        gross_amount="100",
    )
    sell = booked_transaction_event(
        transaction_id="SELL-RECEIPT-DB-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="1",
        price="15",
        gross_amount="15",
    )
    session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name="Disposal Receipt Proof Instrument",
                isin="SG0000000601",
                currency="SGD",
            ),
            canonical_transaction_record(buy),
            canonical_transaction_record(sell),
        ]
    )
    await session.flush()
    session.add(
        PositionLotState(
            lot_id="LOT-RECEIPT-DB-01",
            source_transaction_id=buy.transaction_id,
            portfolio_id=portfolio_id,
            instrument_id=security_id,
            security_id=security_id,
            acquisition_date=date(2026, 1, 1),
            original_quantity=Decimal("10"),
            open_quantity=Decimal("9"),
            lot_cost_local=Decimal("90"),
            lot_cost_base=Decimal("90"),
            accrued_interest_paid_local=Decimal(0),
        )
    )
    await session.commit()


async def _seed_unrelated_source_lot(session: AsyncSession) -> None:
    portfolio_id = "PORT-RECEIPT-DB-OTHER"
    security_id = "SEC-RECEIPT-DB-OTHER"
    buy = booked_transaction_event(
        transaction_id="BUY-RECEIPT-DB-OTHER",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="5",
        price="20",
        gross_amount="100",
    )
    session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name="Unrelated Disposal Receipt Proof Instrument",
                isin="SG0000000602",
                currency="SGD",
            ),
            canonical_transaction_record(buy),
        ]
    )
    await session.flush()
    session.add(
        PositionLotState(
            lot_id="LOT-RECEIPT-DB-OTHER",
            source_transaction_id=buy.transaction_id,
            portfolio_id=portfolio_id,
            instrument_id=security_id,
            security_id=security_id,
            acquisition_date=date(2026, 1, 1),
            original_quantity=Decimal("5"),
            open_quantity=Decimal("5"),
            lot_cost_local=Decimal("100"),
            lot_cost_base=Decimal("100"),
            accrued_interest_paid_local=Decimal(0),
        )
    )
    await session.commit()


def _lineage(algorithm_id: str) -> CalculationLineage:
    return build_calculation_lineage(
        algorithm_id=algorithm_id,
        algorithm_version=1,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload={"transaction_id": "SELL-RECEIPT-DB-01"},
        output_payload={"cost": Decimal("10")},
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    )


def _active_state(*, cost_local: str) -> LotDisposalReceiptState:
    consumed_cost_local = Decimal(cost_local)
    allocation = SourceLotDisposalAllocation(
        source_lot_id="LOT-RECEIPT-DB-01",
        source_transaction_id="BUY-RECEIPT-DB-01",
        source_acquisition_date=date(2026, 1, 1),
        allocation_ordinal=1,
        consumed_quantity=Decimal("1"),
        consumed_cost_local=consumed_cost_local,
        consumed_cost_base=Decimal("10"),
    )
    disposal_lineage = build_calculation_lineage(
        algorithm_id=LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
        algorithm_version=LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=lot_disposal_lineage_input_payload(
            [lot_disposal_allocation_payload(allocation)]
        ),
        output_payload=lot_disposal_lineage_output_payload(
            consumed_cost_base=Decimal("10"),
            consumed_cost_local=consumed_cost_local,
            consumed_quantity=Decimal("1"),
        ),
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    )
    return LotDisposalReceiptState(
        disposal_transaction_id="SELL-RECEIPT-DB-01",
        portfolio_id="PORT-RECEIPT-DB-01",
        instrument_id="SEC-RECEIPT-DB-01",
        security_id="SEC-RECEIPT-DB-01",
        disposal_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
        transaction_type="SELL",
        cost_basis_method=CostBasisMethod.FIFO,
        calculation_policy_id="cost-basis-default",
        calculation_policy_version="1",
        transaction_calculation_lineage=_lineage("transaction-cost"),
        status=LotDisposalReceiptStatus.ACTIVE,
        consumed_quantity=Decimal("1"),
        consumed_cost_local=consumed_cost_local,
        consumed_cost_base=Decimal("10"),
        allocations=(allocation,),
        disposal_calculation_lineage=disposal_lineage,
    )


def _void_state() -> LotDisposalReceiptState:
    active = _active_state(cost_local="10")
    return LotDisposalReceiptState(
        disposal_transaction_id=active.disposal_transaction_id,
        portfolio_id=active.portfolio_id,
        instrument_id=active.instrument_id,
        security_id=active.security_id,
        disposal_timestamp=active.disposal_timestamp,
        transaction_type="BUY",
        cost_basis_method=active.cost_basis_method,
        calculation_policy_id=active.calculation_policy_id,
        calculation_policy_version=active.calculation_policy_version,
        transaction_calculation_lineage=_lineage("corrected-transaction-cost"),
        status=LotDisposalReceiptStatus.VOIDED,
        consumed_quantity=Decimal(0),
        consumed_cost_local=Decimal(0),
        consumed_cost_base=Decimal(0),
        allocations=(),
        disposal_calculation_lineage=None,
        void_reason="RECALCULATED_WITHOUT_LOT_DISPOSAL",
    )
