from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import (
    INTEREST_DEFAULT_POLICY_ID,
    INTEREST_DEFAULT_POLICY_VERSION,
    enrich_interest_transaction_metadata,
)


def _interest_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="INT-LINK-001",
        portfolio_id="PORT-LINK-001",
        instrument_id="BOND-ABC",
        security_id="BOND-ABC",
        transaction_date=datetime(2026, 3, 1, 12, 0, 0),
        transaction_type="INTEREST",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("250"),
        trade_currency="USD",
        currency="USD",
    )


def test_enrich_interest_metadata_populates_defaults() -> None:
    enriched = enrich_interest_transaction_metadata(_interest_event())
    assert enriched.economic_event_id == "EVT-INTEREST-PORT-LINK-001-INT-LINK-001"
    assert (
        enriched.linked_transaction_group_id
        == "LTG-INTEREST-PORT-LINK-001-INT-LINK-001"
    )
    assert enriched.calculation_policy_id == INTEREST_DEFAULT_POLICY_ID
    assert enriched.calculation_policy_version == INTEREST_DEFAULT_POLICY_VERSION
    assert enriched.cash_entry_mode == "AUTO_GENERATE"


def test_enrich_interest_metadata_preserves_upstream_values() -> None:
    event = _interest_event().model_copy(
        update={
            "economic_event_id": "EVT-UPSTREAM-001",
            "linked_transaction_group_id": "LTG-UPSTREAM-001",
            "calculation_policy_id": "INTEREST_SPECIAL_POLICY",
            "calculation_policy_version": "2.1.0",
            "cash_entry_mode": "UPSTREAM_PROVIDED",
            "external_cash_transaction_id": "CASH-UPSTREAM-001",
        }
    )
    enriched = enrich_interest_transaction_metadata(event)
    assert enriched.economic_event_id == "EVT-UPSTREAM-001"
    assert enriched.linked_transaction_group_id == "LTG-UPSTREAM-001"
    assert enriched.calculation_policy_id == "INTEREST_SPECIAL_POLICY"
    assert enriched.calculation_policy_version == "2.1.0"
    assert enriched.cash_entry_mode == "UPSTREAM_PROVIDED"
    assert enriched.external_cash_transaction_id == "CASH-UPSTREAM-001"

