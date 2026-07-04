from pathlib import Path

from scripts.transaction_replay_boundary_guard import (
    find_transaction_replay_boundary_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_required_replay_boundary(root: Path) -> None:
    _write(
        root / "src/libs/portfolio-common/portfolio_common/reprocessing_replay.py",
        "class TransactionReplayReader: pass\n"
        "class TransactionReplayPublisher: pass\n"
        "class ReplayCorrelationMetadata: pass\n"
        "def ordered_unique_transaction_ids(): pass\n"
        "def plan_transaction_replay(): pass\n"
        "def publish_transaction_replay_plan(): pass\n",
    )
    _write(
        root / "src/libs/portfolio-common/portfolio_common/reprocessing_repository.py",
        "class SqlAlchemyTransactionReplayReader: pass\n"
        "class KafkaTransactionReplayPublisher: pass\n"
        "plan_transaction_replay\n"
        "publish_transaction_replay_plan\n",
    )


def test_transaction_replay_boundary_guard_allows_split_replay_boundary(
    tmp_path: Path,
) -> None:
    _write_required_replay_boundary(tmp_path)

    assert find_transaction_replay_boundary_findings(tmp_path) == []


def test_transaction_replay_boundary_guard_rejects_concrete_runtime_in_pure_replay(
    tmp_path: Path,
) -> None:
    _write_required_replay_boundary(tmp_path)
    _write(
        tmp_path / "src/libs/portfolio-common/portfolio_common/reprocessing_replay.py",
        "class TransactionReplayReader: pass\n"
        "class TransactionReplayPublisher: pass\n"
        "class ReplayCorrelationMetadata: pass\n"
        "def ordered_unique_transaction_ids(): pass\n"
        "def plan_transaction_replay(): pass\n"
        "def publish_transaction_replay_plan(): pass\n"
        "AsyncSession\nKafkaProducer\ncorrelation_id_var\npublish_message(\n.execute(\n",
    )

    findings = find_transaction_replay_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "AsyncSession",
        "KafkaProducer",
        "correlation_id_var",
        "publish_message(",
        ".execute(",
    ]


def test_transaction_replay_boundary_guard_rejects_old_repository_planning(
    tmp_path: Path,
) -> None:
    _write_required_replay_boundary(tmp_path)
    _write(
        tmp_path / "src/libs/portfolio-common/portfolio_common/reprocessing_repository.py",
        "class SqlAlchemyTransactionReplayReader: pass\n"
        "class KafkaTransactionReplayPublisher: pass\n"
        "plan_transaction_replay\n"
        "publish_transaction_replay_plan\n"
        "TransactionEvent\n"
        "def _ordered_unique_transaction_ids(): pass\n"
        "def _correlation_headers(): pass\n",
    )

    findings = find_transaction_replay_boundary_findings(tmp_path)

    assert [finding.snippet for finding in findings] == [
        "TransactionEvent",
        "_ordered_unique_transaction_ids",
        "_correlation_headers",
    ]
