"""Shared application contracts for durable position valuation jobs."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Optional

from .domain.tenant import TenantId

VALUATION_CLAIM_HEADER = "valuation_claim_token"


class ValuationJobTransitionOutcome(StrEnum):
    """Classify the result of a processing-owned valuation-job transition."""

    TERMINAL_APPLIED = "TERMINAL_APPLIED"
    REQUEUED = "REQUEUED"
    NOT_OWNED = "NOT_OWNED"


@dataclass(frozen=True, slots=True)
class ValuationJobUpsert:
    """One idempotent position/date/epoch valuation scheduling request."""

    portfolio_id: str
    security_id: str
    valuation_date: date
    epoch: int
    correlation_id: Optional[str] = None
    source_correction_id: Optional[str] = None
    readiness_outbox_id: Optional[int] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AttributedValuationJobUpsert(ValuationJobUpsert):
    """Scheduling request attributed to its exact persisted portfolio owner."""

    tenant_id: TenantId

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, TenantId):
            raise TypeError("valuation job tenant_id must be a TenantId")


@dataclass(frozen=True, slots=True)
class ValuationJobClaim:
    """Immutable tenant and lease authority for one dispatched durable job."""

    tenant_id: TenantId
    job_id: int
    claim_token: str

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, TenantId):
            raise TypeError("valuation claim tenant_id must be a TenantId")
        if type(self.job_id) is not int or self.job_id <= 0:
            raise ValueError("valuation claim job_id must be positive")
        if len(self.claim_token) != 32 or any(
            character not in "0123456789abcdef" for character in self.claim_token
        ):
            raise ValueError("valuation claim token must be 32 lowercase hexadecimal characters")
