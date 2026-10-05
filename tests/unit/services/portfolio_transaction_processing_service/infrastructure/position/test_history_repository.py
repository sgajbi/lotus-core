"""Test SQLAlchemy mapping at the position-history repository boundary."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import PositionHistory, Transaction, TransactionCost
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain import (
    BookedTransaction,
    PositionHistoryRecord,
    build_transaction_correction_identity,
)
from src.services.portfolio_transaction_processing_service.app.domain.position.numeric_policy import (  # noqa: E501
    POSITION_HISTORY_LEDGER_OUTPUT_V1,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.transaction_repository import (  # noqa: E501
    project_derived_financial_transaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position.history_repository import (  # noqa: E501
    SqlAlchemyPositionHistoryRepository,
    _position_history_replay_lock_key,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    PositionMaterializationProgress,
    PositionReplayWindow,
)
from src.services.portfolio_transaction_processing_service.app.ports.position_history import (
    AdmittedPositionCorrectionGroup,
)


def _admitted_group(current, epoch=3):
    return AdmittedPositionCorrectionGroup(
        root_transaction=current,
        admission_identity=build_transaction_correction_identity(current),
        event_id="correction-event",
        repair_delivery_id=None,
        correction_claimed=True,
        repair_claimed=False,
        members=(current,),
        replay_epoch=epoch,
        active_transaction_id=current.transaction_id,
    )


@pytest.mark.parametrize(
    "damage",
    [
        "event",
        "identity",
        "root",
        "duplicate",
        "tenant",
        "portfolio",
        "forged",
        "epoch",
        "ordinary",
    ],
)
def test_group_refuses_invalid_root_and_cost_result_membership(damage):
    root = project_derived_financial_transaction(
        _correction_row(), tenant_id="tenant-test", cost_basis_method="FIFO"
    )
    group = _admitted_group(root)
    child = replace(root, transaction_id="CHILD", originating_transaction_id=root.transaction_id)
    changes = {
        "event": {"event_id": " "},
        "identity": {"admission_identity": build_transaction_correction_identity(child)},
        "root": {"members": (child,)},
        "duplicate": {"members": (root, root)},
        "tenant": {"members": (root, replace(child, tenant_id="other"))},
        "portfolio": {"members": (root, replace(child, portfolio_id="other"))},
        "forged": {"members": (root, replace(child, originating_transaction_id="HISTORY"))},
        "epoch": {"members": (root, replace(child, epoch=7))},
        "ordinary": {"correction_claimed": False, "repair_claimed": False},
    }
    with pytest.raises(ValueError, match="Admitted position group"):
        replace(group, **changes[damage])


@pytest.mark.asyncio
async def test_group_projects_only_members_present_in_bounded_window_in_original_order():
    parent_row, child_row, historical_row = (
        _correction_row(),
        _correction_row("CHILD"),
        _correction_row("HISTORY"),
    )
    child_row.originating_transaction_id = parent_row.transaction_id
    parent, child, historical = (
        project_derived_financial_transaction(
            row, tenant_id="tenant-test", cost_basis_method="FIFO"
        )
        for row in (parent_row, child_row, historical_row)
    )
    unrelated_security = replace(child, transaction_id="OTHER-SECURITY", security_id="OTHER")
    group = replace(
        _admitted_group(parent),
        members=(parent, child, unrelated_security),
        active_transaction_id=child.transaction_id,
    )
    repository = SqlAlchemyPositionHistoryRepository(AsyncMock(spec=AsyncSession))
    with patch(
        "src.services.portfolio_transaction_processing_service.app.infrastructure.position.history_repository.load_derived_financial_transactions",
        new_callable=AsyncMock,
    ) as qualify_history:
        qualify_history.return_value = (historical,)
        rows = [(child_row, "tenant-test", "FIFO"), (historical_row, "tenant-test", "FIFO")]
        assert await repository._project_replay_transactions(rows, admitted_correction=group) == (
            child,
            historical,
        )
        qualify_history.assert_awaited_once_with(repository._session, rows[1:])
        group.require_member(child)
        with pytest.raises(ValueError, match="exact admitted"):
            group.require_member(replace(child, net_cost=Decimal("123")))


def _correction_row(transaction_id="CORRECTION"):
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id="PB-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_type="MATURITY_REDEMPTION",
        quantity=Decimal("10"),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("10"),
        trade_currency="SGD",
        currency="SGD",
        trade_fee=Decimal("0"),
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        embedded_fee_amount_local=Decimal("10"),
        principal_proceeds_local=Decimal("10"),
        net_cost=Decimal("-9"),
        net_cost_local=Decimal("-9"),
        costs=[],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "tenant",
        "portfolio",
        "security",
        "material",
        "effects",
        "policy",
        "cashmode",
        "lineage",
        "missing",
        "empty",
        "duplicate",
    ],
)
async def test_admitted_current_correction_is_exact_and_leaves_history_qualified(damage):
    current_row, historical_row = _correction_row(), _correction_row("HISTORICAL")
    current = project_derived_financial_transaction(
        current_row,
        tenant_id="tenant-test",
        cost_basis_method="FIFO",
    )
    if damage in {"tenant", "portfolio", "security"}:
        field = {
            "tenant": "tenant_id",
            "portfolio": "portfolio_id",
            "security": "security_id",
        }[damage]
        current = replace(current, **{field: "foreign"})
    if damage == "material":
        current = replace(current, embedded_fee_amount_local=Decimal("11"))
    if damage == "effects":
        current = replace(current, net_cost=Decimal("-8"))
    if damage == "policy":
        current = replace(current, calculation_policy_id="CUSTOM_UNADMITTED_POLICY")
    if damage == "cashmode":
        current = replace(current, cash_entry_mode="EXTERNAL")
    if damage == "lineage":
        current = replace(current, calculation_lineage=_calculation_lineage())
    rows = [(historical_row, "tenant-test", "FIFO"), (current_row, "tenant-test", "FIFO")]
    if damage == "missing":
        rows.pop()
    if damage == "empty":
        rows.clear()
    if damage == "duplicate":
        rows.append(rows[-1])
    repository = SqlAlchemyPositionHistoryRepository(AsyncMock(spec=AsyncSession))
    with patch(
        "src.services.portfolio_transaction_processing_service.app.infrastructure.position.history_repository.load_derived_financial_transactions",
        new_callable=AsyncMock,
    ) as qualify_history:
        qualify_history.return_value = (replace(current, transaction_id="HISTORICAL"),)
        if damage is not None:
            with pytest.raises(ValueError, match="Admitted position"):
                await repository._project_replay_transactions(
                    rows,
                    admitted_correction=_admitted_group(current),
                )
            qualify_history.assert_not_awaited()
        else:
            projected = await repository._project_replay_transactions(
                rows,
                admitted_correction=_admitted_group(current),
            )
            assert projected[-1] == current
            qualify_history.assert_awaited_once_with(repository._session, rows[:1])


@pytest.mark.asyncio
async def test_current_admission_cannot_qualify_conflicting_historical_source():
    row = _correction_row()
    current = project_derived_financial_transaction(
        row, tenant_id="tenant-test", cost_basis_method="FIFO"
    )
    repository = SqlAlchemyPositionHistoryRepository(AsyncMock(spec=AsyncSession))
    with patch(
        "src.services.portfolio_transaction_processing_service.app.infrastructure.position.history_repository.load_derived_financial_transactions",
        new_callable=AsyncMock,
    ) as qualify_history:
        qualify_history.side_effect = ValueError("historical source qualification refused")
        rows = [
            (_correction_row("HISTORICAL"), "tenant-test", "FIFO"),
            (row, "tenant-test", "FIFO"),
        ]
        with pytest.raises(ValueError, match="historical source qualification refused"):
            await repository._project_replay_transactions(
                rows,
                admitted_correction=_admitted_group(current),
            )
        with pytest.raises(ValueError, match="historical source qualification refused"):
            await repository._project_replay_transactions(rows, admitted_correction=None)


@pytest.mark.asyncio
async def test_admitted_correction_cannot_cross_replay_epoch():
    row = _correction_row()
    current = project_derived_financial_transaction(
        row, tenant_id="tenant-test", cost_basis_method="FIFO"
    )
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyPositionHistoryRepository(session)
    with pytest.raises(ValueError, match="conflicting replay epoch"):
        await repository.load_replay_window(
            portfolio_id=current.portfolio_id,
            security_id=current.security_id,
            position_date=current.transaction_date.date(),
            epoch=4,
            admitted_correction=_admitted_group(current),
        )
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_admitted_generated_child_preserves_existing_effective_defaults():
    row = _correction_row()
    row.transaction_type = "INTEREST"
    row.principal_proceeds_local = None
    row.embedded_fee_amount_local = None
    current = replace(
        project_derived_financial_transaction(
            row, tenant_id="tenant-test", cost_basis_method="FIFO"
        ),
        cash_entry_mode=None,
        calculation_policy_id=None,
        calculation_policy_version=None,
    )
    repository = SqlAlchemyPositionHistoryRepository(AsyncMock(spec=AsyncSession))
    projected = await repository._project_replay_transactions(
        [(row, "tenant-test", "FIFO")],
        admitted_correction=_admitted_group(current),
    )
    assert projected == (current,)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "keys",
        "ratio",
        "delta",
        "nan",
        "nondecimal",
        "precision",
        "effects",
        "lineage",
        "type",
    ],
)
async def test_admitted_restatement_retains_only_valid_cost_result_context(damage):
    row = _correction_row()
    row.transaction_type = "SPLIT"
    row.quantity = Decimal("75")
    row.embedded_fee_amount_local = None
    row.principal_proceeds_local = None
    row.net_cost = row.net_cost_local = Decimal("0")
    context = {
        "quantity_before": Decimal("75"),
        "quantity_after": Decimal("150"),
        "factor_numerator": Decimal("150"),
        "factor_denominator": Decimal("75"),
    }
    current = replace(
        project_derived_financial_transaction(
            row, tenant_id="tenant-test", cost_basis_method="FIFO"
        ),
        lot_restatement=context,
    )
    if damage == "keys":
        context["unknown"] = Decimal("1")
    if damage == "ratio":
        context["factor_denominator"] = Decimal("74")
    if damage == "delta":
        context["quantity_after"] = context["factor_numerator"] = Decimal("151")
    if damage == "nan":
        context["quantity_before"] = Decimal("NaN")
    if damage == "nondecimal":
        context["factor_numerator"] = "150"
    if damage == "precision":
        context["quantity_before"] = Decimal("75.00000000001")
    if damage == "effects":
        current = replace(current, net_cost=Decimal("1"))
    if damage == "lineage":
        current = replace(current, calculation_lineage=_calculation_lineage())
    if damage == "type":
        row.transaction_type = "MATURITY_REDEMPTION"
        current = replace(current, transaction_type=row.transaction_type)
    repository = SqlAlchemyPositionHistoryRepository(AsyncMock(spec=AsyncSession))
    if damage is not None:
        with pytest.raises(ValueError):
            await repository._project_replay_transactions(
                [(row, "tenant-test", "FIFO")], admitted_correction=_admitted_group(current)
            )
    else:
        result = await repository._project_replay_transactions(
            [(row, "tenant-test", "FIFO")], admitted_correction=_admitted_group(current)
        )
        assert result == (current,)
        assert result[0].lot_restatement == context


def _calculation_lineage() -> CalculationLineage:
    return build_calculation_lineage(
        algorithm_id="position-history-state-transition",
        algorithm_version=1,
        intermediate_precision=POSITION_HISTORY_LEDGER_OUTPUT_V1.working_precision,
        input_payload={"transaction_id": "TX-001"},
        output_payload={"quantity": Decimal("10")},
        numeric_output_policy=POSITION_HISTORY_LEDGER_OUTPUT_V1.lineage_identity(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [None, "tenant", "epoch", "history", "quantity"])
async def test_materialized_receipt_requires_owned_locked_state_and_exact_history(missing) -> None:
    transaction = BookedTransaction(
        transaction_id="TX-001",
        tenant_id="tenant-test",
        portfolio_id="PB-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_type="BUY",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        quantity=Decimal("10"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("250"),
        trade_currency="SGD",
        currency="SGD",
    )
    row = PositionHistory(
        portfolio_id="PB-001",
        security_id="SEC-001",
        transaction_id="TX-001",
        position_date=date(2026, 4, 10),
        epoch=4,
        quantity=None if missing == "quantity" else Decimal("0"),
    )
    owner_result, state_result, history_result = MagicMock(), MagicMock(), MagicMock()
    owner_result.scalar_one_or_none.return_value = None if missing == "tenant" else "tenant-test"
    state_result.scalar_one_or_none.return_value = None if missing == "epoch" else 4
    history_result.scalars.return_value.one_or_none.return_value = (
        None if missing == "history" else row
    )
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [owner_result, state_result, history_result]
    repository = SqlAlchemyPositionHistoryRepository(session)
    with patch.object(repository, "acquire_replay_lock", new_callable=AsyncMock) as replay_lock:
        receipt = await repository.load_materialized_receipt(transaction, expected_epoch=4)
    if missing is not None:
        assert receipt is None
    else:
        assert receipt is not None
        assert (receipt.tenant_id, receipt.portfolio_id, receipt.security_id) == (
            "tenant-test",
            "PB-001",
            "SEC-001",
        )
        assert (receipt.transaction_id, receipt.epoch, receipt.quantity) == (
            "TX-001",
            4,
            Decimal("0"),
        )
    statements = [call.args[0] for call in session.execute.await_args_list]
    assert statements[0]._for_update_arg is not None
    assert statements[0].compile().params["tenant_id_1"] == "tenant-test"
    if missing == "tenant":
        assert len(statements) == 1
        replay_lock.assert_not_awaited()
        return
    assert statements[1]._for_update_arg is not None
    assert statements[1].compile().params["epoch_1"] == 4
    if missing == "epoch":
        assert len(statements) == 2
        replay_lock.assert_not_awaited()
        return
    replay_lock.assert_awaited_once_with(portfolio_id="PB-001", security_id="SEC-001", epoch=4)
    assert statements[2]._for_update_arg.read is True
    assert statements[2].compile().params == {
        "trim_1": "PB-001",
        "trim_2": "SEC-001",
        "trim_3": "TX-001",
        "epoch_1": 4,
        "position_date_1": date(2026, 4, 10),
    }


@pytest.mark.asyncio
async def test_list_all_transactions_maps_orm_rows_to_booked_transactions() -> None:
    session = AsyncMock(spec=AsyncSession)
    lineage = _calculation_lineage()
    row = Transaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("250"),
        trade_currency="SGD",
        currency="SGD",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        linked_component_ids=["LEG-1", "LEG-2"],
        dependency_reference_ids=["PARENT-1"],
        calculation_lineage=lineage.lineage_payload(),
    )
    result = MagicMock()
    result.unique.return_value.all.return_value = [(row, "tenant-test", "FIFO")]
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    transactions = await repository.list_all_transactions(
        portfolio_id=" PB-001 ",
        security_id=" SEC-001 ",
    )

    assert len(transactions) == 1
    assert transactions[0].transaction_id == "TX-001"
    assert transactions[0].linked_component_ids == ("LEG-1", "LEG-2")
    assert transactions[0].dependency_reference_ids == ("PARENT-1",)
    assert transactions[0].epoch is None
    assert transactions[0].calculation_lineage == lineage


@pytest.mark.asyncio
async def test_load_replay_window_maps_anchor_and_transactions_in_one_query() -> None:
    session = AsyncMock(spec=AsyncSession)
    anchor_row = PositionHistory(
        portfolio_id="PB-001",
        security_id="SEC-001",
        transaction_id="TX-001",
        position_date=date(2026, 4, 9),
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=None,
        epoch=2,
    )
    transaction_row = Transaction(
        transaction_id="TX-002",
        portfolio_id="PB-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_type="BUY",
        quantity=Decimal("5"),
        price=Decimal("20"),
        gross_transaction_amount=Decimal("100"),
        trade_fee=Decimal("99"),
        trade_currency="SGD",
        currency="SGD",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    result = MagicMock()
    transaction_row.costs = [
        TransactionCost(fee_type="BROKERAGE", amount=Decimal("1.25"), currency="SGD"),
        TransactionCost(fee_type="STAMP_DUTY", amount=Decimal("0.75"), currency="SGD"),
    ]
    result.unique.return_value.all.return_value = [
        (transaction_row, anchor_row, "tenant-test", "FIFO")
    ]
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    window = await repository.load_replay_window(
        portfolio_id="PB-001",
        security_id="SEC-001",
        position_date=date(2026, 4, 10),
        epoch=2,
    )

    assert window.anchor == PositionHistoryRecord(
        portfolio_id="PB-001",
        security_id="SEC-001",
        transaction_id="TX-001",
        position_date=date(2026, 4, 9),
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("0"),
        epoch=2,
    )
    assert tuple(item.transaction_id for item in window.transactions) == ("TX-002",)
    projected = window.transactions[0]
    assert projected.tenant_id == "tenant-test"
    assert projected.trade_fee == Decimal("99")
    assert projected.brokerage == Decimal("1.25")
    assert projected.stamp_duty == Decimal("0.75")
    assert projected.economic_event_id
    assert projected.linked_transaction_group_id
    assert transaction_row.trade_fee == Decimal("99")
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_replay_window_rehydrates_anchor_calculation_lineage() -> None:
    session = AsyncMock(spec=AsyncSession)
    lineage = _calculation_lineage()
    row = PositionHistory(
        portfolio_id="PB-001",
        security_id="SEC-001",
        transaction_id="TX-001",
        position_date=date(2026, 4, 9),
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("95"),
        epoch=2,
        calculation_lineage=lineage.lineage_payload(),
    )
    result = MagicMock()
    transaction_row = Transaction(
        transaction_id="TX-002",
        portfolio_id="PB-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_type="BUY",
        quantity=Decimal("5"),
        price=Decimal("20"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="SGD",
        currency="SGD",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    result.unique.return_value.all.return_value = [(transaction_row, row, "tenant-test", "FIFO")]
    session.execute.return_value = result

    window = await SqlAlchemyPositionHistoryRepository(session).load_replay_window(
        portfolio_id="PB-001",
        security_id="SEC-001",
        position_date=date(2026, 4, 10),
        epoch=2,
    )

    assert window.anchor is not None
    assert window.anchor.calculation_lineage == lineage


@pytest.mark.asyncio
async def test_save_records_maps_domain_records_without_eager_flush() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyPositionHistoryRepository(session)
    lineage = _calculation_lineage()
    record = PositionHistoryRecord(
        portfolio_id="PB-001",
        security_id="SEC-001",
        transaction_id="TX-001",
        position_date=date(2026, 4, 10),
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("95"),
        epoch=3,
        calculation_lineage=lineage,
    )

    await repository.save_records((record,))

    rows = session.add_all.call_args.args[0]
    assert len(rows) == 1
    assert isinstance(rows[0], PositionHistory)
    assert rows[0].portfolio_id == "PB-001"
    assert rows[0].transaction_id == "TX-001"
    assert rows[0].cost_basis_local == Decimal("95")
    assert rows[0].calculation_lineage == lineage.lineage_payload()
    session.flush.assert_not_awaited()


def test_repository_excludes_production_unused_legacy_reads() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyPositionHistoryRepository(session)

    assert not hasattr(repository, "find_open_security_ids_as_of")
    assert not hasattr(repository, "get_latest_business_date")
    assert not hasattr(repository, "get_transaction_by_id")


@pytest.mark.asyncio
async def test_load_materialization_progress_normalizes_position_key_in_one_query() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.one.return_value = (date(2026, 5, 27), date(2026, 5, 28))
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    progress = await repository.load_materialization_progress(
        portfolio_id=" PORT_COST_01 ", security_id=" SEC01 ", epoch=42
    )

    assert progress == PositionMaterializationProgress(
        latest_history_date=date(2026, 5, 27),
        latest_completed_snapshot_date=date(2026, 5, 28),
    )
    session.execute.assert_awaited_once()
    compiled_query = str(
        session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_history.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(position_history.security_id) = 'SEC01'" in compiled_query
    assert "position_history.epoch = 42" in compiled_query
    assert "trim(daily_position_snapshots.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(daily_position_snapshots.security_id) = 'SEC01'" in compiled_query
    assert "daily_position_snapshots.epoch = 42" in compiled_query


@pytest.mark.asyncio
async def test_acquire_replay_lock_uses_stable_normalized_key() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyPositionHistoryRepository(
        session,
        clock=MagicMock(side_effect=[10.0, 10.125]),
    )

    with patch(
        "src.services.portfolio_transaction_processing_service.app.infrastructure."
        "position.history_repository.observe_position_history_replay_lock_wait"
    ) as observe_wait:
        await repository.acquire_replay_lock(
            portfolio_id=" PORT_COST_01 ", security_id=" SEC01 ", epoch=42
        )

    statement = session.execute.call_args.args[0]
    assert str(statement) == "SELECT pg_advisory_xact_lock(:lock_key)"
    assert statement.compile().params == {
        "lock_key": _position_history_replay_lock_key("PORT_COST_01", "SEC01", 42)
    }
    assert _position_history_replay_lock_key(" PORT_COST_01 ", " SEC01 ", 42) == (
        _position_history_replay_lock_key("PORT_COST_01", "SEC01", 42)
    )
    observe_wait.assert_called_once_with(outcome="acquired", seconds=0.125)


@pytest.mark.asyncio
async def test_acquire_replay_lock_records_failure_without_swallowing() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = RuntimeError("lock unavailable")
    repository = SqlAlchemyPositionHistoryRepository(
        session,
        clock=MagicMock(side_effect=[20.0, 20.25]),
    )

    with (
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure."
            "position.history_repository.observe_position_history_replay_lock_wait"
        ) as observe_wait,
        pytest.raises(RuntimeError, match="lock unavailable"),
    ):
        await repository.acquire_replay_lock(portfolio_id="P1", security_id="S1", epoch=7)

    observe_wait.assert_called_once_with(outcome="failed", seconds=0.25)


@pytest.mark.asyncio
async def test_materialized_receipt_normalizes_lineage_and_position_key() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.side_effect = ["tenant-test", 7]
    result.scalars.return_value.one_or_none.return_value = PositionHistory(
        portfolio_id="PORT_COST_01",
        security_id="SEC01",
        transaction_id="TX01",
        position_date=date(2026, 4, 10),
        epoch=7,
        quantity=Decimal("0"),
    )
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    transaction = BookedTransaction(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        transaction_id=" TX01 ",
        instrument_id="INST01",
        tenant_id="tenant-test",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="SGD",
        currency="SGD",
    )
    with patch.object(repository, "acquire_replay_lock", new_callable=AsyncMock):
        materialized = await repository.load_materialized_receipt(transaction, expected_epoch=7)

    assert materialized is not None
    assert materialized.quantity == Decimal("0")
    compiled_query = str(
        session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_history.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(position_history.security_id) = 'SEC01'" in compiled_query
    assert "trim(position_history.transaction_id) = 'TX01'" in compiled_query
    assert "position_history.epoch = 7" in compiled_query
    assert "FOR UPDATE" in compiled_query


@pytest.mark.asyncio
async def test_load_replay_window_normalizes_key_and_orders_deterministically() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.unique.return_value.all.return_value = []
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    window = await repository.load_replay_window(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        position_date=date(2026, 5, 28),
        epoch=42,
    )

    assert window == PositionReplayWindow(anchor=None, transactions=())
    compiled_query = str(
        session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(transactions.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(transactions.security_id) = 'SEC01'" in compiled_query
    assert "transactions.transaction_date >= '2026-05-28 00:00:00+00:00'" in compiled_query
    assert "position_replay_anchor" in compiled_query
    assert "position_history.position_date < '2026-05-28'" in compiled_query
    assert "position_history.epoch = 42" in compiled_query
    assert (
        "ORDER BY transactions.transaction_date ASC, transactions.transaction_id ASC"
        in compiled_query
    )


@pytest.mark.asyncio
async def test_delete_records_from_normalizes_key_and_epoch() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.rowcount = 3
    session.execute.return_value = result
    repository = SqlAlchemyPositionHistoryRepository(session)

    deleted_count = await repository.delete_records_from(
        portfolio_id=" PORT_COST_01 ",
        security_id=" SEC01 ",
        position_date=date(2026, 5, 28),
        epoch=42,
    )

    assert deleted_count == 3
    compiled_query = str(
        session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_history.portfolio_id) = 'PORT_COST_01'" in compiled_query
    assert "trim(position_history.security_id) = 'SEC01'" in compiled_query
    assert "position_history.position_date >= '2026-05-28'" in compiled_query
    assert "position_history.epoch = 42" in compiled_query
