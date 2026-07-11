"""Deterministic source metadata for transaction-economics products."""

from datetime import date, datetime
from typing import Any, cast

from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)


def transaction_economics_runtime_metadata(
    *,
    product_name: str,
    portfolio_id: str,
    as_of_date: date,
    generated_at: datetime,
    tenant_id: str | None,
    data_quality_status: str,
    latest_evidence_timestamp: datetime | None,
    content_payload: dict[str, Any],
    lineage: dict[str, str],
) -> dict[str, object]:
    """Build stable proof metadata without duplicating volatile response fields."""

    content_hash = stable_content_hash(content_payload)
    metadata = source_data_product_runtime_metadata(
        as_of_date=as_of_date,
        generated_at=generated_at,
        tenant_id=tenant_id,
        data_quality_status=data_quality_status,
        latest_evidence_timestamp=latest_evidence_timestamp,
        content_hash=content_hash,
        source_refs=[f"lotus-core://source/{product_name}/{portfolio_id}/{as_of_date.isoformat()}"],
        lineage={"source_product": product_name, "source_owner": "lotus-core", **lineage},
        use_content_hash_as_source_batch_fingerprint=True,
    )
    metadata.pop("as_of_date")
    return cast(dict[str, object], metadata)
