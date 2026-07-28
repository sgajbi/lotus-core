from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.fx_rate_dto import FxRate
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
