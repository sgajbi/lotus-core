"""Closed retained payload reconstruction and aware native receipt validation."""

import hashlib
from datetime import datetime

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_source_observations import require_observation_identity
from portfolio_common.portfolio_financial_source_cut_admission import closed_source_json
from portfolio_common.portfolio_financial_source_cut_decoding import source_manifest_from_payload


def manifest_from_payload(payload, tenant, product):
    return source_manifest_from_payload(payload, tenant, product)


def require_raw(row):
    if (
        type(row.raw_bytes) is not bytes
        or hashlib.sha256(row.raw_bytes).hexdigest() != row.raw_hash
    ):
        raise ValueError("retained ingress raw hash mismatch")
    return closed_source_json(row.raw_bytes)


def native_capture_identity(tenant_id, portfolio_id, selection, page_index):
    return canonical_content_hash(
        {
            "contract": "NativeSourceCaptureRequest:v1",
            "tenant": tenant_id,
            "portfolio": portfolio_id,
            "product": selection.product_name,
            "version": selection.product_version,
            "selector": selection.selector_hash,
            "content": selection.content_hash,
            "receipt": selection.receipt_job_id,
            "revision": selection.source_revision,
            "page_index": page_index,
        }
    )


def require_capture_fields(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("closed native capture shape required")


def retained_stamp(value):
    if type(value) is not str:
        raise ValueError("actual retained source timestamp required")
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("aware retained source timestamp required")
    return stamp


def require_capture_receipt(receipt, *, tenant, job_id, endpoint, entity, received_at):
    require_capture_fields(
        receipt,
        (
            "job_id",
            "tenant_id",
            "endpoint",
            "entity_type",
            "status",
            "completed_at",
            "accepted_count",
        ),
    )
    require_observation_identity(receipt["job_id"], "actual native receipt")
    received = retained_stamp(received_at)
    completed = retained_stamp(receipt["completed_at"])
    if completed < received:
        raise ValueError("retained native receipt chronology mismatch")
    if (
        (
            receipt["tenant_id"],
            receipt["job_id"],
            receipt["endpoint"],
            receipt["entity_type"],
            receipt["status"],
        )
        != (tenant, job_id, endpoint, entity, "completed")
        or type(receipt["accepted_count"]) is not int
        or receipt["accepted_count"] < 1
    ):
        raise ValueError("retained native correct-family receipt mismatch")
