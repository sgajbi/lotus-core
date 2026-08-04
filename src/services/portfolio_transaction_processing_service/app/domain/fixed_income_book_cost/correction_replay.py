"""Deterministic replay intent for fixed-income authority corrections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    canonical_content_hash,
    require_sha256_digest,
)

from .authority import LotBookCostAuthorityScope
from .policy import AmortizedCostEligibilityReason

FIXED_INCOME_BOOK_COST_CORRECTION_REPLAY_ID_VERSION = 1


@dataclass(frozen=True, slots=True)
class AffectedLotDisposalReplayAnchor:
    """Earliest booked disposal in the deterministic transaction order."""

    transaction_id: str
    transaction_timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transaction_id",
            _normalized_nonblank(self.transaction_id, "transaction_id"),
        )
        if not isinstance(self.transaction_timestamp, datetime):
            raise TypeError("transaction_timestamp must be a datetime")
        if (
            self.transaction_timestamp.tzinfo is None
            or self.transaction_timestamp.utcoffset() is None
        ):
            raise ValueError("transaction_timestamp must be timezone-aware")
        object.__setattr__(
            self,
            "transaction_timestamp",
            self.transaction_timestamp.astimezone(UTC),
        )


@dataclass(frozen=True, slots=True)
class FixedIncomeBookCostProfileDecisionEvidence:
    """Exact immutable profile decision produced by one authority transaction."""

    effective_date: date
    profile_id: str
    profile_version: int
    authority_content_hash: str
    eligibility_reason: AmortizedCostEligibilityReason | None

    def __post_init__(self) -> None:
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date")
        object.__setattr__(
            self,
            "profile_id",
            _normalized_nonblank(self.profile_id, "profile_id"),
        )
        _require_positive_integer(self.profile_version, "profile_version")
        require_sha256_digest(self.authority_content_hash, "authority_content_hash")
        if self.eligibility_reason is not None and not isinstance(
            self.eligibility_reason,
            AmortizedCostEligibilityReason,
        ):
            raise TypeError("eligibility_reason must be an AmortizedCostEligibilityReason or None")


@dataclass(frozen=True, slots=True)
class FixedIncomeBookCostCorrectionReplayIntent:
    """One source-lot correction and its earliest affected disposal suffix."""

    scope: LotBookCostAuthorityScope
    earliest_affected_date: date
    anchor: AffectedLotDisposalReplayAnchor
    source_authority_event_content_hash: str
    profile_decisions: tuple[FixedIncomeBookCostProfileDecisionEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scope, LotBookCostAuthorityScope):
            raise TypeError("scope must be a LotBookCostAuthorityScope")
        if type(self.earliest_affected_date) is not date:
            raise TypeError("earliest_affected_date must be a date")
        if not isinstance(self.anchor, AffectedLotDisposalReplayAnchor):
            raise TypeError("anchor must be an AffectedLotDisposalReplayAnchor")
        if self.anchor.transaction_timestamp.date() < self.earliest_affected_date:
            raise ValueError("anchor cannot precede earliest_affected_date")
        require_sha256_digest(
            self.source_authority_event_content_hash,
            "source_authority_event_content_hash",
        )
        if not isinstance(self.profile_decisions, tuple):
            raise TypeError("profile_decisions must be a tuple")
        if not self.profile_decisions:
            raise ValueError("profile_decisions must not be empty")
        if not all(
            isinstance(decision, FixedIncomeBookCostProfileDecisionEvidence)
            for decision in self.profile_decisions
        ):
            raise TypeError(
                "profile_decisions must contain FixedIncomeBookCostProfileDecisionEvidence values"
            )
        ordered = tuple(
            sorted(
                self.profile_decisions,
                key=lambda decision: (
                    decision.effective_date,
                    decision.profile_version,
                    decision.profile_id,
                ),
            )
        )
        effective_dates = [decision.effective_date for decision in ordered]
        if len(effective_dates) != len(set(effective_dates)):
            raise ValueError("profile_decisions must have unique effective dates")
        object.__setattr__(self, "profile_decisions", ordered)

    @property
    def command_id(self) -> str:
        """Return the stable business idempotency identity for this replay intent."""

        return cast(
            str,
            canonical_content_hash(
                {
                    "anchor": {
                        "transaction_id": self.anchor.transaction_id,
                        "transaction_timestamp": self.anchor.transaction_timestamp,
                    },
                    "earliest_affected_date": self.earliest_affected_date,
                    "identity_version": FIXED_INCOME_BOOK_COST_CORRECTION_REPLAY_ID_VERSION,
                    "profile_decisions": [
                        {
                            "authority_content_hash": decision.authority_content_hash,
                            "effective_date": decision.effective_date,
                            "eligibility_reason": (
                                decision.eligibility_reason.value
                                if decision.eligibility_reason is not None
                                else None
                            ),
                            "profile_id": decision.profile_id,
                            "profile_version": decision.profile_version,
                        }
                        for decision in self.profile_decisions
                    ],
                    "scope": {
                        "legal_book_id": self.scope.legal_book_id,
                        "lot_id": self.scope.lot_id,
                        "portfolio_id": self.scope.portfolio_id,
                        "security_id": self.scope.security_id,
                        "tenant_id": self.scope.tenant_id,
                    },
                    "source_authority_event_content_hash": (
                        self.source_authority_event_content_hash
                    ),
                }
            ),
        )


def _normalized_nonblank(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be nonblank")
    return normalized


def _require_positive_integer(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
