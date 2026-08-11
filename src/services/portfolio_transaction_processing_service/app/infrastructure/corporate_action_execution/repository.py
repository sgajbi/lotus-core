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
from portfolio_common.events import TransactionEvent
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...application.corporate_action_execution import CorporateActionExecutionPlan
from ...application.corporate_action_release import (
    ConflictingCorporateActionExecutionReleaseError,
    CorporateActionExecutionReleaseAuthority,
    CorporateActionReleaseMaterialization,
    CorporateActionReleaseMaterializationOutcome,
    StaleCorporateActionExecutionPlanError,
    build_corporate_action_execution_member_authority,
)
from ..transaction_mapping.booked_transaction import to_booked_transaction


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
    ) -> tuple:
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
                to_booked_transaction(TransactionEvent.model_validate(persisted)),
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
            release.structural_plan_content_hash
            != authority.plan.structural_plan_content_hash
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
        if persisted_payloads != tuple(
            member.lineage_payload() for member in authority.members
        ):
            raise ConflictingCorporateActionExecutionReleaseError(
                "corporate-action release members differ from deterministic authority"
            )


def _require_transaction_scope(plan: CorporateActionExecutionPlan, transaction) -> None:
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
