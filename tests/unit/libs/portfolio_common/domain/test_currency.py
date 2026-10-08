from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.domain.currency import (
    normalize_currency_code,
    normalize_optional_currency_code,
)
from portfolio_common.events import (
    FxRateEvent,
    FxRatePersistedEvent,
    InstrumentEvent,
    MarketPriceEvent,
    MarketPricePersistedEvent,
    PortfolioEvent,
    TransactionEvent,
)

from tests.test_support.tenant import TEST_TENANT_ID


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


def test_fx_rate_persisted_event_has_deterministic_business_content_hash() -> None:
    first = FxRatePersistedEvent.from_observation(
        FxRateEvent(
            from_currency="EUR",
            to_currency="USD",
            rate_date="2026-05-28",
            rate="1.0875000000",
        ),
        generated_at=datetime(2026, 5, 28, 10, tzinfo=timezone.utc),
    )
    second = FxRatePersistedEvent.from_observation(
        FxRateEvent(
            from_currency=" eur ",
            to_currency=" usd ",
            rate_date="2026-05-28",
            rate="1.0875000000",
        ),
        generated_at=datetime(2026, 5, 28, 11, tzinfo=timezone.utc),
    )

    assert first.content_hash == second.content_hash
    assert first.observation_id != second.observation_id
    assert first.content_hash.startswith("sha256:")
    assert first.observation_id.startswith("sha256:")
    assert first.generated_at.isoformat() == "2026-05-28T10:00:00+00:00"


def test_fx_rate_persisted_event_hash_changes_for_correction() -> None:
    original = FxRatePersistedEvent.from_observation(
        FxRateEvent(
            from_currency="EUR",
            to_currency="USD",
            rate_date="2026-05-28",
            rate="1.0875000000",
        )
    )
    correction = FxRatePersistedEvent.from_observation(
        FxRateEvent(
            from_currency="EUR",
            to_currency="USD",
            rate_date="2026-05-28",
            rate="1.0910000000",
        )
    )

    assert original.content_hash != correction.content_hash


def test_fx_rate_persisted_event_replay_has_same_observation_identity() -> None:
    observation = FxRateEvent(
        from_currency="EUR",
        to_currency="USD",
        rate_date="2026-05-28",
        rate="1.0875000000",
    )
    generated_at = datetime(2026, 5, 28, 10, tzinfo=timezone.utc)

    first = FxRatePersistedEvent.from_observation(
        observation,
        generated_at=generated_at,
    )
    replay = FxRatePersistedEvent.from_observation(
        observation,
        generated_at=generated_at,
    )

    assert first.observation_id == replay.observation_id


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("from_currency", "GBP"),
        ("to_currency", "CHF"),
        ("rate_date", "2026-05-27"),
        ("rate", "1.0910000000"),
        ("generated_at", "2026-05-28T11:00:00Z"),
        ("content_hash", "sha256:" + "a" * 64),
        ("observation_id", "sha256:" + "b" * 64),
    ],
)
def test_fx_persisted_event_refuses_identity_content_mismatch(field, replacement) -> None:
    event = FxRatePersistedEvent.from_observation(
        FxRateEvent(from_currency="EUR", to_currency="USD", rate_date="2026-05-28", rate="1.0875"),
        generated_at=datetime(2026, 5, 28, 10, tzinfo=timezone.utc),
    )
    payload = event.model_dump(mode="json")
    payload[field] = replacement
    with pytest.raises(ValueError, match="persisted FX.*identity"):
        FxRatePersistedEvent.model_validate(payload)


def test_fx_persisted_event_wire_replay_preserves_identity_without_diagnostic_lineage() -> None:
    original = FxRatePersistedEvent.from_observation(
        FxRateEvent(from_currency="EUR", to_currency="USD", rate_date="2026-05-28", rate="1.0875"),
        generated_at=datetime(2026, 5, 28, 10, tzinfo=timezone.utc),
    )
    payload = original.model_dump(mode="json")
    payload.update(
        correlation_id="trace-new-replay", event_type="FxRatePersisted", schema_version="1.0.0"
    )
    replay = FxRatePersistedEvent.model_validate(payload)
    assert replay.content_hash == original.content_hash
    assert replay.observation_id == original.observation_id


def test_fx_persisted_event_accepts_existing_canonical_wire_identity() -> None:
    # Independent SHA-256 oracle over sorted compact JSON, not the production factory.
    event = FxRatePersistedEvent.model_validate(
        {
            "from_currency": "EUR",
            "to_currency": "USD",
            "rate_date": "2026-05-28",
            "rate": "1.0875",
            "generated_at": "2026-05-28T10:00:00Z",
            "content_hash": "sha256:bc4c86a5eaa8bbc698e2d75bcb312c87704a48bb6d7f80f9fac7745a299a2c42",
            "observation_id": "sha256:e7b9034ad07a8bc82947096e736461888e99063177a4cc03c12187bd5c2aa9b2",
        }
    )
    assert event.rate == Decimal("1.0875")


@pytest.mark.parametrize("rate", ["0", "-0.0001"])
def test_fx_rate_event_rejects_nonpositive_rates(rate: str) -> None:
    with pytest.raises(ValueError, match="FX rate must be greater than zero"):
        FxRateEvent(
            from_currency="EUR",
            to_currency="USD",
            rate_date="2026-05-28",
            rate=rate,
        )


@pytest.mark.parametrize("rate", ["1.00000000001", "100000000"])
def test_fx_rate_events_reject_values_not_exactly_representable_in_storage(rate: str) -> None:
    with pytest.raises(ValueError, match="bounded-18-10-exact"):
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


@pytest.mark.parametrize("price", ["100.00000000001", "100000000"])
def test_market_price_events_reject_values_not_exactly_representable_in_storage(
    price: str,
) -> None:
    event_fields = {
        "security_id": "SEC_A",
        "price_date": "2026-05-28",
        "price": price,
        "currency": "USD",
    }

    with pytest.raises(ValueError, match="bounded-18-10-exact"):
        MarketPriceEvent(**event_fields)

    with pytest.raises(ValueError, match="bounded-18-10-exact"):
        MarketPricePersistedEvent(**event_fields)


def test_transaction_event_normalizes_currency_codes() -> None:
    event = TransactionEvent(
        transaction_id="TX_CANONICAL_CCY_001",
        portfolio_id="P1",
        tenant_id="tenant-test",
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
        tenant_id=TEST_TENANT_ID,
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
