from datetime import datetime
from decimal import Decimal

import pytest
from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import (
    SELL_AVCO_POLICY_ID,
    SELL_DEFAULT_POLICY_VERSION,
    SELL_FIFO_POLICY_ID,
    enrich_sell_transaction_metadata,
)


def _sell_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="SELL-LINK-001",
        portfolio_id="PORT-LINK-001",
        instrument_id="SEC-ABC",
        security_id="SEC-ABC",
        transaction_date=datetime(2026, 3, 1, 12, 0, 0),
        transaction_type="SELL",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )


def test_enrich_sell_metadata_populates_defaults() -> None:
    enriched = enrich_sell_transaction_metadata(_sell_event())
    assert enriched.economic_event_id == "EVT-SELL-PORT-LINK-001-SELL-LINK-001"
    assert enriched.linked_transaction_group_id == "LTG-SELL-PORT-LINK-001-SELL-LINK-001"
    assert enriched.calculation_policy_id == SELL_FIFO_POLICY_ID
    assert enriched.calculation_policy_version == SELL_DEFAULT_POLICY_VERSION


def test_enrich_sell_metadata_preserves_upstream_values() -> None:
    event = _sell_event().model_copy(
        update={
            "economic_event_id": "EVT-UPSTREAM-001",
            "linked_transaction_group_id": "LTG-UPSTREAM-001",
            "calculation_policy_id": "SELL_SPECIAL_POLICY",
            "calculation_policy_version": "2.1.0",
        }
    )
    enriched = enrich_sell_transaction_metadata(event)
    assert enriched.economic_event_id == "EVT-UPSTREAM-001"
    assert enriched.linked_transaction_group_id == "LTG-UPSTREAM-001"
    assert enriched.calculation_policy_id == "SELL_SPECIAL_POLICY"
    assert enriched.calculation_policy_version == "2.1.0"


def test_enrich_sell_metadata_uses_avco_policy_when_requested() -> None:
    enriched = enrich_sell_transaction_metadata(_sell_event(), cost_basis_method="AVCO")
    assert enriched.calculation_policy_id == SELL_AVCO_POLICY_ID
    assert enriched.calculation_policy_version == SELL_DEFAULT_POLICY_VERSION


def test_enrich_sell_metadata_rejects_legacy_average_cost_alias() -> None:
    with pytest.raises(ValueError, match="Unsupported cost basis method"):
        enrich_sell_transaction_metadata(_sell_event(), cost_basis_method="AVERAGE_COST")
