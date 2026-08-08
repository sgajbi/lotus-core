"""PostgreSQL proof for immutable lot basis-transfer receipt version chains."""

from __future__ import annotations

import runpy
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import (
    LotBasisTransferAllocationRecord,
    LotBasisTransferReceiptRecord,
    PositionLotState,
)
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.domain.cost_basis_receipt_integrity import (
    BASIS_TRANSFER_LINEAGE_ALGORITHM_ID,
    BASIS_TRANSFER_LINEAGE_ALGORITHM_VERSION,
    basis_transfer_lineage_input_payload,
    basis_transfer_lineage_output_payload,
)
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1
from sqlalchemy import event, func, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LotBasisTransferReceiptState,
    LotBasisTransferReceiptStatus,
    LotBasisTransferReconciliationScope,
    SourceLotBasisTransferAllocation,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    CorruptLotBasisTransferReceiptError,
    SqlAlchemyCostBasisLotBasisTransferRepository,
)
from src.services.query_service.app.repositories.lot_basis_transfer_repository import (
    CorruptLotBasisTransferReadModelError,
)
from src.services.query_service.app.repositories.lot_basis_transfer_repository import (
    LotBasisTransferRepository as QueryLotBasisTransferRepository,
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
    / "c146b2c3d513_feat_add_lot_basis_transfer_receipts.py"
)
REDEMPTION_TERMS_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c145b2c3d512_feat_add_redemption_terms.py"
)
CARRY_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "c144b2c3d511_fix_separate_amortized_book_carry.py"
)


@pytest.fixture
def basis_transfer_receipt_schema(clean_db, db_engine) -> None:
    """Apply the branch migration when the cached integration image predates it."""

    with db_engine.begin() as connection:
        schema = inspect(connection)
        operations = Operations(MigrationContext.configure(connection))
        lot_columns = {column["name"] for column in schema.get_columns("position_lot_state")}
        if "amortized_book_carrying_local" not in lot_columns:
            carry_migration = runpy.run_path(str(CARRY_MIGRATION))
            carry_migration["upgrade"].__globals__["op"] = operations
            carry_migration["upgrade"]()
        transaction_columns = {column["name"] for column in schema.get_columns("transactions")}
        if "redemption_price_type" not in transaction_columns:
            redemption_migration = runpy.run_path(str(REDEMPTION_TERMS_MIGRATION))
            redemption_migration["upgrade"].__globals__["op"] = operations
            redemption_migration["upgrade"]()
        if not schema.has_table("lot_basis_transfer_receipts"):
            migration = runpy.run_path(str(MIGRATION))
            migration["upgrade"].__globals__["op"] = operations
            migration["upgrade"]()


