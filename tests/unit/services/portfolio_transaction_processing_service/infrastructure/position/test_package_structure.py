"""Protect domain-owned position infrastructure package organization."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]


def test_position_infrastructure_uses_domain_owned_packages() -> None:
    required_sources = (
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/position/"
        "processing.py",
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/position/"
        "history_repository.py",
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/position/"
        "recalculation_state.py",
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/position/"
        "observability.py",
    )
    retired_names = (
        "position_processing_adapter.py",
        "prometheus_position_history_observer.py",
        "sqlalchemy_position_history_repository.py",
        "sqlalchemy_position_recalculation_state_store.py",
    )
    retired_sources = tuple(
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure"
        / name
        for name in retired_names
    )
    retired_tests = (
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/"
        "test_position_processing_adapter.py",
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/position/"
        "test_sqlalchemy_position_history_repository.py",
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/position/"
        "test_position_recalculation_adapters.py",
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/position/"
        "test_prometheus_position_history_observer.py",
    )

    assert all(path.is_file() for path in required_sources)
    assert all(not path.exists() for path in (*retired_sources, *retired_tests))
