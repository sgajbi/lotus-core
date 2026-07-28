from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.market_price_dto import (
    AuthoritativeMarketPriceSourceFact,
    AuthoritativeMarketPriceSourceFactIngestionRequest,
)


def _record(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "tenant_id": " LOTUS_PB_SG ",
        "legal_book_id": " SG_PRIVATE_BANK_BOOK ",
        "security_id": " BOND_US_CORP_2031 ",
        "price_date": "2026-07-28",
        "price": "99.250000000000000000",
        "currency": " usd ",
        "quote_basis": "PERCENT_OF_PRINCIPAL_CLEAN",
        "fact_status": "ACTIVE",
        "fact_version": 1,
        "source_system": " approved_market_data ",
        "source_record_id": " PX-BOND_US_CORP_2031-20260728 ",
        "source_revision": " rev-1 ",
        "source_content_hash": "a" * 64,
        "observed_at": "2026-07-28T09:30:00+08:00",
    }
    values.update(overrides)
    return values


def test_authoritative_market_price_source_fact_normalizes_exact_authority() -> None:
    record = AuthoritativeMarketPriceSourceFact.model_validate(_record())

    fact = record.to_domain()

    assert fact.scope.key == (
        "LOTUS_PB_SG",
        "SG_PRIVATE_BANK_BOOK",
        "BOND_US_CORP_2031",
    )
    assert fact.price_date == date(2026, 7, 28)
    assert fact.price == Decimal("99.250000000000000000")
    assert fact.currency == "USD"
    assert fact.source_record_key == (
        "approved_market_data",
        "PX-BOND_US_CORP_2031-20260728",
    )


def test_authoritative_market_price_batch_accepts_distinct_source_versions() -> None:
    first = _record()
    second = _record(
        fact_version=2,
        source_revision="rev-2",
        source_content_hash="b" * 64,
    )

    request = AuthoritativeMarketPriceSourceFactIngestionRequest.model_validate(
        {"market_price_source_facts": [first, second]}
    )

    assert [fact.fact_version for fact in request.market_price_source_facts] == [1, 2]


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-Infinity", "0", "-0.01"])
def test_authoritative_market_price_source_fact_rejects_non_positive_finite_price(
    price: str,
) -> None:
    with pytest.raises(ValidationError):
        AuthoritativeMarketPriceSourceFact.model_validate(_record(price=price))


def test_authoritative_market_price_source_fact_requires_aware_observation() -> None:
    with pytest.raises(ValidationError, match="timezone offset"):
        AuthoritativeMarketPriceSourceFact.model_validate(
            _record(observed_at="2026-07-28T09:30:00")
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "tenant_id",
        "legal_book_id",
        "security_id",
        "source_system",
        "source_record_id",
        "source_revision",
    ],
)
def test_authoritative_market_price_source_fact_rejects_blank_authority_and_source_identity(
    field_name: str,
) -> None:
    with pytest.raises(ValidationError, match="must be nonblank"):
        AuthoritativeMarketPriceSourceFact.model_validate(_record(**{field_name: "   "}))


def test_authoritative_market_price_source_fact_rejects_malformed_source_hash() -> None:
    with pytest.raises(ValidationError):
        AuthoritativeMarketPriceSourceFact.model_validate(_record(source_content_hash="A" * 64))


def test_authoritative_market_price_batch_rejects_duplicate_source_version() -> None:
    duplicate = _record()

    with pytest.raises(ValidationError, match="duplicate source-version identities"):
        AuthoritativeMarketPriceSourceFactIngestionRequest.model_validate(
            {"market_price_source_facts": [duplicate, deepcopy(duplicate)]}
        )
