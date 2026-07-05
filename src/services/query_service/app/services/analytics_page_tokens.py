from __future__ import annotations

from .page_token_codec import PageTokenCodec


class AnalyticsPageTokenError(ValueError):
    pass


class AnalyticsPageTokenSignatureError(AnalyticsPageTokenError):
    pass


def encode_analytics_page_token(
    *,
    payload: dict,
    secret: str,
    active_kid: str = "local-dev",
    previous_secrets: dict[str, str] | None = None,
    ttl_seconds: int = 900,
) -> str:
    return PageTokenCodec(
        secret=secret,
        active_kid=active_kid,
        previous_secrets=previous_secrets or {},
        ttl_seconds=ttl_seconds,
    ).encode(payload, route="analytics")


def decode_analytics_page_token(
    *,
    token: str | None,
    secret: str,
    active_kid: str = "local-dev",
    previous_secrets: dict[str, str] | None = None,
    ttl_seconds: int = 900,
) -> dict:
    if not token:
        return {}
    try:
        return PageTokenCodec(
            secret=secret,
            active_kid=active_kid,
            previous_secrets=previous_secrets or {},
            ttl_seconds=ttl_seconds,
        ).decode(token, route="analytics")
    except ValueError as exc:
        message = str(exc)
        if "signature" in message or "key id" in message:
            raise AnalyticsPageTokenSignatureError(message) from exc
        raise AnalyticsPageTokenError("Malformed page token.") from exc
    except Exception as exc:
        raise AnalyticsPageTokenError("Malformed page token.") from exc
