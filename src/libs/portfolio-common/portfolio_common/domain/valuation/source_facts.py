"""Authoritative scope and source evidence for market-price valuation facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import cast

from ..calculation_lineage import FinancialSourceReference, canonical_content_hash
from ..currency import normalize_currency_code


class MarketPriceQuoteBasis(StrEnum):
    """Explicit representation of an authoritative market-price observation."""

    UNIT_PRICE = "UNIT_PRICE"
    PERCENT_OF_PRINCIPAL_CLEAN = "PERCENT_OF_PRINCIPAL_CLEAN"
    PERCENT_OF_PRINCIPAL_DIRTY = "PERCENT_OF_PRINCIPAL_DIRTY"


@dataclass(frozen=True, slots=True)
class ValuationBookScope:
    """Exact tenant and legal-book authority for one portfolio valuation stream."""

    tenant_id: str
    legal_book_id: str

    def __post_init__(self) -> None:
        for field_name in ("tenant_id", "legal_book_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)

    @property
    def key(self) -> tuple[str, str]:
        return (self.tenant_id, self.legal_book_id)


@dataclass(frozen=True, slots=True)
class ValuationAuthorityScope:
    """Exact tenant, legal-book, and instrument scope for valuation authority."""

    tenant_id: str
    legal_book_id: str
    security_id: str

    def __post_init__(self) -> None:
        for field_name in ("tenant_id", "legal_book_id", "security_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)

    @property
    def key(self) -> tuple[str, str, str]:
        """Return the canonical lookup identity without implicit defaults."""

        return (self.tenant_id, self.legal_book_id, self.security_id)

    @property
    def book_scope(self) -> ValuationBookScope:
        """Return the portfolio-owned tenant and legal-book dimensions."""

        return ValuationBookScope(
            tenant_id=self.tenant_id,
            legal_book_id=self.legal_book_id,
        )


def resolve_optional_valuation_book_scope(
    *,
    tenant_id: str | None,
    legal_book_id: str | None,
) -> ValuationBookScope | None:
    """Resolve staged scope metadata without accepting a partially scoped portfolio."""

    if tenant_id is None and legal_book_id is None:
        return None
    if tenant_id is None or legal_book_id is None:
        raise ValueError("tenant_id and legal_book_id must be supplied together")
    return ValuationBookScope(tenant_id=tenant_id, legal_book_id=legal_book_id)


@dataclass(frozen=True, slots=True)
class MarketPriceSourceFact:
    """One source-lineaged market price with an explicit quote representation."""

    scope: ValuationAuthorityScope
    price_date: date
    price: Decimal
    currency: str
    quote_basis: MarketPriceQuoteBasis
    source_reference: FinancialSourceReference

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ValuationAuthorityScope):
            raise TypeError("scope must be a ValuationAuthorityScope")
        if type(self.price_date) is not date:
            raise TypeError("price_date must be an exact date")
        if not isinstance(self.price, Decimal):
            raise TypeError("price must be a Decimal")
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("price must be a positive finite Decimal")
        object.__setattr__(self, "currency", normalize_currency_code(self.currency))
        if not isinstance(self.quote_basis, MarketPriceQuoteBasis):
            raise TypeError("quote_basis must be a MarketPriceQuoteBasis")
        if not isinstance(self.source_reference, FinancialSourceReference):
            raise TypeError("source_reference must be a FinancialSourceReference")

    def content_hash(self) -> str:
        """Bind scope, representation, value, and source evidence deterministically."""

        return cast(
            str,
            canonical_content_hash(
                {
                    "currency": self.currency,
                    "legal_book_id": self.scope.legal_book_id,
                    "price": self.price,
                    "price_date": self.price_date,
                    "quote_basis": self.quote_basis,
                    "security_id": self.scope.security_id,
                    "source_reference": self.source_reference.lineage_payload(),
                    "tenant_id": self.scope.tenant_id,
                }
            ),
        )
