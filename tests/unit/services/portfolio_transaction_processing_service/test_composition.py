from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from portfolio_common.reprocessing_repository import ReprocessingRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    AverageCostPoolRebuildPlanner,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER,
    PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER,
    PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    CanonicalBookedTransactionReplayerFactory,
    CashflowCalculationWorkflow,
    CostCalculationWorkflow,
    SqlAlchemyAverageCostPoolReconciliationAdapter,
    SqlAlchemyBookedTransactionReplayAdapter,
    SqlAlchemyTransactionProcessingUnitOfWork,
    SqlAlchemyTransactionProcessingUnitOfWorkFactory,
    build_process_transaction_use_case,
    build_reconcile_average_cost_pools_use_case,
    build_replay_booked_transaction_use_case,
)


def test_composition_reuses_plain_workflows_and_creates_unit_of_work_per_message() -> None:
    session_factory = MagicMock(spec=lambda: AsyncSession())
    cost_workflow = CostCalculationWorkflow()
    cashflow_workflow = CashflowCalculationWorkflow()
    factory = SqlAlchemyTransactionProcessingUnitOfWorkFactory(
        session_factory=session_factory,
        cost_workflow=cost_workflow,
        cashflow_workflow=cashflow_workflow,
    )

    first = factory()
    second = factory()

    assert isinstance(first, SqlAlchemyTransactionProcessingUnitOfWork)
    assert isinstance(second, SqlAlchemyTransactionProcessingUnitOfWork)
    assert first is not second
    assert first._cost_workflow is second._cost_workflow is cost_workflow
    assert first._cashflow_workflow is second._cashflow_workflow is cashflow_workflow
    assert not hasattr(cost_workflow, "_consumer_config")
    assert not hasattr(cashflow_workflow, "_consumer_config")


def test_target_infrastructure_does_not_import_legacy_cost_delivery() -> None:
    infrastructure_root = Path(
        "src/services/portfolio_transaction_processing_service/app/infrastructure"
    )

    for source_path in infrastructure_root.rglob("*.py"):
        source = source_path.read_text(encoding="utf-8")
        assert "cost_calculator_service.app.consumer" not in source


def test_target_infrastructure_does_not_import_legacy_cashflow_delivery() -> None:
    infrastructure_root = Path(
        "src/services/portfolio_transaction_processing_service/app/infrastructure"
    )

    for source_path in infrastructure_root.rglob("*.py"):
        source = source_path.read_text(encoding="utf-8")
        assert "cashflow_calculator_service.app.consumers" not in source


def test_use_case_builder_accepts_repository_standard_session_factory() -> None:
    session_factory = MagicMock(spec=lambda: AsyncSession())

    use_case = build_process_transaction_use_case(session_factory=session_factory)

    unit_of_work = use_case._unit_of_work_factory()
    assert isinstance(unit_of_work, SqlAlchemyTransactionProcessingUnitOfWork)
    assert unit_of_work._session_factory is session_factory
    assert use_case._observer is PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER
    assert (
        use_case._unit_of_work_factory.cost_workflow._cost_basis_persistence_observer
        is PROMETHEUS_COST_BASIS_PERSISTENCE_OBSERVER
    )


def test_replay_use_case_builder_composes_canonical_repository_dependencies() -> None:
    session_factory = MagicMock(spec=lambda: AsyncSession())
    kafka_producer = MagicMock()

    use_case = build_replay_booked_transaction_use_case(
        session_factory=session_factory,
        kafka_producer=kafka_producer,
    )

    replay_adapter = use_case._replay
    assert isinstance(replay_adapter, SqlAlchemyBookedTransactionReplayAdapter)
    assert replay_adapter.session_factory is session_factory
    assert use_case._observer is PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER
    assert isinstance(
        replay_adapter.replayer_factory,
        CanonicalBookedTransactionReplayerFactory,
    )
    session = MagicMock(spec=AsyncSession)
    replayer = replay_adapter.replayer_factory(session)
    assert isinstance(replayer, ReprocessingRepository)
    assert replayer.db is session
    assert replayer.kafka_producer is kafka_producer


def test_average_cost_reconciliation_builder_uses_target_application_boundary() -> None:
    session_factory = MagicMock(spec=lambda: AsyncSession())

    use_case = build_reconcile_average_cost_pools_use_case(
        session_factory=session_factory,
    )

    assert isinstance(
        use_case._reconciliation,
        SqlAlchemyAverageCostPoolReconciliationAdapter,
    )
    assert use_case._reconciliation._session_factory is session_factory
    assert isinstance(
        use_case._reconciliation._rebuild_planner,
        AverageCostPoolRebuildPlanner,
    )
    assert (
        use_case._reconciliation._rebuild_planner._observer
        is PROMETHEUS_COST_BASIS_CALCULATION_OBSERVER
    )
