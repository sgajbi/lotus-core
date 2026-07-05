import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.services.ingestion_service.app import ops_controls


class _FakeCounter:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def labels(self, **labels: str) -> "_FakeCounter":
        self.calls.append(labels)
        return self

    def inc(self) -> None:
        return None


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


OPS_JWT_ISSUER = "lotus-core-ingest-ops"
OPS_JWT_AUDIENCE = "lotus-core-ingestion-ops"
OPS_JWT_KEY_ID = "ops-key-current"
OPS_JWT_REQUIRED_SCOPE = "lotus-core.ingestion.ops"


def _build_hs256_jwt(
    secret: str,
    payload: dict,
    *,
    kid: str = OPS_JWT_KEY_ID,
    alg: str = "HS256",
) -> str:
    header = {"alg": alg, "typ": "JWT", "kid": kid}

    def _b64(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    header_b64 = _b64(header)
    payload_b64 = _b64(payload)
    signed = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def _valid_ops_jwt_payload(*, principal_claim: str = "sub") -> dict[str, object]:
    now_epoch = int(datetime.now(UTC).timestamp())
    payload: dict[str, object] = {
        "iss": OPS_JWT_ISSUER,
        "aud": OPS_JWT_AUDIENCE,
        "iat": now_epoch - 30,
        "exp": now_epoch + 600,
        "jti": "ops-jwt-test-001",
        "scope": OPS_JWT_REQUIRED_SCOPE,
    }
    payload[principal_claim] = "ops-jwt-user" if principal_claim == "sub" else "ops-client"
    return payload


def _configure_ops_jwt(monkeypatch, secret: str, *, previous_keys: dict[str, str] | None = None):
    monkeypatch.setattr(ops_controls, "OPS_JWT_HS256_SECRET", secret)
    monkeypatch.setattr(ops_controls, "OPS_JWT_KEY_ID", OPS_JWT_KEY_ID)
    monkeypatch.setattr(ops_controls, "OPS_JWT_PREVIOUS_KEYS", previous_keys or {})
    monkeypatch.setattr(ops_controls, "OPS_JWT_ISSUER", OPS_JWT_ISSUER)
    monkeypatch.setattr(ops_controls, "OPS_JWT_AUDIENCE", OPS_JWT_AUDIENCE)
    monkeypatch.setattr(ops_controls, "OPS_JWT_REQUIRED_SCOPE", OPS_JWT_REQUIRED_SCOPE)


def test_ingestion_write_rate_limit_counter_registration_is_idempotent() -> None:
    counter = ops_controls._get_or_create_counter(
        "ingestion_write_rate_limit_denials_total",
        "Ingestion write requests denied by the configured rate-limit policy.",
        ("endpoint", "reason", "enforcement_scope"),
    )

    assert counter is ops_controls.INGESTION_WRITE_RATE_LIMIT_DENIALS_TOTAL


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_require_ops_token_rejects_invalid_token_only_header(monkeypatch) -> None:
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "token_only")
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_REQUIRED", True)
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_VALUE", "expected-token")

    with pytest.raises(HTTPException) as exc_info:
        await ops_controls.require_ops_token(_request({"X-Lotus-Ops-Token": "wrong"}))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "INGESTION_OPS_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_require_ops_token_accepts_jwt_only_bearer(monkeypatch) -> None:
    secret = "test-hs256-secret"
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    _configure_ops_jwt(monkeypatch, secret)
    token = _build_hs256_jwt(secret, _valid_ops_jwt_payload())

    principal = await ops_controls.require_ops_token(_request({"Authorization": f"Bearer {token}"}))

    assert principal == "ops-jwt-user"


@pytest.mark.asyncio
async def test_require_ops_token_prefers_bearer_in_token_or_jwt_mode(monkeypatch) -> None:
    secret = "test-hs256-secret"
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "token_or_jwt")
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_REQUIRED", True)
    monkeypatch.setattr(ops_controls, "OPS_TOKEN_VALUE", "expected-token")
    _configure_ops_jwt(monkeypatch, secret)
    token = _build_hs256_jwt(secret, _valid_ops_jwt_payload(principal_claim="client_id"))

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


@pytest.mark.asyncio
async def test_require_ops_token_rejects_malformed_jwt(monkeypatch) -> None:
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    _configure_ops_jwt(monkeypatch, "test-hs256-secret")

    with pytest.raises(HTTPException) as exc_info:
        await ops_controls.require_ops_token(_request({"Authorization": "Bearer not-a-jwt"}))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "INGESTION_OPS_JWT_MALFORMED"