async def test_repository_preserves_retry_correction_void_and_reactivation_history(
    clean_db,
    basis_transfer_receipt_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyCostBasisLotBasisTransferRepository(async_db_session)
    first = _active_state(transferred_local="25")
    corrected = _active_state(transferred_local="30")

    await repository.reconcile_basis_transfer_receipts(
        reconciliation_scopes=(_scope(),), receipt_states=(first,)
    )
    await repository.reconcile_basis_transfer_receipts(
        reconciliation_scopes=(_scope(),), receipt_states=(first,)
    )
    await repository.reconcile_basis_transfer_receipts(
        reconciliation_scopes=(_scope(),), receipt_states=(corrected,)
    )
    await repository.reconcile_basis_transfer_receipts(
        reconciliation_scopes=(_scope(transaction_type="ADJUSTMENT"),), receipt_states=()
    )
    await repository.reconcile_basis_transfer_receipts(
        reconciliation_scopes=(_scope(),), receipt_states=(corrected,)
    )
    await async_db_session.commit()

    receipts = list(
        (
            await async_db_session.scalars(
                select(LotBasisTransferReceiptRecord).order_by(
                    LotBasisTransferReceiptRecord.receipt_version
                )
            )
        ).all()
    )
    allocations = list(
        (
            await async_db_session.scalars(
                select(LotBasisTransferAllocationRecord).order_by(
                    LotBasisTransferAllocationRecord.receipt_version
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
    assert receipts[0].target_transaction_id == "DEMERGER-IN-DB-01"


async def test_repository_detects_tampered_child_after_restart(
    clean_db,
    basis_transfer_receipt_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    state = _active_state(transferred_local="25")
    await SqlAlchemyCostBasisLotBasisTransferRepository(
        async_db_session
    ).reconcile_basis_transfer_receipts(reconciliation_scopes=(_scope(),), receipt_states=(state,))
    await async_db_session.commit()
    await async_db_session.execute(
        update(LotBasisTransferAllocationRecord).values(allocation_content_hash="0" * 64)
    )
    await async_db_session.commit()

    with pytest.raises(
        CorruptLotBasisTransferReceiptError,
        match="persisted lot basis-transfer receipt is corrupt",
    ):
        await SqlAlchemyCostBasisLotBasisTransferRepository(
            async_db_session
        ).reconcile_basis_transfer_receipts(
            reconciliation_scopes=(_scope(),), receipt_states=(state,)
        )


@pytest.mark.lifecycle
async def test_repository_verifies_sixty_four_transfer_versions_with_two_reads(
    clean_db,
    basis_transfer_receipt_schema,
    async_db_session: AsyncSession,
) -> None:
    await _seed_source_lot(async_db_session)
    repository = SqlAlchemyCostBasisLotBasisTransferRepository(async_db_session)
    states = tuple(_active_state(transferred_local=f"25.{version:02}") for version in range(1, 65))
    for state in states:
        await repository.reconcile_basis_transfer_receipts(
            reconciliation_scopes=(_scope(),),
            receipt_states=(state,),
        )
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
        if statement.lstrip().upper().startswith("SELECT") and "lot_basis_transfer_" in statement:
            statements.append(statement)

    assert async_db_session.bind is not None
    sync_engine = async_db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", record_statement)
    try:
        await repository.reconcile_basis_transfer_receipts(
            reconciliation_scopes=(_scope(),),
            receipt_states=(states[-1],),
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", record_statement)

    assert len(statements) == 2
    assert "lot_basis_transfer_receipts" in statements[0]
    assert "lot_basis_transfer_allocations" in statements[1]
    assert (
        await async_db_session.scalar(
            select(func.count()).select_from(LotBasisTransferReceiptRecord)
        )
        == 64
    )

    statements.clear()
    event.listen(sync_engine, "before_cursor_execute", record_statement)
    try:
        receipt = await QueryLotBasisTransferRepository(async_db_session).get_latest_receipt(
            portfolio_id=states[-1].portfolio_id,
            source_transaction_id=states[-1].source_transaction_id,
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", record_statement)
    assert receipt is not None
    assert receipt[0].receipt_version == 64
    assert len(statements) == 2

    await async_db_session.execute(
        update(LotBasisTransferAllocationRecord)
        .where(LotBasisTransferAllocationRecord.receipt_version == 32)
        .values(allocation_content_hash="0" * 64)
    )
    await async_db_session.commit()
    with pytest.raises(CorruptLotBasisTransferReceiptError, match="receipt is corrupt"):
        await repository.reconcile_basis_transfer_receipts(
            reconciliation_scopes=(_scope(),),
            receipt_states=(states[-1],),
        )
    with pytest.raises(CorruptLotBasisTransferReadModelError, match="chain is corrupt"):
        await QueryLotBasisTransferRepository(async_db_session).get_latest_receipt(
            portfolio_id=states[-1].portfolio_id,
            source_transaction_id=states[-1].source_transaction_id,
        )


async def _seed_source_lot(session: AsyncSession) -> None:
    portfolio_id = "PORT-BASIS-TRANSFER-DB-01"
    security_id = "SEC-BASIS-TRANSFER-DB-01"
    buy = booked_transaction_event(
        transaction_id="BUY-BASIS-TRANSFER-DB-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="10",
        gross_amount="100",
    )
    source = booked_transaction_event(
        transaction_id="DEMERGER-OUT-DB-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        transaction_type="DEMERGER_OUT",
        quantity="0",
        price="0",
        gross_amount="25",
    )
    session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name="Basis Transfer Proof Instrument",
                isin="SG0000000602",
                currency="SGD",
            ),
            canonical_transaction_record(buy),
            canonical_transaction_record(source),
        ]
    )
    await session.flush()
    session.add(
        PositionLotState(
            lot_id="LOT-BASIS-TRANSFER-DB-01",
            source_transaction_id=buy.transaction_id,
            portfolio_id=portfolio_id,
            instrument_id=security_id,
            security_id=security_id,
            acquisition_date=date(2026, 1, 1),
            original_quantity=Decimal("10"),
            open_quantity=Decimal("10"),
            lot_cost_local=Decimal("75"),
            lot_cost_base=Decimal("90"),
            accrued_interest_paid_local=Decimal(0),
        )
    )
    await session.commit()


def _lineage(algorithm_id: str) -> CalculationLineage:
    return build_calculation_lineage(
        algorithm_id=algorithm_id,
        algorithm_version=1,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload={"transaction_id": "DEMERGER-OUT-DB-01"},
        output_payload={"cost": Decimal("25")},
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    )


def _scope(*, transaction_type: str = "DEMERGER_OUT") -> LotBasisTransferReconciliationScope:
    return LotBasisTransferReconciliationScope(
        source_transaction_id="DEMERGER-OUT-DB-01",
        portfolio_id="PORT-BASIS-TRANSFER-DB-01",
        source_instrument_id="SEC-BASIS-TRANSFER-DB-01",
        source_security_id="SEC-BASIS-TRANSFER-DB-01",
        transfer_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        cost_basis_method=CostBasisMethod.FIFO,
        calculation_policy_id="cost-basis-default",
        calculation_policy_version="1",
        transaction_calculation_lineage=_lineage("current-transaction-cost"),
    )


def _active_state(*, transferred_local: str) -> LotBasisTransferReceiptState:
    transferred = Decimal(transferred_local)
    allocation = SourceLotBasisTransferAllocation(
        allocation_ordinal=1,
        source_lot_id="LOT-BASIS-TRANSFER-DB-01",
        source_transaction_id="BUY-BASIS-TRANSFER-DB-01",
        source_acquisition_date=date(2026, 1, 1),
        retained_quantity=Decimal("10"),
        source_cost_local_before=Decimal("100"),
        source_cost_base_before=Decimal("120"),
        transferred_cost_local=transferred,
        transferred_cost_base=Decimal("30"),
        retained_cost_local=Decimal("100") - transferred,
        retained_cost_base=Decimal("90"),
    )
    transfer_lineage = build_calculation_lineage(
        algorithm_id=BASIS_TRANSFER_LINEAGE_ALGORITHM_ID,
        algorithm_version=BASIS_TRANSFER_LINEAGE_ALGORITHM_VERSION,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=basis_transfer_lineage_input_payload((allocation,)),
        output_payload=basis_transfer_lineage_output_payload(
            (allocation,),
            transferred_cost_base=Decimal("30"),
            transferred_cost_local=transferred,
        ),
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    )
    return LotBasisTransferReceiptState(
        source_transaction_id="DEMERGER-OUT-DB-01",
        target_transaction_id="DEMERGER-IN-DB-01",
        target_lot_id="LOT-DEMERGER-IN-DB-01",
        portfolio_id="PORT-BASIS-TRANSFER-DB-01",
        source_instrument_id="SEC-BASIS-TRANSFER-DB-01",
        source_security_id="SEC-BASIS-TRANSFER-DB-01",
        target_instrument_id="TARGET-INSTRUMENT-DB-01",
        transfer_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
        transaction_type="DEMERGER_OUT",
        cost_basis_method=CostBasisMethod.FIFO,
        calculation_policy_id="cost-basis-default",
        calculation_policy_version="1",
        transaction_calculation_lineage=_lineage("transaction-cost"),
        status=LotBasisTransferReceiptStatus.ACTIVE,
        transferred_cost_local=transferred,
        transferred_cost_base=Decimal("30"),
        allocations=(allocation,),
        basis_transfer_calculation_lineage=transfer_lineage,
    )
