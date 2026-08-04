"""Verify strict mapping for correction-triggered disposal replay."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from services.portfolio_transaction_processing_service.app.application.fixed_income_book_cost import (  # noqa: E501
    ConflictingFixedIncomeBookCostReplayCommandError,
    fixed_income_book_cost_disposal_replay_event,
    map_fixed_income_book_cost_disposal_replay_event,
)
from services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AffectedLotDisposalReplayAnchor,
    AmortizedCostEligibilityReason,
    FixedIncomeBookCostCorrectionReplayIntent,
    FixedIncomeBookCostProfileDecisionEvidence,
    LotBookCostAuthorityScope,
)


def _intent() -> FixedIncomeBookCostCorrectionReplayIntent:
    return FixedIncomeBookCostCorrectionReplayIntent(
        scope=LotBookCostAuthorityScope(
            tenant_id="tenant-1",
            legal_book_id="book-1",
            portfolio_id="portfolio-1",
            security_id="security-1",
            lot_id="lot-1",
        ),
        earliest_affected_date=date(2026, 1, 1),
        anchor=AffectedLotDisposalReplayAnchor(
            transaction_id="sell-1",
            transaction_timestamp=datetime(2026, 3, 1, 9, 30, tzinfo=UTC),
        ),
        source_authority_event_content_hash="a" * 64,
        profile_decisions=(
            FixedIncomeBookCostProfileDecisionEvidence(
                effective_date=date(2026, 1, 1),
                profile_id="profile-1",
                profile_version=2,
                authority_content_hash="b" * 64,
                eligibility_reason=AmortizedCostEligibilityReason.ASSIGNMENT_MISSING,
            ),
        ),
    )


def test_round_trip_preserves_business_identity_and_diagnostics() -> None:
    intent = _intent()

    event = fixed_income_book_cost_disposal_replay_event(
        intent,
        correlation_id="correlation-1",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    )

    assert event.command_id == intent.command_id
    assert event.partition_key == "tenant-1|book-1|portfolio-1|security-1|lot-1"
    assert event.correlation_id == "correlation-1"
    assert map_fixed_income_book_cost_disposal_replay_event(event) == intent


def test_diagnostics_do_not_change_business_command_identity() -> None:
    intent = _intent()

    first = fixed_income_book_cost_disposal_replay_event(
        intent,
        correlation_id="correlation-1",
        traceparent=None,
    )
    second = fixed_income_book_cost_disposal_replay_event(
        intent,
        correlation_id="correlation-2",
        traceparent="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
    )

    assert first.command_id == second.command_id == intent.command_id


def test_mapping_rejects_command_identity_that_does_not_bind_payload() -> None:
    event = fixed_income_book_cost_disposal_replay_event(
        _intent(),
        correlation_id=None,
        traceparent=None,
    )

    with pytest.raises(
        ConflictingFixedIncomeBookCostReplayCommandError,
        match="does not match",
    ):
        map_fixed_income_book_cost_disposal_replay_event(
            event.model_copy(update={"command_id": "c" * 64})
        )
