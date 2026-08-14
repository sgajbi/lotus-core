from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from src.services.ingestion_service.app.request_metadata import (
    idempotency_key_reference,
    resolve_idempotency_key,
)


def _request(value: str | None) -> Request:
    headers = [] if value is None else [(b"x-idempotency-key", value.encode("latin-1"))]
    return Request({"type": "http", "headers": headers})


@pytest.mark.parametrize(
    "value",
    ["a", "batch-2026.08.14:001", "A_B", "x" * 128],
)
def test_resolve_idempotency_key_accepts_bounded_opaque_identifiers(value: str) -> None:
    assert resolve_idempotency_key(_request(value)) == value


def test_resolve_idempotency_key_allows_absence() -> None:
    assert resolve_idempotency_key(_request(None)) is None


@pytest.mark.parametrize(
    "value",
    ["", " key", "key ", "key/value", "key@example.com", "x" * 129, "key\tvalue"],
)
def test_resolve_idempotency_key_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_idempotency_key(_request(value))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INGESTION_IDEMPOTENCY_KEY_INVALID"


def test_idempotency_key_reference_is_stable_non_reversible_and_sensitive() -> None:
    first = idempotency_key_reference("client-secret-key-001")

    assert first == idempotency_key_reference("client-secret-key-001")
    assert first != idempotency_key_reference("client-secret-key-002")
    assert first.startswith("sha256:")
    assert "client-secret" not in first
