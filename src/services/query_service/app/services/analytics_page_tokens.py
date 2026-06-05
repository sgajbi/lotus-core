from __future__ import annotations

import base64
import hashlib
import hmac
import json


class AnalyticsPageTokenError(ValueError):
    pass


class AnalyticsPageTokenSignatureError(AnalyticsPageTokenError):
    pass


def encode_analytics_page_token(*, payload: dict, secret: str) -> str:
    serialized = _serialized_page_token_payload(payload)
    signature = _page_token_signature(serialized=serialized, secret=secret)
    envelope = {"p": payload, "s": signature}
    return base64.urlsafe_b64encode(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8")


def decode_analytics_page_token(*, token: str | None, secret: str) -> dict:
    if not token:
        return {}
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        envelope = json.loads(decoded)
        payload = envelope["p"]
        signature = envelope["s"]
        serialized = _serialized_page_token_payload(payload)
        expected = _page_token_signature(serialized=serialized, secret=secret)
        if not hmac.compare_digest(signature, expected):
            raise AnalyticsPageTokenSignatureError("Invalid page token signature.")
        return payload
    except AnalyticsPageTokenSignatureError:
        raise
    except Exception as exc:
        raise AnalyticsPageTokenError("Malformed page token.") from exc


def _serialized_page_token_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _page_token_signature(*, serialized: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        serialized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
