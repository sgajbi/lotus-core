from __future__ import annotations

import hashlib
import json
from typing import Any

from portfolio_common.logging_utils import redact_sensitive

PAYLOAD_EVIDENCE_POLICY_VERSION = "ingestion-payload-evidence.v1"


def canonical_payload_text(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ingestion_payload_fingerprint(payload: dict[str, Any] | None) -> str | None:
    canonical = canonical_payload_text(payload)
    if canonical is None:
        return None
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def source_safe_request_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return redact_sensitive(payload)


def source_safe_payload_fingerprint(payload: dict[str, Any] | None) -> str | None:
    return ingestion_payload_fingerprint(source_safe_request_payload(payload))
