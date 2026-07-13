from types import SimpleNamespace

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)


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
