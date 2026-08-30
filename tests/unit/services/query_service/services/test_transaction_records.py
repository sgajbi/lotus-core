from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import Cashflow, Transaction, TransactionCost
from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN

from src.services.query_service.app.application.transaction_query import (
    TransactionLedgerFilters,
    TransactionLedgerInputEvidence,
)
from src.services.query_service.app.dtos.transaction_dto import TransactionRecord
from src.services.query_service.app.services.transaction_records import (
    _transaction_ledger_qualifiers,
    exact_transaction_record_response,
    paginated_transaction_ledger_response,
    transaction_record_from_row,
    transaction_records_from_rows,
)

pytestmark = pytest.mark.asyncio


def _ledger_filters(**overrides) -> TransactionLedgerFilters:
    values = {
        "portfolio_id": "P1",
        "as_of_date": date(2025, 1, 15),
    }
    values.update(overrides)
    return TransactionLedgerFilters(**values)


def _input_evidence(
    *,
    transaction_count: int,
    latest_evidence_timestamp: datetime | None,
    transaction_digest: str | None = "transaction-digest",
    transaction_cost_digest: str | None = "cost-digest",
    selected_cashflow_digest: str | None = "cashflow-digest",
    selected_fx_rate_digest: str | None = "fx-digest",
) -> TransactionLedgerInputEvidence:
    return TransactionLedgerInputEvidence(
        transaction_count=transaction_count,
        latest_evidence_timestamp=latest_evidence_timestamp,
        transaction_digest=transaction_digest,
        transaction_cost_digest=transaction_cost_digest,
        selected_cashflow_digest=selected_cashflow_digest,
        selected_fx_rate_digest=selected_fx_rate_digest,
    )


async def test_transaction_record_from_row_preserves_costs_and_cashflow() -> None:
    row = Transaction(
        transaction_id="T-CASHFLOW",
        transaction_date=datetime(2025, 1, 10),
        transaction_type="DEPOSIT",
        instrument_id="CASH",
        security_id="CASH",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("5000"),
        currency="USD",
        costs=[
            TransactionCost(
                transaction_id="T-CASHFLOW",
                fee_type="BROKERAGE",
                amount=Decimal("2.50"),
                currency="USD",
            )
        ],
        cashflow=Cashflow(
            amount=Decimal("5000"),
            currency="USD",
            classification="CASHFLOW_IN",
            timing="BOD",
            calculation_type="NET",
            is_position_flow=True,
            is_portfolio_flow=True,
        ),
    )

    record = transaction_record_from_row(row)

    assert isinstance(record, TransactionRecord)
    assert record.transaction_id == "T-CASHFLOW"
    assert len(record.costs) == 1
    assert record.costs[0].fee_type == "BROKERAGE"
    assert record.cashflow is not None
    assert record.cashflow.amount == Decimal("5000")
    assert record.cashflow.is_portfolio_flow is True


async def test_transaction_records_from_rows_applies_reporting_currency_in_row_order() -> None:
    rows = [
        Transaction(
            transaction_id="T1",
            transaction_date=datetime(2025, 1, 10),
            transaction_type="BUY",
            instrument_id="I1",
            security_id="S1",
            quantity=Decimal("10"),
            price=Decimal("100"),
            gross_transaction_amount=Decimal("1000"),
            currency="USD",
        ),
        Transaction(
            transaction_id="T2",
            transaction_date=datetime(2025, 1, 11),
            transaction_type="SELL",
            instrument_id="I2",
            security_id="S2",
            quantity=Decimal("5"),
            price=Decimal("50"),
            gross_transaction_amount=Decimal("250"),
            currency="EUR",
        ),
    ]
    call_order: list[str] = []
    convert_amount = AsyncMock(return_value=Decimal("1"))

    async def apply_reporting_currency_fields(
        *,
        record: TransactionRecord,
        reporting_currency: str,
        as_of_date: date,
        convert_amount: object,
    ) -> None:
        call_order.append(record.transaction_id)
        assert reporting_currency == "SGD"
        assert as_of_date == date(2025, 1, 15)
        assert convert_amount is expected_convert_amount

    expected_convert_amount = convert_amount
    with patch(
        "src.services.query_service.app.services.transaction_records.apply_transaction_reporting_currency_fields",
        new_callable=AsyncMock,
    ) as apply_transaction_reporting_currency_fields:
        apply_transaction_reporting_currency_fields.side_effect = apply_reporting_currency_fields

        records = await transaction_records_from_rows(
            rows=rows,
            reporting_currency="SGD",
            as_of_date=date(2025, 1, 15),
            convert_amount=convert_amount,
        )

    assert [record.transaction_id for record in records] == ["T1", "T2"]
    assert call_order == ["T1", "T2"]
    assert apply_transaction_reporting_currency_fields.await_count == 2


