"""Represent the effective FX rate selected for cost-basis conversion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class EffectiveFxRate:
    """Persistence-neutral FX rate selected from an effective-date series."""

    effective_date: date
    rate: Decimal
