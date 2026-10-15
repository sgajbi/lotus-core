"""Source declarations cannot override identity authority or server admission time."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from portfolio_common.portfolio_source_observation_qualification import parse_submission_grants
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.portfolio_source_observation_dto import (
    FlowEventObservationIngestionRequest,
    FlowEventObservationRecord,
    FlowSourceCutRecord,
)
from src.services.ingestion_service.app.routers.reference_data import (
    ingest_portfolio_flow_event_observations,
)
from tests.test_support.portfolio_flow_source_fixtures import cut, event

pytestmark = pytest.mark.unit


def payload():
    fact = event()
    from dataclasses import asdict

    values = asdict(fact.envelope)
    values.pop("tenant_id")
    values["source_system"] = values.pop("producer_id")
    values["flow_source_record_revision"] = values.pop("source_revision")
    return {
        **values,
        **{k: v for k, v in asdict(fact).items() if k != "envelope"},
        "amount": str(fact.amount),
        "content_hash": fact.content_hash,
    }


def test_explicit_exact_source_record_round_trip_and_manifest_hash():
    from dataclasses import asdict

    fact = event()
    dto = FlowEventObservationRecord.model_validate(payload())
    assert dto.to_observation("tenant-synthetic") == fact
    manifest = cut(fact)
    values = asdict(manifest)
    values.pop("tenant_id")
    values["producer_manifest_hash"] = manifest.content_hash
    assert FlowSourceCutRecord.model_validate(values).to_cut("tenant-synthetic") == manifest


@pytest.mark.parametrize(
    "dedicated,ambiguous",
    [
        ("source_record_id", "event_id"),
        ("source_record_id", "source_event_id"),
        ("flow_source_record_revision", "source_event_version"),
        ("flow_source_record_revision", "source_revision"),
        ("reverses_source_record_id", "reverses_source_event_id"),
        ("flow_source_record_revision", "source_version"),
        ("reverses_source_record_id", "reverses_event_id"),
    ],
)
def test_unreleased_ambiguous_event_names_are_not_input_aliases(dedicated, ambiguous):
    values = payload()
    values[ambiguous] = values.pop(dedicated)
    with pytest.raises(ValidationError):
        FlowEventObservationRecord.model_validate(values)


def test_dedicated_pin_names_and_private_storage_mapping_are_explicit():
    from dataclasses import asdict

    from src.services.ingestion_service.app.DTOs.portfolio_source_observation_dto import (
        FlowEventPinRecord,
    )
    from tests.test_support.portfolio_flow_source_fixtures import pin

    fact = event()
    record = FlowEventObservationRecord.model_validate(payload())
    assert record.source_record_id == record.envelope("tenant-synthetic").source_record_id
    assert record.flow_source_record_revision == record.envelope("tenant-synthetic").source_revision
    correct = asdict(pin(fact))
    assert FlowEventPinRecord.model_validate(correct).model_dump() == correct
    for dedicated, ambiguous in (
        ("source_record_id", "event_id"),
        ("source_record_id", "source_event_id"),
        ("flow_source_record_revision", "source_event_version"),
        ("flow_source_record_revision", "source_revision"),
        ("flow_source_record_revision", "source_version"),
    ):
        values = {**correct, ambiguous: correct[dedicated]}
        values.pop(dedicated)
        with pytest.raises(ValidationError):
            FlowEventPinRecord.model_validate(values)


def test_new_flow_read_wire_and_revision_route_use_only_dedicated_event_names():
    from src.services.query_control_plane_service.app.contracts import (
        portfolio_flow_source_observations as contracts,
    )
    from src.services.query_control_plane_service.app.routers import (
        portfolio_flow_source_observations as flow_routes,
    )

    for model in (contracts.FlowEventEvidence, contracts.FlowTargetPinEvidence):
        assert {"source_record_id", "flow_source_record_revision"} <= set(model.model_fields)
        assert {"event_id", "source_version", "source_event_id", "source_event_version"}.isdisjoint(
            model.model_fields
        )
    assert "reverses_source_record_id" in contracts.FlowEventEvidence.model_fields
    assert "reverses_event_id" not in contracts.FlowEventEvidence.model_fields
    assert "reverses_source_event_id" not in contracts.FlowEventEvidence.model_fields
    routes = {route.path for route in flow_routes.router.routes}
    prefix = "/integration/financial-source-observations/flow-events/"
    assert prefix + "versions/{flow_source_record_revision}" in routes
    assert prefix + "{source_system}/{event_id}/versions/{source_version}" not in routes
    assert (
        prefix + "{source_system}/{source_event_id}/versions/{source_event_version}" not in routes
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("received_at", "2026-01-01T00:00:00Z"),
        ("receipt_job_id", "forged"),
        ("tenant_id", "foreign"),
        ("amount", 1.5),
        ("amount", None),
    ],
)
def test_forbidden_fields_and_inexact_amounts(key, value):
    with pytest.raises(ValidationError):
        FlowEventObservationRecord.model_validate({**payload(), key: value})


@pytest.mark.parametrize(
    "key", ["posting_state", "reversal_state", "reverses_source_record_id", "reversal_target"]
)
def test_missing_declaration_is_not_defaulted(key):
    values = payload()
    values.pop(key)
    with pytest.raises(ValidationError):
        FlowEventObservationRecord.model_validate(values)


def test_source_owned_ingestion_examples_bind_actual_typed_hashes_and_required_dependencies():
    from portfolio_common.domain.portfolio_flow_source_observations import require_flow_cut_events

    from src.services.ingestion_service.app.DTOs.portfolio_source_observation_dto import (
        FlowSourceCutIngestionRequest,
    )

    events = FlowEventObservationIngestionRequest.model_validate(
        FlowEventObservationIngestionRequest.model_json_schema()["examples"][0]
    )
    cuts = FlowSourceCutIngestionRequest.model_validate(
        FlowSourceCutIngestionRequest.model_json_schema()["examples"][0]
    )
    facts = tuple(r.to_observation("tenant-synthetic") for r in events.observations)
    manifest = cuts.cuts[0].to_cut("tenant-synthetic")
    assert require_flow_cut_events(manifest, facts)
    missing = cuts.cuts[0].model_dump()
    missing.pop("dependency_pins")
    with pytest.raises(ValidationError):
        FlowSourceCutRecord.model_validate(missing)


def test_server_grant_parser_is_bounded_strict_empty_and_explicit():
    grant = {
        "tenant_id": "tenant-synthetic",
        "portfolio_id": "portfolio-synthetic",
        "producer_id": "producer-synthetic",
        "family": "flow_event",
    }
    assert parse_submission_grants("") == ()
    assert parse_submission_grants("[]") == ()
    assert parse_submission_grants(json.dumps([grant]))[0].producer_id == "producer-synthetic"
    for invalid in (
        "null",
        "{}",
        "[{}]",
        json.dumps([grant, grant]),
        json.dumps([grant] * 101),
        json.dumps([{**grant, "family": "unknown"}]),
        json.dumps([{**grant, "producer_id": "*"}]),
        json.dumps([{**grant, "tenant_id": 123}]),
        json.dumps([{**grant, "authority": "qualified"}]),
        '[{"tenant_id":"one","tenant_id":"two"}]',
        " " * 65537,
    ):
        with pytest.raises(ValueError):
            parse_submission_grants(invalid)


@pytest.mark.asyncio
async def test_native_handler_captures_current_ingress_as_internal_metadata():
    submitted = []

    class Commands:
        async def submit(self, submission):
            submitted.append(submission)
            return "receipt"

    context = SimpleNamespace(identity_verified=True)
    http = SimpleNamespace(
        headers={"X-Idempotency-Key": "flow-unit"}, state=SimpleNamespace(tenant_context=context)
    )
    request = FlowEventObservationIngestionRequest(observations=[payload()])
    before = datetime.now(UTC)
    await ingest_portfolio_flow_event_observations(request, http, Commands())
    assert before <= submitted[0].received_at <= datetime.now(UTC)
    assert submitted[0].received_at.date() != request.observations[0].business_date
    assert "received_at" not in request.model_dump()["observations"][0]
