import hashlib
import json
from copy import deepcopy
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def hash_canonical_payload(payload: Any) -> str:
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def strip_keys(payload: Any, *, exclude: set[str]) -> Any:
    if isinstance(payload, dict):
        return {
            key: strip_keys(value, exclude=exclude)
            for key, value in payload.items()
            if key not in exclude
        }
    if isinstance(payload, list):
        return [strip_keys(item, exclude=exclude) for item in payload]
    return deepcopy(payload)
