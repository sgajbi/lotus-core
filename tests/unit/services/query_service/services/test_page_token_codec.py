import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from src.services.query_service.app.services.page_token_codec import PageTokenCodec


def test_page_token_codec_round_trips_signed_payload():
    codec = PageTokenCodec("secret")
    payload = {"scope": "portfolio-tax-lots", "offset": 20, "portfolio_id": "P1"}

    token = codec.encode(payload)

    assert codec.decode(token) == payload


def test_page_token_codec_rejects_wrong_secret():
    token = PageTokenCodec("secret-a", active_kid="kid-a").encode({"offset": 20})

    with pytest.raises(ValueError, match="Invalid page token signature"):
        PageTokenCodec("secret-b", active_kid="kid-a").decode(token)


def test_page_token_codec_envelope_includes_version_key_and_expiry():
    expires_at = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    codec = PageTokenCodec("secret", active_kid="kid-2026")

    token = codec.encode({"offset": 20}, expires_at=expires_at)
    envelope = json.loads(base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8"))

    assert envelope["v"] == 1
    assert envelope["kid"] == "kid-2026"
    assert envelope["exp"] == int(expires_at.timestamp())
    assert envelope["iss"] == "lotus-core.query-service"
    assert envelope["aud"] == "query-service.page-token"
    assert envelope["p"] == {"offset": 20}


def test_page_token_codec_rejects_expired_token():
    codec = PageTokenCodec("secret")
    token = codec.encode(
        {"offset": 20},
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="Expired page token"):
        codec.decode(token)


def test_page_token_codec_enforces_route_and_tenant_binding():
    codec = PageTokenCodec("secret")
    token = codec.encode(
        {"offset": 20},
        route="/integration/portfolio-tax-lots",
        tenant_id="tenant-a",
    )

    assert codec.decode(
        token,
        route="/integration/portfolio-tax-lots",
        tenant_id="tenant-a",
    ) == {"offset": 20}
    with pytest.raises(ValueError, match="route mismatch"):
        codec.decode(token, route="/integration/transaction-cost-curve", tenant_id="tenant-a")
    with pytest.raises(ValueError, match="tenant mismatch"):
        codec.decode(token, route="/integration/portfolio-tax-lots", tenant_id="tenant-b")


def test_page_token_codec_decodes_previous_key_for_rotation_window():
    old_codec = PageTokenCodec("old-secret", active_kid="old-key")
    token = old_codec.encode({"offset": 20})
    new_codec = PageTokenCodec(
        "new-secret",
        active_kid="new-key",
        previous_secrets={"old-key": "old-secret"},
    )

    assert new_codec.decode(token) == {"offset": 20}


def test_page_token_codec_handles_empty_and_malformed_tokens():
    codec = PageTokenCodec("secret")

    assert codec.decode(None) == {}
    assert codec.decode("") == {}
    with pytest.raises(ValueError, match="Malformed page token"):
        codec.decode("not-valid-base64")


def _token(payload):
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


@pytest.mark.parametrize(
    "envelope",
    [
        {"p": {"offset": 1}},
        {"p": {"offset": 1}, "s": 123},
        {"p": ["not", "a", "dict"], "s": "bad-signature"},
    ],
)
def test_page_token_codec_rejects_malformed_envelopes(envelope):
    codec = PageTokenCodec("secret")

    with pytest.raises(
        ValueError,
        match="Malformed page token|Invalid page token signature|Unsupported page token version",
    ):
        codec.decode(_token(envelope))
