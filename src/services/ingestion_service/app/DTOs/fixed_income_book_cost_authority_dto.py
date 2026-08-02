"""API request contract for fixed-income book-cost source authority."""

from __future__ import annotations

from portfolio_common.event_contracts.fixed_income_book_cost import (
    FixedIncomeBookCostAuthority,
    FixedIncomeBookCostAuthorityEvent,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FixedIncomeBookCostAuthorityIngestionRequest(BaseModel):
    """Atomic caller batch transformed into one governed event per authority record."""

    authorities: list[FixedIncomeBookCostAuthority] = Field(
        min_length=1,
        max_length=1000,
        description=(
            "Source-versioned fixed-income book-cost policy, clean-cost basis, contractual "
            "schedule, and effective-yield authority. Every record is ordered by exact tenant, "
            "legal-book, portfolio, security, and source-lot identity."
        ),
    )

    @model_validator(mode="after")
    def reject_duplicate_source_versions(
        self,
    ) -> FixedIncomeBookCostAuthorityIngestionRequest:
        identities = [_source_version_identity(authority) for authority in self.authorities]
        if len(identities) != len(set(identities)):
            raise ValueError("authorities contains duplicate source-version identities")
        return self

    def events(self) -> tuple[FixedIncomeBookCostAuthorityEvent, ...]:
        """Create source-controlled envelopes instead of accepting caller envelope metadata."""

        return tuple(
            FixedIncomeBookCostAuthorityEvent(authority=authority) for authority in self.authorities
        )

    model_config = ConfigDict(extra="forbid")


def _source_version_identity(authority: FixedIncomeBookCostAuthority) -> tuple[object, ...]:
    header = authority.header
    scope = header.scope
    source = header.source
    return (
        authority.authority_type,
        scope.tenant_id,
        scope.legal_book_id,
        scope.portfolio_id,
        scope.security_id,
        scope.lot_id,
        source.source_system,
        source.source_record_id,
        source.source_version,
    )
