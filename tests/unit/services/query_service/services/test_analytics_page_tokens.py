from __future__ import annotations

import pytest

from src.services.query_service.app.services.analytics_page_tokens import (
    AnalyticsPageTokenError,
    AnalyticsPageTokenSignatureError,
    decode_analytics_page_token,
    encode_analytics_page_token,
)


def test_analytics_page_token_round_trip_is_deterministic_for_payload_order() -> None:
    left = encode_analytics_page_token(
        payload={"valuation_date": "2025-01-01", "security_id": "SEC_1"},
        secret="secret",
    )
    right = encode_analytics_page_token(
        payload={"security_id": "SEC_1", "valuation_date": "2025-01-01"},
        secret="secret",
    )

    assert left == right
    assert decode_analytics_page_token(token=left, secret="secret") == {
        "valuation_date": "2025-01-01",
        "security_id": "SEC_1",
    }


def test_decode_analytics_page_token_returns_empty_payload_for_blank_token() -> None:
    assert decode_analytics_page_token(token=None, secret="secret") == {}
    assert decode_analytics_page_token(token="", secret="secret") == {}


def test_decode_analytics_page_token_rejects_wrong_secret() -> None:
    token = encode_analytics_page_token(payload={"valuation_date": "2025-01-01"}, secret="secret")

    with pytest.raises(AnalyticsPageTokenSignatureError, match="Invalid page token signature"):
        decode_analytics_page_token(token=token, secret="other-secret")


def test_decode_analytics_page_token_rejects_malformed_token() -> None:
    with pytest.raises(AnalyticsPageTokenError, match="Malformed page token"):
        decode_analytics_page_token(token="not-valid-base64", secret="secret")
