"""Protect booked transaction replay infrastructure ownership."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]


def test_booked_transaction_replay_uses_domain_owned_package() -> None:
    source_root = (
        REPOSITORY_ROOT / "src/services/portfolio_transaction_processing_service/app/infrastructure"
    )
    root_exports = (source_root / "__init__.py").read_text(encoding="utf-8")

    assert (source_root / "transaction_replay/booked_transaction.py").is_file()
    assert not (source_root / "transaction_replay_adapter.py").exists()
    assert not (
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/"
        "test_transaction_replay_adapter.py"
    ).exists()
    assert "SqlAlchemyBookedTransactionReplayAdapter" not in root_exports
    assert "CanonicalTransactionReplayer" not in root_exports
