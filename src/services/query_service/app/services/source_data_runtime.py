from __future__ import annotations

from datetime import date, datetime

from ..dtos.source_data_product_identity import source_data_product_runtime_metadata


def source_product_runtime_metadata(
    as_of_date: date,
    *,
    tenant_id: str | None = None,
    data_quality_status: str | None = None,
    latest_evidence_timestamp: datetime | None = None,
    content_hash: str | None = None,
    source_refs: list[str] | None = None,
    lineage: dict[str, str] | None = None,
) -> dict[str, object]:
    return source_data_product_runtime_metadata(
        as_of_date=as_of_date,
        tenant_id=tenant_id,
        data_quality_status=data_quality_status or "UNKNOWN",
        latest_evidence_timestamp=latest_evidence_timestamp,
        content_hash=content_hash,
        source_refs=source_refs,
        lineage=lineage,
    )


def source_product_runtime_metadata_without_as_of_date(
    as_of_date: date,
    *,
    tenant_id: str | None = None,
    data_quality_status: str | None = None,
    latest_evidence_timestamp: datetime | None = None,
    content_hash: str | None = None,
    source_refs: list[str] | None = None,
    lineage: dict[str, str] | None = None,
) -> dict[str, object]:
    metadata = source_product_runtime_metadata(
        as_of_date,
        tenant_id=tenant_id,
        data_quality_status=data_quality_status,
        latest_evidence_timestamp=latest_evidence_timestamp,
        content_hash=content_hash,
        source_refs=source_refs,
        lineage=lineage,
    )
    metadata.pop("as_of_date")
    return metadata
