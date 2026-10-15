"""Append decisions and replay retain actual receipts; PostgreSQL races are separate."""

from dataclasses import asdict, replace
from datetime import UTC, date, datetime

import pytest
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.portfolio_flow_source_observation_models import (
    FlowEventObservationHead,
    FlowEventObservationRow,
    FlowSourceCutRow,
    cut_values,
)
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAdmission,
)

from src.services.ingestion_service.app.services.portfolio_flow_source_observation_writer import (
    PortfolioFlowSourceObservationWriter,
)
from tests.test_support.portfolio_flow_source_fixtures import cut, dated_event, event, pin

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]
ADMITTED = datetime(2026, 10, 15, tzinfo=UTC)


def row(fact):
    values = {k: v for k, v in asdict(fact).items() if k != "envelope"}
    values["reverses_event_id"] = values.pop("reverses_source_record_id")
    return FlowEventObservationRow(
        **{**asdict(fact.envelope), "coverage": fact.envelope.coverage.value},
        **values,
        observation_id=fact.content_hash,
        content_hash=fact.content_hash,
        received_at=ADMITTED,
        receipt_job_id="original-receipt",
        admission_policy_version="portfolio-source-observation-admission.v1",
        qualification="unqualified",
    )


def admission(fact):
    e = fact.envelope
    return UnqualifiedProducerAdmission(
        ProducerSubmissionGrant(e.tenant_id, e.portfolio_id, e.producer_id, fact.family)
    )


class Session:
    def __init__(self, *results, events=()):
        self.results = list(results)
        self.added = []
        self.events = events
        self.isolation = "read committed"

    def in_transaction(self):
        return True

    async def execute(self, statement, params):
        assert "pg_advisory_xact_lock" in str(statement)

    async def scalar(self, statement):
        if str(statement) == "SHOW transaction_isolation":
            return self.isolation
        return self.results.pop(0)

    async def scalars(self, statement):
        membership = "SELECT DISTINCT" in str(statement)

        class Result:
            def all(inner):
                return [e.source_record_id for e in self.events] if membership else self.events

        return Result()

    def add(self, record):
        self.added.append(record)

    async def flush(self):
        pass


async def test_exact_replay_keeps_original_receipt_and_time_without_rewinding_head():
    fact = event()
    retained = row(fact)
    session = Session(retained)
    result = await PortfolioFlowSourceObservationWriter(session).append(
        (fact,),
        (admission(fact),),
        receipt_job_id="retry-receipt",
        received_at=datetime.now(UTC),
    )
    assert result == (fact.content_hash,)
    assert retained.receipt_job_id == "original-receipt" and retained.received_at == ADMITTED
    assert session.added == [] and session.results == []


async def test_original_and_contiguous_cancel_correction_keep_both_immutable_rows():
    original = event()
    first = Session(None, None)
    await PortfolioFlowSourceObservationWriter(first).append(
        (original,),
        (admission(original),),
        receipt_job_id="original-receipt",
        received_at=ADMITTED,
    )
    assert len(first.added) == 2
    stored, head = first.added
    assert isinstance(head, FlowEventObservationHead)
    correction = replace(
        original,
        posting_state="CANCELLED",
        envelope=replace(
            original.envelope,
            source_revision=2,
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
        ),
    )
    second = Session(None, head, stored)
    later = datetime.now(UTC)
    await PortfolioFlowSourceObservationWriter(second).append(
        (correction,),
        (admission(correction),),
        receipt_job_id="correction-receipt",
        received_at=later,
    )
    assert stored.posting_state == "POSTED" and stored.received_at == ADMITTED
    assert second.added[0].posting_state == "CANCELLED" and second.added[0].received_at == later
    assert head.content_hash == correction.content_hash


async def test_divergent_replay_and_foreign_admission_refused_without_insert():
    original = event()
    session = Session(row(original))
    with pytest.raises(ObservationConflict, match="DIVERGENT"):
        await PortfolioFlowSourceObservationWriter(session).append(
            (replace(original, posting_state="CANCELLED"),),
            (admission(original),),
            receipt_job_id="refused",
            received_at=ADMITTED,
        )
    assert session.added == []
    foreign = admission(event(envelope=replace(original.envelope, tenant_id="foreign")))
    with pytest.raises(ObservationConflict, match="NOT_ADMITTED"):
        await PortfolioFlowSourceObservationWriter(Session()).append(
            (original,),
            (foreign,),
            receipt_job_id="refused",
            received_at=ADMITTED,
        )


