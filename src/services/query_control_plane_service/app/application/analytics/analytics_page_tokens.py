"""Signed analytics continuation-token encoding and error mapping."""

from __future__ import annotations

from typing import cast

from portfolio_common.page_tokens import PageTokenCodec


class AnalyticsPageTokenError(ValueError):
    pass


class AnalyticsPageTokenSignatureError(AnalyticsPageTokenError):
    pass


def encode_analytics_page_token(
    *,
    payload: dict[str, object],
    secret: str,
    active_kid: str = "local-dev",
    previous_secrets: dict[str, str] | None = None,
    ttl_seconds: int = 900,
) -> str:
    return cast(
        str,
        PageTokenCodec(
            secret=secret,
            active_kid=active_kid,
            previous_secrets=previous_secrets or {},
            ttl_seconds=ttl_seconds,
        ).encode(payload, route="analytics"),
    )


def decode_analytics_page_token(
    *,
    token: str | None,
    secret: str,
    active_kid: str = "local-dev",
    previous_secrets: dict[str, str] | None = None,
    ttl_seconds: int = 900,
) -> dict[str, object]:
    if not token:
        return {}
    try:
        return cast(
            dict[str, object],
            PageTokenCodec(
                secret=secret,
                active_kid=active_kid,
                previous_secrets=previous_secrets or {},
                ttl_seconds=ttl_seconds,
            ).decode(token, route="analytics"),
        )
    except ValueError as exc:
        message = str(exc)
        if "signature" in message or "key id" in message:
            raise AnalyticsPageTokenSignatureError(message) from exc
        raise AnalyticsPageTokenError("Malformed page token.") from exc
    except Exception as exc:
        raise AnalyticsPageTokenError("Malformed page token.") from exc