async def test_transaction_records_from_rows_skips_reporting_currency_without_context() -> None:
    row = Transaction(
        transaction_id="T1",
        transaction_date=datetime(2025, 1, 10),
        transaction_type="BUY",
        instrument_id="I1",
        security_id="S1",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        currency="USD",
    )

    with patch(
        "src.services.query_service.app.services.transaction_records.apply_transaction_reporting_currency_fields",
        new_callable=AsyncMock,
    ) as apply_transaction_reporting_currency_fields:
        records = await transaction_records_from_rows(
            rows=[row],
            reporting_currency="SGD",
            as_of_date=None,
            convert_amount=AsyncMock(),
        )

    assert [record.transaction_id for record in records] == ["T1"]
    apply_transaction_reporting_currency_fields.assert_not_awaited()


def _transaction_record(transaction_id: str) -> TransactionRecord:
    return TransactionRecord(
        transaction_id=transaction_id,
        transaction_date=datetime(2025, 1, 10),
        transaction_type="BUY",
        instrument_id="I1",
        security_id="S1",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        currency="USD",
    )


async def test_paginated_transaction_ledger_response_marks_complete_window() -> None:
    latest_evidence_timestamp = datetime(2025, 1, 16, 9, 30, tzinfo=UTC)

    response = paginated_transaction_ledger_response(
        portfolio_id="P1",
        reporting_currency="SGD",
        total_count=2,
        skip=0,
        limit=10,
        transactions=[_transaction_record("T1"), _transaction_record("T2")],
        effective_as_of_date=date(2025, 1, 15),
        end_date=date(2025, 1, 31),
        latest_evidence_timestamp=latest_evidence_timestamp,
        ledger_filters=_ledger_filters(end_date=date(2025, 1, 31)),
        input_evidence=_input_evidence(
            transaction_count=2,
            latest_evidence_timestamp=latest_evidence_timestamp,
        ),
    )

    assert response.product_name == "TransactionLedgerWindow"
    assert response.product_version == "v1"
    assert response.portfolio_id == "P1"
    assert response.reporting_currency == "SGD"
    assert response.total == 2
    assert response.skip == 0
    assert response.limit == 10
    assert [transaction.transaction_id for transaction in response.transactions] == ["T1", "T2"]
    assert response.as_of_date == date(2025, 1, 15)
    assert response.data_quality_status == COMPLETE
    assert response.latest_evidence_timestamp == latest_evidence_timestamp
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("rs_")
    assert response.policy_version == "transaction-ledger-window-v1"
    assert response.source_batch_fingerprint is None
    assert response.source_lineage["reconstruction_scope_id"] == response.snapshot_id
    assert response.source_lineage["reconstruction_restatement_version"] == "current"
    assert response.reason_codes == ["TRANSACTION_LEDGER_READY"]
    assert response.missing_instrument_reference_count == 0
    assert response.missing_instrument_security_ids == []


async def test_exact_transaction_record_response_binds_identity_and_product_proof() -> None:
    latest_evidence_timestamp = datetime(2025, 1, 16, 9, 30, tzinfo=UTC)
    filters = _ledger_filters(transaction_id="T1")

    response = exact_transaction_record_response(
        portfolio_id="P1",
        reporting_currency="SGD",
        transaction=_transaction_record("T1"),
        effective_as_of_date=date(2025, 1, 15),
        latest_evidence_timestamp=latest_evidence_timestamp,
        ledger_filters=filters,
        input_evidence=_input_evidence(
            transaction_count=1,
            latest_evidence_timestamp=latest_evidence_timestamp,
        ),
    )

    assert response.product_name == "TransactionLedgerWindow"
    assert response.portfolio_id == "P1"
    assert response.reporting_currency == "SGD"
    assert response.transaction.transaction_id == "T1"
    assert response.data_quality_status == COMPLETE
    assert response.reason_codes == ["TRANSACTION_LEDGER_READY"]
    assert response.snapshot_id is not None
    assert response.source_refs == [
        "lotus-core://source/TransactionLedgerWindow/P1/2025-01-15/transactions/T1"
    ]
    assert response.source_lineage["reconstruction_scope_id"] == response.snapshot_id


