"""Economic response-page identity, deliberately not an authoritative source cut."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Sequence

from portfolio_common.source_data_product_metadata import stable_content_hash
from pydantic import BaseModel

from .analytics_quality import analytics_source_runtime_metadata, timeseries_source_evidence_current


def canonical_economic_value(value: Any) -> Any:
    """Canonicalize decimals without context rounding or exponent expansion."""

    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Economic content identity requires finite decimals.")
        if not value:
            return {"decimal": "0"}
        sign, digits, raw_exponent = value.as_tuple()
        exponent = int(raw_exponent)
        coefficient = list(digits)
        while coefficient[-1] == 0:
            coefficient.pop()
            exponent += 1
        return {"decimal": f"{'-' if sign else ''}{''.join(map(str, coefficient))}e{exponent}"}
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: canonical_economic_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical_economic_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    raise ValueError(f"Unsupported economic content value: {type(value).__name__}")


def analytics_page_content_identity(
    *,
    product: str,
    request_scope: str,
    rows: Sequence[BaseModel],
    data_quality_status: str,
) -> dict[str, object]:
    """Hash actual rows and requested economic basis, excluding transport timestamps.

    Row order and decimal presentation do not change identity. Duplicate rows remain
    counted. The request scope supplies basis, never substitutes for economic rows.
    No comparable full-window source cut, ingestion lineage or snapshot is inferred.
    """

    canonical_rows = [canonical_economic_value(row.model_dump(mode="python")) for row in rows]
    canonical_rows.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
    return {
        "content_hash": stable_content_hash(
            {
                "identity_version": "analytics-response-page-v1",
                "product": product,
                "request_scope": request_scope,
                "data_quality_status": data_quality_status,
                "rows": canonical_rows,
            }
        ),
        "lineage": {"content_identity_scope": "response_page", "source_cut_status": "UNAVAILABLE"},
    }


def analytics_page_runtime_metadata(
    *,
    product: str,
    request_scope: str,
    rows: Sequence[BaseModel],
    as_of_date: date,
    generated_at: datetime,
    data_quality_status: str,
) -> dict[str, object]:
    """Compose page content identity with the existing source evidence policy."""

    return analytics_source_runtime_metadata(
        **analytics_page_content_identity(
            product=product,
            request_scope=request_scope,
            rows=rows,
            data_quality_status=data_quality_status,
        ),
        as_of_date=as_of_date,
        generated_at=generated_at,
        data_quality_status=data_quality_status,
        source_evidence_current=timeseries_source_evidence_current(
            data_quality_status=data_quality_status
        ),
    )
