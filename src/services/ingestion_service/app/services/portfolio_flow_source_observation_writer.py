"""Flow facts/cuts under the existing receipt transaction, without financial writes."""

from dataclasses import asdict

from portfolio_common.database_models import Portfolio, Transaction
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_flow_source_observations import (
    require_flow_cut_events,
    require_flow_target,
)
from portfolio_common.domain.portfolio_source_observations import (
    ObservationConflict,
    ObservationFamily,
    require_successor,
)
from portfolio_common.portfolio_flow_source_observation_models import (
    FlowEventObservationHead,
    FlowEventObservationRow,
    FlowSourceCutRow,
    cut_from_row,
    cut_values,
    flow_from_row,
)
from portfolio_common.portfolio_source_observation_models import SOURCE_IDENTITY_COLUMNS
from sqlalchemy import select, text

from .portfolio_source_observation_writer import PortfolioSourceObservationWriter, _scope_predicates


class PortfolioFlowSourceObservationWriter(PortfolioSourceObservationWriter):
    async def _lock_producer(self, tenant_id, portfolio_id, producer_id):
        if await self.session.scalar(text("SHOW transaction_isolation")) != "read committed":
            raise ObservationConflict("FLOW_SOURCE_REQUIRES_READ_COMMITTED")
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {
                "scope": canonical_content_hash(
                    {"flow_membership": [tenant_id, portfolio_id, producer_id]}
                )
            },
        )

    async def append(self, facts, admissions, *, receipt_job_id, received_at):
        if not self.session.in_transaction():
            raise RuntimeError("flow observations require the active receipt transaction")
        if not facts or len(facts) != len(admissions):
            raise ValueError("each flow observation requires admission")
        for fact, admission in zip(facts, admissions, strict=True):
            self._require_admission(fact, admission)
        # The same producer lock fences window membership before either event or cut writes.
        scopes = sorted(
            {(f.envelope.tenant_id, f.envelope.portfolio_id, f.envelope.producer_id) for f in facts}
        )
        for scope in scopes:
            await self._lock_producer(*scope)
        return await super().append(
            facts, admissions, receipt_job_id=receipt_job_id, received_at=received_at
        )

    async def _append_one(self, fact, admission, *, receipt_job_id, received_at):
        if fact.family is not ObservationFamily.FLOW_EVENT:
            raise TypeError("flow writer requires flow facts")
        envelope = fact.envelope
        existing = await self.session.scalar(
            select(FlowEventObservationRow).where(
                *_scope_predicates(FlowEventObservationRow, envelope),
                FlowEventObservationRow.source_revision == envelope.source_revision,
            )
        )
        if existing is not None:
            if flow_from_row(existing).content_hash != fact.content_hash:
                raise ObservationConflict("SOURCE_OBSERVATION_DIVERGENT_REPLAY")
            return existing.observation_id
        head = await self.session.scalar(
            select(FlowEventObservationHead)
            .where(
                *_scope_predicates(FlowEventObservationHead, envelope),
            )
            .with_for_update()
        )
        if head is None:
            if envelope.source_revision != 1:
                raise ObservationConflict("SOURCE_OBSERVATION_STALE_HEAD")
        else:
            row = await self.session.scalar(
                select(FlowEventObservationRow).where(
                    *_scope_predicates(FlowEventObservationRow, envelope),
                    FlowEventObservationRow.observation_id == head.observation_id,
                )
            )
            if row is None:
                raise ObservationConflict("SOURCE_OBSERVATION_STALE_HEAD")
            original = flow_from_row(row)
            require_successor(original, fact, original_id=head.observation_id)
            if original.currency != fact.currency:
                raise ObservationConflict("SOURCE_OBSERVATION_OWNER_MISMATCH")
        await self._require_reference(fact)
        await self._require_reversal_dependencies(fact)
        values = asdict(envelope)
        values["coverage"] = envelope.coverage.value
        values.update({k: v for k, v in asdict(fact).items() if k != "envelope"})
        # Keep the private SQL column; public source-event semantics are explicit.
        values["reverses_event_id"] = values.pop("reverses_source_record_id")
        self.session.add(
            FlowEventObservationRow(
                **values,
                observation_id=fact.content_hash,
                content_hash=fact.content_hash,
                receipt_job_id=receipt_job_id,
                received_at=received_at,
                admission_policy_version=admission.policy_version,
                qualification=admission.qualification,
            )
        )
        await self.session.flush()
        if head is None:
            self.session.add(
                FlowEventObservationHead(
                    **{k: getattr(envelope, k) for k in SOURCE_IDENTITY_COLUMNS},
                    observation_id=fact.content_hash,
                    content_hash=fact.content_hash,
                )
            )
        else:
            head.observation_id = head.content_hash = fact.content_hash
        await self.session.flush()
        return fact.content_hash

    async def _require_reversal_dependencies(self, fact):
        current = fact
        seen = {fact.envelope.source_record_id}
        while current.reversal_target is not None:
            if len(seen) >= 1000:
                raise ObservationConflict("FLOW_SOURCE_REVERSAL_DEPENDENCY_LIMIT")
            pin = current.reversal_target
            envelope = current.envelope
            row = await self.session.scalar(
                select(FlowEventObservationRow).where(
                    FlowEventObservationRow.tenant_id == envelope.tenant_id,
                    FlowEventObservationRow.portfolio_id == envelope.portfolio_id,
                    FlowEventObservationRow.producer_id == envelope.producer_id,
                    FlowEventObservationRow.source_record_id == pin.source_record_id,
                    FlowEventObservationRow.source_revision == pin.flow_source_record_revision,
                    FlowEventObservationRow.observation_id == pin.observation_id,
                    FlowEventObservationRow.content_hash == pin.content_hash,
                )
            )
            if row is None:
                raise ObservationConflict("FLOW_SOURCE_REVERSAL_TARGET_UNAVAILABLE")
            try:
                target = flow_from_row(row)
                require_flow_target(current, target, pin)
                if target.envelope.source_record_id in seen:
                    raise ValueError("source-event reversal cycle")
            except ValueError as exc:
                raise ObservationConflict("FLOW_SOURCE_REVERSAL_INVALID") from exc
            seen.add(target.envelope.source_record_id)
            current = target

    async def _require_reference(self, fact):
        if fact.transaction_id is None and fact.economic_event_id is None:
            return
        envelope = fact.envelope
        predicates = [
            Portfolio.tenant_id == envelope.tenant_id,
            Transaction.portfolio_id == envelope.portfolio_id,
            Transaction.source_system == envelope.producer_id,
            Transaction.source_record_id == envelope.source_record_id,
        ]
        if fact.transaction_id is not None:
            predicates.append(Transaction.transaction_id == fact.transaction_id)
        if fact.economic_event_id is not None:
            predicates.append(Transaction.economic_event_id == fact.economic_event_id)
        reference = await self.session.scalar(
            select(Transaction.transaction_id)
            .join(
                Portfolio,
                Portfolio.portfolio_id == Transaction.portfolio_id,
            )
            .where(*predicates)
            .limit(1)
        )
        if reference is None:
            raise ObservationConflict("FLOW_SOURCE_REFERENCE_MISMATCH")

    async def append_cut(self, cut, admission, *, receipt_job_id, received_at):
        if not self.session.in_transaction():
            raise RuntimeError("flow cut requires the active receipt transaction")
        grant = admission.grant
        if (
            (grant.tenant_id, grant.portfolio_id, grant.producer_id)
            != (cut.tenant_id, cut.portfolio_id, cut.source_system)
            or grant.family is not ObservationFamily.FLOW_EVENT
            or admission.qualification != "unqualified"
        ):
            raise ObservationConflict("SOURCE_OBSERVATION_PRODUCER_NOT_ADMITTED")
        await self._lock_producer(cut.tenant_id, cut.portfolio_id, cut.source_system)
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": canonical_content_hash({"flow_cut_chain": cut.chain_key})},
        )
        scope = [
            getattr(FlowSourceCutRow, k) == getattr(cut, k)
            for k in ("tenant_id", "portfolio_id", "source_system", "source_cut_id")
        ]
        existing = await self.session.scalar(
            select(FlowSourceCutRow).where(
                *scope,
                FlowSourceCutRow.cut_revision == cut.cut_revision,
            )
        )
        if existing is not None:
            if cut_from_row(existing).content_hash != cut.content_hash:
                raise ObservationConflict("FLOW_SOURCE_CUT_DIVERGENT_REPLAY")
            return existing.manifest_hash
        head = await self.session.scalar(
            select(FlowSourceCutRow)
            .where(*scope)
            .order_by(
                FlowSourceCutRow.cut_revision.desc(),
            )
            .limit(1)
            .with_for_update()
        )
        if head is None:
            if cut.cut_revision != 1:
                raise ObservationConflict("FLOW_SOURCE_CUT_STALE_HEAD")
        elif (
            cut.cut_revision != head.cut_revision + 1
            or cut.predecessor_cut_hash != head.manifest_hash
            or cut.expected_head_hash != head.manifest_hash
        ):
            raise ObservationConflict("FLOW_SOURCE_CUT_STALE_HEAD")
        members = set(
            (
                await self.session.scalars(
                    select(FlowEventObservationRow.source_record_id)
                    .where(
                        FlowEventObservationRow.tenant_id == cut.tenant_id,
                        FlowEventObservationRow.portfolio_id == cut.portfolio_id,
                        FlowEventObservationRow.producer_id == cut.source_system,
                        FlowEventObservationRow.currency == cut.currency,
                        FlowEventObservationRow.definition_version == cut.definition_version,
                        FlowEventObservationRow.business_date >= cut.coverage_from,
                        FlowEventObservationRow.business_date <= cut.coverage_to,
                    )
                    .distinct()
                    .limit(1001)
                )
            ).all()
        )
        if len(members) > 1000:
            raise ObservationConflict("FLOW_SOURCE_CUT_MEMBERSHIP_LIMIT")
        if members != {p.source_record_id for p in cut.event_pins}:
            raise ObservationConflict("FLOW_SOURCE_CUT_INVALID_MEMBERSHIP")
        rows = tuple(
            (
                await self.session.scalars(
                    select(FlowEventObservationRow).where(
                        FlowEventObservationRow.tenant_id == cut.tenant_id,
                        FlowEventObservationRow.portfolio_id == cut.portfolio_id,
                        FlowEventObservationRow.producer_id == cut.source_system,
                        FlowEventObservationRow.observation_id.in_(
                            [p.observation_id for p in cut.event_pins + cut.dependency_pins]
                        ),
                    )
                )
            ).all()
        )
        try:
            member_ids = {p.observation_id for p in cut.event_pins}
            require_flow_cut_events(
                cut,
                tuple(flow_from_row(row) for row in rows if row.observation_id in member_ids),
                tuple(flow_from_row(row) for row in rows if row.observation_id not in member_ids),
            )
        except ValueError as exc:
            raise ObservationConflict("FLOW_SOURCE_CUT_INVALID_MEMBERSHIP") from exc
        self.session.add(
            FlowSourceCutRow(
                **cut_values(cut),
                manifest_hash=cut.content_hash,
                receipt_job_id=receipt_job_id,
                received_at=received_at,
            )
        )
        await self.session.flush()
        return cut.content_hash
