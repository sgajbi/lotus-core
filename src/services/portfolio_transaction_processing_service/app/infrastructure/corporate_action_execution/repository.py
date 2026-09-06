"""Materialize frozen corporate-action releases from current READY evidence."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from portfolio_common.database_models import (
    CorporateActionChildObservationRecord,
    CorporateActionEventRecord,
    CorporateActionExecutionMemberRecord,
    CorporateActionExecutionReleaseRecord,
    CorporateActionReadinessEvaluationRecord,
)
from portfolio_common.database_models import Transaction as TransactionRecord
from sqlalchemy import case, func, insert, literal, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ...application.corporate_action_execution import CorporateActionExecutionPlan
from ...application.corporate_action_release import (
    ClaimedCorporateActionExecutionRelease,
    ConflictingCorporateActionExecutionReleaseError,
    CorporateActionExecutionLeaseRequest,
    CorporateActionExecutionMemberAuthority,
    CorporateActionExecutionPayloadAuthorityError,
    CorporateActionExecutionReleaseAuthority,
    CorporateActionReleaseMaterialization,
    CorporateActionReleaseMaterializationOutcome,
    CorporateActionReleaseProgressOutcome,
    LostCorporateActionExecutionLeaseError,
    StaleCorporateActionExecutionPlanError,
    build_corporate_action_execution_member_authority,
)
from ...domain import BookedTransaction, build_transaction_semantic_identity
from ..transaction_mapping.booked_transaction import to_booked_transaction_from_record


class SqlAlchemyCorporateActionExecutionReleaseRepository:
    """Persist one complete release generation within the caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(
        self,
        plan: CorporateActionExecutionPlan,
    ) -> CorporateActionReleaseMaterialization:
        if not isinstance(plan, CorporateActionExecutionPlan):
            raise TypeError("plan must be a CorporateActionExecutionPlan")
        await self._acquire_release_lock(plan)
        readiness, event = await self._require_current_ready_evidence(plan)
        members = await self._build_member_authority(
            plan,
            event_id=event.id,
        )
        authority = CorporateActionExecutionReleaseAuthority(plan=plan, members=members)
        existing = await self._session.scalar(
            select(CorporateActionExecutionReleaseRecord).where(
                CorporateActionExecutionReleaseRecord.readiness_evaluation_id == readiness.id
            )
        )
        if existing is not None:
            await self._require_same_release(existing, authority)
            return _materialization(
                existing,
                CorporateActionReleaseMaterializationOutcome.UNCHANGED,
            )

        release = CorporateActionExecutionReleaseRecord(
            readiness_evaluation_id=readiness.id,
            structural_plan_content_hash=plan.structural_plan_content_hash,
            release_authority_hash=authority.release_authority_hash,
            member_count=len(authority.members),
        )
        self._session.add(release)
        await self._session.flush()
        await self._session.execute(
            insert(CorporateActionExecutionMemberRecord),
            [
                {
                    "release_id": release.id,
                    **member.lineage_payload(),
                }
                for member in authority.members
            ],
        )
        return _materialization(
            release,
            CorporateActionReleaseMaterializationOutcome.APPENDED,
        )

    async def claim_next(
        self,
        lease: CorporateActionExecutionLeaseRequest,
    ) -> ClaimedCorporateActionExecutionRelease | None:
        """Claim one pending or expired release using database-clock lease fencing."""

        if not isinstance(lease, CorporateActionExecutionLeaseRequest):
            raise TypeError("lease must be a CorporateActionExecutionLeaseRequest")
        await self._supersede_stale_pending_releases()
        release = CorporateActionExecutionReleaseRecord
        candidate_readiness = aliased(CorporateActionReadinessEvaluationRecord)
        active_release = aliased(CorporateActionExecutionReleaseRecord)
        active_readiness = aliased(CorporateActionReadinessEvaluationRecord)
        same_event_is_processing = (
            select(1)
            .select_from(active_release)
            .join(
                active_readiness,
                active_readiness.id == active_release.readiness_evaluation_id,
            )
            .where(
                active_release.id != release.id,
                active_release.status == "PROCESSING",
                active_readiness.event_id == candidate_readiness.event_id,
            )
            .correlate(release, candidate_readiness)
            .exists()
        )
        candidate = await self._session.scalar(
            select(release)
            .join(
                candidate_readiness,
                candidate_readiness.id == release.readiness_evaluation_id,
            )
            .where(
                or_(
                    release.status == "PENDING",
                    (release.status == "PROCESSING")
                    & (release.lease_expires_at <= func.clock_timestamp()),
                ),
                ~same_event_is_processing,
            )
            .order_by(release.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if candidate is None:
            return None
        lease_expiry = func.clock_timestamp() + literal(lease.duration_seconds) * text(
            "INTERVAL '1 second'"
        )
        claimed = await self._session.scalar(
            update(release)
            .where(release.id == candidate.id)
            .values(
                status="PROCESSING",
                attempt_count=release.attempt_count + 1,
                fence_token=release.fence_token + 1,
                lease_owner=lease.owner,
                lease_token=lease.token,
                lease_expires_at=lease_expiry,
                terminal_reason=None,
                updated_at=func.now(),
            )
            .returning(release)
            .execution_options(populate_existing=True)
        )
        if claimed is None:
            return None
        member = await self._session.scalar(
            select(CorporateActionExecutionMemberRecord).where(
                CorporateActionExecutionMemberRecord.release_id == claimed.id,
                CorporateActionExecutionMemberRecord.execution_ordinal
                == claimed.next_execution_ordinal,
                CorporateActionExecutionMemberRecord.status == "PENDING",
            )
        )
        if member is None:
            raise ConflictingCorporateActionExecutionReleaseError(
                "claimed corporate-action release lacks its exact next member"
            )
        return _claimed_release(claimed, member)

    async def load_owned_transaction(
        self,
        claim: ClaimedCorporateActionExecutionRelease,
    ) -> BookedTransaction:
        """Reload and authenticate the frozen monetary payload under live lease ownership."""

        if not isinstance(claim, ClaimedCorporateActionExecutionRelease):
            raise TypeError("claim must be a ClaimedCorporateActionExecutionRelease")
        owned = await self._session.scalar(
            select(CorporateActionExecutionReleaseRecord.id).where(
                CorporateActionExecutionReleaseRecord.id == claim.release_id,
                CorporateActionExecutionReleaseRecord.status == "PROCESSING",
                CorporateActionExecutionReleaseRecord.next_execution_ordinal
                == claim.next_member.execution_ordinal,
                CorporateActionExecutionReleaseRecord.lease_owner == claim.lease_owner,
                CorporateActionExecutionReleaseRecord.lease_token == claim.lease_token,
                CorporateActionExecutionReleaseRecord.fence_token == claim.fence_token,
                CorporateActionExecutionReleaseRecord.lease_expires_at > func.clock_timestamp(),
            )
        )
        if owned is None:
            raise LostCorporateActionExecutionLeaseError(
                "corporate-action release lease ownership was lost before payload load"
            )
        persisted = await self._session.scalar(
            select(TransactionRecord).where(
                TransactionRecord.transaction_id == claim.next_member.transaction_id
            )
        )
        if persisted is None:
            raise CorporateActionExecutionPayloadAuthorityError(
                "corporate-action release transaction payload is unavailable"
            )
        transaction = replace(
            to_booked_transaction_from_record(persisted),
            epoch=claim.next_member.transaction_epoch,
        )
        identity = build_transaction_semantic_identity(transaction)
        if identity.payload_fingerprint != claim.next_member.transaction_payload_fingerprint:
            raise CorporateActionExecutionPayloadAuthorityError(
                "corporate-action release transaction payload changed after materialization"
            )
        return transaction

    async def advance_member(
        self,
        *,
        release_id: int,
        expected_ordinal: int,
        lease_token: str,
        fence_token: int,
    ) -> CorporateActionReleaseProgressOutcome:
        """Complete one exact member and advance its owned release atomically."""

        _require_positive_integer(release_id, "release_id")
        _require_nonnegative_integer(expected_ordinal, "expected_ordinal")
        _require_sha256_digest(lease_token, "lease_token")
        _require_positive_integer(fence_token, "fence_token")
        release = CorporateActionExecutionReleaseRecord
        owned = await self._session.scalar(
            select(release)
            .where(
                release.id == release_id,
                release.status == "PROCESSING",
                release.next_execution_ordinal == expected_ordinal,
                release.lease_token == lease_token,
                release.fence_token == fence_token,
                release.lease_expires_at > func.clock_timestamp(),
            )
            .with_for_update()
        )
        if owned is None:
            return CorporateActionReleaseProgressOutcome.LOST_OWNERSHIP
        member_result = await self._session.execute(
            update(CorporateActionExecutionMemberRecord)
            .where(
                CorporateActionExecutionMemberRecord.release_id == release_id,
                CorporateActionExecutionMemberRecord.execution_ordinal == expected_ordinal,
                CorporateActionExecutionMemberRecord.status == "PENDING",
            )
            .values(
                status="COMPLETE",
                completed_fence_token=fence_token,
                completed_at=func.now(),
            )
        )
        if int(member_result.rowcount or 0) != 1:
            raise ConflictingCorporateActionExecutionReleaseError(
                "owned corporate-action release member is not pending"
            )
        next_ordinal = release.next_execution_ordinal + 1
        completes_release = next_ordinal == release.member_count
        advanced = await self._session.scalar(
            update(release)
            .where(
                release.id == release_id,
                release.status == "PROCESSING",
                release.next_execution_ordinal == expected_ordinal,
                release.lease_token == lease_token,
                release.fence_token == fence_token,
                release.lease_expires_at > func.clock_timestamp(),
            )
            .values(
                next_execution_ordinal=next_ordinal,
                status=case((completes_release, "COMPLETE"), else_="PROCESSING"),
                lease_owner=case((completes_release, None), else_=release.lease_owner),
                lease_token=case((completes_release, None), else_=release.lease_token),
                lease_expires_at=case((completes_release, None), else_=release.lease_expires_at),
                completed_at=case((completes_release, func.now()), else_=None),
                updated_at=func.now(),
            )
            .returning(release.status)
        )
        if advanced is None:
            raise ConflictingCorporateActionExecutionReleaseError(
                "owned corporate-action release did not advance"
            )
        return (
            CorporateActionReleaseProgressOutcome.COMPLETE
            if advanced == "COMPLETE"
            else CorporateActionReleaseProgressOutcome.ADVANCED
        )

    async def fail_release(
        self,
        *,
        release_id: int,
        expected_ordinal: int,
        lease_token: str,
        fence_token: int,
        terminal_reason: str,
    ) -> bool:
        """Fail one owned release without allowing a stale worker to mutate progress."""

        _require_positive_integer(release_id, "release_id")
        _require_nonnegative_integer(expected_ordinal, "expected_ordinal")
        _require_sha256_digest(lease_token, "lease_token")
        _require_positive_integer(fence_token, "fence_token")
        reason = terminal_reason.strip()
        if not reason or len(reason) > 512:
            raise ValueError("terminal_reason must contain at most 512 nonblank characters")
        result = await self._session.execute(
            update(CorporateActionExecutionReleaseRecord)
            .where(
                CorporateActionExecutionReleaseRecord.id == release_id,
                CorporateActionExecutionReleaseRecord.status == "PROCESSING",
                CorporateActionExecutionReleaseRecord.next_execution_ordinal == expected_ordinal,
                CorporateActionExecutionReleaseRecord.lease_token == lease_token,
                CorporateActionExecutionReleaseRecord.fence_token == fence_token,
                CorporateActionExecutionReleaseRecord.lease_expires_at > func.clock_timestamp(),
            )
            .values(
                status="FAILED",
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                terminal_reason=reason,
                updated_at=func.now(),
            )
        )
        return int(result.rowcount or 0) == 1

    async def load_owned_next(
        self,
        *,
        release_id: int,
        lease_token: str,
        fence_token: int,
    ) -> ClaimedCorporateActionExecutionRelease | None:
        """Reload the exact next member only while the caller still owns the lease."""

        _require_positive_integer(release_id, "release_id")
        _require_sha256_digest(lease_token, "lease_token")
        _require_positive_integer(fence_token, "fence_token")
        release = await self._session.scalar(
            select(CorporateActionExecutionReleaseRecord).where(
                CorporateActionExecutionReleaseRecord.id == release_id,
                CorporateActionExecutionReleaseRecord.status == "PROCESSING",
                CorporateActionExecutionReleaseRecord.lease_token == lease_token,
                CorporateActionExecutionReleaseRecord.fence_token == fence_token,
                CorporateActionExecutionReleaseRecord.lease_expires_at > func.clock_timestamp(),
            )
        )
        if release is None:
            return None
        member = await self._session.scalar(
            select(CorporateActionExecutionMemberRecord).where(
                CorporateActionExecutionMemberRecord.release_id == release.id,
                CorporateActionExecutionMemberRecord.execution_ordinal
                == release.next_execution_ordinal,
                CorporateActionExecutionMemberRecord.status == "PENDING",
            )
        )
        if member is None:
            raise ConflictingCorporateActionExecutionReleaseError(
                "owned corporate-action release lacks its exact next member"
            )
        return _claimed_release(release, member)

    async def renew_lease(
        self,
        *,
        release_id: int,
        lease: CorporateActionExecutionLeaseRequest,
        fence_token: int,
    ) -> bool:
        """Extend an unexpired owned lease using the PostgreSQL clock."""

        _require_positive_integer(release_id, "release_id")
        if not isinstance(lease, CorporateActionExecutionLeaseRequest):
            raise TypeError("lease must be a CorporateActionExecutionLeaseRequest")
        _require_positive_integer(fence_token, "fence_token")
        lease_expiry = func.clock_timestamp() + literal(lease.duration_seconds) * text(
            "INTERVAL '1 second'"
        )
        result = await self._session.execute(
            update(CorporateActionExecutionReleaseRecord)
            .where(
                CorporateActionExecutionReleaseRecord.id == release_id,
                CorporateActionExecutionReleaseRecord.status == "PROCESSING",
                CorporateActionExecutionReleaseRecord.lease_owner == lease.owner,
                CorporateActionExecutionReleaseRecord.lease_token == lease.token,
                CorporateActionExecutionReleaseRecord.fence_token == fence_token,
                CorporateActionExecutionReleaseRecord.lease_expires_at > func.clock_timestamp(),
            )
            .values(lease_expires_at=lease_expiry, updated_at=func.now())
        )
        return int(result.rowcount or 0) == 1

    async def _supersede_stale_pending_releases(self) -> None:
        release = CorporateActionExecutionReleaseRecord
        readiness = CorporateActionReadinessEvaluationRecord
        event = CorporateActionEventRecord
        stale_current_state = (
            select(1)
            .select_from(readiness)
            .join(event, event.id == readiness.event_id)
            .where(
                readiness.id == release.readiness_evaluation_id,
                or_(
                    event.state_version != readiness.state_version,
                    event.readiness_status != "READY",
                ),
            )
            .correlate(release)
            .exists()
        )
        await self._session.execute(
            update(release)
            .where(release.status == "PENDING", stale_current_state)
            .values(
                status="SUPERSEDED",
                terminal_reason="superseded_by_newer_event_state",
                updated_at=func.now(),
            )
        )

    async def _acquire_release_lock(self, plan: CorporateActionExecutionPlan) -> None:
        lock_identity = (
            f"ca-release:{plan.portfolio_id}:{plan.corporate_action_event_id}:"
            f"{plan.readiness_state_version}"
        )
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(lock_identity, 0)))
        )

    async def _require_current_ready_evidence(
        self,
        plan: CorporateActionExecutionPlan,
    ) -> tuple[CorporateActionReadinessEvaluationRecord, CorporateActionEventRecord]:
        row = (
            await self._session.execute(
                select(
                    CorporateActionReadinessEvaluationRecord,
                    CorporateActionEventRecord,
                )
                .join(
                    CorporateActionEventRecord,
                    CorporateActionEventRecord.id
                    == CorporateActionReadinessEvaluationRecord.event_id,
                )
                .where(
                    CorporateActionEventRecord.portfolio_id == plan.portfolio_id,
                    CorporateActionEventRecord.corporate_action_event_id
                    == plan.corporate_action_event_id,
                    CorporateActionEventRecord.linked_transaction_group_id
                    == plan.linked_transaction_group_id,
                    CorporateActionEventRecord.parent_event_reference
                    == plan.parent_event_reference,
                    CorporateActionEventRecord.readiness_status == "READY",
                    CorporateActionEventRecord.state_version == plan.readiness_state_version,
                    CorporateActionEventRecord.last_observation_sequence
                    == plan.through_observation_sequence,
                    CorporateActionReadinessEvaluationRecord.state_version
                    == plan.readiness_state_version,
                    CorporateActionReadinessEvaluationRecord.through_observation_sequence
                    == plan.through_observation_sequence,
                    CorporateActionReadinessEvaluationRecord.readiness_status == "READY",
                    CorporateActionReadinessEvaluationRecord.manifest_content_hash
                    == plan.manifest_content_hash,
                    CorporateActionReadinessEvaluationRecord.execution_plan_content_hash
                    == plan.structural_plan_content_hash,
                )
            )
        ).one_or_none()
        if row is None:
            raise StaleCorporateActionExecutionPlanError(
                "corporate-action execution plan is not the current READY authority"
            )
        readiness = cast(CorporateActionReadinessEvaluationRecord, row[0])
        persisted_order = tuple(readiness.ordered_transaction_ids)
        if persisted_order != plan.ordered_transaction_ids:
            raise StaleCorporateActionExecutionPlanError(
                "corporate-action execution order differs from READY authority"
            )
        return readiness, cast(CorporateActionEventRecord, row[1])

    async def _build_member_authority(
        self,
        plan: CorporateActionExecutionPlan,
        *,
        event_id: int,
    ) -> tuple[CorporateActionExecutionMemberAuthority, ...]:
        observation = CorporateActionChildObservationRecord
        transaction = TransactionRecord
        rows = (
            await self._session.execute(
                select(observation, transaction)
                .join(transaction, transaction.transaction_id == observation.transaction_id)
                .where(
                    observation.event_id == event_id,
                    observation.observation_sequence <= plan.through_observation_sequence,
                    observation.transaction_id.in_(plan.ordered_transaction_ids),
                )
                .distinct(observation.transaction_id)
                .order_by(
                    observation.transaction_id,
                    observation.transaction_epoch.desc(),
                    observation.observation_sequence.desc(),
                )
            )
        ).all()
        by_transaction_id = {row[0].transaction_id: row for row in rows}
        if set(by_transaction_id) != set(plan.ordered_transaction_ids):
            raise StaleCorporateActionExecutionPlanError(
                "READY release members are missing persisted observation evidence"
            )
        members = []
        for ordinal, transaction_id in enumerate(plan.ordered_transaction_ids):
            observed, persisted = by_transaction_id[transaction_id]
            if observed.transaction_payload_fingerprint is None:
                raise StaleCorporateActionExecutionPlanError(
                    "READY release member lacks transaction payload authority"
                )
            booked = replace(
                to_booked_transaction_from_record(persisted),
                epoch=observed.transaction_epoch,
            )
            _require_transaction_scope(plan, booked)
            try:
                member = build_corporate_action_execution_member_authority(
                    execution_ordinal=ordinal,
                    observation_id=observed.id,
                    observed_child_content_hash=observed.observed_content_hash,
                    transaction_epoch=observed.transaction_epoch,
                    observed_transaction_payload_fingerprint=(
                        observed.transaction_payload_fingerprint
                    ),
                    transaction=booked,
                )
            except ValueError as exc:
                raise StaleCorporateActionExecutionPlanError(
                    "persisted transaction payload differs from observed release authority"
                ) from exc
            members.append(member)
        return tuple(members)

    async def _require_same_release(
        self,
        release: CorporateActionExecutionReleaseRecord,
        authority: CorporateActionExecutionReleaseAuthority,
    ) -> None:
        if (
            release.structural_plan_content_hash != authority.plan.structural_plan_content_hash
            or release.release_authority_hash != authority.release_authority_hash
            or release.member_count != len(authority.members)
        ):
            raise ConflictingCorporateActionExecutionReleaseError(
                "corporate-action release identity already exists with different authority"
            )
        persisted_members = (
            await self._session.scalars(
                select(CorporateActionExecutionMemberRecord)
                .where(CorporateActionExecutionMemberRecord.release_id == release.id)
                .order_by(CorporateActionExecutionMemberRecord.execution_ordinal)
            )
        ).all()
        persisted_payloads = tuple(
            {
                "execution_ordinal": member.execution_ordinal,
                "observation_id": member.observation_id,
                "observed_child_content_hash": member.observed_child_content_hash,
                "transaction_epoch": member.transaction_epoch,
                "transaction_id": member.transaction_id,
                "transaction_payload_fingerprint": member.transaction_payload_fingerprint,
            }
            for member in persisted_members
        )
        if persisted_payloads != tuple(member.lineage_payload() for member in authority.members):
            raise ConflictingCorporateActionExecutionReleaseError(
                "corporate-action release members differ from deterministic authority"
            )


