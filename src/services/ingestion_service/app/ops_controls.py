from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import HTTPException, Request, status

from .settings import get_ingestion_service_settings

_SETTINGS = get_ingestion_service_settings()

OPS_TOKEN_REQUIRED = _SETTINGS.ops_auth.token_required
OPS_TOKEN_VALUE = _SETTINGS.ops_auth.token_value
OPS_AUTH_MODE = _SETTINGS.ops_auth.auth_mode
OPS_JWT_HS256_SECRET = _SETTINGS.ops_auth.jwt_hs256_secret
OPS_JWT_ISSUER = _SETTINGS.ops_auth.jwt_issuer
OPS_JWT_AUDIENCE = _SETTINGS.ops_auth.jwt_audience
OPS_JWT_CLOCK_SKEW_SECONDS = _SETTINGS.ops_auth.jwt_clock_skew_seconds

RATE_LIMIT_ENABLED = _SETTINGS.rate_limit.enabled
RATE_LIMIT_WINDOW_SECONDS = _SETTINGS.rate_limit.window_seconds
RATE_LIMIT_MAX_REQUESTS = _SETTINGS.rate_limit.max_requests
RATE_LIMIT_MAX_RECORDS = _SETTINGS.rate_limit.max_records


@dataclass(slots=True)
class _WriteEvent:
    observed_at: datetime
    record_count: int


_write_events: dict[str, deque[_WriteEvent]] = defaultdict(deque)
_rate_limit_lock = Lock()


def _evict_expired(events: deque[_WriteEvent], now_utc: datetime) -> None:
    cutoff = now_utc - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    while events and events[0].observed_at < cutoff:
        events.popleft()


def _normalized_record_count(record_count: int) -> int:
    return max(record_count, 1)


def _projected_rate_limit_usage(
    *,
    events: deque[_WriteEvent],
    record_count: int,
) -> tuple[int, int]:
    current_records = sum(item.record_count for item in events)
    return len(events) + 1, current_records + record_count


def _rate_limit_exceeded(*, projected_requests: int, projected_records: int) -> bool:
    return (
        projected_requests > RATE_LIMIT_MAX_REQUESTS or projected_records > RATE_LIMIT_MAX_RECORDS
    )


def _rate_limit_error_message() -> str:
    return (
        "Ingestion write rate limit exceeded. "
        f"window_seconds={RATE_LIMIT_WINDOW_SECONDS}, "
        f"max_requests={RATE_LIMIT_MAX_REQUESTS}, "
        f"max_records={RATE_LIMIT_MAX_RECORDS}."
    )


def _record_write_event(
    *,
    events: deque[_WriteEvent],
    now_utc: datetime,
    record_count: int,
) -> None:
    events.append(_WriteEvent(observed_at=now_utc, record_count=record_count))


def enforce_ingestion_write_rate_limit(*, endpoint: str, record_count: int) -> None:
    if not RATE_LIMIT_ENABLED:
        return

    record_count = _normalized_record_count(record_count)
    now_utc = datetime.now(UTC)
    with _rate_limit_lock:
        events = _write_events[endpoint]
        _evict_expired(events, now_utc)
        projected_requests, projected_records = _projected_rate_limit_usage(
            events=events,
            record_count=record_count,
        )
        if _rate_limit_exceeded(
            projected_requests=projected_requests,
            projected_records=projected_records,
        ):
            raise PermissionError(_rate_limit_error_message())
        _record_write_event(events=events, now_utc=now_utc, record_count=record_count)


def _ops_auth_error(status_code: int, *, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _decode_jwt_segment(segment: str) -> dict:
    padding = "=" * (-len(segment) % 4)
    raw = base64.urlsafe_b64decode((segment + padding).encode("utf-8"))
    return json.loads(raw.decode("utf-8"))


def _validate_jwt_signature(*, header_b64: str, payload_b64: str, signature_b64: str) -> None:
    signed = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected = hmac.new(OPS_JWT_HS256_SECRET.encode("utf-8"), signed, hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected).decode("utf-8").rstrip("=")
    if not hmac.compare_digest(expected_b64, signature_b64):
        raise _ops_auth_error(
            status.HTTP_403_FORBIDDEN,
            code="INGESTION_OPS_JWT_INVALID_SIGNATURE",
            message="Invalid JWT signature.",
        )


def _validate_hs256_header(header: dict) -> None:
    if header.get("alg") != "HS256":
        raise _ops_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            code="INGESTION_OPS_JWT_UNSUPPORTED_ALG",
            message="Only HS256 JWT is supported.",
        )


