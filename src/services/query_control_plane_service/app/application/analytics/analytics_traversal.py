"""Continuation drift detection, not retained source-cut authority."""

from __future__ import annotations

import hmac
import json
from dataclasses import asdict, fields, is_dataclass
from typing import Any, cast

from portfolio_common.source_data_product_metadata import stable_content_hash

from ...domain.analytics import (
    AnalyticsCashflowEvidence,
    PositionValuationObservation,
    PriorPositionValuation,
)
from .analytics_content_identity import canonical_economic_value
from .analytics_input_errors import AnalyticsInputError

TRAVERSAL_VERSION = "analytics-selected-inputs-v1"


def _dependency_value(value: Any) -> Any:
    """Canonicalize code-owned records/maps without losing duplicate source rows."""
    if is_dataclass(value) and not isinstance(value, type):
        return _dependency_value(asdict(value))
    if isinstance(value, dict):
        entries = [[_dependency_value(key), _dependency_value(item)] for key, item in value.items()]
        return sorted(entries, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, tuple):
        # Tuple keys are ordered identities (for example security/date), not bags.
        return [_dependency_value(item) for item in value]
    if isinstance(value, list):
        entries = [_dependency_value(item) for item in value]
        return sorted(entries, key=lambda item: json.dumps(item, sort_keys=True))
    return canonical_economic_value(value)


def selected_inputs_fingerprint(**inputs: Any) -> str:
    """Bind selected dependency values; absent provider/revision custody stays absent."""
    record_types = {
        "positions": PositionValuationObservation,
        "portfolio_flows": AnalyticsCashflowEvidence,
        "position_flows": AnalyticsCashflowEvidence,
        "previous": PriorPositionValuation,
    }
    for name, record_type in record_types.items():
        if name in inputs:
            # Match the existing sparse reader projection without serializing arbitrary objects.
            inputs[name] = [
                {field.name: getattr(row, field.name, None) for field in fields(record_type)}
                for row in inputs[name]
            ]
    return cast(
        str,
        stable_content_hash({"version": TRAVERSAL_VERSION, "inputs": _dependency_value(inputs)}),
    )


def validate_traversal_continuation(
    *, cursor: dict[str, Any], snapshot_epoch: int, fingerprint: str
) -> None:
    """Old/missing witnesses cannot silently start another traversal identity."""
    if not cursor:
        return
    token_fingerprint = cursor.get("selected_inputs_fingerprint")
    if (
        cursor.get("traversal_version") != TRAVERSAL_VERSION
        or type(cursor.get("snapshot_epoch")) is not int
        or cursor["snapshot_epoch"] != snapshot_epoch
        or not isinstance(token_fingerprint, str)
        or len(token_fingerprint) != 71
        or not token_fingerprint.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in token_fingerprint[7:])
        or not hmac.compare_digest(token_fingerprint, fingerprint)
    ):
        raise AnalyticsInputError(
            "STALE_CONTINUATION", "Analytics source changed; restart pagination."
        )
