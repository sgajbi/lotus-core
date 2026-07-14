"""Verify foreign-exchange domain values map to governed integration events."""

from datetime import date
from decimal import Decimal

from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    FxContractInstrument,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_mapping import (  # noqa: E501
    foreign_exchange_instrument,
)


def test_fx_contract_instrument_event_preserves_domain_values() -> None:
    instrument = FxContractInstrument(
        security_id="FXC-2026-0001",
        name="FX CONTRACT EUR/USD 2026-07-01",
        isin="SYN-FX-FXC-2026-0001",
        currency="USD",
        product_type="FX_CONTRACT",
        asset_class="FX",
        maturity_date=date(2026, 7, 1),
        portfolio_id="PORT-FX-1",
        trade_date=date(2026, 4, 1),
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
    )

    event = foreign_exchange_instrument.to_fx_contract_instrument_event(instrument)

    for field_name in instrument.__dataclass_fields__:
        assert getattr(event, field_name) == getattr(instrument, field_name)