@pytest.mark.asyncio
async def test_require_ops_token_rejects_bad_jwt_algorithm(monkeypatch) -> None:
    secret = "test-hs256-secret"
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    _configure_ops_jwt(monkeypatch, secret)
    token = _build_hs256_jwt(secret, _valid_ops_jwt_payload(), alg="none")

    with pytest.raises(HTTPException) as exc_info:
        await ops_controls.require_ops_token(_request({"Authorization": f"Bearer {token}"}))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "INGESTION_OPS_JWT_UNSUPPORTED_ALG"


@pytest.mark.asyncio
async def test_require_ops_token_rejects_missing_required_jwt_claim(monkeypatch) -> None:
    secret = "test-hs256-secret"
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    _configure_ops_jwt(monkeypatch, secret)
    payload = _valid_ops_jwt_payload()
    payload.pop("iat")
    token = _build_hs256_jwt(secret, payload)

    with pytest.raises(HTTPException) as exc_info:
        await ops_controls.require_ops_token(_request({"Authorization": f"Bearer {token}"}))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "INGESTION_OPS_JWT_MISSING_CLAIMS"
    assert "iat" in exc_info.value.detail["message"]


@pytest.mark.asyncio
async def test_require_ops_token_rejects_expired_jwt(monkeypatch) -> None:
    secret = "test-hs256-secret"
    now_epoch = int(datetime.now(UTC).timestamp())
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    monkeypatch.setattr(ops_controls, "OPS_JWT_CLOCK_SKEW_SECONDS", 0)
    _configure_ops_jwt(monkeypatch, secret)
    payload = _valid_ops_jwt_payload()
    payload["exp"] = now_epoch - 1
    token = _build_hs256_jwt(secret, payload)

    with pytest.raises(HTTPException) as exc_info:
        await ops_controls.require_ops_token(_request({"Authorization": f"Bearer {token}"}))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "INGESTION_OPS_JWT_EXPIRED"


@pytest.mark.asyncio
async def test_require_ops_token_rejects_wrong_jwt_issuer(monkeypatch) -> None:
    secret = "test-hs256-secret"
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    _configure_ops_jwt(monkeypatch, secret)
    payload = _valid_ops_jwt_payload()
    payload["iss"] = "wrong-issuer"
    token = _build_hs256_jwt(secret, payload)

    with pytest.raises(HTTPException) as exc_info:
        await ops_controls.require_ops_token(_request({"Authorization": f"Bearer {token}"}))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "INGESTION_OPS_JWT_ISSUER_INVALID"


@pytest.mark.asyncio
async def test_require_ops_token_rejects_wrong_jwt_audience(monkeypatch) -> None:
    secret = "test-hs256-secret"
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    _configure_ops_jwt(monkeypatch, secret)
    payload = _valid_ops_jwt_payload()
    payload["aud"] = "wrong-audience"
    token = _build_hs256_jwt(secret, payload)

    with pytest.raises(HTTPException) as exc_info:
        await ops_controls.require_ops_token(_request({"Authorization": f"Bearer {token}"}))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "INGESTION_OPS_JWT_AUDIENCE_INVALID"


@pytest.mark.asyncio
async def test_require_ops_token_rejects_missing_ops_jwt_scope(monkeypatch) -> None:
    secret = "test-hs256-secret"
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    _configure_ops_jwt(monkeypatch, secret)
    payload = _valid_ops_jwt_payload()
    payload["scope"] = "lotus-core.other"
    token = _build_hs256_jwt(secret, payload)

    with pytest.raises(HTTPException) as exc_info:
        await ops_controls.require_ops_token(_request({"Authorization": f"Bearer {token}"}))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "INGESTION_OPS_JWT_SCOPE_MISSING"


@pytest.mark.asyncio
async def test_require_ops_token_accepts_rotated_previous_jwt_key(monkeypatch) -> None:
    active_secret = "test-hs256-secret-active"
    previous_secret = "test-hs256-secret-previous"
    previous_key_id = "ops-key-previous"
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    _configure_ops_jwt(monkeypatch, active_secret, previous_keys={previous_key_id: previous_secret})
    token = _build_hs256_jwt(
        previous_secret,
        _valid_ops_jwt_payload(),
        kid=previous_key_id,
    )

    principal = await ops_controls.require_ops_token(_request({"Authorization": f"Bearer {token}"}))

    assert principal == "ops-jwt-user"


