"""Protect domain-owned cashflow infrastructure package organization."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]


def test_cashflow_persistence_flat_paths_remain_retired() -> None:
    current_source = (
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "cashflow/persistence.py"
    )
    retired_paths = (
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "cashflow_repository.py",
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/cashflow/"
        "test_cashflow_repository.py",
    )

    assert current_source.is_file()
    assert all(not path.exists() for path in retired_paths)
