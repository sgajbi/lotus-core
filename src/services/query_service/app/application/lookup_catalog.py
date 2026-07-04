from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PortfolioLookupQuery:
    client_id: str | None
    booking_center_code: str | None
    q: str | None
    limit: int


@dataclass(frozen=True, slots=True)
class InstrumentLookupQuery:
    product_type: str | None
    q: str | None
    limit: int


@dataclass(frozen=True, slots=True)
class CurrencyLookupQuery:
    source: str
    q: str | None
    limit: int


@dataclass(frozen=True, slots=True)
class LookupCatalogItem:
    id: str
    label: str

    @classmethod
    def from_raw(cls, item: Any) -> LookupCatalogItem:
        if isinstance(item, dict):
            return cls(id=str(item.get("id", "")), label=str(item.get("label", "")))
        return cls(id=str(item.id), label=str(item.label))


@dataclass(frozen=True, slots=True)
class LookupCatalogResult:
    items: list[LookupCatalogItem] = field(default_factory=list)
