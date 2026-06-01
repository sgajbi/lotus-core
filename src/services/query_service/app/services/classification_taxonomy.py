from __future__ import annotations

from datetime import date
from typing import Any

from ..dtos.reference_integration_dto import ClassificationTaxonomyResponse
from .reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
)
from .reference_data_mappers import classification_taxonomy_entry
from .request_fingerprint import request_fingerprint
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


def build_classification_taxonomy_response(
    *,
    as_of_date: date,
    taxonomy_scope: str | None,
    rows: list[Any],
) -> ClassificationTaxonomyResponse:
    taxonomy_request_fingerprint = request_fingerprint(
        {
            "taxonomy_key": "classification_taxonomy",
            "as_of_date": as_of_date.isoformat(),
            "taxonomy_scope": taxonomy_scope,
        }
    )
    return ClassificationTaxonomyResponse(
        as_of_date=as_of_date,
        records=[classification_taxonomy_entry(row) for row in rows],
        request_fingerprint=taxonomy_request_fingerprint,
        **source_product_runtime_metadata_without_as_of_date(
            as_of_date,
            data_quality_status=market_reference_data_quality_status(
                rows,
                required_count=len(rows),
            ),
            latest_evidence_timestamp=latest_reference_evidence_timestamp(rows),
        ),
    )
