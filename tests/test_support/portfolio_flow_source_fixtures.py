"""Synthetic explicit source facts; no runtime or bank evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal

from portfolio_common.domain.portfolio_flow_source_observations import (
    FlowEventObservation,
    FlowEventPin,
    FlowSourceCut,
)
from portfolio_common.domain.portfolio_source_observations import (
    ObservationCoverage,
    ObservationEnvelope,
)


def event(source_record_id="source-event", **changes):
    envelope = ObservationEnvelope(
        "tenant-synthetic",
        "portfolio-synthetic",
        "producer-synthetic",
        source_record_id,
        1,
        "source-cut",
        "v1",
        date(2026, 1, 1),
        date(2026, 2, 1),
        datetime(2026, 1, 31, tzinfo=UTC),
        datetime(2026, 1, 31, tzinfo=UTC),
        ObservationCoverage.COMPLETE,
        "monthly-explicit-events",
    )
    return FlowEventObservation(
        **{
            "envelope": envelope,
            "business_date": date(2026, 1, 2),
            "currency": "SGD",
            "amount": Decimal("10.001000000000000000001"),
            "classification": "EXTERNAL_CASH",
            "posting_state": "POSTED",
            "reversal_state": "NONE",
            "reverses_source_record_id": None,
            "reversal_target": None,
            **changes,
        }
    )


def cut(*events, **changes):
    return FlowSourceCut(
        **{
            "tenant_id": "tenant-synthetic",
            "portfolio_id": "portfolio-synthetic",
            "source_system": "producer-synthetic",
            "source_cut_id": "source-cut",
            "cut_revision": 1,
            "definition_version": "v1",
            "currency": "SGD",
            "coverage_from": date(2026, 1, 1),
            "coverage_to": date(2026, 1, 31),
            "coverage": ObservationCoverage.COMPLETE,
            "event_pins": tuple(
                FlowEventPin(
                    f.envelope.source_record_id,
                    f.content_hash,
                    f.content_hash,
                    f.envelope.source_revision,
                )
                for f in sorted(events, key=lambda f: f.envelope.source_record_id)
            ),
            "dependency_pins": (),
            "predecessor_cut_hash": None,
            "expected_head_hash": None,
            **changes,
        }
    )


def pin(fact):
    return FlowEventPin(
        fact.envelope.source_record_id,
        fact.content_hash,
        fact.content_hash,
        fact.envelope.source_revision,
    )


def dated_event(source_record_id, business_date, **changes):
    from dataclasses import replace

    first = business_date.replace(day=1)
    following = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    fact = event(source_record_id, **changes)
    return replace(
        fact,
        business_date=business_date,
        envelope=replace(fact.envelope, effective_from=first, effective_to=following),
    )
