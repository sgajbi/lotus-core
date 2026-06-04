from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import Transaction

from src.services.query_service.app.services.transaction_reads import (
    read_realized_tax_evidence,
    read_transaction_ledger_page,
)

pytestmark = pytest.mark.asyncio


def _ledger_filters() -> dict[str, object]:
    return {
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 1, 31),
    }


async def test_read_transaction_ledger_page_skips_page_read_for_empty_window() -> None:
    repository = AsyncMock()
    repository.get_transactions_count.return_value = 0

    page = await read_transaction_ledger_page(
        repository=repository,
        ledger_filters=_ledger_filters(),
        skip=0,
        limit=10,
        sort_by="transaction_date",
        sort_order="desc",
    )

    assert page.total_count == 0
    assert page.rows == []
    assert page.latest_evidence_timestamp is None
    repository.get_transactions.assert_not_awaited()
    repository.get_latest_evidence_timestamp.assert_not_awaited()


async def test_read_transaction_ledger_page_uses_page_rows_for_complete_window_evidence() -> None:
    repository = AsyncMock()
    repository.get_transactions_count.return_value = 2
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
    )

    assert page.total_count == 2
    assert [row.transaction_id for row in page.rows] == ["T1", "T2"]
    assert page.latest_evidence_timestamp == datetime(2025, 1, 16, 9, 0, tzinfo=UTC)
    repository.get_latest_evidence_timestamp.assert_not_awaited()


async def test_read_transaction_ledger_page_reads_global_evidence_for_partial_window() -> None:
    repository = AsyncMock()
    repository.get_transactions_count.return_value = 25
    repository.get_transactions.return_value = [
        Transaction(
            transaction_id="T1",
            updated_at=datetime(2025, 1, 15, 9, 0, tzinfo=UTC),
        )
    ]
    repository.get_latest_evidence_timestamp.return_value = datetime(2025, 1, 20, 9, 0, tzinfo=UTC)
    ledger_filters = _ledger_filters()

    page = await read_transaction_ledger_page(
        repository=repository,
        ledger_filters=ledger_filters,
        skip=10,
        limit=10,
        sort_by="transaction_date",
        sort_order="desc",
    )

    assert page.total_count == 25
    assert page.latest_evidence_timestamp == datetime(2025, 1, 20, 9, 0, tzinfo=UTC)
    repository.get_transactions.assert_awaited_once_with(
        skip=10,
        limit=10,
        sort_by="transaction_date",
        sort_order="desc",
        **ledger_filters,
    )
    repository.get_latest_evidence_timestamp.assert_awaited_once_with(**ledger_filters)


async def test_read_transaction_ledger_page_reads_global_evidence_for_short_page() -> None:
    repository = AsyncMock()
    repository.get_transactions_count.return_value = 2
    repository.get_transactions.return_value = [
        Transaction(
            transaction_id="T1",
            updated_at=datetime(2025, 1, 15, 9, 0, tzinfo=UTC),
        )
    ]
    repository.get_latest_evidence_timestamp.return_value = datetime(2025, 1, 20, 9, 0, tzinfo=UTC)
    ledger_filters = _ledger_filters()

    page = await read_transaction_ledger_page(
        repository=repository,
        ledger_filters=ledger_filters,
        skip=0,
        limit=10,
        sort_by=None,
        sort_order="desc",
    )

    assert page.total_count == 2
    assert page.latest_evidence_timestamp == datetime(2025, 1, 20, 9, 0, tzinfo=UTC)
    repository.get_latest_evidence_timestamp.assert_awaited_once_with(**ledger_filters)


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

    async def get_transactions_count(**_: object) -> int:
        call_order.append("count")
        return 2

    async def list_realized_tax_evidence_transactions(**_: object) -> list[Transaction]:
        call_order.append("tax_evidence")
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
    repository.get_transactions_count.assert_awaited_once_with(**ledger_filters)
    repository.list_realized_tax_evidence_transactions.assert_awaited_once_with(**ledger_filters)


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
