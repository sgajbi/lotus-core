from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import (
    FX_DEFAULT_POLICY_ID,
    FX_DEFAULT_POLICY_VERSION,
    enrich_fx_transaction_metadata,
)


def _fx_forward_event() -> TransactionEvent:
    return TransactionEvent(
        transaction_id="FX-LINK-001",
        portfolio_id="PORT-FX-001",
        instrument_id="FXC-EURUSD-001",
        security_id="FXC-EURUSD-001",
        transaction_date=datetime(2026, 4, 1, 9, 0, 0),
        transaction_type="FX_FORWARD",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1095000"),
        trade_currency="USD",
        currency="USD",
        component_type="FX_CONTRACT_OPEN",
    )


def test_enrich_fx_metadata_populates_defaults_for_forward() -> None:
    enriched = enrich_fx_transaction_metadata(_fx_forward_event())
    assert enriched.economic_event_id == "EVT-FX-PORT-FX-001-FX-LINK-001"
    assert enriched.linked_transaction_group_id == "LTG-FX-PORT-FX-001-FX-LINK-001"
    assert enriched.calculation_policy_id == FX_DEFAULT_POLICY_ID
    assert enriched.calculation_policy_version == FX_DEFAULT_POLICY_VERSION
    assert enriched.component_id == "FX-LINK-001"
    assert enriched.fx_contract_id == "FXC-LTG-FX-PORT-FX-001-FX-LINK-001"
    assert enriched.spot_exposure_model == "NONE"
    assert enriched.fx_realized_pnl_mode == "NONE"
    assert enriched.instrument_id == "FXC-LTG-FX-PORT-FX-001-FX-LINK-001"
    assert enriched.security_id == "FXC-LTG-FX-PORT-FX-001-FX-LINK-001"
    assert enriched.fx_contract_open_transaction_id == "FX-LINK-001"


def test_enrich_fx_metadata_populates_swap_defaults() -> None:
    event = _fx_forward_event().model_copy(update={"transaction_type": "FX_SWAP"})
    enriched = enrich_fx_transaction_metadata(event)
    assert enriched.fx_contract_id == "FXC-FXSWAP-LTG-FX-PORT-FX-001-FX-LINK-001-FAR"
    assert enriched.swap_event_id == "FXSWAP-LTG-FX-PORT-FX-001-FX-LINK-001"
    assert enriched.near_leg_group_id == "FXSWAP-LTG-FX-PORT-FX-001-FX-LINK-001-NEAR"
    assert enriched.far_leg_group_id == "FXSWAP-LTG-FX-PORT-FX-001-FX-LINK-001-FAR"


def test_enrich_fx_metadata_infers_cash_leg_role() -> None:
    event = _fx_forward_event().model_copy(
        update={
            "transaction_type": "FX_SPOT",
            "component_type": "FX_CASH_SETTLEMENT_BUY",
            "fx_contract_id": None,
        }
    )
    enriched = enrich_fx_transaction_metadata(event)
    assert enriched.fx_cash_leg_role == "BUY"
    assert enriched.fx_contract_id is None


def test_enrich_fx_metadata_preserves_upstream_values() -> None:
    event = _fx_forward_event().model_copy(
        update={
            "economic_event_id": "EVT-UPSTREAM-001",
            "linked_transaction_group_id": "LTG-UPSTREAM-001",
            "calculation_policy_id": "FX_SPECIAL_POLICY",
            "calculation_policy_version": "2.0.0",
            "component_id": "FX-COMP-UPSTREAM-001",
            "fx_contract_id": "FXC-UPSTREAM-001",
            "swap_event_id": "FXSWAP-UPSTREAM-001",
            "fx_cash_leg_role": "SELL",
        }
    )
    enriched = enrich_fx_transaction_metadata(event)
    assert enriched.economic_event_id == "EVT-UPSTREAM-001"
    assert enriched.linked_transaction_group_id == "LTG-UPSTREAM-001"
    assert enriched.calculation_policy_id == "FX_SPECIAL_POLICY"
    assert enriched.calculation_policy_version == "2.0.0"
    assert enriched.component_id == "FX-COMP-UPSTREAM-001"
    assert enriched.fx_contract_id == "FXC-UPSTREAM-001"
    assert enriched.swap_event_id == "FXSWAP-UPSTREAM-001"
    assert enriched.fx_cash_leg_role == "SELL"


def test_enrich_fx_metadata_routes_contract_close_to_contract_instrument() -> None:
    event = _fx_forward_event().model_copy(
        update={
            "component_type": "FX_CONTRACT_CLOSE",
            "fx_contract_id": "FXC-UPSTREAM-002",
            "instrument_id": "LEG-INST",
            "security_id": "LEG-SEC",
        }
    )

    enriched = enrich_fx_transaction_metadata(event)

    assert enriched.instrument_id == "FXC-UPSTREAM-002"
    assert enriched.security_id == "FXC-UPSTREAM-002"
    assert enriched.fx_contract_close_transaction_id == "FX-LINK-001"
