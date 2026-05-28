import pytest
from portfolio_common.currency_codes import normalize_currency_code
from portfolio_common.events import FxRateEvent, MarketPriceEvent, MarketPricePersistedEvent


def test_normalize_currency_code_returns_canonical_iso_code() -> None:
    assert normalize_currency_code(" usd ") == "USD"


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
