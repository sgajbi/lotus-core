from pathlib import Path

from scripts.position_reducer_boundary_guard import (
    find_position_reducer_boundary_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_boundary(root: Path) -> None:
    _write(
        root / "src/services/calculators/position_calculator/app/core/position_reducer.py",
        "class PositionBalanceState: pass\n"
        "class BackdatedReplayDecision: pass\n"
        "def calculate_next_position_state(): pass\n"
        "def plan_backdated_replay(): pass\n"
        "def cash_position_deltas(): pass\n",
    )
    _write(
        root / "src/services/calculators/position_calculator/app/core/position_logic.py",
        "calculate_next_position_state\n"
        "plan_backdated_replay\n"
        "PositionBalanceState\n"
        "EpochFencer\n"
        "OutboxRepository\n"
        "REPROCESSING_EPOCH_BUMPED_TOTAL\n",
    )


def test_position_reducer_boundary_guard_allows_split_boundary(tmp_path: Path) -> None:
    _write_required_boundary(tmp_path)

    assert find_position_reducer_boundary_findings(tmp_path) == []


def test_position_reducer_boundary_guard_rejects_runtime_coupling_in_reducer(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)
    _write(
        tmp_path / "src/services/calculators/position_calculator/app/core/position_reducer.py",
        "class PositionBalanceState: pass\n"
        "class BackdatedReplayDecision: pass\n"
        "def calculate_next_position_state(): pass\n"
        "def plan_backdated_replay(): pass\n"
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


def test_position_reducer_boundary_guard_rejects_legacy_reducer_logic_in_orchestrator(
    tmp_path: Path,
) -> None:
    _write_required_boundary(tmp_path)
    _write(
        tmp_path / "src/services/calculators/position_calculator/app/core/position_logic.py",
        "calculate_next_position_state\n"
        "plan_backdated_replay\n"
        "PositionBalanceState\n"
        "EpochFencer\n"
        "OutboxRepository\n"
        "REPROCESSING_EPOCH_BUMPED_TOTAL\n"
        "CASH_POSITION_DELTA_TRANSACTION_TYPES\n"
        "POSITION_TRANSFER_TRANSACTION_TYPES\n"
        "SAME_INSTRUMENT_CORPORATE_ACTION_TYPES\n"
        "def _cash_position_deltas(): pass\n"
        "def _buy_position_state(): pass\n"
        "def _sell_position_state(): pass\n"
        "def _transfer_position_state(): pass\n"
        "def _same_instrument_action_state(): pass\n"
        "def _needs_original_backdated_replay(): pass\n"
        "def _effective_completed_date(): pass\n",
    )

    findings = find_position_reducer_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "CASH_POSITION_DELTA_TRANSACTION_TYPES",
        "POSITION_TRANSFER_TRANSACTION_TYPES",
        "SAME_INSTRUMENT_CORPORATE_ACTION_TYPES",
        "def _cash_position_deltas",
        "def _buy_position_state",
        "def _sell_position_state",
        "def _transfer_position_state",
        "def _same_instrument_action_state",
        "def _needs_original_backdated_replay",
        "def _effective_completed_date",
    ]
