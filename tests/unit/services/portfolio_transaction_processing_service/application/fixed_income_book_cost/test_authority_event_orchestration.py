"""Verify authority-event persistence and exact-scope materialization orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from unittest.mock import AsyncMock

import pytest
from portfolio_common.event_contracts import FixedIncomeBookCostAuthorityEvent

from services.portfolio_transaction_processing_service.app.application.fixed_income_book_cost import (  # noqa: E501
    ApplyFixedIncomeBookCostAuthorityEventUseCase,
    HandleFixedIncomeBookCostAuthorityEventUseCase,
)
from services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AmortizedCostEligibilityReason,
    AmortizedCostPolicyRegistry,
)
from services.portfolio_transaction_processing_service.app.ports import (
    LotAmortizedCostAuthorityAppendOutcome,
    LotAmortizedCostAuthorityBundle,
    LotAmortizedCostAuthorityPort,
    LotAmortizedCostProfileAppendOutcome,
    LotAmortizedCostProfileHead,
    LotAmortizedCostProfilePort,
)
from tests.test_support.fixed_income_book_cost import resolved_fixed_income_book_cost_inputs


def _basis_event(basis) -> FixedIncomeBookCostAuthorityEvent:
    return FixedIncomeBookCostAuthorityEvent.model_validate(
        {
            "event_type": "fixed_income.book_cost.authority.received",
            "schema_version": "1.0.0",
            "authority": {
                "authority_type": "CLEAN_COST_BASIS",
                "header": {
                    "scope": {
                        "tenant_id": basis.scope.tenant_id,
                        "legal_book_id": basis.scope.legal_book_id,
                        "portfolio_id": basis.scope.portfolio_id,
                        "security_id": basis.scope.security_id,
                        "lot_id": basis.scope.lot_id,
                    },
                    "source": {
                        "source_system": basis.source.source_system,
                        "source_record_id": basis.source.source_record_id,
                        "source_revision": basis.source.source_revision,
                        "source_version": basis.source.fact_version,
                        "observed_at": basis.source.observed_at.isoformat(),
                    },
                    "status": basis.fact_status.value,
                    "valid_from": basis.valid_from.isoformat(),
                    "valid_to": basis.valid_to.isoformat() if basis.valid_to else None,
                },
                "currency": basis.currency,
                "initial_clean_cost_local": str(basis.initial_clean_cost_local),
                "fees_in_basis_local": str(basis.fees_in_basis_local),
                "redemption_value_local": str(basis.redemption_value_local),
                "discount_origin": basis.discount_origin.value,
            },
        }
    )


def _assignment_event(assignment) -> FixedIncomeBookCostAuthorityEvent:
    return FixedIncomeBookCostAuthorityEvent.model_validate(
        {
            "event_type": "fixed_income.book_cost.authority.received",
            "schema_version": "1.0.0",
            "authority": {
                "authority_type": "POLICY_ASSIGNMENT",
                "header": {
                    "scope": {
                        "tenant_id": assignment.scope.tenant_id,
                        "legal_book_id": assignment.scope.legal_book_id,
                        "portfolio_id": assignment.scope.portfolio_id,
                        "security_id": assignment.scope.security_id,
                        "lot_id": assignment.scope.lot_id,
                    },
                    "source": {
                        "source_system": assignment.source_system,
                        "source_record_id": assignment.source_record_id,
                        "source_revision": assignment.source_revision,
                        "source_version": assignment.assignment_version,
                        "observed_at": assignment.observed_at.isoformat(),
                    },
                    "status": assignment.assignment_status.value,
                    "valid_from": assignment.valid_from.isoformat(),
                    "valid_to": (assignment.valid_to.isoformat() if assignment.valid_to else None),
                },
                "policy_id": assignment.policy_id,
                "policy_version": assignment.policy_version,
                "assignment_reason": assignment.assignment_reason,
            },
        }
    )


def _bundle(*, basis_facts) -> LotAmortizedCostAuthorityBundle:
    resolved = resolved_fixed_income_book_cost_inputs()
    assert resolved.yield_fact is not None
    return LotAmortizedCostAuthorityBundle(
        assignments=(resolved.assignment,),
        basis_facts=tuple(basis_facts),
        schedule_facts=(resolved.schedule_fact,),
        yield_facts=(resolved.yield_fact,),
    )


def _dependencies():
    authority = AsyncMock(spec=LotAmortizedCostAuthorityPort)
    profiles = AsyncMock(spec=LotAmortizedCostProfilePort)
    authority.append.return_value = LotAmortizedCostAuthorityAppendOutcome.APPENDED
    profiles.latest_verified_head.return_value = None
    profiles.latest_verified_head_for_effective_date.side_effect = (
        lambda _scope, *, effective_date: profiles.latest_verified_head.return_value
    )
    profiles.effective_boundaries_from.return_value = ()
    profiles.append.return_value = LotAmortizedCostProfileAppendOutcome.APPENDED
    return authority, profiles


class _UnitOfWork:
    def __init__(self, authority, profiles) -> None:
        self.authority = authority
        self.profiles = profiles
        self.committed = False
        self.exit_error: BaseException | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, exc_value, _traceback) -> None:
        self.exit_error = exc_value

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_applies_mapped_authority_then_materializes_event_owned_scope() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    authority.load.return_value = _bundle(basis_facts=(resolved.basis_fact,))
    event = _basis_event(resolved.basis_fact)
    effective_date = date(2026, 1, 1)

    result = await ApplyFixedIncomeBookCostAuthorityEventUseCase(
        authority=authority,
        profiles=profiles,
    ).execute(
        event,
        effective_date=effective_date,
        policy=resolved.policy,
    )

    authority.append.assert_awaited_once_with(resolved.basis_fact)
    authority.load.assert_awaited_once_with(resolved.basis_fact.scope)
    profiles.acquire_materialization_lock.assert_awaited_once_with(resolved.basis_fact.scope)
    persisted_profile = profiles.append.await_args.args[0]
    assert persisted_profile.scope == resolved.basis_fact.scope
    assert persisted_profile.effective_date == effective_date
    assert persisted_profile.policy_id == resolved.policy.policy_id
    assert persisted_profile.policy_version == resolved.policy.policy_version
    assert result.scope == resolved.basis_fact.scope
    assert result.persistence.appended_count == 1
    assert result.materialization.outcome is LotAmortizedCostProfileAppendOutcome.APPENDED


@pytest.mark.asyncio
async def test_exact_duplicate_is_unchanged_for_authority_and_materialization() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    authority.load.return_value = _bundle(basis_facts=(resolved.basis_fact,))
    event = _basis_event(resolved.basis_fact)
    use_case = ApplyFixedIncomeBookCostAuthorityEventUseCase(
        authority=authority,
        profiles=profiles,
    )

    first = await use_case.execute(
        event,
        effective_date=date(2026, 1, 1),
        policy=resolved.policy,
    )
    first_profile = profiles.append.await_args.args[0]
    authority.append.return_value = LotAmortizedCostAuthorityAppendOutcome.UNCHANGED
    profiles.latest_verified_head.return_value = LotAmortizedCostProfileHead(
        profile_id=first_profile.profile_id,
        profile_version=first_profile.profile_version,
        profile_content_hash=first_profile.content_hash(),
        authority_content_hash=first.materialization.authority_content_hash,
    )
    profiles.append.reset_mock()

    duplicate = await use_case.execute(
        event,
        effective_date=date(2026, 1, 1),
        policy=resolved.policy,
    )

    assert duplicate.persistence.appended_count == 0
    assert duplicate.persistence.unchanged_count == 1
    assert duplicate.materialization.outcome is LotAmortizedCostProfileAppendOutcome.UNCHANGED
    assert duplicate.materialization.profile_version == 1
    profiles.append.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_correction_appends_next_profile_from_latest_source_version() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    corrected = replace(
        resolved.basis_fact,
        source=replace(
            resolved.basis_fact.source,
            source_revision="revision-2",
            fact_version=2,
        ),
    )
    authority.load.return_value = _bundle(basis_facts=(resolved.basis_fact,))
    use_case = ApplyFixedIncomeBookCostAuthorityEventUseCase(
        authority=authority,
        profiles=profiles,
    )

    first = await use_case.execute(
        _basis_event(resolved.basis_fact),
        effective_date=date(2026, 1, 1),
        policy=resolved.policy,
    )
    first_profile = profiles.append.await_args.args[0]
    profiles.latest_verified_head.return_value = LotAmortizedCostProfileHead(
        profile_id=first_profile.profile_id,
        profile_version=first_profile.profile_version,
        profile_content_hash=first_profile.content_hash(),
        authority_content_hash=first.materialization.authority_content_hash,
    )
    authority.load.return_value = _bundle(
        basis_facts=(resolved.basis_fact, corrected),
    )

    correction = await use_case.execute(
        _basis_event(corrected),
        effective_date=date(2026, 1, 1),
        policy=resolved.policy,
    )

    assert authority.append.await_args.args[0] == corrected
    assert correction.persistence.appended_count == 1
    assert correction.materialization.outcome is LotAmortizedCostProfileAppendOutcome.APPENDED
    assert correction.materialization.profile_version == 2
    assert correction.materialization.authority_content_hash != (
        first.materialization.authority_content_hash
    )
    corrected_profile = profiles.append.await_args.args[0]
    assert any(
        reference.source_record_id == corrected.source.source_record_id
        and reference.source_revision == "revision-2"
        for reference in corrected_profile.source_references
    )


@pytest.mark.asyncio
async def test_atomic_handler_resolves_exact_policy_and_commits_active_profile() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    authority.load.return_value = _bundle(basis_facts=(resolved.basis_fact,))
    unit_of_work = _UnitOfWork(authority, profiles)

    result = await HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=lambda: unit_of_work,
        policies=AmortizedCostPolicyRegistry((resolved.policy,)),
    ).execute(_basis_event(resolved.basis_fact))

    assert unit_of_work.committed is True
    assert unit_of_work.exit_error is None
    assert result.persistence.appended_count == 1
    assert result.materialization.eligibility_reason is None
    assert profiles.append.await_args.args[0].policy_id == resolved.policy.policy_id
    assert authority.load.await_count == 2


@pytest.mark.asyncio
async def test_atomic_handler_rematerializes_every_later_persisted_boundary() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    later_boundary = date(2026, 7, 1)
    later_policy = replace(
        resolved.policy,
        policy_id="IFRS9_EIR_REVISED",
        policy_version=2,
    )
    initial_assignment = replace(resolved.assignment, valid_to=date(2026, 6, 30))
    later_assignment = replace(
        resolved.assignment,
        policy_id=later_policy.policy_id,
        policy_version=later_policy.policy_version,
        valid_from=later_boundary,
        assignment_version=2,
        source_record_id="AMORT_LOT_001_POLICY_REVISED",
        source_revision="revision-2",
    )
    authority.load.return_value = replace(
        _bundle(basis_facts=(resolved.basis_fact,)),
        assignments=(initial_assignment, later_assignment),
    )
    profiles.effective_boundaries_from.return_value = (
        date(2026, 1, 1),
        later_boundary,
    )
    unit_of_work = _UnitOfWork(authority, profiles)

    result = await HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=lambda: unit_of_work,
        policies=AmortizedCostPolicyRegistry((resolved.policy, later_policy)),
    ).execute(_basis_event(resolved.basis_fact))

    persisted_profiles = [call.args[0] for call in profiles.append.await_args_list]
    assert [profile.effective_date for profile in persisted_profiles] == [
        date(2026, 1, 1),
        later_boundary,
    ]
    assert [profile.policy_id for profile in persisted_profiles] == [
        resolved.policy.policy_id,
        later_policy.policy_id,
    ]
    assert result.materialization.outcome is LotAmortizedCostProfileAppendOutcome.APPENDED
    assert len(result.rematerializations) == 1
    assert result.rematerializations[0].outcome is LotAmortizedCostProfileAppendOutcome.APPENDED
    assert unit_of_work.committed is True
    assert authority.load.await_count == 4


@pytest.mark.asyncio
async def test_assignment_correction_moved_later_replays_superseded_boundary() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    previous = resolved.assignment
    current = replace(
        previous,
        valid_from=date(2026, 7, 1),
        assignment_version=2,
        source_revision="revision-2",
    )
    authority.load.return_value = replace(
        _bundle(basis_facts=(resolved.basis_fact,)),
        assignments=(previous, current),
    )
    profiles.effective_boundaries_from.return_value = (previous.valid_from,)
    unit_of_work = _UnitOfWork(authority, profiles)

    result = await HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=lambda: unit_of_work,
        policies=AmortizedCostPolicyRegistry((resolved.policy,)),
    ).execute(_assignment_event(current))

    profiles.effective_boundaries_from.assert_awaited_once_with(
        current.scope,
        effective_date=previous.valid_from,
    )
    persisted_profiles = [call.args[0] for call in profiles.append.await_args_list]
    assert [profile.effective_date for profile in persisted_profiles] == [
        previous.valid_from,
        current.valid_from,
    ]
    assert persisted_profiles[0].eligibility_reason is (
        AmortizedCostEligibilityReason.ASSIGNMENT_MISSING
    )
    assert persisted_profiles[1].eligibility_reason is None
    assert result.materialization.profile_id == persisted_profiles[1].profile_id
    assert result.rematerializations[0].profile_id == persisted_profiles[0].profile_id
    assert unit_of_work.committed is True


@pytest.mark.asyncio
async def test_assignment_correction_moved_earlier_replays_from_new_boundary() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    previous = replace(resolved.assignment, valid_from=date(2026, 7, 1))
    current = replace(
        previous,
        valid_from=date(2026, 1, 1),
        assignment_version=2,
        source_revision="revision-2",
    )
    authority.load.return_value = replace(
        _bundle(basis_facts=(resolved.basis_fact,)),
        assignments=(previous, current),
    )
    profiles.effective_boundaries_from.return_value = (previous.valid_from,)
    unit_of_work = _UnitOfWork(authority, profiles)

    result = await HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=lambda: unit_of_work,
        policies=AmortizedCostPolicyRegistry((resolved.policy,)),
    ).execute(_assignment_event(current))

    profiles.effective_boundaries_from.assert_awaited_once_with(
        current.scope,
        effective_date=current.valid_from,
    )
    persisted_profiles = [call.args[0] for call in profiles.append.await_args_list]
    assert [profile.effective_date for profile in persisted_profiles] == [
        current.valid_from,
        previous.valid_from,
    ]
    assert result.materialization.profile_id == persisted_profiles[0].profile_id
    assert result.rematerializations[0].profile_id == persisted_profiles[1].profile_id
    assert unit_of_work.committed is True


@pytest.mark.asyncio
async def test_exact_duplicate_assignment_does_not_broaden_replay_or_append_profile() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    assignment = resolved.assignment
    authority.load.return_value = replace(
        _bundle(basis_facts=(resolved.basis_fact,)),
        assignments=(assignment,),
    )
    first_unit_of_work = _UnitOfWork(authority, profiles)
    handler = HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=lambda: first_unit_of_work,
        policies=AmortizedCostPolicyRegistry((resolved.policy,)),
    )

    first = await handler.execute(_assignment_event(assignment))
    first_profile = profiles.append.await_args.args[0]
    profiles.latest_verified_head.return_value = LotAmortizedCostProfileHead(
        profile_id=first_profile.profile_id,
        profile_version=first_profile.profile_version,
        profile_content_hash=first_profile.content_hash(),
        authority_content_hash=first.materialization.authority_content_hash,
    )
    authority.append.return_value = LotAmortizedCostAuthorityAppendOutcome.UNCHANGED
    authority.load.reset_mock()
    profiles.append.reset_mock()
    profiles.effective_boundaries_from.reset_mock()
    duplicate_unit_of_work = _UnitOfWork(authority, profiles)
    duplicate_handler = HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=lambda: duplicate_unit_of_work,
        policies=AmortizedCostPolicyRegistry((resolved.policy,)),
    )

    duplicate = await duplicate_handler.execute(_assignment_event(assignment))

    assert duplicate.persistence.unchanged_count == 1
    assert duplicate.materialization.outcome is LotAmortizedCostProfileAppendOutcome.UNCHANGED
    profiles.append.assert_not_awaited()
    profiles.effective_boundaries_from.assert_awaited_once_with(
        assignment.scope,
        effective_date=assignment.valid_from,
    )
    assert authority.load.await_count == 2
    assert duplicate_unit_of_work.committed is True


@pytest.mark.asyncio
async def test_atomic_handler_commits_parked_evidence_when_assignment_is_missing() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    authority.load.return_value = LotAmortizedCostAuthorityBundle(
        basis_facts=(resolved.basis_fact,)
    )
    unit_of_work = _UnitOfWork(authority, profiles)

    result = await HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=lambda: unit_of_work,
        policies=AmortizedCostPolicyRegistry((resolved.policy,)),
    ).execute(_basis_event(resolved.basis_fact))

    assert unit_of_work.committed is True
    assert result.materialization.eligibility_reason is (
        AmortizedCostEligibilityReason.ASSIGNMENT_MISSING
    )
    parked = profiles.append.await_args.args[0]
    assert parked.policy_id is None
    assert parked.policy_version is None


@pytest.mark.asyncio
async def test_atomic_handler_commits_parked_evidence_for_unregistered_policy() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    authority.load.return_value = _bundle(basis_facts=(resolved.basis_fact,))
    unit_of_work = _UnitOfWork(authority, profiles)

    result = await HandleFixedIncomeBookCostAuthorityEventUseCase(
        unit_of_work_factory=lambda: unit_of_work,
        policies=AmortizedCostPolicyRegistry(()),
    ).execute(_basis_event(resolved.basis_fact))

    assert unit_of_work.committed is True
    assert result.materialization.eligibility_reason is (
        AmortizedCostEligibilityReason.POLICY_UNSUPPORTED
    )


@pytest.mark.asyncio
async def test_atomic_handler_does_not_commit_when_profile_persistence_fails() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    authority.load.return_value = _bundle(basis_facts=(resolved.basis_fact,))
    profiles.append.side_effect = RuntimeError("database unavailable")
    unit_of_work = _UnitOfWork(authority, profiles)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await HandleFixedIncomeBookCostAuthorityEventUseCase(
            unit_of_work_factory=lambda: unit_of_work,
            policies=AmortizedCostPolicyRegistry((resolved.policy,)),
        ).execute(_basis_event(resolved.basis_fact))

    assert unit_of_work.committed is False
    assert isinstance(unit_of_work.exit_error, RuntimeError)


@pytest.mark.asyncio
async def test_atomic_handler_rolls_back_when_later_boundary_rebuild_fails() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    authority.load.return_value = _bundle(basis_facts=(resolved.basis_fact,))
    profiles.effective_boundaries_from.return_value = (
        date(2026, 1, 1),
        date(2026, 7, 1),
    )
    profiles.append.side_effect = (
        LotAmortizedCostProfileAppendOutcome.APPENDED,
        RuntimeError("later boundary unavailable"),
    )
    unit_of_work = _UnitOfWork(authority, profiles)

    with pytest.raises(RuntimeError, match="later boundary unavailable"):
        await HandleFixedIncomeBookCostAuthorityEventUseCase(
            unit_of_work_factory=lambda: unit_of_work,
            policies=AmortizedCostPolicyRegistry((resolved.policy,)),
        ).execute(_basis_event(resolved.basis_fact))

    assert profiles.append.await_count == 2
    assert unit_of_work.committed is False
    assert isinstance(unit_of_work.exit_error, RuntimeError)


@pytest.mark.asyncio
async def test_assignment_correction_rolls_back_when_superseded_boundary_rebuild_fails() -> None:
    authority, profiles = _dependencies()
    resolved = resolved_fixed_income_book_cost_inputs()
    previous = resolved.assignment
    current = replace(
        previous,
        valid_from=date(2026, 7, 1),
        assignment_version=2,
        source_revision="revision-2",
    )
    authority.load.return_value = replace(
        _bundle(basis_facts=(resolved.basis_fact,)),
        assignments=(previous, current),
    )
    profiles.effective_boundaries_from.return_value = (previous.valid_from,)
    profiles.append.side_effect = RuntimeError("superseded boundary unavailable")
    unit_of_work = _UnitOfWork(authority, profiles)

    with pytest.raises(RuntimeError, match="superseded boundary unavailable"):
        await HandleFixedIncomeBookCostAuthorityEventUseCase(
            unit_of_work_factory=lambda: unit_of_work,
            policies=AmortizedCostPolicyRegistry((resolved.policy,)),
        ).execute(_assignment_event(current))

    authority.append.assert_awaited_once_with(current)
    assert unit_of_work.committed is False
    assert isinstance(unit_of_work.exit_error, RuntimeError)
