"""Purpose-bound HMAC references for protected ingestion evidence."""

from __future__ import annotations

import hashlib
import hmac


def purpose_bound_hmac_sha256_reference(
    *,
    purpose: bytes,
    value: bytes,
    key_id: str,
    hmac_secret: str,
) -> str:
    """Return a key-versioned pseudonym under an explicit cryptographic domain."""
    if not purpose or not key_id or not hmac_secret:
        raise ValueError("HMAC purpose, key id and HMAC secret are required.")
    digest = hmac.new(
        hmac_secret.encode("utf-8"),
        purpose + b"\x00" + value,
        hashlib.sha256,
    ).hexdigest()
    return f"hmac-sha256:v1:{key_id}:{digest}"
