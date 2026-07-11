"""Deterministic source metadata for DPM readiness products."""

from datetime import date, datetime
from typing import Any, cast

from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)


def dpm_source_runtime_metadata(
    *,
    product_name: str,
    source_key: str,
    as_of_date: date,
    generated_at: datetime,
    tenant_id: str | None,
    data_quality_status: str,
    latest_evidence_timestamp: datetime | None,
    content_payload: dict[str, Any],
    lineage: dict[str, str],
    source_evidence_current: bool | None = None,
    freshness_status: str | None = None,
) -> dict[str, object]:
    """Build source-owned proof metadata excluding volatile generation time from its hash."""

    content_hash = stable_content_hash(content_payload)
    return cast(
        dict[str, object],
        source_data_product_runtime_metadata(
            as_of_date=as_of_date,
            generated_at=generated_at,
            tenant_id=tenant_id,
            data_quality_status=data_quality_status,
            latest_evidence_timestamp=latest_evidence_timestamp,
            content_hash=content_hash,
            source_refs=[
                f"lotus-core://source/{product_name}/{source_key}/{as_of_date.isoformat()}"
            ],
            lineage={"source_product": product_name, "source_owner": "lotus-core", **lineage},
            source_evidence_current=source_evidence_current,
            freshness_status=freshness_status,
            use_content_hash_as_source_batch_fingerprint=True,
        ),
    )
