"""Application use case for governed classification taxonomy evidence."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import cast

from portfolio_common.market_reference_quality import (
    BLOCKING_QUALITY_STATUSES,
    PARTIAL_QUALITY_STATUSES,
    STALE_QUALITY_STATUSES,
    MarketReferenceCoverageSignal,
    classify_market_reference_coverage,
)
from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.classification_taxonomy import (
    ClassificationTaxonomyEntry,
    ClassificationTaxonomyRequest,
    ClassificationTaxonomyResponse,
)
from ..domain.classification_taxonomy import ClassificationTaxonomyEvidence
from ..ports.classification_taxonomy import ClassificationTaxonomyReader
from .source_evidence import latest_evidence_timestamp


class ClassificationTaxonomyService:
    """Resolve taxonomy evidence through a persistence-independent read port."""

    def __init__(
        self,
        *,
        reader: ClassificationTaxonomyReader,
        clock: Callable[[], datetime],
    ) -> None:
        self._reader = reader
        self._clock = clock

    async def get(
        self, *, request: ClassificationTaxonomyRequest
    ) -> ClassificationTaxonomyResponse:
        records = sorted(
            await self._reader.list_effective(
                as_of_date=request.as_of_date,
                taxonomy_scope=request.taxonomy_scope,
            ),
            key=lambda row: (
                row.taxonomy_scope,
                row.dimension_name,
                row.dimension_value,
                row.effective_from,
                row.classification_set_id,
            ),
        )
        return build_classification_taxonomy_response(
            request=request,
            records=records,
            generated_at=self._clock(),
        )


def build_classification_taxonomy_response(
    *,
    request: ClassificationTaxonomyRequest,
    records: list[ClassificationTaxonomyEvidence],
    generated_at: datetime,
) -> ClassificationTaxonomyResponse:
    """Build deterministic taxonomy content and source-owned supportability metadata."""

    quality_status = _data_quality_status(records)
    evidence_timestamp = latest_evidence_timestamp(records)
    content_hash = cast(
        str,
        stable_content_hash(
            {
                "product_name": "InstrumentReferenceBundle",
                "product_version": "v1",
                "as_of_date": request.as_of_date,
                "taxonomy_scope": request.taxonomy_scope,
                "records": [asdict(record) for record in records],
                "latest_evidence_timestamp": evidence_timestamp,
            }
        ),
    )
    current = quality_status == "COMPLETE"
    metadata = source_data_product_runtime_metadata(
        generated_at=generated_at,
        as_of_date=request.as_of_date,
        data_quality_status=quality_status,
        latest_evidence_timestamp=evidence_timestamp,
        content_hash=content_hash,
        source_refs=[
            "lotus-core://source/InstrumentReferenceBundle/"
            f"{request.taxonomy_scope or 'all'}/{request.as_of_date.isoformat()}"
        ],
        lineage={
            "source_owner": "lotus-core",
            "source_product": "InstrumentReferenceBundle",
            "taxonomy_scope": request.taxonomy_scope or "all",
            "source_system": "lotus-core",
        },
        source_evidence_current=current,
        freshness_status="CURRENT" if current else quality_status,
        use_content_hash_as_source_batch_fingerprint=True,
    )
    return ClassificationTaxonomyResponse(
        records=[_to_contract(record) for record in records],
        request_fingerprint=request_fingerprint(
            {
                "taxonomy_key": "classification_taxonomy",
                "as_of_date": request.as_of_date.isoformat(),
                "taxonomy_scope": request.taxonomy_scope,
            }
        ),
        **metadata,
    )


def _to_contract(record: ClassificationTaxonomyEvidence) -> ClassificationTaxonomyEntry:
    return ClassificationTaxonomyEntry(
        classification_set_id=record.classification_set_id,
        taxonomy_scope=record.taxonomy_scope,
        dimension_name=record.dimension_name,
        dimension_value=record.dimension_value,
        dimension_description=record.dimension_description,
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        quality_status=record.quality_status,
    )


def _data_quality_status(records: list[ClassificationTaxonomyEvidence]) -> str:
    if not records:
        return "UNKNOWN"
    statuses = [record.quality_status.strip().upper() for record in records]
    return cast(
        str,
        classify_market_reference_coverage(
            MarketReferenceCoverageSignal(
                required_count=len(records),
                observed_count=len(statuses),
                stale_count=_status_count(statuses, STALE_QUALITY_STATUSES),
                estimated_count=_status_count(statuses, PARTIAL_QUALITY_STATUSES),
                blocking_count=_status_count(statuses, BLOCKING_QUALITY_STATUSES),
            )
        ),
    )


def _status_count(statuses: list[str], status_family: set[str]) -> int:
    return sum(status in status_family for status in statuses)
