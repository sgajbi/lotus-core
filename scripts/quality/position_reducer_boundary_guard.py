from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

POSITION_APPLICATION_MODULE = Path(
    "src/services/portfolio_transaction_processing_service/app/application/position_history.py"
)
POSITION_REDUCER_MODULE = Path(
    "src/services/portfolio_transaction_processing_service/app/domain/position/reducer.py"
)
LEGACY_POSITION_DOMAIN_MODULES = (
    Path("src/services/portfolio_transaction_processing_service/app/domain/position_history.py"),
    Path("src/services/portfolio_transaction_processing_service/app/domain/position_reducer.py"),
)
LEGACY_POSITION_INFRASTRUCTURE_MODULES = (
    Path(
        "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "position_calculation_workflow.py"
    ),
    Path(
        "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "position_repository.py"
    ),
)

REQUIRED_REDUCER_SNIPPETS = (
    "class PositionBalanceState",
    "class BackdatedRecalculationDecision",
    "def calculate_next_position_state",
    "def plan_backdated_recalculation",
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
REQUIRED_APPLICATION_SNIPPETS = (
    "class PositionHistoryProcessor",
    "PositionHistoryRepository",
    "PositionRecalculationStateStore",
    "PositionHistoryObserver",
    "build_position_history",
)
FORBIDDEN_APPLICATION_SNIPPETS = {
    "AsyncSession": "position application policy must not depend on database sessions",
    "sqlalchemy": "position application policy must not import SQLAlchemy",
    "portfolio_common.database_models": (
        "position application policy must not depend on persistence models"
    ),
    "TransactionEvent": "position application policy must not depend on event DTOs",
    "PositionStateRepository": "position application policy must depend on its state-store port",
    "SqlAlchemyPositionHistoryRepository": (
        "position application policy must depend on its repository port"
    ),
    "PrometheusPositionHistoryObserver": (
        "position application policy must depend on its observer port"
    ),
    "import logging": "position application policy must observe through its port",
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
        PositionReducerBoundaryFinding(
            path=legacy_path.as_posix(),
            snippet="<legacy-position-domain-module>",
            reason="position domain code belongs in the domain/position package",
        )
        for legacy_path in LEGACY_POSITION_DOMAIN_MODULES
        if (root / legacy_path).exists()
    )
    findings.extend(
        _required_snippet_findings(
            root=root,
            relative_path=POSITION_APPLICATION_MODULE,
            snippets=REQUIRED_APPLICATION_SNIPPETS,
        )
    )
    findings.extend(
        _forbidden_snippet_findings(
            root=root,
            relative_path=POSITION_APPLICATION_MODULE,
            snippets=FORBIDDEN_APPLICATION_SNIPPETS,
        )
    )
    findings.extend(
        PositionReducerBoundaryFinding(
            path=legacy_path.as_posix(),
            snippet="<legacy-position-infrastructure-module>",
            reason="position orchestration and persistence use application ports and adapters",
        )
        for legacy_path in LEGACY_POSITION_INFRASTRUCTURE_MODULES
        if (root / legacy_path).exists()
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
