from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from pydantic import ValidationError


def _interest_event(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "transaction_id": "INTEREST-EVENT-001",
        "portfolio_id": "PORT-001",
        "tenant_id": "tenant-test",
        "instrument_id": "BOND-001",
        "security_id": "BOND-001",
        "transaction_date": datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
        "settlement_date": datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc),
        "transaction_type": "INTEREST",
        "quantity": Decimal(0),
        "price": Decimal(0),
        "gross_transaction_amount": Decimal("10"),
        "trade_currency": "USD",
        "currency": "USD",
        "trade_fee": Decimal("2"),
        "interest_direction": "EXPENSE",
    }
    payload.update(changes)
    return payload


@pytest.mark.parametrize(
    ("cash_entry_mode", "cash_fields"),
    [
        ("AUTO_GENERATE", {"settlement_cash_account_id": "CASH-USD-001"}),
        (
            "UPSTREAM_PROVIDED",
            {"external_cash_transaction_id": "EXTERNAL-CASH-001"},
        ),
    ],
)
@pytest.mark.parametrize("net_interest_amount", [None, Decimal("-1")])
def test_transaction_event_rejects_negative_interest_pre_fee_net(
    cash_entry_mode: str,
    cash_fields: dict[str, str],
    net_interest_amount: Decimal | None,
) -> None:
    with pytest.raises(ValidationError) as raised:
        TransactionEvent.model_validate(
            _interest_event(
                cash_entry_mode=cash_entry_mode,
                withholding_tax_amount=Decimal("6"),
                other_interest_deductions_amount=Decimal("5"),
                net_interest_amount=net_interest_amount,
                **cash_fields,
            )
        )

    assert raised.value.errors()[0]["type"] == "INTEREST_018_NEGATIVE_PRE_FEE_NET"


def test_transaction_event_accepts_linkage_and_policy_metadata() -> None:
    event = TransactionEvent(
        transaction_id="TXN-META-001",
        portfolio_id="PORT-001",
        tenant_id="tenant-test",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 2, 28, 12, 30, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("100"),
        price=Decimal("12.34"),
        gross_transaction_amount=Decimal("1234"),
        trade_currency="USD",
        currency="USD",
        economic_event_id="EVT-2026-001",
        linked_transaction_group_id="LTG-2026-001",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        source_system="OMS_PRIMARY",
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id="CASH-ENTRY-2026-0001",
        parent_event_reference="UPSTREAM-CA-REF-2026-0001",
        child_role="SOURCE_POSITION_CLOSE",
        source_instrument_id="OLD_SEC_001",
        target_instrument_id="NEW_SEC_001",
        linked_cash_transaction_id="CA-CIL-CASH-001",
        has_synthetic_flow=True,
        synthetic_flow_classification="POSITION_TRANSFER_OUT",
    )

    assert event.economic_event_id == "EVT-2026-001"
    assert event.linked_transaction_group_id == "LTG-2026-001"
    assert event.calculation_policy_id == "BUY_DEFAULT_POLICY"
    assert event.calculation_policy_version == "1.0.0"
    assert event.source_system == "OMS_PRIMARY"
    assert event.cash_entry_mode == "UPSTREAM_PROVIDED"
    assert event.external_cash_transaction_id == "CASH-ENTRY-2026-0001"
    assert event.parent_event_reference == "UPSTREAM-CA-REF-2026-0001"
    assert event.child_role == "SOURCE_POSITION_CLOSE"
    assert event.source_instrument_id == "OLD_SEC_001"
    assert event.target_instrument_id == "NEW_SEC_001"
    assert event.linked_cash_transaction_id == "CA-CIL-CASH-001"
    assert event.has_synthetic_flow is True
    assert event.synthetic_flow_classification == "POSITION_TRANSFER_OUT"


def test_transaction_db_model_exposes_metadata_columns() -> None:
    column_names = {column.name for column in DBTransaction.__table__.columns}

    assert "economic_event_id" in column_names
    assert "linked_transaction_group_id" in column_names
    assert "calculation_policy_id" in column_names
    assert "calculation_policy_version" in column_names
    assert "source_system" in column_names
    assert "cash_entry_mode" in column_names
    assert "external_cash_transaction_id" in column_names
    assert "parent_event_reference" in column_names
    assert "child_role" in column_names
    assert "source_instrument_id" in column_names
    assert "target_instrument_id" in column_names
    assert "linked_cash_transaction_id" in column_names
    assert "has_synthetic_flow" in column_names
    assert "synthetic_flow_classification" in column_names