def _validate_jwt_time_window(payload: dict) -> None:
    now_epoch = int(datetime.now(UTC).timestamp())
    exp = payload.get("exp")
    if isinstance(exp, int) and now_epoch > exp + OPS_JWT_CLOCK_SKEW_SECONDS:
        raise _ops_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            code="INGESTION_OPS_JWT_EXPIRED",
            message="JWT token is expired.",
        )
    nbf = payload.get("nbf")
    if isinstance(nbf, int) and now_epoch + OPS_JWT_CLOCK_SKEW_SECONDS < nbf:
        raise _ops_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            code="INGESTION_OPS_JWT_NOT_YET_VALID",
            message="JWT token is not yet valid.",
        )


def _validate_jwt_issuer(payload: dict) -> None:
    if OPS_JWT_ISSUER and payload.get("iss") != OPS_JWT_ISSUER:
        raise _ops_auth_error(
            status.HTTP_403_FORBIDDEN,
            code="INGESTION_OPS_JWT_ISSUER_INVALID",
            message="JWT issuer does not match configured issuer.",
        )


def _jwt_audience_matches(audience: object) -> bool:
    if isinstance(audience, str):
        return audience == OPS_JWT_AUDIENCE
    if isinstance(audience, list):
        return OPS_JWT_AUDIENCE in audience
    return False


def _validate_jwt_audience(payload: dict) -> None:
    if OPS_JWT_AUDIENCE and not _jwt_audience_matches(payload.get("aud")):
        raise _ops_auth_error(
            status.HTTP_403_FORBIDDEN,
            code="INGESTION_OPS_JWT_AUDIENCE_INVALID",
            message="JWT audience does not match configured audience.",
        )


def _jwt_principal(payload: dict) -> str | None:
    principal = payload.get("sub") or payload.get("client_id") or payload.get("azp")
    return str(principal) if principal else None


def _validate_hs256_jwt(token: str) -> str | None:
    if not OPS_JWT_HS256_SECRET:
        raise _ops_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            code="INGESTION_OPS_JWT_SECRET_MISSING",
            message="JWT auth is enabled but LOTUS_CORE_INGEST_OPS_JWT_HS256_SECRET is missing.",
        )
    parts = token.split(".")
    if len(parts) != 3:
        raise _ops_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            code="INGESTION_OPS_JWT_MALFORMED",
            message="Malformed JWT.",
        )
    header_b64, payload_b64, signature_b64 = parts
    _validate_jwt_signature(
        header_b64=header_b64,
        payload_b64=payload_b64,
        signature_b64=signature_b64,
    )
    header = _decode_jwt_segment(header_b64)
    payload = _decode_jwt_segment(payload_b64)
    _validate_hs256_header(header)
    _validate_jwt_time_window(payload)
    _validate_jwt_issuer(payload)
    _validate_jwt_audience(payload)
    return _jwt_principal(payload)


def _bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    return auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""


def _require_bearer_jwt(bearer_token: str) -> str:
    if not bearer_token:
        raise _ops_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            code="INGESTION_OPS_JWT_REQUIRED",
            message="Missing bearer JWT token.",
        )
    principal = _validate_hs256_jwt(bearer_token)
    return principal or "ops-jwt"


def _require_ops_token_header(request: Request, ops_token: str | None) -> str:
    if not OPS_TOKEN_REQUIRED:
        return "ops-token-not-required"
    if not ops_token:
        raise _ops_auth_error(
            status.HTTP_401_UNAUTHORIZED,
            code="INGESTION_OPS_TOKEN_REQUIRED",
            message="Missing X-Lotus-Ops-Token header for privileged ingestion operations API.",
        )
    if ops_token != OPS_TOKEN_VALUE:
        raise _ops_auth_error(
            status.HTTP_403_FORBIDDEN,
            code="INGESTION_OPS_TOKEN_INVALID",
            message="Invalid X-Lotus-Ops-Token.",
        )
    return request.headers.get("X-Principal", "ops-token")


async def require_ops_token(
    request: Request,
) -> str:
    ops_token = request.headers.get("X-Lotus-Ops-Token")
    bearer_token = _bearer_token(request)

    if OPS_AUTH_MODE == "jwt_only":
        return _require_bearer_jwt(bearer_token)

    if OPS_AUTH_MODE == "token_only":
        return _require_ops_token_header(request, ops_token)

    # Default mode: token_or_jwt
    if bearer_token:
        return _require_bearer_jwt(bearer_token)
    return _require_ops_token_header(request, ops_token)
