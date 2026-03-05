from datetime import datetime
from decimal import Decimal

from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent


def test_transaction_event_accepts_linkage_and_policy_metadata() -> None:
    event = TransactionEvent(
        transaction_id="TXN-META-001",
        portfolio_id="PORT-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 2, 28, 12, 30, 0),
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
    )

    assert event.economic_event_id == "EVT-2026-001"
    assert event.linked_transaction_group_id == "LTG-2026-001"
    assert event.calculation_policy_id == "BUY_DEFAULT_POLICY"
    assert event.calculation_policy_version == "1.0.0"
    assert event.source_system == "OMS_PRIMARY"
    assert event.cash_entry_mode == "UPSTREAM_PROVIDED"
    assert event.external_cash_transaction_id == "CASH-ENTRY-2026-0001"


def test_transaction_db_model_exposes_metadata_columns() -> None:
    column_names = {column.name for column in DBTransaction.__table__.columns}

    assert "economic_event_id" in column_names
    assert "linked_transaction_group_id" in column_names
    assert "calculation_policy_id" in column_names
    assert "calculation_policy_version" in column_names
    assert "source_system" in column_names
    assert "cash_entry_mode" in column_names
    assert "external_cash_transaction_id" in column_names

