from __future__ import annotations

from typing import Any

REPLAYABLE_RECORD_KEY_FIELDS: dict[str, tuple[str, str]] = {
    "/ingest/transactions": ("transactions", "transaction_id"),
    "/ingest/portfolios": ("portfolios", "portfolio_id"),
    "/ingest/instruments": ("instruments", "security_id"),
    "/ingest/business-dates": ("business_dates", "business_date"),
}


def failed_record_keys_from_failures(failures: list[Any]) -> list[str]:
    failed_keys: set[str] = set()
    for failure in failures:
        for item in list(failure.failed_record_keys or []):
            if isinstance(item, str):
                failed_keys.add(item)
    return sorted(failed_keys)


def replayable_record_keys_from_payload(
    *,
    endpoint: str,
    payload: dict[str, Any] | None,
) -> list[str]:
    if not isinstance(payload, dict):
        return []

    record_mapping = REPLAYABLE_RECORD_KEY_FIELDS.get(endpoint)
    if record_mapping is None:
        return []

    collection_name, key_field = record_mapping
    return [
        str(item.get(key_field))
        for item in payload.get(collection_name, [])
        if isinstance(item, dict) and item.get(key_field)
    ]
