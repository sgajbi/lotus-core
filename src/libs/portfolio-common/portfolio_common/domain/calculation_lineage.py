"""Cross-domain deterministic lineage for financial calculations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
            require_sha256_digest(str(getattr(self, field_name)), field_name)

    def lineage_payload(self) -> dict[str, object]:
        """Return the canonical payload used when this calculation is a downstream input."""

        return {
            "algorithm_id": self.algorithm_id,
            "algorithm_version": self.algorithm_version,
            "calculation_content_hash": self.calculation_content_hash,
            "input_content_hash": self.input_content_hash,
            "intermediate_precision": self.intermediate_precision,
            "output_content_hash": self.output_content_hash,
        }


@dataclass(frozen=True, slots=True)
class FinancialSourceReference:
    """Immutable source evidence for one financial input fact."""

    source_system: str
    source_record_id: str
    source_revision: str
    source_content_hash: str
    observed_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("source_system", "source_record_id", "source_revision"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"{field_name} must be nonblank")
            object.__setattr__(self, field_name, normalized)
        if not isinstance(self.source_content_hash, str):
            raise TypeError("source_content_hash must be a string")
        require_sha256_digest(self.source_content_hash, "source_content_hash")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")

    def lineage_payload(self) -> dict[str, object]:
        """Return normalized source fields for a calculation input payload."""

        return {
            "observed_at": self.observed_at,
            "source_content_hash": self.source_content_hash,
            "source_record_id": self.source_record_id.strip(),
            "source_revision": self.source_revision.strip(),
            "source_system": self.source_system.strip(),
        }


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
        return {"datetime": value.astimezone(UTC).isoformat()}
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


def require_sha256_digest(value: str, field_name: str) -> str:
    """Validate and return a canonical lowercase SHA-256 digest."""

    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return value
