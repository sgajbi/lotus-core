from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.fx_rate_dto import FxRate, FxRateIngestionRequest
from src.services.ingestion_service.app.DTOs.market_price_dto import (
    AuthoritativeMarketPriceSourceFact,
    MarketPrice,
)


def _market_price_payload(price: str) -> dict[str, object]:
    return {
        "security_id": "SEC_A",
        "price_date": "2026-07-28",
        "price": price,
        "currency": "USD",
    }


def _fx_rate_payload(rate: str) -> dict[str, object]:
    return {
        "from_currency": "USD",
        "to_currency": "SGD",
        "rate_date": "2026-07-28",
        "rate": rate,
    }


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (MarketPrice, _market_price_payload("99999999.9999999999")),
        (FxRate, _fx_rate_payload("99999999.9999999999")),
    ],
)
def test_legacy_reference_value_accepts_exact_storage_boundary(
    model,
    payload: dict[str, object],
) -> None:
    record = model.model_validate(payload)

    value = record.price if isinstance(record, MarketPrice) else record.rate
    assert value == Decimal("99999999.9999999999")


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (MarketPrice, _market_price_payload("1.00000000001")),
        (MarketPrice, _market_price_payload("100000000")),
        (FxRate, _fx_rate_payload("1.00000000001")),
        (FxRate, _fx_rate_payload("100000000")),
    ],
)
def test_legacy_reference_value_rejects_scale_or_magnitude_loss(
    model,
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="bounded-18-10-exact"):
        model.model_validate(payload)


def test_authoritative_market_price_remains_exact_unbounded() -> None:
    price = f"{'9' * 40}.{'1' * 40}"
    record = AuthoritativeMarketPriceSourceFact.model_validate(
        {
            "tenant_id": "LOTUS_PB_SG",
            "legal_book_id": "SG_PRIVATE_BANK_BOOK",
            "security_id": "BOND_US_CORP_2031",
            "price_date": "2026-07-28",
            "price": price,
            "currency": "USD",
            "quote_basis": "PERCENT_OF_PRINCIPAL_CLEAN",
            "fact_status": "ACTIVE",
            "fact_version": 1,
            "source_system": "approved_market_data",
            "source_record_id": "PX-BOND_US_CORP_2031-20260728",
            "source_revision": "rev-1",
            "source_content_hash": "a" * 64,
            "observed_at": "2026-07-28T09:30:00+08:00",
        }
    )

    assert record.price == Decimal(price)


@pytest.mark.parametrize("scope", ["record", "batch"])
@pytest.mark.parametrize(
    "claim",
    [
        "provider_id",
        "observed_at",
        "source_revision",
        "content_hash",
        "source_cut_id",
        "calendar_version",
    ],
)
def test_legacy_fx_intake_refuses_unsupported_custody_claims(scope: str, claim: str) -> None:
    record = _fx_rate_payload("1.3500000000")
    payload: dict[str, object] = {"fx_rates": [record]}
    target = record if scope == "record" else payload
    target[claim] = "caller-asserted-custody"

    with pytest.raises(ValidationError) as rejected:
        FxRateIngestionRequest.model_validate(payload)

    assert any(
        error["type"] == "extra_forbidden" and error["loc"][-1] == claim
        for error in rejected.value.errors()
    )


def test_legacy_fx_intake_preserves_valid_business_content_for_native_event() -> None:
    from portfolio_common.events import FxRateEvent, event_business_payload

    accepted = FxRateIngestionRequest.model_validate(
        {"fx_rates": [{**_fx_rate_payload("1.3500000000"), "from_currency": " usd "}]}
    )
    event = FxRateEvent.model_validate(accepted.fx_rates[0].model_dump())
    assert event_business_payload(event) == {
        "from_currency": "USD",
        "to_currency": "SGD",
        "rate_date": accepted.fx_rates[0].rate_date,
        "rate": Decimal("1.3500000000"),
    }


def test_fx_intake_schema_declares_closed_record_and_batch_contracts() -> None:
    schema = FxRateIngestionRequest.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["FxRate"]["additionalProperties"] is False
    assert set(schema["$defs"]["FxRate"]["properties"]) == {
        "from_currency",
        "to_currency",
        "rate_date",
        "rate",
    }
