"""PostgreSQL proof for immutable lot-disposal receipt version chains."""

from __future__ import annotations

import runpy
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import (
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    PositionLotState,
)
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from sqlalchemy import event, func, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LotDisposalReceiptState,
    LotDisposalReceiptStatus,
    SourceLotDisposalAllocation,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    CorruptLotDisposalReceiptError,
    SqlAlchemyCostBasisLotDisposalRepository,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
    portfolio_record,
)

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

    await async_db_session.execute(
        update(LotDisposalAllocationRecord)
        .where(LotDisposalAllocationRecord.receipt_version == 32)
        .values(allocation_content_hash="0" * 64)
    )
    await async_db_session.commit()
    with pytest.raises(CorruptLotDisposalReceiptError, match="receipt is corrupt"):
        await repository.reconcile_disposal_receipts(receipt_states=(states[-1],))


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


def _lineage(algorithm_id: str) -> CalculationLineage:
    return build_calculation_lineage(
        algorithm_id=algorithm_id,
        algorithm_version=1,
        intermediate_precision=38,
        input_payload={"transaction_id": "SELL-RECEIPT-DB-01"},
        output_payload={"cost": Decimal("10")},
    )


def _active_state(*, cost_local: str) -> LotDisposalReceiptState:
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
        consumed_cost_local=Decimal(cost_local),
        consumed_cost_base=Decimal("10"),
        allocations=(
            SourceLotDisposalAllocation(
                source_lot_id="LOT-RECEIPT-DB-01",
                source_transaction_id="BUY-RECEIPT-DB-01",
                source_acquisition_date=date(2026, 1, 1),
                allocation_ordinal=1,
                consumed_quantity=Decimal("1"),
                consumed_cost_local=Decimal(cost_local),
                consumed_cost_base=Decimal("10"),
            ),
        ),
        disposal_calculation_lineage=_lineage("lot-disposal"),
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
