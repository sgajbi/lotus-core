from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import (
    BUY_DEFAULT_POLICY_ID,
    BUY_DEFAULT_POLICY_VERSION,
    enrich_buy_transaction_metadata,
)


def _buy_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="BUY-LINK-001",
        portfolio_id="PORT-LINK-001",
        instrument_id="SEC-ABC",
        security_id="SEC-ABC",
        transaction_date=datetime(2026, 3, 1, 12, 0, 0),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )


def test_enrich_buy_metadata_populates_defaults() -> None:
    enriched = enrich_buy_transaction_metadata(_buy_event())
    assert enriched.economic_event_id == "EVT-BUY-PORT-LINK-001-BUY-LINK-001"
    assert enriched.linked_transaction_group_id == "LTG-BUY-PORT-LINK-001-BUY-LINK-001"
    assert enriched.calculation_policy_id == BUY_DEFAULT_POLICY_ID
    assert enriched.calculation_policy_version == BUY_DEFAULT_POLICY_VERSION


def test_enrich_buy_metadata_preserves_upstream_values() -> None:
    event = _buy_event().model_copy(
        update={
            "economic_event_id": "EVT-UPSTREAM-001",
            "linked_transaction_group_id": "LTG-UPSTREAM-001",
            "calculation_policy_id": "BUY_SPECIAL_POLICY",
            "calculation_policy_version": "2.1.0",
        }
    )
    enriched = enrich_buy_transaction_metadata(event)
    assert enriched.economic_event_id == "EVT-UPSTREAM-001"
    assert enriched.linked_transaction_group_id == "LTG-UPSTREAM-001"
    assert enriched.calculation_policy_id == "BUY_SPECIAL_POLICY"
    assert enriched.calculation_policy_version == "2.1.0"
