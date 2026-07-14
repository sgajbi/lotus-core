"""Test deterministic ordering within linked corporate-action groups."""

from pathlib import Path
from types import SimpleNamespace

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)

REPO_ROOT = Path(__file__).resolve().parents[7]
SERVICE_TEST_ROOT = REPO_ROOT / "tests/unit/services/portfolio_transaction_processing_service"
TARGET_TEST = SERVICE_TEST_ROOT / "domain/transaction/corporate_action/test_ordering.py"
RETIRED_TEST = SERVICE_TEST_ROOT / "transaction/test_corporate_action_ordering.py"


def test_corporate_action_ordering_is_owned_by_domain_family() -> None:
    assert Path(__file__).resolve() == TARGET_TEST.resolve()
    assert not RETIRED_TEST.exists()


def test_corporate_action_dependency_rank_normalizes_transaction_type() -> None:
    assert (
        corporate_action.corporate_action_dependency_rank(
            SimpleNamespace(transaction_type=" spin_off ")
        )
        == 0
    )
    assert (
        corporate_action.corporate_action_dependency_rank(
            SimpleNamespace(transaction_type=" demerger_in ")
        )
        == 1
    )
    assert (
        corporate_action.corporate_action_dependency_rank(
            SimpleNamespace(transaction_type=" cash_consideration ")
        )
        == 2
    )


def test_corporate_action_dependency_rank_leaves_unknown_types_last() -> None:
    assert (
        corporate_action.corporate_action_dependency_rank(
            SimpleNamespace(transaction_type=" spin_off_reversal ")
        )
        == 4
    )
