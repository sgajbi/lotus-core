from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

POSITION_LOGIC_MODULE = Path(
    "src/services/calculators/position_calculator/app/core/position_logic.py"
)
POSITION_REDUCER_MODULE = Path(
    "src/services/calculators/position_calculator/app/core/position_reducer.py"
)

REQUIRED_REDUCER_SNIPPETS = (
    "class PositionBalanceState",
    "class BackdatedReplayDecision",
    "def calculate_next_position_state",
    "def plan_backdated_replay",
    "def cash_position_deltas",
)
FORBIDDEN_REDUCER_SNIPPETS = {
    "AsyncSession": "pure position reducers must not depend on database sessions",
    "PositionRepository": "pure position reducers must not depend on repositories",
    "PositionStateRepository": "pure position reducers must not depend on repositories",
    "OutboxRepository": "pure position reducers must not stage outbox events",
    "EpochFencer": "pure position reducers must not own epoch-fencing orchestration",
    "REPROCESSING_EPOCH_BUMPED_TOTAL": "pure position reducers must not emit metrics",
    "correlation_id_var": "pure position reducers must not read request lineage context",
    "PositionHistory": "pure position reducers must not depend on persistence models",
    "TransactionEvent": "pure position reducers must not depend on event DTOs",
    "BaseModel": "pure position reducers must not depend on Pydantic DTOs",
    "sqlalchemy": "pure position reducers must not import SQLAlchemy",
}
REQUIRED_LOGIC_SNIPPETS = (
    "calculate_next_position_state",
    "plan_backdated_replay",
    "PositionBalanceState",
    "EpochFencer",
    "OutboxRepository",
    "REPROCESSING_EPOCH_BUMPED_TOTAL",
)
FORBIDDEN_LOGIC_SNIPPETS = {
    "CASH_POSITION_DELTA_TRANSACTION_TYPES": (
        "position transaction type policy belongs in position_reducer.py"
    ),
    "POSITION_TRANSFER_TRANSACTION_TYPES": (
        "position transaction type policy belongs in position_reducer.py"
    ),
    "SAME_INSTRUMENT_CORPORATE_ACTION_TYPES": (
        "position transaction type policy belongs in position_reducer.py"
    ),
    "def _cash_position_deltas": "cash reducer helpers belong in position_reducer.py",
    "def _buy_position_state": "buy reducer helpers belong in position_reducer.py",
    "def _sell_position_state": "sell reducer helpers belong in position_reducer.py",
    "def _transfer_position_state": "transfer reducer helpers belong in position_reducer.py",
    "def _same_instrument_action_state": (
        "corporate-action reducer helpers belong in position_reducer.py"
    ),
    "def _needs_original_backdated_replay": (
        "backdated replay decisions belong in position_reducer.py"
    ),
    "def _effective_completed_date": "effective-date planning belongs in position_reducer.py",
}


@dataclass(frozen=True, slots=True)
class PositionReducerBoundaryFinding:
    path: str
    snippet: str
    reason: str


def find_position_reducer_boundary_findings(
    root: Path,
) -> list[PositionReducerBoundaryFinding]:
    findings: list[PositionReducerBoundaryFinding] = []
    findings.extend(
        _required_snippet_findings(
            root=root,
            relative_path=POSITION_REDUCER_MODULE,
            snippets=REQUIRED_REDUCER_SNIPPETS,
        )
    )
    findings.extend(
        _forbidden_snippet_findings(
            root=root,
            relative_path=POSITION_REDUCER_MODULE,
            snippets=FORBIDDEN_REDUCER_SNIPPETS,
        )
    )
    findings.extend(
        _required_snippet_findings(
            root=root,
            relative_path=POSITION_LOGIC_MODULE,
            snippets=REQUIRED_LOGIC_SNIPPETS,
        )
    )
    findings.extend(
        _forbidden_snippet_findings(
            root=root,
            relative_path=POSITION_LOGIC_MODULE,
            snippets=FORBIDDEN_LOGIC_SNIPPETS,
        )
    )
    return findings


def _required_snippet_findings(
    *,
    root: Path,
    relative_path: Path,
    snippets: tuple[str, ...],
) -> list[PositionReducerBoundaryFinding]:
    path = root / relative_path
    if not path.exists():
        return [
            PositionReducerBoundaryFinding(
                path=relative_path.as_posix(),
                snippet="<missing-file>",
                reason="required position reducer boundary file is missing",
            )
        ]
    source = path.read_text(encoding="utf-8")
    return [
        PositionReducerBoundaryFinding(
            path=relative_path.as_posix(),
            snippet=snippet,
            reason="required position reducer boundary snippet is missing",
        )
        for snippet in snippets
        if snippet not in source
    ]


def _forbidden_snippet_findings(
    *,
    root: Path,
    relative_path: Path,
    snippets: dict[str, str],
) -> list[PositionReducerBoundaryFinding]:
    path = root / relative_path
    if not path.exists():
        return []
    source = path.read_text(encoding="utf-8")
    return [
        PositionReducerBoundaryFinding(
            path=relative_path.as_posix(),
            snippet=snippet,
            reason=reason,
        )
        for snippet, reason in snippets.items()
        if snippet in source
    ]


def main() -> int:
    findings = find_position_reducer_boundary_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Position reducer boundary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
