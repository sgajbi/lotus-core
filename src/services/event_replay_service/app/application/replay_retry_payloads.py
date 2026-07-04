from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

_RetryPayloadFilter = Callable[[dict[str, Any], set[str]], dict[str, Any]]


def filter_payload_by_record_keys(
    *,
    endpoint: str,
    payload: dict[str, Any],
    record_keys: list[str],
) -> dict[str, Any]:
    if not record_keys:
        return payload
    key_set = set(record_keys)
    payload_filter = _PARTIAL_RETRY_PAYLOAD_FILTERS.get(endpoint)
    if payload_filter is None:
        raise ValueError(f"Partial retry is not supported for endpoint '{endpoint}'.")
    return payload_filter(payload, key_set)


def deterministic_replay_fingerprint(
    *,
    event_id: str,
    correlation_id: str | None,
    job_id: str | None,
    endpoint: str | None,
    payload: dict[str, Any] | None,
    idempotency_key: str | None,
    alternate_lookup_key: str | None = None,
) -> str:
    basis = {
        "event_id": event_id,
        "correlation_id": correlation_id,
        "job_id": job_id,
        "endpoint": endpoint,
        "idempotency_key": idempotency_key,
        "payload": payload or {},
    }
    if alternate_lookup_key is not None:
        basis["alternate_lookup_key"] = alternate_lookup_key
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def payload_record_count(payload: dict[str, Any] | None) -> int:
    if not payload:
        return 0
    counts = [len(value) for value in payload.values() if isinstance(value, list)]
    if counts:
        return max(counts)
    return 1


def _filter_record_collection_payload(
    *,
    payload: dict[str, Any],
    collection_name: str,
    record_key_name: str,
    key_set: set[str],
    stringify_record_key: bool = False,
) -> dict[str, Any]:
    rows = [
        row
        for row in payload.get(collection_name, [])
        if _retry_record_key(row, record_key_name, stringify_record_key) in key_set
    ]
    return {collection_name: rows}


def _retry_record_key(row: dict[str, Any], record_key_name: str, stringify: bool) -> Any:
    value = row.get(record_key_name)
    return str(value) if stringify else value


def _filter_transaction_retry_payload(payload: dict[str, Any], key_set: set[str]) -> dict[str, Any]:
    return _filter_record_collection_payload(
        payload=payload,
        collection_name="transactions",
        record_key_name="transaction_id",
        key_set=key_set,
    )


def _filter_portfolio_retry_payload(payload: dict[str, Any], key_set: set[str]) -> dict[str, Any]:
    return _filter_record_collection_payload(
        payload=payload,
        collection_name="portfolios",
        record_key_name="portfolio_id",
        key_set=key_set,
    )


def _filter_instrument_retry_payload(payload: dict[str, Any], key_set: set[str]) -> dict[str, Any]:
    return _filter_record_collection_payload(
        payload=payload,
        collection_name="instruments",
        record_key_name="security_id",
        key_set=key_set,
    )


def _filter_business_date_retry_payload(
    payload: dict[str, Any], key_set: set[str]
) -> dict[str, Any]:
    return _filter_record_collection_payload(
        payload=payload,
        collection_name="business_dates",
        record_key_name="business_date",
        key_set=key_set,
        stringify_record_key=True,
    )


def _filter_reprocess_transaction_retry_payload(
    payload: dict[str, Any], key_set: set[str]
) -> dict[str, Any]:
    rows = [txn_id for txn_id in payload.get("transaction_ids", []) if txn_id in key_set]
    return {"transaction_ids": rows}


_PARTIAL_RETRY_PAYLOAD_FILTERS: dict[str, _RetryPayloadFilter] = {
    "/ingest/transactions": _filter_transaction_retry_payload,
    "/ingest/portfolios": _filter_portfolio_retry_payload,
    "/ingest/instruments": _filter_instrument_retry_payload,
    "/ingest/business-dates": _filter_business_date_retry_payload,
    "/reprocess/transactions": _filter_reprocess_transaction_retry_payload,
}
