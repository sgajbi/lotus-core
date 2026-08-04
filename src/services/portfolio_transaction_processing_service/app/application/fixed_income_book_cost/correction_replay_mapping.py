"""Map fixed-income correction replay between domain and transport contracts."""

from __future__ import annotations

from portfolio_common.event_contracts import (
    FixedIncomeBookCostAuthorityScope,
    FixedIncomeBookCostDisposalReplayRequestedEvent,
    FixedIncomeBookCostProfileDecisionContract,
    FixedIncomeBookCostReplayEligibilityReason,
)

from ...domain.fixed_income_book_cost import (
    AffectedLotDisposalReplayAnchor,
    AmortizedCostEligibilityReason,
    FixedIncomeBookCostCorrectionReplayIntent,
    FixedIncomeBookCostProfileDecisionEvidence,
    LotBookCostAuthorityScope,
)


class ConflictingFixedIncomeBookCostReplayCommandError(ValueError):
    """Raised when transport command identity differs from its business evidence."""


def fixed_income_book_cost_disposal_replay_event(
    intent: FixedIncomeBookCostCorrectionReplayIntent,
    *,
    correlation_id: str | None,
    traceparent: str | None,
) -> FixedIncomeBookCostDisposalReplayRequestedEvent:
    """Return the strict additive event staged for one domain replay intent."""

    if not isinstance(intent, FixedIncomeBookCostCorrectionReplayIntent):
        raise TypeError("intent must be a FixedIncomeBookCostCorrectionReplayIntent")
    return FixedIncomeBookCostDisposalReplayRequestedEvent(
        command_id=intent.command_id,
        scope=_event_scope(intent.scope),
        earliest_affected_date=intent.earliest_affected_date.isoformat(),
        first_affected_transaction_id=intent.anchor.transaction_id,
        first_affected_transaction_timestamp=intent.anchor.transaction_timestamp.isoformat(),
        source_authority_event_content_hash=intent.source_authority_event_content_hash,
        profile_decisions=tuple(
            FixedIncomeBookCostProfileDecisionContract(
                effective_date=decision.effective_date.isoformat(),
                profile_id=decision.profile_id,
                profile_version=decision.profile_version,
                authority_content_hash=decision.authority_content_hash,
                eligibility_reason=(
                    FixedIncomeBookCostReplayEligibilityReason(decision.eligibility_reason.value)
                    if decision.eligibility_reason is not None
                    else None
                ),
            )
            for decision in intent.profile_decisions
        ),
        correlation_id=correlation_id,
        traceparent=traceparent,
    )


def map_fixed_income_book_cost_disposal_replay_event(
    event: FixedIncomeBookCostDisposalReplayRequestedEvent,
) -> FixedIncomeBookCostCorrectionReplayIntent:
    """Return a domain intent and reject a forged or stale command identity."""

    if not isinstance(event, FixedIncomeBookCostDisposalReplayRequestedEvent):
        raise TypeError("event must be a FixedIncomeBookCostDisposalReplayRequestedEvent")
    intent = FixedIncomeBookCostCorrectionReplayIntent(
        scope=LotBookCostAuthorityScope(
            tenant_id=event.scope.tenant_id,
            legal_book_id=event.scope.legal_book_id,
            portfolio_id=event.scope.portfolio_id,
            security_id=event.scope.security_id,
            lot_id=event.scope.lot_id,
        ),
        earliest_affected_date=event.earliest_affected_date,
        anchor=AffectedLotDisposalReplayAnchor(
            transaction_id=event.first_affected_transaction_id,
            transaction_timestamp=event.first_affected_transaction_timestamp,
        ),
        source_authority_event_content_hash=event.source_authority_event_content_hash,
        profile_decisions=tuple(
            FixedIncomeBookCostProfileDecisionEvidence(
                effective_date=decision.effective_date,
                profile_id=decision.profile_id,
                profile_version=decision.profile_version,
                authority_content_hash=decision.authority_content_hash,
                eligibility_reason=(
                    AmortizedCostEligibilityReason(decision.eligibility_reason.value)
                    if decision.eligibility_reason is not None
                    else None
                ),
            )
            for decision in event.profile_decisions
        ),
    )
    if event.command_id != intent.command_id:
        raise ConflictingFixedIncomeBookCostReplayCommandError(
            "fixed-income book-cost replay command_id does not match business evidence"
        )
    return intent


def _event_scope(scope: LotBookCostAuthorityScope) -> FixedIncomeBookCostAuthorityScope:
    return FixedIncomeBookCostAuthorityScope(
        tenant_id=scope.tenant_id,
        legal_book_id=scope.legal_book_id,
        portfolio_id=scope.portfolio_id,
        security_id=scope.security_id,
        lot_id=scope.lot_id,
    )
