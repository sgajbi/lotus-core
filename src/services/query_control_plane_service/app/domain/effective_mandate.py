"""Domain records for effective discretionary mandate identity."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EffectiveMandateBinding:
    """Minimal effective mandate identity required by client-profile products."""

    client_id: str
    mandate_id: str
    observed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
