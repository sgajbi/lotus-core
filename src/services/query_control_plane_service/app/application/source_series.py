"""Shared source-proof policy for canonical time-series products."""

from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, datetime
from typing import Any, Literal, Protocol, cast

from portfolio_common.request_fingerprints import series_request_fingerprint
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.common import IntegrationWindow
from .source_evidence import latest_evidence_timestamp

SourceSeriesCompleteness = Literal["COMPLETE", "PARTIAL", "EMPTY"]


class SourceSeriesRequest(Protocol):
    """Request fields required to identify a source series window."""

    as_of_date: date
    window: IntegrationWindow

    def model_dump(self, *, mode: Literal["json"]) -> dict[str, Any]: ...


class SourceSeriesEvidence(Protocol):
    """Evidence fields required by shared series quality policy."""

    @property
    def series_date(self) -> date: ...

    @property
    def series_currency(self) -> str: ...

    @property
    def quality_status(self) -> str: ...

    @property
    def observed_at(self) -> datetime | None: ...

    @property
    def created_at(self) -> datetime | None: ...

    @property
    def updated_at(self) -> datetime | None: ...


def build_source_series_metadata(
    *,
    product_name: str,
    series_kind: str,
    identifier_key: str,
    identifier_value: str,
    request: SourceSeriesRequest,
    rows: Sequence[SourceSeriesEvidence],
    generated_at: datetime,
) -> dict[str, object]:
    """Build deterministic identity, completeness, freshness, and lineage metadata."""

    completeness = source_series_completeness(
        rows,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )
    latest_evidence = latest_evidence_timestamp(rows)
    request_fingerprint = series_request_fingerprint(
        series_key=series_kind,
        identifier_key=identifier_key,
        identifier_value=identifier_value,
        request=request,
    )
    content_hash = stable_content_hash(
        {
            "product_name": product_name,
            "product_version": "v1",
            "series_kind": series_kind,
            identifier_key: identifier_value,
            "request": request.model_dump(mode="json"),
            "records": [asdict(cast(Any, row)) for row in rows],
            "completeness_status": completeness,
            "latest_evidence_timestamp": latest_evidence,
        }
    )
    current = completeness == "COMPLETE" and latest_evidence is not None
    runtime = source_data_product_runtime_metadata(
        generated_at=generated_at,
        as_of_date=request.as_of_date,
        data_quality_status=(
            "COMPLETE" if completeness == "COMPLETE" else "EMPTY" if not rows else "PARTIAL"
        ),
        latest_evidence_timestamp=latest_evidence,
        content_hash=content_hash,
        source_refs=[
            f"lotus-core://source/{product_name}/{series_kind}/{identifier_value}/"
            f"{request.window.start_date.isoformat()}/{request.window.end_date.isoformat()}"
        ],
        lineage={
            "source_owner": "lotus-core",
            "source_product": product_name,
            "series_kind": series_kind,
        },
        source_evidence_current=current,
        freshness_status="CURRENT" if current else "UNAVAILABLE" if not rows else "PARTIAL",
        use_content_hash_as_source_batch_fingerprint=True,
    )
    return {
        "request_fingerprint": request_fingerprint,
        "record_count": len(rows),
        "completeness_status": completeness,
        **runtime,
    }


def source_series_completeness(
    rows: Sequence[SourceSeriesEvidence], *, start_date: date, end_date: date
) -> SourceSeriesCompleteness:
    """Classify quality, currency consistency, and requested boundary coverage."""

    if not rows:
        return "EMPTY"
    accepted = all(row.quality_status.strip().upper() in {"ACCEPTED", "COMPLETE"} for row in rows)
    one_currency = len({row.series_currency.strip().upper() for row in rows}) == 1
    covers_boundaries = rows[0].series_date == start_date and rows[-1].series_date == end_date
    return "COMPLETE" if accepted and one_currency and covers_boundaries else "PARTIAL"
