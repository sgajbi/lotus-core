"""Deterministic input, calculation, and output lineage for financial results."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


@dataclass(frozen=True, slots=True)
class CalculationLineage:
    """Three-layer deterministic evidence for one financial calculation."""

    algorithm_id: str
    algorithm_version: int
    intermediate_precision: int
    input_content_hash: str
    calculation_content_hash: str
    output_content_hash: str

    def __post_init__(self) -> None:
        if not self.algorithm_id.strip():
            raise ValueError("algorithm_id must be nonblank")
        if self.algorithm_version < 1:
            raise ValueError("algorithm_version must be positive")
        if self.intermediate_precision < 1:
            raise ValueError("intermediate_precision must be positive")
        for field_name in (
            "input_content_hash",
            "calculation_content_hash",
            "output_content_hash",
        ):
            _require_sha256(str(getattr(self, field_name)), field_name)


def build_calculation_lineage(
    *,
    algorithm_id: str,
    algorithm_version: int,
    intermediate_precision: int,
    input_payload: Mapping[str, object],
    output_payload: Mapping[str, object],
) -> CalculationLineage:
    """Bind normalized inputs, algorithm semantics, and outputs with SHA-256 evidence."""

    normalized_algorithm_id = algorithm_id.strip()
    if not normalized_algorithm_id:
        raise ValueError("algorithm_id must be nonblank")
    if algorithm_version < 1:
        raise ValueError("algorithm_version must be positive")
    if intermediate_precision < 1:
        raise ValueError("intermediate_precision must be positive")

    input_content_hash = canonical_content_hash(input_payload)
    calculation_content_hash = canonical_content_hash(
        {
            "algorithm_id": normalized_algorithm_id,
            "algorithm_version": algorithm_version,
            "input_content_hash": input_content_hash,
            "intermediate_precision": intermediate_precision,
        }
    )
    output_content_hash = canonical_content_hash(
        {
            "calculation_content_hash": calculation_content_hash,
            "output": output_payload,
        }
    )
    return CalculationLineage(
        algorithm_id=normalized_algorithm_id,
        algorithm_version=algorithm_version,
        intermediate_precision=intermediate_precision,
        input_content_hash=input_content_hash,
        calculation_content_hash=calculation_content_hash,
        output_content_hash=output_content_hash,
    )


def canonical_content_hash(payload: Mapping[str, object]) -> str:
    """Hash a supported financial payload without float or key-order ambiguity."""

    normalized = _normalize_lineage_value(payload)
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_lineage_value(value: object) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise TypeError("float values are prohibited in financial calculation lineage")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal values are prohibited in calculation lineage")
        return {"decimal": str(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("lineage datetime values must be timezone-aware")
        return {"datetime": value.isoformat()}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    if isinstance(value, Enum):
        return _normalize_lineage_value(value.value)
    if isinstance(value, Mapping):
        normalized_mapping: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise TypeError("calculation lineage mapping keys must be nonblank strings")
            normalized_mapping[key] = _normalize_lineage_value(item)
        return normalized_mapping
    if isinstance(value, Set):
        normalized_items = [_normalize_lineage_value(item) for item in value]
        return sorted(normalized_items, key=_canonical_sort_key)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_lineage_value(item) for item in value]
    raise TypeError(f"unsupported calculation lineage value: {type(value).__name__}")


def _canonical_sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
