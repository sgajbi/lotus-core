"""Shared query-service policy for usable position-snapshot valuation states."""

from __future__ import annotations

from .control_code_normalization import normalize_control_code

USABLE_VALUATION_STATUSES = frozenset({"VALUED", "VALUED_CURRENT", "VALUED_STALE"})


def has_usable_valuation_status(value: object) -> bool:
    """Return whether a snapshot status permits its monetary valuation to be consumed."""

    return normalize_control_code(value) in USABLE_VALUATION_STATUSES
