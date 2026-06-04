import json
from hashlib import sha256
from typing import Any


def request_fingerprint(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def series_request_fingerprint(
    series_key: str,
    identifier_key: str,
    identifier_value: str,
    request: Any,
    extras: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "series_key": series_key,
        identifier_key: identifier_value,
        "as_of_date": request.as_of_date.isoformat(),
        "window": {
            "start_date": request.window.start_date.isoformat(),
            "end_date": request.window.end_date.isoformat(),
        },
        "frequency": request.frequency,
    }
    if extras:
        payload.update(extras)
    return request_fingerprint(payload)
