from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    ValuationAuthorityScope,
    ValuationBookScope,
    resolve_optional_valuation_book_scope,
)


def _source_reference() -> FinancialSourceReference:
    return FinancialSourceReference(
        source_system="approved-market-data",
        source_record_id="PRICE-001",
        source_revision="7",
        source_content_hash="a" * 64,
        observed_at=datetime(2026, 7, 23, 4, 30, tzinfo=UTC),
    )


def _fact(**overrides: object) -> MarketPriceSourceFact:
    values: dict[str, object] = {
        "scope": ValuationAuthorityScope(
            tenant_id=" TENANT-SG ",
            legal_book_id=" PB-SG-01 ",
            security_id=" BOND-001 ",
        ),
        "price_date": date(2026, 7, 22),
        "price": Decimal("99.25"),
        "currency": " usd ",
        "quote_basis": MarketPriceQuoteBasis.PERCENT_OF_PRINCIPAL_CLEAN,
        "source_reference": _source_reference(),
    }
    values.update(overrides)
    return MarketPriceSourceFact(**values)  # type: ignore[arg-type]


def test_valuation_authority_scope_normalizes_without_defaulting() -> None:
    scope = ValuationAuthorityScope(
        tenant_id=" TENANT-SG ",
        legal_book_id=" PB-SG-01 ",
        security_id=" BOND-001 ",
    )

    assert scope.key == ("TENANT-SG", "PB-SG-01", "BOND-001")
    assert scope.book_scope == ValuationBookScope("TENANT-SG", "PB-SG-01")


def test_optional_valuation_book_scope_preserves_legacy_absence() -> None:
    assert resolve_optional_valuation_book_scope(tenant_id=None, legal_book_id=None) is None


@pytest.mark.parametrize(
    ("tenant_id", "legal_book_id"),
    [("TENANT-SG", None), (None, "PB-SG-01")],
)
def test_optional_valuation_book_scope_rejects_partial_authority(
    tenant_id: str | None,
    legal_book_id: str | None,
) -> None:
    with pytest.raises(ValueError, match="must be supplied together"):
        resolve_optional_valuation_book_scope(
            tenant_id=tenant_id,
            legal_book_id=legal_book_id,
        )


@pytest.mark.parametrize("field_name", ["tenant_id", "legal_book_id", "security_id"])
def test_valuation_authority_scope_rejects_missing_dimension(field_name: str) -> None:
    values = {
        "tenant_id": "TENANT-SG",
        "legal_book_id": "PB-SG-01",
        "security_id": "BOND-001",
    }
    values[field_name] = " "

    with pytest.raises(ValueError, match=rf"{field_name} must be nonblank"):
        ValuationAuthorityScope(**values)


@pytest.mark.parametrize(
    ("scope_type", "field_name"),
    [
        (ValuationBookScope, "tenant_id"),
        (ValuationBookScope, "legal_book_id"),
        (ValuationAuthorityScope, "tenant_id"),
        (ValuationAuthorityScope, "legal_book_id"),
        (ValuationAuthorityScope, "security_id"),
    ],
)
@pytest.mark.parametrize("invalid_value", [None, 42, Decimal("1")])
def test_valuation_scope_rejects_manufactured_non_string_authority(
    scope_type: type[ValuationBookScope] | type[ValuationAuthorityScope],
    field_name: str,
    invalid_value: object,
) -> None:
    values: dict[str, object] = {
        "tenant_id": "TENANT-SG",
        "legal_book_id": "PB-SG-01",
    }
    if scope_type is ValuationAuthorityScope:
        values["security_id"] = "BOND-001"
    values[field_name] = invalid_value

    with pytest.raises(TypeError, match=rf"{field_name} must be a string"):
        scope_type(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("quote_basis", "price"),
    [
        (MarketPriceQuoteBasis.UNIT_PRICE, Decimal("1013.5")),
        (MarketPriceQuoteBasis.PERCENT_OF_PRINCIPAL_CLEAN, Decimal("99.25")),
        (MarketPriceQuoteBasis.PERCENT_OF_PRINCIPAL_DIRTY, Decimal("100.125")),
    ],
)
def test_market_price_source_fact_accepts_explicit_quote_basis(
    quote_basis: MarketPriceQuoteBasis,
    price: Decimal,
) -> None:
    fact = _fact(quote_basis=quote_basis, price=price)

    assert fact.quote_basis is quote_basis
    assert fact.price == price
    assert fact.currency == "USD"
    assert fact.scope.key == ("TENANT-SG", "PB-SG-01", "BOND-001")


def test_market_price_source_fact_hash_binds_scope_representation_and_lineage() -> None:
    fact = _fact()

    assert fact.content_hash() == _fact().content_hash()
    assert fact.content_hash() != _fact(quote_basis=MarketPriceQuoteBasis.UNIT_PRICE).content_hash()
    assert (
        fact.content_hash()
        != _fact(
            scope=ValuationAuthorityScope(
                tenant_id="TENANT-SG",
                legal_book_id="PB-SG-02",
                security_id="BOND-001",
            )
        ).content_hash()
    )


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-1"), Decimal("NaN")])
def test_market_price_source_fact_rejects_unsupported_price(price: Decimal) -> None:
    with pytest.raises(ValueError, match="positive finite Decimal"):
        _fact(price=price)


def test_market_price_source_fact_requires_typed_scope_and_lineage() -> None:
    with pytest.raises(TypeError, match="scope must be"):
        _fact(scope={"tenant_id": "TENANT-SG"})
    with pytest.raises(TypeError, match="source_reference must be"):
        _fact(source_reference={"source_system": "approved-market-data"})


@pytest.mark.parametrize(
    "price_date",
    ["2026-07-22", datetime(2026, 7, 22, 12, tzinfo=UTC)],
)
def test_market_price_source_fact_requires_exact_business_date(price_date: object) -> None:
    with pytest.raises(TypeError, match="price_date must be an exact date"):
        _fact(price_date=price_date)
