from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from ..dtos.reporting_dto import AllocationDimension
from .reporting_classification import resolve_region

ZERO = Decimal("0")
UNCLASSIFIED_BUCKET = "UNCLASSIFIED"


@dataclass(frozen=True, slots=True)
class AllocationInputRow:
    instrument: Any | None
    snapshot: Any
    market_value_reporting_currency: Decimal


@dataclass(frozen=True, slots=True)
class AllocationBucketResult:
    dimension_value: str
    market_value_reporting_currency: Decimal
    weight: Decimal
    position_count: int


@dataclass(frozen=True, slots=True)
class AllocationViewResult:
    dimension: AllocationDimension
    total_market_value_reporting_currency: Decimal
    buckets: tuple[AllocationBucketResult, ...]


@dataclass(frozen=True, slots=True)
class AllocationCalculationResult:
    total_market_value_reporting_currency: Decimal
    views: tuple[AllocationViewResult, ...]


AllocationAccessor = Callable[[Any | None, Any], object | None]

ALLOCATION_DIMENSION_ACCESSORS: dict[AllocationDimension, AllocationAccessor] = {
    "asset_class": lambda instrument, snapshot: instrument.asset_class if instrument else None,
    "currency": lambda instrument, snapshot: (
        instrument.currency if instrument and instrument.currency else snapshot.security_id
    ),
    "sector": lambda instrument, snapshot: instrument.sector if instrument else None,
    "country": lambda instrument, snapshot: instrument.country_of_risk if instrument else None,
    "region": lambda instrument, snapshot: (
        resolve_region(instrument.country_of_risk) if instrument else None
    ),
    "product_type": lambda instrument, snapshot: instrument.product_type if instrument else None,
    "rating": lambda instrument, snapshot: instrument.rating if instrument else None,
    "issuer_id": lambda instrument, snapshot: instrument.issuer_id if instrument else None,
    "issuer_name": lambda instrument, snapshot: instrument.issuer_name if instrument else None,
    "ultimate_parent_issuer_id": (
        lambda instrument, snapshot: instrument.ultimate_parent_issuer_id if instrument else None
    ),
    "ultimate_parent_issuer_name": (
        lambda instrument, snapshot: instrument.ultimate_parent_issuer_name if instrument else None
    ),
}


def calculate_allocation_views(
    *,
    rows: list[AllocationInputRow],
    dimensions: list[AllocationDimension],
) -> AllocationCalculationResult:
    total_market_value = sum(
        (row.market_value_reporting_currency for row in rows),
        ZERO,
    )
    views_payload: dict[AllocationDimension, dict[str, Decimal]] = {
        dimension: defaultdict(lambda: ZERO) for dimension in dimensions
    }
    views_position_counts: dict[AllocationDimension, dict[str, int]] = {
        dimension: defaultdict(int) for dimension in dimensions
    }

    for row in rows:
        for dimension in dimensions:
            accessor = ALLOCATION_DIMENSION_ACCESSORS[dimension]
            raw_value = accessor(row.instrument, row.snapshot)
            bucket_key = str(raw_value or UNCLASSIFIED_BUCKET)
            views_payload[dimension][bucket_key] += row.market_value_reporting_currency
            views_position_counts[dimension][bucket_key] += 1

    views: list[AllocationViewResult] = []
    for dimension in dimensions:
        buckets = [
            AllocationBucketResult(
                dimension_value=bucket_key,
                market_value_reporting_currency=bucket_value,
                weight=(bucket_value / total_market_value if total_market_value else ZERO),
                position_count=views_position_counts[dimension][bucket_key],
            )
            for bucket_key, bucket_value in sorted(views_payload[dimension].items())
        ]
        views.append(
            AllocationViewResult(
                dimension=dimension,
                total_market_value_reporting_currency=total_market_value,
                buckets=tuple(buckets),
            )
        )

    return AllocationCalculationResult(
        total_market_value_reporting_currency=total_market_value,
        views=tuple(views),
    )
