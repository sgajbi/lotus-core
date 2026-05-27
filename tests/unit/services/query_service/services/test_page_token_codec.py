import pytest

from src.services.query_service.app.services.page_token_codec import PageTokenCodec


def test_page_token_codec_round_trips_signed_payload():
    codec = PageTokenCodec("secret")
    payload = {"scope": "portfolio-tax-lots", "offset": 20, "portfolio_id": "P1"}

    token = codec.encode(payload)

    assert codec.decode(token) == payload


def test_page_token_codec_rejects_wrong_secret():
    token = PageTokenCodec("secret-a").encode({"offset": 20})

    with pytest.raises(ValueError, match="Invalid page token signature"):
        PageTokenCodec("secret-b").decode(token)


def test_page_token_codec_handles_empty_and_malformed_tokens():
    codec = PageTokenCodec("secret")

    assert codec.decode(None) == {}
    assert codec.decode("") == {}
    with pytest.raises(ValueError, match="Malformed page token"):
        codec.decode("not-valid-base64")
