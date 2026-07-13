from pathlib import Path

from scripts.quality.position_reducer_boundary_guard import (
    find_position_reducer_boundary_findings,
)

POSITION_APPLICATION_PATH = (
    "src/services/portfolio_transaction_processing_service/app/application/position_history.py"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_boundary(root: Path) -> None:
    _write(
        root / POSITION_APPLICATION_PATH,
        "class PositionHistoryProcessor: pass\n"
        "PositionHistoryRepository\n"
        "PositionRecalculationStateStore\n"
        "PositionHistoryObserver\n"
        "build_position_history\n",
    )
    _write(
        root
        / "src/services/portfolio_transaction_processing_service/app/domain/position/reducer.py",
        "class PositionBalanceState: pass\n"
        "class BackdatedRecalculationDecision: pass\n"
        "def calculate_next_position_state(): pass\n"
        "def plan_backdated_recalculation(): pass\n"
        "def cash_position_deltas(): pass\n",
    )


def test_position_reducer_boundary_guard_allows_split_boundary(tmp_path: Path) -> None:
    _write_required_boundary(tmp_path)

    assert find_position_reducer_boundary_findings(tmp_path) == []


def test_position_reducer_boundary_guard_rejects_runtime_coupling_in_reducer(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)
    _write(
        tmp_path
        / "src/services/portfolio_transaction_processing_service/app/domain/position/reducer.py",
        "class PositionBalanceState: pass\n"
        "class BackdatedRecalculationDecision: pass\n"
        "def calculate_next_position_state(): pass\n"
        "def plan_backdated_recalculation(): pass\n"
        "def cash_position_deltas(): pass\n"
        "AsyncSession\n"
        "PositionRepository\n"
        "PositionStateRepository\n"
        "OutboxRepository\n"
        "EpochFencer\n"
        "REPROCESSING_EPOCH_BUMPED_TOTAL\n"
        "correlation_id_var\n"
        "PositionHistory\n"
        "TransactionEvent\n"
        "BaseModel\n"
        "sqlalchemy\n",
    )

    findings = find_position_reducer_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "AsyncSession",
        "PositionRepository",
        "PositionStateRepository",
        "OutboxRepository",
        "EpochFencer",
        "REPROCESSING_EPOCH_BUMPED_TOTAL",
        "correlation_id_var",
        "PositionHistory",
        "TransactionEvent",
        "BaseModel",
        "sqlalchemy",
    ]


def test_position_reducer_boundary_guard_rejects_flat_legacy_domain_module(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)
    _write(
        tmp_path
        / "src/services/portfolio_transaction_processing_service/app/domain/position_reducer.py",
        "legacy reducer\n",
    )

    findings = find_position_reducer_boundary_findings(tmp_path)

    assert [(finding.path, finding.snippet) for finding in findings] == [
        (
            "src/services/portfolio_transaction_processing_service/app/domain/position_reducer.py",
            "<legacy-position-domain-module>",
        )
    ]


def test_position_reducer_boundary_guard_rejects_legacy_infrastructure_modules(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)
    _write(
        tmp_path / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "position_calculation_workflow.py",
        "legacy workflow\n",
    )
    _write(
        tmp_path / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "position_repository.py",
        "legacy repository\n",
    )

    findings = find_position_reducer_boundary_findings(tmp_path)

    assert [(finding.path, finding.snippet) for finding in findings] == [
        (
            "src/services/portfolio_transaction_processing_service/app/infrastructure/"
            "position_calculation_workflow.py",
            "<legacy-position-infrastructure-module>",
        ),
        (
            "src/services/portfolio_transaction_processing_service/app/infrastructure/"
            "position_repository.py",
            "<legacy-position-infrastructure-module>",
        ),
    ]


def test_position_reducer_boundary_guard_rejects_runtime_coupling_in_application(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)
    application_path = tmp_path / POSITION_APPLICATION_PATH
    application_path.write_text(
        application_path.read_text(encoding="utf-8")
        + "AsyncSession\n"
        + "sqlalchemy\n"
        + "portfolio_common.database_models\n"
        + "TransactionEvent\n"
        + "PositionStateRepository\n"
        + "SqlAlchemyPositionHistoryRepository\n"
        + "PrometheusPositionHistoryObserver\n"
        + "import logging\n",
        encoding="utf-8",
    )

    findings = find_position_reducer_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "AsyncSession",
        "sqlalchemy",
        "portfolio_common.database_models",
        "TransactionEvent",
        "PositionStateRepository",
        "SqlAlchemyPositionHistoryRepository",
        "PrometheusPositionHistoryObserver",
        "import logging",
    ]
