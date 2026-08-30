from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import Transaction

from src.services.query_service.app.application.transaction_query import (
    TransactionLedgerFilters,
    TransactionLedgerInputEvidence,
    transaction_ledger_query_spec,
)
from src.services.query_service.app.services.transaction_reads import (
    read_exact_transaction_ledger_record,
    read_realized_tax_evidence,
    read_transaction_ledger_page,
)

pytestmark = pytest.mark.asyncio


def _ledger_filters() -> TransactionLedgerFilters:
    return TransactionLedgerFilters(
        portfolio_id="P1",
        instrument_id="I1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )


def _input_evidence(
    transaction_count: int,
    latest_evidence_timestamp: datetime | None = None,
) -> TransactionLedgerInputEvidence:
    return TransactionLedgerInputEvidence(
        transaction_count=transaction_count,
        latest_evidence_timestamp=latest_evidence_timestamp,
        transaction_digest="transaction-digest" if transaction_count else None,
        transaction_cost_digest="cost-digest" if transaction_count else None,
        selected_cashflow_digest="cashflow-digest" if transaction_count else None,
        selected_fx_rate_digest=None,
    )


async def test_read_transaction_ledger_page_skips_page_read_for_empty_window() -> None:
    repository = AsyncMock()
    repository.get_transaction_ledger_input_evidence.return_value = _input_evidence(0)

    page = await read_transaction_ledger_page(
        repository=repository,
        ledger_filters=_ledger_filters(),
        skip=0,
        limit=10,
        sort_by="transaction_date",
        sort_order="desc",
        reporting_currency=None,
    )

    assert page.total_count == 0
    assert page.rows == []
    assert page.latest_evidence_timestamp is None
    repository.get_transactions.assert_not_awaited()
    repository.get_transaction_ledger_input_evidence.assert_awaited_once()


async def test_read_transaction_ledger_page_uses_page_rows_for_complete_window_evidence() -> None:
    repository = AsyncMock()
    repository.get_transaction_ledger_input_evidence.return_value = _input_evidence(
        2,
        datetime(2025, 1, 16, 9, 0, tzinfo=UTC),
    )
    repository.get_transactions.return_value = [
        Transaction(
            transaction_id="T1",
            updated_at=datetime(2025, 1, 15, 9, 0, tzinfo=UTC),
        ),
        Transaction(
            transaction_id="T2",
            updated_at=datetime(2025, 1, 16, 9, 0, tzinfo=UTC),
        ),
    ]

    page = await read_transaction_ledger_page(
        repository=repository,
        ledger_filters=_ledger_filters(),
        skip=0,
        limit=10,
        sort_by="transaction_date",
        sort_order="desc",
        reporting_currency=None,
    )

    assert page.total_count == 2
    assert [row.transaction_id for row in page.rows] == ["T1", "T2"]
    assert page.latest_evidence_timestamp == datetime(2025, 1, 16, 9, 0, tzinfo=UTC)
    assert page.input_evidence.transaction_digest == "transaction-digest"


async def test_read_transaction_ledger_page_reads_global_evidence_for_partial_window() -> None:
    repository = AsyncMock()
    repository.get_transaction_ledger_input_evidence.return_value = _input_evidence(
        25,
        datetime(2025, 1, 20, 9, 0, tzinfo=UTC),
    )
    repository.get_transactions.return_value = [
        Transaction(
            transaction_id="T1",
            updated_at=datetime(2025, 1, 15, 9, 0, tzinfo=UTC),
        )
    ]
    ledger_filters = _ledger_filters()
    expected_query_spec = transaction_ledger_query_spec(
        filters=ledger_filters,
        sort_by="transaction_date",
        sort_order="desc",
    )

    page = await read_transaction_ledger_page(
        repository=repository,
        ledger_filters=ledger_filters,
        skip=10,
        limit=10,
        sort_by="transaction_date",
        sort_order="desc",
        reporting_currency=None,
    )

    assert page.total_count == 25
    assert page.latest_evidence_timestamp == datetime(2025, 1, 20, 9, 0, tzinfo=UTC)
    repository.get_transactions.assert_awaited_once_with(
        skip=10,
        limit=10,
        query_spec=expected_query_spec,
    )
    repository.get_transaction_ledger_input_evidence.assert_awaited_once_with(
        filters=ledger_filters,
        reporting_currency=None,
        as_of_date=None,
    )


async def test_read_transaction_ledger_page_reads_global_evidence_for_short_page() -> None:
    repository = AsyncMock()
    repository.get_transaction_ledger_input_evidence.return_value = _input_evidence(
        2,
        datetime(2025, 1, 20, 9, 0, tzinfo=UTC),
    )
    repository.get_transactions.return_value = [
        Transaction(
            transaction_id="T1",
            updated_at=datetime(2025, 1, 15, 9, 0, tzinfo=UTC),
        )
    ]
    ledger_filters = _ledger_filters()

    page = await read_transaction_ledger_page(
        repository=repository,
        ledger_filters=ledger_filters,
        skip=0,
        limit=10,
        sort_by=None,
        sort_order="desc",
        reporting_currency=None,
    )

    assert page.total_count == 2
    assert page.latest_evidence_timestamp == datetime(2025, 1, 20, 9, 0, tzinfo=UTC)
    repository.get_transaction_ledger_input_evidence.assert_awaited_once()


async def test_exact_projected_record_resolves_trade_date_before_fx_evidence() -> None:
    call_order: list[str] = []
    repository = AsyncMock()
    projected_trade_date = date(2027, 6, 15)
    projected = Transaction(
        transaction_id="T-PROJECTED",
        transaction_date=datetime(2027, 6, 15, 9, 30, tzinfo=UTC),
        security_id="S1",
        updated_at=datetime(2026, 8, 30, 9, 30, tzinfo=UTC),
    )
    evidence = _input_evidence(1, projected.updated_at)

    async def get_transactions(**_: object) -> list[Transaction]:
        call_order.append("record")
        return [projected]

    async def get_input_evidence(**kwargs: object) -> TransactionLedgerInputEvidence:
        call_order.append("fx_evidence")
        assert kwargs["as_of_date"] == projected_trade_date
        assert kwargs["reporting_currency"] == "SGD"
        return evidence

    repository.get_transactions.side_effect = get_transactions
    repository.get_transaction_ledger_input_evidence.side_effect = get_input_evidence
    repository.list_known_instrument_security_ids.return_value = {"S1"}
    ledger_filters = TransactionLedgerFilters(
        portfolio_id="P1",
        transaction_id="T-PROJECTED",
        as_of_date=None,
    )

    page = await read_exact_transaction_ledger_record(
        repository=repository,
        ledger_filters=ledger_filters,
        reporting_currency="SGD",
    )

    assert page.rows == [projected]
    assert page.evidence_as_of_date == projected_trade_date
    assert page.input_evidence is evidence
    assert call_order == ["record", "fx_evidence"]
    repository.get_transactions.assert_awaited_once_with(
        query_spec=transaction_ledger_query_spec(
            filters=ledger_filters,
            sort_by=None,
            sort_order="desc",
        ),
        skip=0,
        limit=2,
    )


async def test_read_realized_tax_evidence_reads_count_and_tax_rows_sequentially() -> None:
    call_order: list[str] = []
    repository = AsyncMock()
    tax_transactions = [
        Transaction(
            transaction_id="TAX-1",
            updated_at=datetime(2025, 1, 15, 9, 0, tzinfo=UTC),
        ),
        Transaction(
            transaction_id="TAX-2",
            updated_at=datetime(2025, 1, 16, 9, 0, tzinfo=UTC),
        ),
    ]

    async def get_transactions_count(*, filters: TransactionLedgerFilters) -> int:
        call_order.append("count")
        assert filters == ledger_filters
        return 2

    async def list_realized_tax_evidence_transactions(
        *,
        filters: TransactionLedgerFilters,
    ) -> list[Transaction]:
        call_order.append("tax_evidence")
        assert filters == ledger_filters
        return tax_transactions

    repository.get_transactions_count.side_effect = get_transactions_count
    repository.list_realized_tax_evidence_transactions.side_effect = (
        list_realized_tax_evidence_transactions
    )
    ledger_filters = _ledger_filters()

    evidence = await read_realized_tax_evidence(
        repository=repository,
        ledger_filters=ledger_filters,
    )

    assert evidence.source_transaction_count == 2
    assert evidence.tax_transactions == tax_transactions
    assert evidence.latest_evidence_timestamp == datetime(2025, 1, 16, 9, 0, tzinfo=UTC)
    assert call_order == ["count", "tax_evidence"]
    repository.get_transactions_count.assert_awaited_once_with(filters=ledger_filters)
    repository.list_realized_tax_evidence_transactions.assert_awaited_once_with(
        filters=ledger_filters
    )


async def test_read_realized_tax_evidence_reports_empty_evidence_timestamp() -> None:
    repository = AsyncMock()
    repository.get_transactions_count.return_value = 3
    repository.list_realized_tax_evidence_transactions.return_value = []

    evidence = await read_realized_tax_evidence(
        repository=repository,
        ledger_filters=_ledger_filters(),
    )

    assert evidence.source_transaction_count == 3
    assert evidence.tax_transactions == []
    assert evidence.latest_evidence_timestamp is None
