from types import SimpleNamespace

from portfolio_common.ca_bundle_a_ordering import ca_bundle_a_dependency_rank


def test_ca_bundle_a_dependency_rank_normalizes_transaction_type() -> None:
    assert ca_bundle_a_dependency_rank(SimpleNamespace(transaction_type=" spin_off ")) == 0
    assert ca_bundle_a_dependency_rank(SimpleNamespace(transaction_type=" demerger_in ")) == 1
    assert (
        ca_bundle_a_dependency_rank(SimpleNamespace(transaction_type=" cash_consideration ")) == 2
    )


def test_ca_bundle_a_dependency_rank_leaves_unknown_types_last() -> None:
    assert ca_bundle_a_dependency_rank(SimpleNamespace(transaction_type=" spin_off_reversal ")) == 4
