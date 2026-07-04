from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPLAY_MODULE = Path("src/libs/portfolio-common/portfolio_common/reprocessing_replay.py")
REPOSITORY_MODULE = Path("src/libs/portfolio-common/portfolio_common/reprocessing_repository.py")

REQUIRED_REPLAY_SNIPPETS = (
    "class TransactionReplayReader",
    "class TransactionReplayPublisher",
    "class ReplayCorrelationMetadata",
    "def ordered_unique_transaction_ids",
    "def plan_transaction_replay",
    "def publish_transaction_replay_plan",
)
FORBIDDEN_REPLAY_SNIPPETS = {
    "AsyncSession": "pure replay planning must not depend on SQLAlchemy sessions",
    "KafkaProducer": "pure replay planning must not depend on Kafka producers",
    "correlation_id_var": "pure replay planning must receive correlation metadata explicitly",
    "publish_message(": "Kafka publication belongs in the publisher adapter",
    ".execute(": "database reads belong in the reader adapter",
}
REQUIRED_REPOSITORY_SNIPPETS = (
    "class SqlAlchemyTransactionReplayReader",
    "class KafkaTransactionReplayPublisher",
    "plan_transaction_replay",
    "publish_transaction_replay_plan",
)
FORBIDDEN_REPOSITORY_SNIPPETS = {
    "TransactionEvent": "event payload planning belongs in reprocessing_replay.py",
    "_ordered_unique_transaction_ids": (
        "ordered replay deduplication belongs in reprocessing_replay.py"
    ),
    "_correlation_headers": "correlation header construction belongs in ReplayCorrelationMetadata",
}


@dataclass(frozen=True, slots=True)
class TransactionReplayBoundaryFinding:
    path: str
    snippet: str
    reason: str


def find_transaction_replay_boundary_findings(
    root: Path,
) -> list[TransactionReplayBoundaryFinding]:
    findings: list[TransactionReplayBoundaryFinding] = []
    findings.extend(
        _required_snippet_findings(
            root=root,
            relative_path=REPLAY_MODULE,
            snippets=REQUIRED_REPLAY_SNIPPETS,
        )
    )
    findings.extend(
        _forbidden_snippet_findings(
            root=root,
            relative_path=REPLAY_MODULE,
            snippets=FORBIDDEN_REPLAY_SNIPPETS,
        )
    )
    findings.extend(
        _required_snippet_findings(
            root=root,
            relative_path=REPOSITORY_MODULE,
            snippets=REQUIRED_REPOSITORY_SNIPPETS,
        )
    )
    findings.extend(
        _forbidden_snippet_findings(
            root=root,
            relative_path=REPOSITORY_MODULE,
            snippets=FORBIDDEN_REPOSITORY_SNIPPETS,
        )
    )
    return findings


def _required_snippet_findings(
    *,
    root: Path,
    relative_path: Path,
    snippets: tuple[str, ...],
) -> list[TransactionReplayBoundaryFinding]:
    path = root / relative_path
    if not path.exists():
        return [
            TransactionReplayBoundaryFinding(
                path=relative_path.as_posix(),
                snippet="<missing-file>",
                reason="required transaction replay boundary file is missing",
            )
        ]
    source = path.read_text(encoding="utf-8")
    return [
        TransactionReplayBoundaryFinding(
            path=relative_path.as_posix(),
            snippet=snippet,
            reason="required transaction replay boundary snippet is missing",
        )
        for snippet in snippets
        if snippet not in source
    ]


def _forbidden_snippet_findings(
    *,
    root: Path,
    relative_path: Path,
    snippets: dict[str, str],
) -> list[TransactionReplayBoundaryFinding]:
    path = root / relative_path
    if not path.exists():
        return []
    source = path.read_text(encoding="utf-8")
    return [
        TransactionReplayBoundaryFinding(
            path=relative_path.as_posix(),
            snippet=snippet,
            reason=reason,
        )
        for snippet, reason in snippets.items()
        if snippet in source
    ]


def main() -> int:
    findings = find_transaction_replay_boundary_findings(Path.cwd())
    if findings:
        for finding in findings:
            print(f"{finding.path}: {finding.snippet}: {finding.reason}")
        return 1
    print("Transaction replay boundary guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