async def test_complete_empty_cut_and_missing_member_have_different_admission():
    original = event()
    session = Session(None, None)
    manifest = cut()
    result = await PortfolioFlowSourceObservationWriter(session).append_cut(
        manifest,
        admission(original),
        receipt_job_id="empty-cut-receipt",
        received_at=ADMITTED,
    )
    assert result == manifest.content_hash and session.added[0].event_pins == []
    missing = Session(None, None)
    with pytest.raises(ObservationConflict, match="INVALID_MEMBERSHIP"):
        await PortfolioFlowSourceObservationWriter(missing).append_cut(
            cut(original),
            admission(original),
            receipt_job_id="refused",
            received_at=ADMITTED,
        )
    assert missing.added == []


async def test_omitted_retained_event_and_limit_refuse_complete_zero():
    original = event()
    omitted = Session(None, None, events=(row(original),))
    with pytest.raises(ObservationConflict, match="INVALID_MEMBERSHIP"):
        await PortfolioFlowSourceObservationWriter(omitted).append_cut(
            cut(),
            admission(original),
            receipt_job_id="refused",
            received_at=ADMITTED,
        )
    overflow = Session(None, None, events=tuple(row(event(str(i))) for i in range(1001)))
    with pytest.raises(ObservationConflict, match="MEMBERSHIP_LIMIT"):
        await PortfolioFlowSourceObservationWriter(overflow).append_cut(
            cut(),
            admission(original),
            receipt_job_id="refused",
            received_at=ADMITTED,
        )
    assert omitted.added == overflow.added == []


async def test_exact_cut_replay_precedes_membership_and_preserves_native_receipt():
    original = event()
    manifest = cut(original)
    stored = FlowSourceCutRow(
        **cut_values(manifest),
        manifest_hash=manifest.content_hash,
        received_at=ADMITTED,
        receipt_job_id="original-cut-receipt",
    )
    late = Session(stored, events=(row(original), row(event("late"))))
    result = await PortfolioFlowSourceObservationWriter(late).append_cut(
        manifest,
        admission(original),
        receipt_job_id="retry",
        received_at=datetime.now(UTC),
    )
    assert result == manifest.content_hash and late.added == []
    assert stored.received_at == ADMITTED and stored.receipt_job_id == "original-cut-receipt"


async def test_repeatable_read_cannot_admit_a_stale_membership_snapshot():
    original = event()
    session = Session()
    session.isolation = "repeatable read"
    with pytest.raises(ObservationConflict, match="READ_COMMITTED"):
        await PortfolioFlowSourceObservationWriter(session).append_cut(
            cut(),
            admission(original),
            receipt_job_id="refused",
            received_at=ADMITTED,
        )
    assert session.added == []


async def test_writer_resolves_original_cross_window_target_after_late_head_correction():
    original = dated_event("december", date(2025, 12, 15))
    reversal = event(
        "january",
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="december",
        reversal_target=pin(original),
    )
    session = Session(row(original))
    await PortfolioFlowSourceObservationWriter(session)._require_reversal_dependencies(reversal)
    assert session.results == []
    with pytest.raises(ObservationConflict, match="TARGET_UNAVAILABLE"):
        await PortfolioFlowSourceObservationWriter(Session(None))._require_reversal_dependencies(
            reversal
        )
    correction = replace(
        original,
        envelope=replace(
            original.envelope,
            source_revision=2,
            predecessor_id=original.content_hash,
            expected_head_hash=original.content_hash,
        ),
    )
    with pytest.raises(ObservationConflict, match="REVERSAL_INVALID"):
        await PortfolioFlowSourceObservationWriter(
            Session(row(correction))
        )._require_reversal_dependencies(reversal)


async def test_writer_validates_multihop_chronology_and_source_event_cycles():
    original = dated_event("a", date(2025, 11, 15))
    december = dated_event(
        "b",
        date(2025, 12, 15),
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="a",
        reversal_target=pin(original),
    )
    january = event(
        "c",
        classification="REVERSAL",
        reversal_state="REVERSES",
        reverses_source_record_id="b",
        reversal_target=pin(december),
    )
    await PortfolioFlowSourceObservationWriter(
        Session(row(december), row(original))
    )._require_reversal_dependencies(january)
    cycle = replace(january, envelope=replace(january.envelope, source_record_id="a"))
    with pytest.raises(ObservationConflict, match="REVERSAL_INVALID"):
        await PortfolioFlowSourceObservationWriter(
            Session(row(december), row(original))
        )._require_reversal_dependencies(cycle)