def _require_transaction_scope(
    plan: CorporateActionExecutionPlan,
    transaction: BookedTransaction,
) -> None:
    if (
        transaction.portfolio_id != plan.portfolio_id
        or transaction.economic_event_id != plan.corporate_action_event_id
        or transaction.linked_transaction_group_id != plan.linked_transaction_group_id
        or transaction.parent_event_reference != plan.parent_event_reference
    ):
        raise StaleCorporateActionExecutionPlanError(
            "persisted transaction is outside corporate-action release authority"
        )


def _materialization(
    release: CorporateActionExecutionReleaseRecord,
    outcome: CorporateActionReleaseMaterializationOutcome,
) -> CorporateActionReleaseMaterialization:
    return CorporateActionReleaseMaterialization(
        outcome=outcome,
        release_id=release.id,
        release_authority_hash=release.release_authority_hash,
        member_count=release.member_count,
    )


def _member_authority(
    member: CorporateActionExecutionMemberRecord,
) -> CorporateActionExecutionMemberAuthority:
    return CorporateActionExecutionMemberAuthority(
        execution_ordinal=member.execution_ordinal,
        transaction_id=member.transaction_id,
        observation_id=member.observation_id,
        transaction_epoch=member.transaction_epoch,
        observed_child_content_hash=member.observed_child_content_hash,
        transaction_payload_fingerprint=member.transaction_payload_fingerprint,
    )


def _claimed_release(
    release: CorporateActionExecutionReleaseRecord,
    member: CorporateActionExecutionMemberRecord,
) -> ClaimedCorporateActionExecutionRelease:
    if (
        release.lease_owner is None
        or release.lease_token is None
        or release.lease_expires_at is None
    ):
        raise ConflictingCorporateActionExecutionReleaseError(
            "claimed corporate-action release lacks complete lease authority"
        )
    return ClaimedCorporateActionExecutionRelease(
        release_id=release.id,
        release_authority_hash=release.release_authority_hash,
        member_count=release.member_count,
        next_member=_member_authority(member),
        attempt_count=release.attempt_count,
        fence_token=release.fence_token,
        lease_owner=release.lease_owner,
        lease_token=release.lease_token,
        lease_expires_at=release.lease_expires_at,
    )


def _require_positive_integer(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_nonnegative_integer(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_sha256_digest(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or value != value.strip()
    ):
        raise ValueError(f"{field_name} must be a canonical sha256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a canonical sha256 digest") from exc
