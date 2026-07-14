"""Protect transaction-readiness package ownership after compatibility retirement."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]


def test_transaction_readiness_uses_layer_owned_packages() -> None:
    required_sources = (
        REPOSITORY_ROOT / "src/services/portfolio_transaction_processing_service/app/application/"
        "transaction_readiness/registration.py",
        REPOSITORY_ROOT / "src/services/portfolio_transaction_processing_service/app/ports/"
        "transaction_readiness.py",
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "transaction_readiness/stage_repository.py",
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "transaction_readiness/event_staging.py",
    )
    retired_paths = (
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "pipeline_stage_processing_adapter.py",
        REPOSITORY_ROOT
        / "src/services/portfolio_transaction_processing_service/app/infrastructure/"
        "transaction_stage_repository.py",
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/"
        "test_pipeline_stage_processing_adapter.py",
    )

    assert all(path.is_file() for path in required_sources)
    assert all(not path.exists() for path in retired_paths)
