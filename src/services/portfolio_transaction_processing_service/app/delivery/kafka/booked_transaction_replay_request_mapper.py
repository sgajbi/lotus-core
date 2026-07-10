from __future__ import annotations

import json
from dataclasses import dataclass

from ...application import ReplayBookedTransactionCommand


class BookedTransactionReplayRequestPayloadError(ValueError):
    """Raised when a replay request cannot be decoded as the supported JSON object."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BookedTransactionReplayRequest:
    transaction_id: str | None
    correlation_id: str | None


def parse_booked_transaction_replay_request(
    message_value: bytes | None,
) -> BookedTransactionReplayRequest:
    if message_value is None:
        raise BookedTransactionReplayRequestPayloadError(
            "Booked transaction replay request payload is missing"
        )
    try:
        payload = json.loads(message_value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BookedTransactionReplayRequestPayloadError(
            "Booked transaction replay request must contain valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise BookedTransactionReplayRequestPayloadError(
            "Booked transaction replay request must be a JSON object"
        )
    return BookedTransactionReplayRequest(
        transaction_id=_normalized_optional_text(
            payload.get("transaction_id"),
            field_name="transaction_id",
        ),
        correlation_id=_normalized_optional_text(
            payload.get("correlation_id"),
            field_name="correlation_id",
        ),
    )


def map_booked_transaction_replay_request(
    request: BookedTransactionReplayRequest,
    *,
    correlation_id: str | None,
) -> ReplayBookedTransactionCommand | None:
    if request.transaction_id is None:
        return None
    return ReplayBookedTransactionCommand(
        transaction_id=request.transaction_id,
        correlation_id=correlation_id,
    )


def _normalized_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BookedTransactionReplayRequestPayloadError(
            f"Booked transaction replay request {field_name} must be a string"
        )
    normalized = value.strip()
    return normalized or None
