"""One bounded statement snapshot for exact immutable cut membership and receipts."""

from portfolio_common.database_models import IngestionJob
from portfolio_common.portfolio_flow_source_observation_models import (
    FlowEventObservationRow,
    FlowSourceCutRow,
    cut_from_row,
    flow_from_row,
)
from sqlalchemy import BigInteger, and_, cast, func, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased

from ..ports.portfolio_flow_source_observations import PersistedFlowCut, PersistedFlowEvent


def _completed_receipt(job, row, *, cut=False):
    return and_(
        job.tenant_id == row.tenant_id,
        job.job_id == row.receipt_job_id,
        job.status == "completed",
        job.completed_at.is_not(None),
        job.endpoint
        == (
            "/ingest/portfolio-flow-source-cuts"
            if cut
            else "/ingest/portfolio-flow-event-observations"
        ),
        job.entity_type
        == ("portfolio_flow_source_cut" if cut else "portfolio_flow_event_observation"),
    )


def flow_cut_snapshot_statement(*, tenant_id, portfolio_id, request):
    cut, event = FlowSourceCutRow, FlowEventObservationRow
    pins = (
        func.jsonb_array_elements(
            cast(cut.event_pins, JSONB).concat(cast(cut.dependency_pins, JSONB))
        )
        .table_valued("value")
        .lateral()
    )
    event_job, cut_job = aliased(IngestionJob), aliased(IngestionJob)
    return (
        select(cut, event, event_job.job_id, cut_job.job_id)
        .select_from(cut)
        .outerjoin(
            pins,
            true(),
        )
        .outerjoin(
            event,
            and_(
                event.tenant_id == cut.tenant_id,
                event.portfolio_id == cut.portfolio_id,
                event.producer_id == cut.source_system,
                event.source_record_id == pins.c.value.op("->>")("source_record_id"),
                event.observation_id == pins.c.value.op("->>")("observation_id"),
                event.content_hash == pins.c.value.op("->>")("content_hash"),
                event.source_revision
                == cast(pins.c.value.op("->>")("flow_source_record_revision"), BigInteger),
            ),
        )
        .outerjoin(event_job, _completed_receipt(event_job, event))
        .outerjoin(
            cut_job,
            _completed_receipt(cut_job, cut, cut=True),
        )
        .where(
            cut.tenant_id == tenant_id,
            cut.portfolio_id == portfolio_id,
            cut.source_system == request.source_system,
            cut.source_cut_id == request.source_cut_id,
            cut.cut_revision == request.cut_revision,
            cut.manifest_hash == request.manifest_hash,
        )
    )


class SqlAlchemyPortfolioFlowObservationReader:
    def __init__(self, session):
        self.session = session

    async def read_cut(self, *, tenant_id, portfolio_id, request):
        rows = (
            await self.session.execute(
                flow_cut_snapshot_statement(
                    tenant_id=tenant_id,
                    portfolio_id=portfolio_id,
                    request=request,
                )
            )
        ).all()
        if not rows:
            return None
        row = rows[0][0]
        cut = cut_from_row(row)
        if any(cut_job is None for _, _, _, cut_job in rows):
            raise ValueError("flow cut receipt unavailable")
        events = []
        for _, event, receipt_job, _ in rows:
            if event is None:
                if cut.event_pins or cut.dependency_pins:
                    raise ValueError("flow cut pin unresolved")
                continue
            if receipt_job is None:
                raise ValueError("flow event receipt unavailable")
            events.append(PersistedFlowEvent(flow_from_row(event), event.received_at, receipt_job))
        member_ids = {p.observation_id for p in cut.event_pins}
        return PersistedFlowCut(
            cut,
            row.received_at,
            row.receipt_job_id,
            tuple(e for e in events if e.fact.content_hash in member_ids),
            tuple(e for e in events if e.fact.content_hash not in member_ids),
        )

    async def read_event(
        self,
        *,
        tenant_id,
        portfolio_id,
        source_system,
        source_record_id,
        flow_source_record_revision,
    ):
        event = FlowEventObservationRow
        row = await self.session.scalar(
            select(event)
            .join(
                IngestionJob,
                _completed_receipt(IngestionJob, event),
            )
            .where(
                event.tenant_id == tenant_id,
                event.portfolio_id == portfolio_id,
                event.producer_id == source_system,
                event.source_record_id == source_record_id,
                event.source_revision == flow_source_record_revision,
            )
        )
        return (
            PersistedFlowEvent(flow_from_row(row), row.received_at, row.receipt_job_id)
            if row is not None
            else None
        )
