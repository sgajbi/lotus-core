import hashlib
import hmac
import re
from uuid import uuid4

from fastapi import HTTPException, Request
from portfolio_common.logging_utils import (
    correlation_id_var,
    normalize_lineage_value,
    request_id_var,
    trace_id_var,
)

_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_INVALID_IDEMPOTENCY_KEY_DETAIL = {
    "code": "INGESTION_IDEMPOTENCY_KEY_INVALID",
    "message": (
        "X-Idempotency-Key must be 1-128 ASCII letters, digits, period, underscore, colon, "
        "or hyphen; surrounding whitespace is not accepted."
    ),
}


def resolve_idempotency_key(request: Request) -> str | None:
    value = request.headers.get("X-Idempotency-Key")
    if value is None:
        return None
    if _IDEMPOTENCY_KEY_PATTERN.fullmatch(value) is None:
        raise HTTPException(status_code=400, detail=_INVALID_IDEMPOTENCY_KEY_DETAIL)
    return value


def idempotency_key_reference(*, value: str, key_id: str, hmac_secret: str) -> str:
    """Return a purpose-bound pseudonymous operator reference for a validated key."""
    if not key_id or not hmac_secret:
        raise ValueError("Idempotency reference key id and HMAC secret are required.")
    message = b"lotus-core/ingestion/idempotency-key-reference/v1\x00" + value.encode("utf-8")
    digest = hmac.new(hmac_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"hmac-sha256:v1:{key_id}:{digest}"


def create_ingestion_job_id() -> str:
    return f"job_{uuid4().hex}"


def get_request_lineage() -> tuple[str | None, str | None, str | None]:
    return (
        normalize_lineage_value(correlation_id_var.get()),
        normalize_lineage_value(request_id_var.get()),
        normalize_lineage_value(trace_id_var.get()),
    )
