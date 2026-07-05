import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

PAGE_TOKEN_VERSION = 1
DEFAULT_PAGE_TOKEN_KID = "local-dev"
DEFAULT_PAGE_TOKEN_TTL_SECONDS = 900
DEFAULT_PAGE_TOKEN_ISSUER = "lotus-core.query-service"
DEFAULT_PAGE_TOKEN_AUDIENCE = "query-service.page-token"


@dataclass(frozen=True)
class PageTokenCodec:
    secret: str
    active_kid: str = DEFAULT_PAGE_TOKEN_KID
    previous_secrets: dict[str, str] = field(default_factory=dict)
    ttl_seconds: int = DEFAULT_PAGE_TOKEN_TTL_SECONDS
    issuer: str = DEFAULT_PAGE_TOKEN_ISSUER
    audience: str = DEFAULT_PAGE_TOKEN_AUDIENCE

    def encode(
        self,
        payload: dict[str, Any],
        *,
        route: str | None = None,
        tenant_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> str:
        expiry = expires_at or datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)
        envelope = {
            "v": PAGE_TOKEN_VERSION,
            "kid": self.active_kid,
            "exp": int(expiry.timestamp()),
            "iss": self.issuer,
            "aud": self.audience,
            "route": route,
            "tenant": tenant_id,
            "p": payload,
        }
        signature = _signature(envelope, secret=self.secret)
        return base64.urlsafe_b64encode(
            json.dumps({**envelope, "s": signature}, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("utf-8")

    def decode(
        self,
        token: str | None,
        *,
        route: str | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        if not token:
            return {}
        try:
            decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
            envelope = json.loads(decoded)
            payload = envelope["p"]
            signature = envelope["s"]
        except (
            binascii.Error,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            UnicodeDecodeError,
        ) as exc:
            raise ValueError("Malformed page token.") from exc

        if not isinstance(signature, str):
            raise ValueError("Malformed page token.")
        if not isinstance(payload, dict):
            raise ValueError("Malformed page token payload.")

        self._validate_envelope(envelope, route=route, tenant_id=tenant_id)
        secret = self._secret_for_kid(envelope["kid"])
        signed_envelope = {key: value for key, value in envelope.items() if key != "s"}
        expected = _signature(signed_envelope, secret=secret)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid page token signature.")
        return payload

    def _secret_for_kid(self, kid: str) -> str:
        if kid == self.active_kid:
            return self.secret
        if kid in self.previous_secrets:
            return self.previous_secrets[kid]
        raise ValueError("Unknown page token key id.")

    def _validate_envelope(
        self,
        envelope: dict[str, Any],
        *,
        route: str | None,
        tenant_id: str | None,
    ) -> None:
        if envelope.get("v") != PAGE_TOKEN_VERSION:
            raise ValueError("Unsupported page token version.")
        if not isinstance(envelope.get("kid"), str) or not envelope["kid"].strip():
            raise ValueError("Malformed page token key id.")
        if envelope.get("iss") != self.issuer or envelope.get("aud") != self.audience:
            raise ValueError("Page token issuer or audience mismatch.")
        if route is not None and envelope.get("route") != route:
            raise ValueError("Page token route mismatch.")
        if tenant_id is not None and envelope.get("tenant") != tenant_id:
            raise ValueError("Page token tenant mismatch.")
        exp = envelope.get("exp")
        if not isinstance(exp, int):
            raise ValueError("Malformed page token expiry.")
        if exp < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("Expired page token.")


def _signature(envelope: dict[str, Any], *, secret: str) -> str:
    serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        secret.encode("utf-8"),
        serialized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