async def test_paginated_transaction_ledger_response_marks_partial_window() -> None:
    response = paginated_transaction_ledger_response(
        portfolio_id="P1",
        reporting_currency=None,
        total_count=25,
        skip=10,
        limit=10,
        transactions=[_transaction_record("T11")],
        effective_as_of_date=date(2025, 1, 15),
        end_date=None,
        latest_evidence_timestamp=None,
        ledger_filters=_ledger_filters(),
        input_evidence=_input_evidence(
            transaction_count=25,
            latest_evidence_timestamp=None,
        ),
    )

    assert response.data_quality_status == PARTIAL
    assert response.as_of_date == date(2025, 1, 15)
    assert response.reason_codes == ["TRANSACTION_LEDGER_PAGE_PARTIAL"]


async def test_transaction_ledger_response_marks_missing_instrument_reference_partial() -> None:
    response = paginated_transaction_ledger_response(
        portfolio_id="P1",
        reporting_currency=None,
        total_count=2,
        skip=0,
        limit=10,
        transactions=[_transaction_record("T1"), _transaction_record("T2")],
        effective_as_of_date=date(2025, 1, 15),
        end_date=None,
        latest_evidence_timestamp=None,
        ledger_filters=_ledger_filters(),
        input_evidence=_input_evidence(
            transaction_count=2,
            latest_evidence_timestamp=None,
        ),
        missing_instrument_security_ids=["S2"],
    )

    assert response.data_quality_status == PARTIAL
    assert response.reason_codes == ["TRANSACTION_LEDGER_INSTRUMENT_REFERENCE_MISSING"]
    assert response.missing_instrument_reference_count == 1
    assert response.missing_instrument_security_ids == ["S2"]


async def test_paginated_transaction_ledger_response_uses_end_date_then_today_fallback() -> None:
    end_date_response = paginated_transaction_ledger_response(
        portfolio_id="P1",
        reporting_currency=None,
        total_count=0,
        skip=0,
        limit=10,
        transactions=[],
        effective_as_of_date=None,
        end_date=date(2025, 1, 31),
        latest_evidence_timestamp=None,
        ledger_filters=_ledger_filters(as_of_date=None, end_date=date(2025, 1, 31)),
        input_evidence=_input_evidence(
            transaction_count=0,
            latest_evidence_timestamp=None,
            transaction_digest=None,
            transaction_cost_digest=None,
            selected_cashflow_digest=None,
            selected_fx_rate_digest=None,
        ),
        today=lambda: date(2025, 2, 1),
    )
    today_response = paginated_transaction_ledger_response(
        portfolio_id="P1",
        reporting_currency=None,
        total_count=0,
        skip=0,
        limit=10,
        transactions=[],
        effective_as_of_date=None,
        end_date=None,
        latest_evidence_timestamp=None,
        ledger_filters=_ledger_filters(as_of_date=None),
        input_evidence=_input_evidence(
            transaction_count=0,
            latest_evidence_timestamp=None,
            transaction_digest=None,
            transaction_cost_digest=None,
            selected_cashflow_digest=None,
            selected_fx_rate_digest=None,
        ),
        today=lambda: date(2025, 2, 1),
    )

    assert end_date_response.as_of_date == date(2025, 1, 31)
    assert today_response.as_of_date == date(2025, 2, 1)
    assert end_date_response.data_quality_status == UNKNOWN
    assert today_response.data_quality_status == UNKNOWN
    assert end_date_response.reason_codes == ["TRANSACTION_LEDGER_EMPTY"]
    assert today_response.reason_codes == ["TRANSACTION_LEDGER_EMPTY"]


async def test_transaction_ledger_snapshot_identity_is_pagination_invariant() -> None:
    common = {
        "portfolio_id": "P1",
        "reporting_currency": "SGD",
        "total_count": 25,
        "effective_as_of_date": date(2025, 1, 15),
        "end_date": date(2025, 1, 31),
        "latest_evidence_timestamp": datetime(2025, 1, 16, 9, 30, tzinfo=UTC),
        "input_evidence": _input_evidence(
            transaction_count=25,
            latest_evidence_timestamp=datetime(2025, 1, 16, 9, 30, tzinfo=UTC),
        ),
        "ledger_filters": _ledger_filters(
            security_id="S1",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        ),
    }

    first_page = paginated_transaction_ledger_response(
        **common,
        skip=0,
        limit=10,
        transactions=[_transaction_record("T1")],
    )
    later_page = paginated_transaction_ledger_response(
        **common,
        skip=10,
        limit=5,
        transactions=[_transaction_record("T11")],
        missing_instrument_security_ids=["S1"],
    )

    assert first_page.snapshot_id == later_page.snapshot_id
    assert first_page.source_lineage == later_page.source_lineage


