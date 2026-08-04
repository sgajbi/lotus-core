"""Verify deterministic fixed-income correction replay intent identity."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AffectedLotDisposalReplayAnchor,
    AmortizedCostEligibilityReason,
    FixedIncomeBookCostCorrectionReplayIntent,
    FixedIncomeBookCostProfileDecisionEvidence,
    LotBookCostAuthorityScope,
)

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


def _scope() -> LotBookCostAuthorityScope:
    return LotBookCostAuthorityScope(
        tenant_id="tenant-1",
        legal_book_id="book-1",
        portfolio_id="portfolio-1",
        security_id="security-1",
        lot_id="lot-1",
    )


def _decision(
    effective_date: date = date(2026, 1, 1),
    *,
    profile_id: str = "profile-1",
    profile_version: int = 2,
    authority_content_hash: str = _HASH_B,
) -> FixedIncomeBookCostProfileDecisionEvidence:
    return FixedIncomeBookCostProfileDecisionEvidence(
        effective_date=effective_date,
        profile_id=profile_id,
        profile_version=profile_version,
        authority_content_hash=authority_content_hash,
        eligibility_reason=None,
    )


def _intent() -> FixedIncomeBookCostCorrectionReplayIntent:
    return FixedIncomeBookCostCorrectionReplayIntent(
        scope=_scope(),
        earliest_affected_date=date(2026, 1, 1),
        anchor=AffectedLotDisposalReplayAnchor(
            transaction_id="sell-1",
            transaction_timestamp=datetime(2026, 3, 1, 9, 30, tzinfo=UTC),
        ),
        source_authority_event_content_hash=_HASH_A,
        profile_decisions=(_decision(),),
    )


def test_command_identity_is_stable_across_decision_order_and_timezone_offsets() -> None:
    first = _intent()
    later = _decision(
        date(2026, 7, 1),
        profile_id="profile-2",
        profile_version=3,
        authority_content_hash=_HASH_C,
    )
    offset = timezone(timedelta(hours=8))
    equivalent = replace(
        first,
        anchor=AffectedLotDisposalReplayAnchor(
            transaction_id="sell-1",
            transaction_timestamp=datetime(2026, 3, 1, 17, 30, tzinfo=offset),
        ),
        profile_decisions=(later, first.profile_decisions[0]),
    )
    canonical = replace(first, profile_decisions=(first.profile_decisions[0], later))

    assert equivalent.profile_decisions == canonical.profile_decisions
    assert equivalent.command_id == canonical.command_id
    assert len(canonical.command_id) == 64


@pytest.mark.parametrize(
    "changed",
    (
        {"source_authority_event_content_hash": _HASH_C},
        {"earliest_affected_date": date(2026, 2, 1)},
        {
            "anchor": AffectedLotDisposalReplayAnchor(
                transaction_id="sell-2",
                transaction_timestamp=datetime(2026, 3, 1, 9, 30, tzinfo=UTC),
            )
        },
        {"profile_decisions": (_decision(profile_version=3),)},
    ),
)
def test_command_identity_changes_with_business_replay_evidence(changed: dict[str, object]) -> None:
    original = _intent()

    assert replace(original, **changed).command_id != original.command_id


def test_profile_decision_preserves_fail_closed_eligibility_evidence() -> None:
    decision = replace(
        _decision(),
        eligibility_reason=AmortizedCostEligibilityReason.ASSIGNMENT_CONFLICTING,
    )

    intent = replace(_intent(), profile_decisions=(decision,))

    assert intent.profile_decisions[0].eligibility_reason is (
        AmortizedCostEligibilityReason.ASSIGNMENT_CONFLICTING
    )
    assert len(intent.command_id) == 64


def test_anchor_requires_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AffectedLotDisposalReplayAnchor(
            transaction_id="sell-1",
            transaction_timestamp=datetime(2026, 3, 1, 9, 30),
        )


def test_intent_rejects_anchor_before_affected_boundary() -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        replace(
            _intent(),
            earliest_affected_date=date(2026, 4, 1),
        )


def test_intent_rejects_empty_or_duplicate_profile_decisions() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        replace(_intent(), profile_decisions=())

    with pytest.raises(ValueError, match="unique effective dates"):
        replace(
            _intent(),
            profile_decisions=(
                _decision(),
                _decision(profile_id="profile-2", profile_version=3),
            ),
        )


def test_intent_rejects_malformed_evidence_hash() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        replace(_intent(), source_authority_event_content_hash="not-a-hash")
