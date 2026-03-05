from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import (
    DIVIDEND_DEFAULT_POLICY_ID,
    DIVIDEND_DEFAULT_POLICY_VERSION,
    enrich_dividend_transaction_metadata,
)


def _dividend_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="DIV-LINK-001",
        portfolio_id="PORT-LINK-001",
        instrument_id="SEC-ABC",
        security_id="SEC-ABC",
        transaction_date=datetime(2026, 3, 1, 12, 0, 0),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("250"),
        trade_currency="USD",
        currency="USD",
    )


def test_enrich_dividend_metadata_populates_defaults() -> None:
    enriched = enrich_dividend_transaction_metadata(_dividend_event())
    assert enriched.economic_event_id == "EVT-DIVIDEND-PORT-LINK-001-DIV-LINK-001"
    assert (
        enriched.linked_transaction_group_id
        == "LTG-DIVIDEND-PORT-LINK-001-DIV-LINK-001"
    )
    assert enriched.calculation_policy_id == DIVIDEND_DEFAULT_POLICY_ID
    assert enriched.calculation_policy_version == DIVIDEND_DEFAULT_POLICY_VERSION
    assert enriched.cash_entry_mode == "AUTO_GENERATE"


def test_enrich_dividend_metadata_preserves_upstream_values() -> None:
    event = _dividend_event().model_copy(
        update={
            "economic_event_id": "EVT-UPSTREAM-001",
            "linked_transaction_group_id": "LTG-UPSTREAM-001",
            "calculation_policy_id": "DIVIDEND_SPECIAL_POLICY",
            "calculation_policy_version": "2.1.0",
            "cash_entry_mode": "UPSTREAM_PROVIDED",
            "external_cash_transaction_id": "CASH-UPSTREAM-001",
        }
    )
    enriched = enrich_dividend_transaction_metadata(event)
    assert enriched.economic_event_id == "EVT-UPSTREAM-001"
    assert enriched.linked_transaction_group_id == "LTG-UPSTREAM-001"
    assert enriched.calculation_policy_id == "DIVIDEND_SPECIAL_POLICY"
    assert enriched.calculation_policy_version == "2.1.0"
    assert enriched.cash_entry_mode == "UPSTREAM_PROVIDED"
    assert enriched.external_cash_transaction_id == "CASH-UPSTREAM-001"

