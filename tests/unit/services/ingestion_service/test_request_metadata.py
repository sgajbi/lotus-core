from __future__ import annotations

import hashlib

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
    kwargs = {"key_id": "ops-2026-08", "hmac_secret": "s" * 32}
    first = idempotency_key_reference(value="client-secret-key-001", **kwargs)

    assert first == idempotency_key_reference(value="client-secret-key-001", **kwargs)
    assert first != idempotency_key_reference(value="client-secret-key-002", **kwargs)
    assert first.startswith("hmac-sha256:v1:ops-2026-08:")
    assert "client-secret" not in first


def test_idempotency_key_reference_resists_low_entropy_dictionary_confirmation() -> None:
    reference = idempotency_key_reference(
        value="a",
        key_id="ops-2026-08",
        hmac_secret="purpose-specific-secret-value-001",
    )

    assert reference != f"sha256:{hashlib.sha256(b'a').hexdigest()}"
    assert reference == (
        "hmac-sha256:v1:ops-2026-08:"
        "3e793a4266b054812b324cd65064deb2c76a8f5af1fd3e41945391d31f0a7dc8"
    )


def test_idempotency_key_reference_is_key_and_key_id_scoped() -> None:
    common = {"value": "batch-2026-08-14"}

    first = idempotency_key_reference(
        **common,
        key_id="ops-2026-08",
        hmac_secret="purpose-specific-secret-value-001",
    )
    assert first != idempotency_key_reference(
        **common,
        key_id="ops-2026-08",
        hmac_secret="purpose-specific-secret-value-002",
    )
    assert first != idempotency_key_reference(
        **common,
        key_id="ops-2026-09",
        hmac_secret="purpose-specific-secret-value-001",
    )


@pytest.mark.parametrize("key_id,hmac_secret", [("", "secret"), ("key", "")])
def test_idempotency_key_reference_requires_explicit_key_authority(
    key_id: str,
    hmac_secret: str,
) -> None:
    with pytest.raises(ValueError, match="key id and HMAC secret"):
        idempotency_key_reference(value="a", key_id=key_id, hmac_secret=hmac_secret)
