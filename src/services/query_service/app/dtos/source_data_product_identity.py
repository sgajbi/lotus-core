import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from portfolio_common.logging_utils import correlation_id_var, normalize_lineage_value
from portfolio_common.reconciliation_quality import UNKNOWN
from portfolio_common.reconstruction_identity import CURRENT_RESTATEMENT_VERSION
from pydantic import BaseModel, Field

SOURCE_METADATA_UNAVAILABLE_HASH = (
    "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)


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


class SourceDataDegradationDetail(BaseModel):
    section: str = Field(
        ...,
        description="Response section where source degradation applies.",
        examples=["positions"],
    )
    record_key: str | None = Field(
        None,
        description="Stable record key inside the section when degradation is row-scoped.",
        examples=["security_id:EQ_US_AAPL"],
    )
    affected_fields: list[str] = Field(
        default_factory=list,
        description="Response fields affected by fallback, stale, partial, or unavailable data.",
        examples=[["valuation.market_price", "valuation.market_value"]],
    )
    source_kind: Literal["AUTHORITATIVE", "FALLBACK", "DERIVED_DEFAULT", "UNAVAILABLE"] = Field(
        ...,
        description="Kind of source used for the affected field values.",
        examples=["FALLBACK"],
    )
    source_product_name: str = Field(
        ...,
        description="Source-data product that owns the affected evidence.",
        examples=["HoldingsAsOf"],
    )
    source_product_version: str = Field(
        "v1",
        description="Version of the source-data product that owns the affected evidence.",
        examples=["v1"],
    )
    source_as_of_date: date | None = Field(
        None,
        description="Business as-of date of the source evidence used for the affected fields.",
        examples=["2026-04-10"],
    )
    latest_evidence_timestamp: datetime | None = Field(
        None,
        description="Latest known source evidence timestamp for the affected fields.",
        examples=["2026-04-10T01:30:00Z"],
    )
    freshness_status: Literal["CURRENT", "STALE", "PARTIAL", "UNAVAILABLE", "UNKNOWN"] = Field(
        ...,
        description="Freshness posture for the affected fields.",
        examples=["PARTIAL"],
    )
    reason_code: str = Field(
        ...,
        description="Bounded machine-readable reason for the degradation detail.",
        examples=["HOLDINGS_VALUATION_FALLBACK"],
    )


class SourceDataDegradationSummary(BaseModel):
    status: Literal["NONE", "PARTIAL", "STALE", "UNAVAILABLE", "UNKNOWN"] = Field(
        "NONE",
        description="Highest-severity degradation posture across this response.",
        examples=["PARTIAL"],
    )
    reason_codes: list[str] = Field(
        default_factory=list,
        description="Deduplicated bounded reason codes present in the degradation details.",
        examples=[["HOLDINGS_VALUATION_FALLBACK"]],
    )
    details: list[SourceDataDegradationDetail] = Field(
        default_factory=list,
        description="Row, section, or field-level degradation details.",
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
        description=(
            "Source-owned deterministic SHA-256 fingerprint for this response evidence. When a "
            "caller supplies a legacy source-batch label, Core still emits the canonical content "
            "hash here so downstream proof tooling can validate the response without deriving "
            "source authority itself."
        ),
        examples=["sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"],
    )
    snapshot_id: str | None = Field(
        None,
        description="Deterministic snapshot identity when the product scope has one.",
        examples=["pss_0123456789abcdef0123456789abcdef"],
    )
    content_hash: str = Field(
        SOURCE_METADATA_UNAVAILABLE_HASH,
        description=(
            "Deterministic SHA-256 hash of the source-owned response content and proof basis, "
            "excluding volatile response-generation timestamps."
        ),
        examples=["sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"],
    )
    source_digest: str = Field(
        SOURCE_METADATA_UNAVAILABLE_HASH,
        description=(
            "Alias of content_hash for downstream proof tooling that uses source digest "
            "terminology."
        ),
        examples=["sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"],
    )
    source_refs: list[str] = Field(
        default_factory=list,
        description="Deterministic source references used to assemble this product response.",
        examples=[["lotus-core://source/PortfolioStateSnapshot/PF-001/2026-04-10"]],
    )
    source_lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Bounded source lineage identifiers for support and proof validation.",
        examples=[{"source_product": "PortfolioStateSnapshot", "source_owner": "lotus-core"}],
    )
    degradation: SourceDataDegradationSummary = Field(
        default_factory=lambda: SourceDataDegradationSummary(),
        description=(
            "Per-section or per-field degradation metadata. Empty details mean Core did not "
            "apply fallback, stale, partial, or unavailable source handling for this response."
        ),
    )
    source_evidence_current: bool = Field(
        False,
        description=(
            "Whether Core considers the returned source evidence current for the requested "
            "as-of scope."
        ),
        examples=[True],
    )
    freshness_status: str = Field(
        "UNAVAILABLE",
        description=(
            "Text freshness posture for downstream proof tooling. CURRENT means Core considers "
            "the source evidence current for the requested as-of scope."
        ),
        examples=["CURRENT"],
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
    content_hash: str | None = None,
    source_digest: str | None = None,
    source_refs: list[str] | None = None,
    lineage: dict[str, str] | None = None,
    source_evidence_current: bool | None = None,
    freshness_status: str | None = None,
    use_content_hash_as_source_batch_fingerprint: bool = False,
) -> dict[str, object]:
    resolved_generated_at = generated_at or datetime.now(UTC)
    normalized_source_batch_fingerprint = normalize_lineage_value(source_batch_fingerprint)
    normalized_refs = [
        ref for ref in (normalize_lineage_value(ref) for ref in source_refs or []) if ref
    ]
    normalized_lineage = {
        key: value
        for key, value in (
            (str(key), normalize_lineage_value(value)) for key, value in (lineage or {}).items()
        )
        if value
    }
    resolved_content_hash = content_hash or source_digest or SOURCE_METADATA_UNAVAILABLE_HASH
    resolved_source_evidence_current = (
        _default_source_evidence_current(
            data_quality_status=data_quality_status,
            latest_evidence_timestamp=latest_evidence_timestamp,
        )
        if source_evidence_current is None
        else source_evidence_current
    )
    return {
        "tenant_id": normalize_lineage_value(tenant_id),
        "generated_at": resolved_generated_at,
        "as_of_date": as_of_date,
        "restatement_version": CURRENT_RESTATEMENT_VERSION,
        "reconciliation_status": reconciliation_status,
        "data_quality_status": data_quality_status,
        "latest_evidence_timestamp": latest_evidence_timestamp,
        "source_batch_fingerprint": _accepted_source_fingerprint(
            normalized_source_batch_fingerprint,
            content_hash=resolved_content_hash,
            use_content_hash_as_source_batch_fingerprint=(
                use_content_hash_as_source_batch_fingerprint
            ),
        ),
        "snapshot_id": normalize_lineage_value(snapshot_id),
        "content_hash": resolved_content_hash,
        "source_digest": source_digest or resolved_content_hash,
        "source_refs": normalized_refs,
        "source_lineage": normalized_lineage,
        "source_evidence_current": resolved_source_evidence_current,
        "freshness_status": freshness_status
        or _default_freshness_status(
            data_quality_status=data_quality_status,
            source_evidence_current=resolved_source_evidence_current,
        ),
        "policy_version": normalize_lineage_value(policy_version),
        "correlation_id": normalize_lineage_value(correlation_id_var.get()),
    }


def stable_content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _default_source_evidence_current(
    *, data_quality_status: str, latest_evidence_timestamp: datetime | None
) -> bool:
    return data_quality_status.strip().upper() in {"COMPLETE", "PARTIAL"} and (
        latest_evidence_timestamp is not None
    )


def _accepted_source_fingerprint(
    value: str | None,
    *,
    content_hash: str,
    use_content_hash_as_source_batch_fingerprint: bool,
) -> str | None:
    if use_content_hash_as_source_batch_fingerprint:
        return content_hash
    return value


def _default_freshness_status(*, data_quality_status: str, source_evidence_current: bool) -> str:
    if source_evidence_current:
        return "CURRENT"
    if data_quality_status.strip().upper() == "STALE":
        return "STALE"
    return "UNAVAILABLE"
