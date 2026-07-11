"""Application use case for the effective index definition catalog."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.index_catalog import (
    IndexCatalogRequest,
    IndexCatalogResponse,
    IndexDefinitionResponse,
)
from ..domain.index_definition import IndexDefinitionEvidence
from ..ports.index_definition import IndexDefinitionReader

CatalogCompleteness = Literal["COMPLETE", "PARTIAL", "EMPTY"]


class IndexCatalogService:
    """Resolve deterministic index masters through a persistence-independent port."""

    def __init__(self, *, reader: IndexDefinitionReader, clock: Callable[[], datetime]) -> None:
        self._reader = reader
        self._clock = clock

    async def list(self, *, request: IndexCatalogRequest) -> IndexCatalogResponse:
        definitions = await self._reader.list_definitions(
            as_of_date=request.as_of_date,
            index_ids=request.index_ids,
            index_currency=request.index_currency,
            index_type=request.index_type,
            index_status=request.index_status,
        )
        return build_index_catalog_response(
            request=request,
            definitions=definitions,
            generated_at=self._clock(),
        )


def build_index_catalog_response(
    *,
    request: IndexCatalogRequest,
    definitions: list[IndexDefinitionEvidence],
    generated_at: datetime,
) -> IndexCatalogResponse:
    """Build ordered index records and deterministic collection source proof."""

    records = [_record(definition) for definition in definitions]
    completeness = _completeness(definitions)
    latest_evidence = _latest_evidence(definitions)
    quality_complete = completeness == "COMPLETE"
    content_hash = stable_content_hash(
        {
            "product_name": "IndexDefinition",
            "product_version": "v1",
            "request": request.model_dump(mode="json"),
            "definitions": [asdict(definition) for definition in definitions],
            "completeness_status": completeness,
            "latest_evidence_timestamp": latest_evidence,
        }
    )
    metadata = source_data_product_runtime_metadata(
        generated_at=generated_at,
        as_of_date=request.as_of_date,
        data_quality_status=(
            "COMPLETE" if quality_complete else "EMPTY" if not records else "PARTIAL"
        ),
        latest_evidence_timestamp=latest_evidence,
        content_hash=content_hash,
        source_refs=[
            f"lotus-core://source/IndexDefinition/catalog/{request.as_of_date.isoformat()}"
        ],
        lineage={
            "source_owner": "lotus-core",
            "source_product": "IndexDefinition",
            "catalog_scope": "effective_definitions",
        },
        source_evidence_current=quality_complete,
        freshness_status="CURRENT"
        if quality_complete
        else "UNAVAILABLE"
        if not records
        else "PARTIAL",
        use_content_hash_as_source_batch_fingerprint=True,
    )
    return IndexCatalogResponse(
        records=records,
        record_count=len(records),
        completeness_status=completeness,
        **metadata,
    )


def _record(definition: IndexDefinitionEvidence) -> IndexDefinitionResponse:
    return IndexDefinitionResponse(
        index_id=definition.index_id,
        index_name=definition.index_name,
        index_currency=definition.index_currency,
        index_type=definition.index_type,
        index_status=definition.index_status,
        index_provider=definition.index_provider,
        index_market=definition.index_market,
        classification_set_id=definition.classification_set_id,
        classification_labels=dict(definition.classification_labels),
        effective_from=definition.effective_from,
        effective_to=definition.effective_to,
        quality_status=definition.quality_status,
        source_timestamp=definition.source_timestamp,
        source_vendor=definition.source_vendor,
        source_record_id=definition.source_record_id,
    )


def _completeness(definitions: list[IndexDefinitionEvidence]) -> CatalogCompleteness:
    if not definitions:
        return "EMPTY"
    accepted = {"ACCEPTED", "COMPLETE"}
    return (
        "COMPLETE"
        if all(definition.quality_status.strip().upper() in accepted for definition in definitions)
        else "PARTIAL"
    )


def _latest_evidence(definitions: list[IndexDefinitionEvidence]) -> datetime | None:
    timestamps = [
        timestamp
        for definition in definitions
        for timestamp in (definition.source_timestamp, definition.updated_at, definition.created_at)
        if timestamp is not None
    ]
    return max(timestamps) if timestamps else None