async def test_exact_identity_qualifier_does_not_invalidate_legacy_ledger_scope() -> None:
    legacy_qualifiers = _transaction_ledger_qualifiers(
        ledger_filters=_ledger_filters(security_id="S1"),
        reporting_currency="SGD",
    )
    exact_qualifiers = _transaction_ledger_qualifiers(
        ledger_filters=_ledger_filters(transaction_id="T1", security_id="S1"),
        reporting_currency="SGD",
    )

    assert [name for name, _value in legacy_qualifiers] == [
        "instrument_id",
        "security_id",
        "transaction_type",
        "component_type",
        "linked_transaction_group_id",
        "fx_contract_id",
        "swap_event_id",
        "near_leg_group_id",
        "far_leg_group_id",
        "start_date",
        "end_date",
        "as_of_date",
        "reporting_currency",
    ]
    assert exact_qualifiers == (("transaction_id", "T1"), *legacy_qualifiers)


@pytest.mark.parametrize(
    "overrides",
    [
        {"reporting_currency": "EUR"},
        {"ledger_filters": _ledger_filters(instrument_id="I2")},
        {"ledger_filters": _ledger_filters(security_id="S2")},
        {"ledger_filters": _ledger_filters(transaction_type="SELL")},
        {"ledger_filters": _ledger_filters(component_type="FX_CONTRACT_OPEN")},
        {"ledger_filters": _ledger_filters(linked_transaction_group_id="LTG-FX-001")},
        {"ledger_filters": _ledger_filters(fx_contract_id="FXC-001")},
        {"ledger_filters": _ledger_filters(swap_event_id="FXSWAP-001")},
        {"ledger_filters": _ledger_filters(near_leg_group_id="FXSWAP-001-NEAR")},
        {"ledger_filters": _ledger_filters(far_leg_group_id="FXSWAP-001-FAR")},
        {"ledger_filters": _ledger_filters(start_date=date(2025, 1, 1))},
        {"ledger_filters": _ledger_filters(end_date=date(2025, 1, 31))},
        {"ledger_filters": _ledger_filters(as_of_date=date(2025, 1, 14))},
        {
            "total_count": 26,
            "input_evidence": _input_evidence(
                transaction_count=26,
                latest_evidence_timestamp=datetime(2025, 1, 16, 9, 30, tzinfo=UTC),
            ),
        },
        {
            "latest_evidence_timestamp": datetime(2025, 1, 16, 9, 31, tzinfo=UTC),
            "input_evidence": _input_evidence(
                transaction_count=25,
                latest_evidence_timestamp=datetime(2025, 1, 16, 9, 31, tzinfo=UTC),
            ),
        },
        {
            "input_evidence": _input_evidence(
                transaction_count=25,
                latest_evidence_timestamp=datetime(2025, 1, 16, 9, 30, tzinfo=UTC),
                transaction_digest="changed-transaction-digest",
            ),
        },
        {
            "input_evidence": _input_evidence(
                transaction_count=25,
                latest_evidence_timestamp=datetime(2025, 1, 16, 9, 30, tzinfo=UTC),
                transaction_cost_digest="changed-cost-digest",
            ),
        },
        {
            "input_evidence": _input_evidence(
                transaction_count=25,
                latest_evidence_timestamp=datetime(2025, 1, 16, 9, 30, tzinfo=UTC),
                selected_cashflow_digest="changed-cashflow-digest",
            ),
        },
        {
            "input_evidence": _input_evidence(
                transaction_count=25,
                latest_evidence_timestamp=datetime(2025, 1, 16, 9, 30, tzinfo=UTC),
                selected_fx_rate_digest="changed-fx-digest",
            ),
        },
    ],
)
async def test_transaction_ledger_snapshot_identity_changes_with_scope_or_evidence(
    overrides,
) -> None:
    common = {
        "portfolio_id": "P1",
        "reporting_currency": "SGD",
        "total_count": 25,
        "skip": 0,
        "limit": 10,
        "transactions": [_transaction_record("T1")],
        "effective_as_of_date": date(2025, 1, 15),
        "end_date": None,
        "latest_evidence_timestamp": datetime(2025, 1, 16, 9, 30, tzinfo=UTC),
        "input_evidence": _input_evidence(
            transaction_count=25,
            latest_evidence_timestamp=datetime(2025, 1, 16, 9, 30, tzinfo=UTC),
        ),
        "ledger_filters": _ledger_filters(security_id="S1"),
    }
    changed = {**common, **overrides}

    baseline = paginated_transaction_ledger_response(**common)
    revised = paginated_transaction_ledger_response(**changed)

    assert baseline.snapshot_id != revised.snapshot_id
