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


def enforce_ingestion_write_rate_limit(*, endpoint: str, record_count: int) -> None:
    if not RATE_LIMIT_ENABLED:
        return
    if record_count < 1:
        record_count = 1

    now_utc = datetime.now(UTC)
    with _rate_limit_lock:
        events = _write_events[endpoint]
        _evict_expired(events, now_utc)
        current_requests = len(events)
        current_records = sum(item.record_count for item in events)
        projected_requests = current_requests + 1
        projected_records = current_records + record_count
        if (
            projected_requests > RATE_LIMIT_MAX_REQUESTS
            or projected_records > RATE_LIMIT_MAX_RECORDS
        ):
            raise PermissionError(
                "Ingestion write rate limit exceeded. "
                f"window_seconds={RATE_LIMIT_WINDOW_SECONDS}, "
                f"max_requests={RATE_LIMIT_MAX_REQUESTS}, "
                f"max_records={RATE_LIMIT_MAX_RECORDS}."
            )
        events.append(_WriteEvent(observed_at=now_utc, record_count=record_count))


async def require_ops_token(
    request: Request,
) -> str:
    ops_token = request.headers.get("X-Lotus-Ops-Token")

    def _validate_hs256_jwt(token: str) -> str | None:
        if not OPS_JWT_HS256_SECRET:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "INGESTION_OPS_JWT_SECRET_MISSING",
                    "message": "JWT auth is enabled but LOTUS_CORE_INGEST_OPS_JWT_HS256_SECRET is missing.",
                },
            )
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INGESTION_OPS_JWT_MALFORMED", "message": "Malformed JWT."},
            )
        header_b64, payload_b64, signature_b64 = parts
        signed = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected = hmac.new(OPS_JWT_HS256_SECRET.encode("utf-8"), signed, hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected).decode("utf-8").rstrip("=")
        if not hmac.compare_digest(expected_b64, signature_b64):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INGESTION_OPS_JWT_INVALID_SIGNATURE",
                    "message": "Invalid JWT signature.",
                },
            )

        def _decode_segment(segment: str) -> dict:
            padding = "=" * (-len(segment) % 4)
            raw = base64.urlsafe_b64decode((segment + padding).encode("utf-8"))
            return json.loads(raw.decode("utf-8"))

        header = _decode_segment(header_b64)
        payload = _decode_segment(payload_b64)
        if header.get("alg") != "HS256":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "INGESTION_OPS_JWT_UNSUPPORTED_ALG",
                    "message": "Only HS256 JWT is supported.",
                },
            )
        now_epoch = int(datetime.now(UTC).timestamp())
        exp = payload.get("exp")
        if isinstance(exp, int) and now_epoch > exp + OPS_JWT_CLOCK_SKEW_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INGESTION_OPS_JWT_EXPIRED", "message": "JWT token is expired."},
            )
        nbf = payload.get("nbf")
        if isinstance(nbf, int) and now_epoch + OPS_JWT_CLOCK_SKEW_SECONDS < nbf:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "INGESTION_OPS_JWT_NOT_YET_VALID",
                    "message": "JWT token is not yet valid.",
                },
            )
        if OPS_JWT_ISSUER and payload.get("iss") != OPS_JWT_ISSUER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INGESTION_OPS_JWT_ISSUER_INVALID",
                    "message": "JWT issuer does not match configured issuer.",
                },
            )
        if OPS_JWT_AUDIENCE:
            aud = payload.get("aud")
            if isinstance(aud, str):
                valid_aud = aud == OPS_JWT_AUDIENCE
            elif isinstance(aud, list):
                valid_aud = OPS_JWT_AUDIENCE in aud
            else:
                valid_aud = False
            if not valid_aud:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "INGESTION_OPS_JWT_AUDIENCE_INVALID",
                        "message": "JWT audience does not match configured audience.",
                    },
                )
        principal = payload.get("sub") or payload.get("client_id") or payload.get("azp")
        return str(principal) if principal else None

    auth_header = request.headers.get("Authorization", "")
    bearer_token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""

    if OPS_AUTH_MODE == "jwt_only":
        if not bearer_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "INGESTION_OPS_JWT_REQUIRED",
                    "message": "Missing bearer JWT token.",
                },
            )
        principal = _validate_hs256_jwt(bearer_token)
        return principal or "ops-jwt"

    if OPS_AUTH_MODE == "token_only":
        if not OPS_TOKEN_REQUIRED:
            return "ops-token-not-required"
        if not ops_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "INGESTION_OPS_TOKEN_REQUIRED",
                    "message": (
                        "Missing X-Lotus-Ops-Token header for privileged ingestion operations API."
                    ),
                },
            )
        if ops_token != OPS_TOKEN_VALUE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INGESTION_OPS_TOKEN_INVALID",
                    "message": "Invalid X-Lotus-Ops-Token.",
                },
            )
        return request.headers.get("X-Principal", "ops-token")

    # Default mode: token_or_jwt
    if bearer_token:
        principal = _validate_hs256_jwt(bearer_token)
        return principal or "ops-jwt"
    if not OPS_TOKEN_REQUIRED:
        return "ops-token-not-required"
    if not ops_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INGESTION_OPS_TOKEN_REQUIRED",
                "message": (
                    "Missing X-Lotus-Ops-Token header for privileged ingestion operations API."
                ),
            },
        )
    if ops_token != OPS_TOKEN_VALUE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INGESTION_OPS_TOKEN_INVALID",
                "message": "Invalid X-Lotus-Ops-Token.",
            },
        )
    return request.headers.get("X-Principal", "ops-token")
