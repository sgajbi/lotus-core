from datetime import date

import pytest

from src.services.query_service.app.application.transaction_query import (
    TransactionLedgerFilters,
    TransactionSortSpec,
    transaction_ledger_filters,
    transaction_ledger_query_spec,
)
from src.services.query_service.app.application.transaction_sorting import (
    TransactionSortValidationError,
)


def test_transaction_ledger_filters_capture_api_query_policy() -> None:
    filters = transaction_ledger_filters(
        portfolio_id="P1",
        instrument_id="I1",
        security_id=" S1 ",
        transaction_type="BUY",
        component_type="SECURITY_TRADE",
        linked_transaction_group_id="LTG-1",
        fx_contract_id="FXC-1",
        swap_event_id="SWAP-1",
        near_leg_group_id="NEAR-1",
        far_leg_group_id="FAR-1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        as_of_date=date(2025, 2, 1),
    )

    assert filters == TransactionLedgerFilters(
        portfolio_id="P1",
        instrument_id="I1",
        security_id=" S1 ",
        transaction_type="BUY",
        component_type="SECURITY_TRADE",
        linked_transaction_group_id="LTG-1",
        fx_contract_id="FXC-1",
        swap_event_id="SWAP-1",
        near_leg_group_id="NEAR-1",
        far_leg_group_id="FAR-1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        as_of_date=date(2025, 2, 1),
    )


def test_transaction_ledger_query_spec_normalizes_sort_before_repository_access() -> None:
    filters = TransactionLedgerFilters(portfolio_id="P1")

    query_spec = transaction_ledger_query_spec(
        filters=filters,
        sort_by=None,
        sort_order=None,
    )

    assert query_spec.filters is filters
    assert query_spec.sort == TransactionSortSpec(field="transaction_date", order="desc")


def test_transaction_ledger_query_spec_rejects_invalid_sort_before_sql_translation() -> None:
    with pytest.raises(TransactionSortValidationError, match="sort_by"):
        transaction_ledger_query_spec(
            filters=TransactionLedgerFilters(portfolio_id="P1"),
            sort_by="unsupported_field",
            sort_order="desc",
        )
