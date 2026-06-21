import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.services.ingestion_service.app import ops_controls

pytestmark = pytest.mark.asyncio


def _request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/ingestion/health/summary",
            "headers": [
                (key.lower().encode("latin-1"), value.encode("latin-1"))
                for key, value in headers.items()
            ],
        }
    )


def _build_hs256_jwt(secret: str, payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}

    def _b64(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    header_b64 = _b64(header)
    payload_b64 = _b64(payload)
    signed = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{header_b64}.{payload_b64}.{signature_b64}"


async def test_require_ops_token_accepts_token_only_header(monkeypatch) -> None:
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "token_only")
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_REQUIRED", True)
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_VALUE", "expected-token")

    principal = await ops_controls.require_ops_token(
        _request(
            {
                "X-Lotus-Ops-Token": "expected-token",
                "X-Principal": "ops-user",
            }
        )
    )

    assert principal == "ops-user"


async def test_require_ops_token_rejects_invalid_token_only_header(monkeypatch) -> None:
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "token_only")
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_REQUIRED", True)
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_VALUE", "expected-token")

    with pytest.raises(HTTPException) as exc_info:
        await ops_controls.require_ops_token(_request({"X-Lotus-Ops-Token": "wrong"}))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "INGESTION_OPS_TOKEN_INVALID"


async def test_require_ops_token_accepts_jwt_only_bearer(monkeypatch) -> None:
    secret = "test-hs256-secret"
    now_epoch = int(datetime.now(UTC).timestamp())
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    monkeypatch.setattr(ops_controls, "OPS_JWT_HS256_SECRET", secret)
    monkeypatch.setattr(ops_controls, "OPS_JWT_ISSUER", "")
    monkeypatch.setattr(ops_controls, "OPS_JWT_AUDIENCE", "")
    token = _build_hs256_jwt(secret, {"sub": "ops-jwt-user", "exp": now_epoch + 600})

    principal = await ops_controls.require_ops_token(_request({"Authorization": f"Bearer {token}"}))

    assert principal == "ops-jwt-user"


async def test_require_ops_token_prefers_bearer_in_token_or_jwt_mode(monkeypatch) -> None:
    secret = "test-hs256-secret"
    now_epoch = int(datetime.now(UTC).timestamp())
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "token_or_jwt")
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_REQUIRED", True)
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_VALUE", "expected-token")
    monkeypatch.setattr(ops_controls, "OPS_JWT_HS256_SECRET", secret)
    monkeypatch.setattr(ops_controls, "OPS_JWT_ISSUER", "")
    monkeypatch.setattr(ops_controls, "OPS_JWT_AUDIENCE", "")
    token = _build_hs256_jwt(secret, {"client_id": "ops-client", "exp": now_epoch + 600})

    principal = await ops_controls.require_ops_token(
        _request(
            {
                "Authorization": f"Bearer {token}",
                "X-Lotus-Ops-Token": "expected-token",
                "X-Principal": "token-principal",
            }
        )
    )

    assert principal == "ops-client"
