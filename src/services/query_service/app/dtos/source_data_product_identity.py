from datetime import UTC, date, datetime

from portfolio_common.logging_utils import correlation_id_var, normalize_lineage_value
from portfolio_common.reconciliation_quality import UNKNOWN
from portfolio_common.reconstruction_identity import CURRENT_RESTATEMENT_VERSION
from pydantic import BaseModel, Field


def product_name_field(product_name: str):
    return Field(
        product_name,
        description="RFC-0083 source-data product name represented by this response.",
        examples=[product_name],
    )


def product_version_field():
    return Field(
        "v1",
        description="RFC-0083 source-data product version represented by this response.",
        examples=["v1"],
    )


class SourceDataProductRuntimeMetadata(BaseModel):
    tenant_id: str | None = Field(
        None,
        description=(
            "Tenant or book-of-record scope for this source-data product. Null until runtime "
            "tenant enforcement is available for this product."
        ),
        examples=["tenant-sg"],
    )
    generated_at: datetime = Field(
        ...,
        description="UTC timestamp when this source-data product response was generated.",
        examples=["2026-04-15T01:30:00Z"],
    )
    as_of_date: date = Field(
        ...,
        description="Business as-of date used to resolve this source-data product.",
        examples=["2026-03-26"],
    )
    restatement_version: str = Field(
        CURRENT_RESTATEMENT_VERSION,
        description="Restatement version for the reconstructed source-data product scope.",
        examples=[CURRENT_RESTATEMENT_VERSION],
    )
    reconciliation_status: str = Field(
        UNKNOWN,
        description="Reconciliation status for the product scope when available.",
        examples=[UNKNOWN],
    )
    data_quality_status: str = Field(
        UNKNOWN,
        description="Data-quality status for the returned product rows.",
        examples=[UNKNOWN],
    )
    latest_evidence_timestamp: datetime | None = Field(
        None,
        description="Latest linked evidence timestamp available for this product scope.",
        examples=["2026-04-15T01:29:59Z"],
    )
    source_batch_fingerprint: str | None = Field(
        None,
        description="Source-batch fingerprint when the product can be traced to a batch.",
        examples=["sbf_9c3f13c0a5d14f3e"],
    )
    snapshot_id: str | None = Field(
        None,
        description="Deterministic snapshot identity when the product scope has one.",
        examples=["pss_0123456789abcdef0123456789abcdef"],
    )
    policy_version: str | None = Field(
        None,
        description="Policy version applied to this product response when applicable.",
        examples=["policy-v1"],
    )
    correlation_id: str | None = Field(
        None,
        description="Request correlation identifier associated with this response.",
        examples=["QRY:01234567-89ab-cdef-0123-456789abcdef"],
    )


def source_data_product_runtime_metadata(
    *,
    as_of_date: date,
    generated_at: datetime | None = None,
    tenant_id: str | None = None,
    reconciliation_status: str = UNKNOWN,
    data_quality_status: str = UNKNOWN,
    latest_evidence_timestamp: datetime | None = None,
    source_batch_fingerprint: str | None = None,
    snapshot_id: str | None = None,
    policy_version: str | None = None,
) -> dict[str, object]:
    resolved_generated_at = generated_at or datetime.now(UTC)
    return {
        "tenant_id": normalize_lineage_value(tenant_id),
        "generated_at": resolved_generated_at,
        "as_of_date": as_of_date,
        "restatement_version": CURRENT_RESTATEMENT_VERSION,
        "reconciliation_status": reconciliation_status,
        "data_quality_status": data_quality_status,
        "latest_evidence_timestamp": latest_evidence_timestamp,
        "source_batch_fingerprint": normalize_lineage_value(source_batch_fingerprint),
        "snapshot_id": normalize_lineage_value(snapshot_id),
        "policy_version": normalize_lineage_value(policy_version),
        "correlation_id": normalize_lineage_value(correlation_id_var.get()),
    }
