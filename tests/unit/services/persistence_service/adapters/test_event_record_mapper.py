from datetime import date
from decimal import Decimal

from portfolio_common.events import (
    FxRateEvent,
    InstrumentEvent,
    MarketPriceEvent,
    PortfolioEvent,
)

from src.services.persistence_service.app.adapters.event_record_mapper import (
    event_business_record_values,
)


def test_event_business_record_values_preserves_database_native_types() -> None:
    portfolio = PortfolioEvent(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        base_currency="usd",
        open_date="2025-01-06",
        close_date="2026-04-10",
        risk_exposure="balanced",
        investment_time_horizon="long_term",
        portfolio_type="discretionary",
        objective="Canonical private banking balanced mandate.",
        booking_center_code="Singapore",
        client_id="CIF_SG_000184",
        advisor_id="advisor_sg_001",
        status="active",
    )
    fx_rate = FxRateEvent(
        from_currency="usd",
        to_currency="sgd",
        rate_date="2026-04-10",
        rate="1.3525",
    )
    market_price = MarketPriceEvent(
        security_id="AAPL",
        price_date="2026-04-10",
        price="198.25",
        currency="usd",
    )
    instrument = InstrumentEvent(
        security_id="US912810TX63",
        name="US Treasury 10Y",
        isin="US912810TX63",
        currency="usd",
        product_type="bond",
        trade_date="2025-03-31",
        maturity_date="2036-02-15",
    )

    portfolio_values = event_business_record_values(portfolio)
    fx_rate_values = event_business_record_values(fx_rate)
    market_price_values = event_business_record_values(market_price)
    instrument_values = event_business_record_values(instrument)

    assert portfolio_values["open_date"] == date(2025, 1, 6)
    assert portfolio_values["close_date"] == date(2026, 4, 10)
    assert fx_rate_values["rate_date"] == date(2026, 4, 10)
    assert fx_rate_values["rate"] == Decimal("1.3525")
    assert market_price_values["price_date"] == date(2026, 4, 10)
    assert market_price_values["price"] == Decimal("198.25")
    assert instrument_values["trade_date"] == date(2025, 3, 31)
    assert instrument_values["maturity_date"] == date(2036, 2, 15)
