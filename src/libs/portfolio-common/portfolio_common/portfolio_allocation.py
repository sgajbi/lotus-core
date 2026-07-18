"""Pure portfolio allocation aggregation policy shared by serving planes."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext
from heapq import heappush, heapreplace
from typing import Any, Callable, Literal

from .domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
    canonical_content_hash,
)
from .portfolio_geography import resolve_region

AllocationDimension = Literal[
    "asset_class",
    "currency",
    "sector",
    "country",
    "region",
    "product_type",
    "rating",
    "issuer_id",
    "issuer_name",
    "ultimate_parent_issuer_id",
    "ultimate_parent_issuer_name",
]

ZERO = Decimal("0")
UNCLASSIFIED_BUCKET = "UNCLASSIFIED"
ALLOCATION_ALGORITHM_ID = "PORTFOLIO_ALLOCATION"
ALLOCATION_ALGORITHM_VERSION = 1
ALLOCATION_INTERMEDIATE_PRECISION = 28

AllocationContributorType = Literal["direct_position", "look_through_component"]


@dataclass(frozen=True, slots=True)
class AllocationContributorInput:
    """Source-owned identity for one allocation contribution row."""

    contributor_type: AllocationContributorType
    portfolio_id: str
    security_id: str
    booked_security_id: str
    source_snapshot_id: int
    component_record_id: int | None = None
    component_weight: Decimal | None = None
    component_effective_from: date | None = None
    component_effective_to: date | None = None
    component_source_system: str | None = None
    component_source_record_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("portfolio_id", "security_id", "booked_security_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be nonblank")
        if self.source_snapshot_id < 1:
            raise ValueError("source_snapshot_id must be positive")
        if self.contributor_type == "direct_position":
            if self.security_id != self.booked_security_id:
                raise ValueError("direct contributor security must equal booked security")
            if self.component_record_id is not None or self.component_weight is not None:
                raise ValueError("direct contributor cannot carry component identity")
            return
        if self.component_record_id is None or self.component_record_id < 1:
            raise ValueError("look-through contributor requires a positive component_record_id")
        if self.component_weight is None or not self.component_weight.is_finite():
            raise ValueError("look-through contributor requires a finite component_weight")
        if self.component_effective_from is None:
            raise ValueError("look-through contributor requires component_effective_from")
        if (
            self.component_effective_to is not None
            and self.component_effective_to < self.component_effective_from
        ):
            raise ValueError("component effective interval is invalid")

    def lineage_payload(self) -> dict[str, object]:
        """Return the exact identity and source facts consumed by allocation."""

        return {
            "booked_security_id": self.booked_security_id,
            "component_effective_from": self.component_effective_from,
            "component_effective_to": self.component_effective_to,
            "component_record_id": self.component_record_id,
            "component_source_record_id": self.component_source_record_id,
            "component_source_system": self.component_source_system,
            "component_weight": self.component_weight,
            "contributor_type": self.contributor_type,
            "portfolio_id": self.portfolio_id,
            "security_id": self.security_id,
            "source_snapshot_id": self.source_snapshot_id,
        }


@dataclass(frozen=True, slots=True)
class AllocationInputRow:
    instrument: Any | None
    snapshot: Any
    market_value_reporting_currency: Decimal
    contributor: AllocationContributorInput | None = None


@dataclass(frozen=True, slots=True)
class AllocationContributorResult:
    contributor: AllocationContributorInput
    market_value_reporting_currency: Decimal
    bucket_weight: Decimal | None


@dataclass(frozen=True, slots=True)
class AllocationBucketResult:
    dimension_value: str
    market_value_reporting_currency: Decimal
    weight: Decimal
    position_count: int
    contributor_count: int
    contributors: tuple[AllocationContributorResult, ...]
    contributors_truncated: bool
    omitted_market_value_reporting_currency: Decimal


@dataclass(frozen=True, slots=True)
class AllocationViewResult:
    dimension: AllocationDimension
    total_market_value_reporting_currency: Decimal
    buckets: tuple[AllocationBucketResult, ...]


@dataclass(frozen=True, slots=True)
class AllocationCalculationResult:
    total_market_value_reporting_currency: Decimal
    views: tuple[AllocationViewResult, ...]
    calculation_lineage: CalculationLineage


@dataclass(slots=True)
class _RankedContributor:
    """Heap candidate ordered so the least-preferred retained row is at index zero."""

    rank: tuple[object, ...]
    contributor: AllocationContributorInput
    market_value_reporting_currency: Decimal

    def __lt__(self, other: "_RankedContributor") -> bool:
        return self.rank > other.rank


@dataclass(slots=True)
class _BucketAccumulator:
    market_value_reporting_currency: Decimal = ZERO
    position_count: int = 0
    contributor_count: int = 0
    retained: list[_RankedContributor] = field(default_factory=list)

    def add(self, row: AllocationInputRow, contributor_limit: int) -> None:
        self.market_value_reporting_currency += row.market_value_reporting_currency
        self.position_count += 1
        if row.contributor is None:
            return
        self.contributor_count += 1
        if contributor_limit < 1:
            return
        candidate = _RankedContributor(
            rank=_contributor_rank(row.contributor, row.market_value_reporting_currency),
            contributor=row.contributor,
            market_value_reporting_currency=row.market_value_reporting_currency,
        )
        if len(self.retained) < contributor_limit:
            heappush(self.retained, candidate)
        elif candidate.rank < self.retained[0].rank:
            heapreplace(self.retained, candidate)


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

UPPERCASE_ALLOCATION_DIMENSIONS: set[AllocationDimension] = {
    "asset_class",
    "currency",
    "sector",
    "country",
    "rating",
    "issuer_id",
    "ultimate_parent_issuer_id",
}


def _allocation_bucket_key(dimension: AllocationDimension, raw_value: object | None) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return UNCLASSIFIED_BUCKET
    if dimension in UPPERCASE_ALLOCATION_DIMENSIONS:
        return value.upper()
    return value


def _contributor_rank(
    contributor: AllocationContributorInput,
    market_value_reporting_currency: Decimal,
) -> tuple[object, ...]:
    return (
        -abs(market_value_reporting_currency),
        contributor.portfolio_id,
        contributor.booked_security_id,
        contributor.security_id,
        contributor.contributor_type,
        contributor.source_snapshot_id,
        contributor.component_record_id or 0,
        contributor.component_source_system or "",
        contributor.component_source_record_id or "",
    )


def _retained_contributors(
    accumulator: _BucketAccumulator,
) -> tuple[AllocationContributorResult, ...]:
    return tuple(
        AllocationContributorResult(
            contributor=candidate.contributor,
            market_value_reporting_currency=candidate.market_value_reporting_currency,
            bucket_weight=(
                candidate.market_value_reporting_currency
                / accumulator.market_value_reporting_currency
                if accumulator.market_value_reporting_currency
                else None
            ),
        )
        for candidate in sorted(accumulator.retained, key=lambda item: item.rank)
    )


def _row_lineage_payload(
    row: AllocationInputRow,
    dimensions: list[AllocationDimension],
) -> dict[str, object]:
    if not row.market_value_reporting_currency.is_finite():
        raise ValueError("allocation market value must be finite")
    return {
        "classifications": {
            dimension: _allocation_bucket_key(
                dimension,
                ALLOCATION_DIMENSION_ACCESSORS[dimension](row.instrument, row.snapshot),
            )
            for dimension in dimensions
        },
        "contributor": row.contributor.lineage_payload() if row.contributor else None,
        "market_value_reporting_currency": row.market_value_reporting_currency,
        "security_id": str(getattr(row.snapshot, "security_id", "")).strip(),
    }


def _allocation_output_payload(
    *,
    total_market_value: Decimal,
    views: list[AllocationViewResult],
) -> dict[str, object]:
    return {
        "total_market_value_reporting_currency": total_market_value,
        "views": [
            {
                "buckets": [
                    {
                        "contributor_count": bucket.contributor_count,
                        "contributors": [
                            {
                                **contributor.contributor.lineage_payload(),
                                "bucket_weight": contributor.bucket_weight,
                                "market_value_reporting_currency": (
                                    contributor.market_value_reporting_currency
                                ),
                            }
                            for contributor in bucket.contributors
                        ],
                        "contributors_truncated": bucket.contributors_truncated,
                        "dimension_value": bucket.dimension_value,
                        "market_value_reporting_currency": (bucket.market_value_reporting_currency),
                        "omitted_market_value_reporting_currency": (
                            bucket.omitted_market_value_reporting_currency
                        ),
                        "position_count": bucket.position_count,
                        "weight": bucket.weight,
                    }
                    for bucket in view.buckets
                ],
                "dimension": view.dimension,
                "total_market_value_reporting_currency": (
                    view.total_market_value_reporting_currency
                ),
            }
            for view in views
        ],
    }


def calculate_allocation_views(
    *,
    rows: list[AllocationInputRow],
    dimensions: list[AllocationDimension],
    contributor_limit_per_bucket: int = 0,
    calculation_context: Mapping[str, object] | None = None,
) -> AllocationCalculationResult:
    if contributor_limit_per_bucket < 0:
        raise ValueError("contributor_limit_per_bucket cannot be negative")
    input_rows = [_row_lineage_payload(row, dimensions) for row in rows]
    input_rows.sort(key=canonical_content_hash)

    with localcontext() as context:
        context.prec = ALLOCATION_INTERMEDIATE_PRECISION
        total_market_value = sum(
            (row.market_value_reporting_currency for row in rows),
            ZERO,
        )
        views_payload: dict[
            AllocationDimension,
            dict[str, _BucketAccumulator],
        ] = {dimension: defaultdict(_BucketAccumulator) for dimension in dimensions}

        for row in rows:
            for dimension in dimensions:
                accessor = ALLOCATION_DIMENSION_ACCESSORS[dimension]
                raw_value = accessor(row.instrument, row.snapshot)
                bucket_key = _allocation_bucket_key(dimension, raw_value)
                views_payload[dimension][bucket_key].add(
                    row,
                    contributor_limit_per_bucket,
                )

        views: list[AllocationViewResult] = []
        for dimension in dimensions:
            buckets: list[AllocationBucketResult] = []
            for bucket_key, accumulator in sorted(views_payload[dimension].items()):
                contributors = _retained_contributors(accumulator)
                retained_market_value = sum(
                    (contributor.market_value_reporting_currency for contributor in contributors),
                    ZERO,
                )
                buckets.append(
                    AllocationBucketResult(
                        dimension_value=bucket_key,
                        market_value_reporting_currency=(
                            accumulator.market_value_reporting_currency
                        ),
                        weight=(
                            accumulator.market_value_reporting_currency / total_market_value
                            if total_market_value
                            else ZERO
                        ),
                        position_count=accumulator.position_count,
                        contributor_count=accumulator.contributor_count,
                        contributors=contributors,
                        contributors_truncated=(accumulator.contributor_count > len(contributors)),
                        omitted_market_value_reporting_currency=(
                            accumulator.market_value_reporting_currency - retained_market_value
                        ),
                    )
                )
            views.append(
                AllocationViewResult(
                    dimension=dimension,
                    total_market_value_reporting_currency=total_market_value,
                    buckets=tuple(buckets),
                )
            )

        output_payload = _allocation_output_payload(
            total_market_value=total_market_value,
            views=views,
        )
        lineage = build_calculation_lineage(
            algorithm_id=ALLOCATION_ALGORITHM_ID,
            algorithm_version=ALLOCATION_ALGORITHM_VERSION,
            intermediate_precision=ALLOCATION_INTERMEDIATE_PRECISION,
            input_payload={
                "calculation_context": dict(calculation_context or {}),
                "contributor_limit_per_bucket": contributor_limit_per_bucket,
                "dimensions": dimensions,
                "rows": input_rows,
            },
            output_payload=output_payload,
        )

    return AllocationCalculationResult(
        total_market_value_reporting_currency=total_market_value,
        views=tuple(views),
        calculation_lineage=lineage,
    )
