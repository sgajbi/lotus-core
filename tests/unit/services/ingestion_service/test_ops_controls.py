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
    now_epoch = int(datetime.now(UTC).timestamp())
    monkeypatch.setattr(ops_controls, "OPS_AUTH_MODE", "jwt_only")
    monkeypatch.setattr(ops_controls, "OPS_JWT_HS256_SECRET", secret)
    monkeypatch.setattr(ops_controls, "OPS_JWT_ISSUER", "")
    monkeypatch.setattr(ops_controls, "OPS_JWT_AUDIENCE", "")
    token = _build_hs256_jwt(secret, {"sub": "ops-jwt-user", "exp": now_epoch + 600})

    principal = await ops_controls.require_ops_token(_request({"Authorization": f"Bearer {token}"}))

    assert principal == "ops-jwt-user"


@pytest.mark.asyncio
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
