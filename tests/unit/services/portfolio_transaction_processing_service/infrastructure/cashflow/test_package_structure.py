"""Protect domain-owned cashflow infrastructure package organization."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]


def test_cashflow_infrastructure_uses_domain_owned_packages() -> None:
    required_sources = (
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "cashflow/persistence.py",
        REPOSITORY_ROOT / "src/services/portfolio_transaction_processing_service/app/application/"
        "cashflow_processing/use_case.py",
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/domain/cashflow/"
        "calculation.py",
        REPOSITORY_ROOT
        / "tests/unit/services/portfolio_transaction_processing_service/domain/cashflow/"
        "test_calculation.py",
        REPOSITORY_ROOT
        / "tests/unit/services/portfolio_transaction_processing_service/domain/cashflow/"
        "test_settlement_and_transfer_policy.py",
    )
    retired_paths = (
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "cashflow_repository.py",
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/cashflow/"
        "test_cashflow_repository.py",
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "cashflow_staging_workflow.py",
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "cashflow_processing_adapter.py",
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/cashflow/"
        "test_cashflow_staging_workflow.py",
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/"
        "test_cashflow_processing_adapter.py",
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "cashflow_calculation.py",
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/cashflow/"
        "test_cashflow_calculation.py",
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/cashflow/"
        "test_cashflow_domain_policy.py",
    )

    assert all(path.is_file() for path in required_sources)
    assert all(not path.exists() for path in retired_paths)