def test_ingestion_write_rate_limit_noops_when_disabled(monkeypatch) -> None:
    ops_controls._write_events.clear()
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENABLED", False)

    ops_controls.enforce_ingestion_write_rate_limit(endpoint="/ingest/test", record_count=10)

    assert "/ingest/test" not in ops_controls._write_events


def test_ingestion_write_rate_limit_contract_declares_local_scope(monkeypatch) -> None:
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENFORCEMENT_SCOPE", "local_process")
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_GATEWAY_POLICY_ID", "")

    contract = ops_controls.ingestion_write_rate_limit_contract()

    assert contract["enforcement_scope"] == "local_process"
    assert contract["local_process_enforcement"] is True
    assert contract["global_enforcement_claimed"] is False


def test_ingestion_write_rate_limit_gateway_scope_requires_policy(monkeypatch) -> None:
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENFORCEMENT_SCOPE", "upstream_gateway")
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_GATEWAY_POLICY_ID", "")

    with pytest.raises(RuntimeError) as exc_info:
        ops_controls.validate_ingestion_write_rate_limit_contract()

    assert "LOTUS_CORE_INGEST_RATE_LIMIT_GATEWAY_POLICY_ID" in str(exc_info.value)


def test_ingestion_write_rate_limit_gateway_scope_accepts_policy(monkeypatch) -> None:
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENFORCEMENT_SCOPE", "upstream_gateway")
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_GATEWAY_POLICY_ID", "kong-ingest-write-v1")

    ops_controls.validate_ingestion_write_rate_limit_contract()
    contract = ops_controls.ingestion_write_rate_limit_contract()

    assert contract["global_enforcement_claimed"] is True
    assert contract["local_process_enforcement"] is False
    assert contract["gateway_policy_id"] == "kong-ingest-write-v1"


def test_ingestion_write_rate_limit_upstream_gateway_bypasses_local_store(monkeypatch) -> None:
    ops_controls._write_events.clear()
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENFORCEMENT_SCOPE", "upstream_gateway")

    ops_controls.enforce_ingestion_write_rate_limit(endpoint="/ingest/test", record_count=10)

    assert "/ingest/test" not in ops_controls._write_events


def test_ingestion_write_rate_limit_floors_record_count(monkeypatch) -> None:
    ops_controls._write_events.clear()
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENFORCEMENT_SCOPE", "local_process")
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_MAX_REQUESTS", 10)
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_MAX_RECORDS", 10)

    ops_controls.enforce_ingestion_write_rate_limit(endpoint="/ingest/test", record_count=0)

    assert ops_controls._write_events["/ingest/test"][0].record_count == 1


def test_ingestion_write_rate_limit_blocks_projected_record_budget(monkeypatch) -> None:
    ops_controls._write_events.clear()
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENFORCEMENT_SCOPE", "local_process")
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_MAX_REQUESTS", 10)
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_MAX_RECORDS", 2)
    fake_counter = _FakeCounter()
    monkeypatch.setattr(ops_controls, "INGESTION_WRITE_RATE_LIMIT_DENIALS_TOTAL", fake_counter)

    ops_controls.enforce_ingestion_write_rate_limit(endpoint="/ingest/test", record_count=2)
    with pytest.raises(PermissionError) as exc_info:
        ops_controls.enforce_ingestion_write_rate_limit(endpoint="/ingest/test", record_count=1)

    assert "reason=record_budget" in str(exc_info.value)
    assert "max_records=2" in str(exc_info.value)
    assert len(ops_controls._write_events["/ingest/test"]) == 1
    assert fake_counter.calls == [
        {
            "endpoint": "/ingest/test",
            "reason": "record_budget",
            "enforcement_scope": "local_process",
        }
    ]


def test_ingestion_write_rate_limit_is_endpoint_scoped(monkeypatch) -> None:
    ops_controls._write_events.clear()
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_ENFORCEMENT_SCOPE", "local_process")
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_MAX_REQUESTS", 1)
    monkeypatch.setattr(ops_controls, "RATE_LIMIT_MAX_RECORDS", 100)

    ops_controls.enforce_ingestion_write_rate_limit(endpoint="/ingest/a", record_count=1)
    ops_controls.enforce_ingestion_write_rate_limit(endpoint="/ingest/b", record_count=1)

    assert len(ops_controls._write_events["/ingest/a"]) == 1
    assert len(ops_controls._write_events["/ingest/b"]) == 1
