import pytest
from portfolio_common.currency_codes import (
    normalize_currency_code,
    normalize_optional_currency_code,
)
from portfolio_common.events import (
    FxRateEvent,
    InstrumentEvent,
    MarketPriceEvent,
    MarketPricePersistedEvent,
    PortfolioEvent,
    TransactionEvent,
)


def test_normalize_currency_code_returns_canonical_iso_code() -> None:
    assert normalize_currency_code(" usd ") == "USD"


def test_normalize_optional_currency_code_preserves_none() -> None:
    assert normalize_optional_currency_code(None) is None


@pytest.mark.parametrize("value", ["", " us ", "USDT", "12D", object()])
def test_normalize_currency_code_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_currency_code(value)


def test_fx_rate_event_normalizes_currency_codes() -> None:
    event = FxRateEvent(
        from_currency=" eur ",
        to_currency=" usd ",
        rate_date="2026-05-28",
        rate="1.0875000000",
    )

    assert event.from_currency == "EUR"
    assert event.to_currency == "USD"


@pytest.mark.parametrize("rate", ["0", "-0.0001"])
def test_fx_rate_event_rejects_nonpositive_rates(rate: str) -> None:
    with pytest.raises(ValueError, match="FX rate must be greater than zero"):
        FxRateEvent(
            from_currency="EUR",
            to_currency="USD",
            rate_date="2026-05-28",
            rate=rate,
        )


def test_market_price_events_normalize_currency_codes() -> None:
    raw_event = MarketPriceEvent(
        security_id="SEC_A",
        price_date="2026-05-28",
        price="100.2500000000",
        currency=" usd ",
    )
    persisted_event = MarketPricePersistedEvent.model_validate(raw_event.model_dump())

    assert raw_event.currency == "USD"
    assert persisted_event.currency == "USD"


@pytest.mark.parametrize("price", ["0", "-0.01"])
def test_market_price_events_reject_nonpositive_prices(price: str) -> None:
    with pytest.raises(ValueError, match="Market price must be greater than zero"):
        MarketPriceEvent(
            security_id="SEC_A",
            price_date="2026-05-28",
            price=price,
            currency="USD",
        )

    with pytest.raises(ValueError, match="Market price must be greater than zero"):
        MarketPricePersistedEvent(
            security_id="SEC_A",
            price_date="2026-05-28",
            price=price,
            currency="USD",
        )


def test_transaction_event_normalizes_currency_codes() -> None:
    event = TransactionEvent(
        transaction_id="TX_CANONICAL_CCY_001",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity="10",
        price="100",
        gross_transaction_amount="1000",
        trade_currency=" usd ",
        currency=" usd ",
        pair_base_currency=" eur ",
        pair_quote_currency=" usd ",
        buy_currency=" usd ",
        sell_currency=" eur ",
        synthetic_flow_currency=" sgd ",
    )

    assert event.trade_currency == "USD"
    assert event.currency == "USD"
    assert event.pair_base_currency == "EUR"
    assert event.pair_quote_currency == "USD"
    assert event.buy_currency == "USD"
    assert event.sell_currency == "EUR"
    assert event.synthetic_flow_currency == "SGD"


def test_instrument_event_normalizes_currency_codes() -> None:
    event = InstrumentEvent(
        security_id="FX_FORWARD_001",
        name="EUR/USD Forward",
        isin="FXFORWARD001",
        currency=" usd ",
        product_type="fx_forward",
        pair_base_currency=" eur ",
        pair_quote_currency=" usd ",
        buy_currency=" eur ",
        sell_currency=" usd ",
    )

    assert event.currency == "USD"
    assert event.pair_base_currency == "EUR"
    assert event.pair_quote_currency == "USD"
    assert event.buy_currency == "EUR"
    assert event.sell_currency == "USD"


def test_portfolio_event_normalizes_base_currency() -> None:
    event = PortfolioEvent(
        portfolio_id="P1",
        base_currency=" usd ",
        open_date="2026-05-28",
        risk_exposure="balanced",
        investment_time_horizon="long_term",
        portfolio_type="discretionary",
        booking_center_code="SG",
        client_id="C1",
        status="ACTIVE",
    )

    assert event.base_currency == "USD"
