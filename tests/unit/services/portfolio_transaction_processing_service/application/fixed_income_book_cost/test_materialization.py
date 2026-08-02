"""Verify transaction-safe fixed-income book-cost profile materialization."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from services.portfolio_transaction_processing_service.app.application.fixed_income_book_cost import (  # noqa: E501
    MaterializeLotAmortizedCostProfileUseCase,
)
from services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AmortizedCostEligibilityReason,
    AmortizedCostProfileStatus,
)
from services.portfolio_transaction_processing_service.app.ports import (
    LotAmortizedCostAuthorityBundle,
    LotAmortizedCostAuthorityPort,
    LotAmortizedCostProfileAppendOutcome,
    LotAmortizedCostProfileHead,
    LotAmortizedCostProfilePort,
)
from tests.test_support.fixed_income_book_cost import (
    fixed_income_book_cost_scope,
    resolved_fixed_income_book_cost_inputs,
)


def _bundle() -> LotAmortizedCostAuthorityBundle:
    resolved = resolved_fixed_income_book_cost_inputs()
    assert resolved.yield_fact is not None
    return LotAmortizedCostAuthorityBundle(
        assignments=(resolved.assignment,),
        basis_facts=(resolved.basis_fact,),
        schedule_facts=(resolved.schedule_fact,),
        yield_facts=(resolved.yield_fact,),
    )


def _dependencies():
    authority = AsyncMock(spec=LotAmortizedCostAuthorityPort)
    profiles = AsyncMock(spec=LotAmortizedCostProfilePort)
    return authority, profiles


@pytest.mark.asyncio
async def test_materialization_locks_before_reloading_and_appends_active_profile() -> None:
    authority, profiles = _dependencies()
    calls: list[str] = []
    profiles.acquire_materialization_lock.side_effect = lambda _scope: calls.append("lock")
    authority.load.side_effect = lambda _scope: (calls.append("load"), _bundle())[1]
    profiles.latest_head.side_effect = lambda _scope: (calls.append("head"), None)[1]
    profiles.append.return_value = LotAmortizedCostProfileAppendOutcome.APPENDED
    resolved = resolved_fixed_income_book_cost_inputs()

    result = await MaterializeLotAmortizedCostProfileUseCase(
        authority=authority,
        profiles=profiles,
    ).execute(
        scope=fixed_income_book_cost_scope(),
        effective_date=date(2026, 1, 1),
        policy=resolved.policy,
    )

    assert calls == ["lock", "load", "head"]
    assert result.outcome is LotAmortizedCostProfileAppendOutcome.APPENDED
    assert result.profile_version == 1
    assert result.eligibility_reason is None
    profile = profiles.append.await_args.args[0]
    assert profile.status is AmortizedCostProfileStatus.ACTIVE
    assert profile.authority_content_hash == resolved.cache_key.authority_content_hash


@pytest.mark.asyncio
async def test_materialization_skips_unchanged_active_authority() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    authority.load.return_value = _bundle()
    profiles.latest_head.return_value = LotAmortizedCostProfileHead(
        profile_id="lot-amortized-cost:existing",
        profile_version=4,
        profile_content_hash="a" * 64,
        authority_content_hash=resolved.cache_key.authority_content_hash,
    )

    result = await MaterializeLotAmortizedCostProfileUseCase(
        authority=authority,
        profiles=profiles,
    ).execute(
        scope=fixed_income_book_cost_scope(),
        effective_date=date(2026, 1, 1),
        policy=resolved.policy,
    )

    assert result.outcome is LotAmortizedCostProfileAppendOutcome.UNCHANGED
    assert result.profile_version == 4
    profiles.append.assert_not_awaited()


@pytest.mark.asyncio
async def test_materialization_parks_missing_authority_without_inventing_economics() -> None:
    authority, profiles = _dependencies()
    authority.load.return_value = LotAmortizedCostAuthorityBundle()
    profiles.latest_head.return_value = None
    profiles.append.return_value = LotAmortizedCostProfileAppendOutcome.APPENDED
    resolved = resolved_fixed_income_book_cost_inputs()

    result = await MaterializeLotAmortizedCostProfileUseCase(
        authority=authority,
        profiles=profiles,
    ).execute(
        scope=fixed_income_book_cost_scope(),
        effective_date=date(2026, 1, 1),
        policy=resolved.policy,
    )

    assert result.eligibility_reason is AmortizedCostEligibilityReason.ASSIGNMENT_MISSING
    profile = profiles.append.await_args.args[0]
    assert profile.status is AmortizedCostProfileStatus.PARKED
    assert profile.periods == ()
    assert profile.calculation_lineage is None
    assert profile.authority_content_hash == result.authority_content_hash


@pytest.mark.asyncio
async def test_materialization_appends_next_version_when_authority_changes() -> None:
    authority, profiles = _dependencies()
    authority.load.return_value = _bundle()
    profiles.latest_head.return_value = LotAmortizedCostProfileHead(
        profile_id="lot-amortized-cost:existing",
        profile_version=7,
        profile_content_hash="a" * 64,
        authority_content_hash="b" * 64,
    )
    profiles.append.return_value = LotAmortizedCostProfileAppendOutcome.APPENDED
    resolved = resolved_fixed_income_book_cost_inputs()

    result = await MaterializeLotAmortizedCostProfileUseCase(
        authority=authority,
        profiles=profiles,
    ).execute(
        scope=fixed_income_book_cost_scope(),
        effective_date=date(2026, 1, 1),
        policy=resolved.policy,
    )

    assert result.profile_version == 8
    assert profiles.append.await_args.args[0].profile_version == 8
