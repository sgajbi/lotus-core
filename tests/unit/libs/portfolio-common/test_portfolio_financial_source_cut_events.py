"""Completion wire facts retain exact neutral posture at the transport boundary."""

import json

import pytest
from portfolio_common.portfolio_financial_source_cut_events import (
    PortfolioFinancialSourceCutCompletedEvent,
)

pytestmark = pytest.mark.unit


def payload():
    return dict(
        event_type="PortfolioFinancialSourceCutCompleted",
        schema_version="1.0.0",
        tenant_id="tenant",
        product_name="PortfolioHistoricalRegistry",
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        content_hash="a" * 64,
        predecessor_hash=None,
        receipt_job_id="receipt",
        completed_at="2026-10-16T00:00:00Z",
        qualification="UNQUALIFIED",
        population_verification="UNVERIFIED",
        compatibility_posture="UNAVAILABLE",
        correlation_id=None,
        traceparent=None,
    )


def test_exact_reference_wire_round_trip_and_frozen_policy():
    value = payload()
    event = PortfolioFinancialSourceCutCompletedEvent.model_validate_json(json.dumps(value))
    assert event.model_dump(mode="json") == value
    with pytest.raises(ValueError):
        event.revision = 2
    corrected = dict(value, revision=2, predecessor_hash="b" * 64)
    assert PortfolioFinancialSourceCutCompletedEvent.model_validate(corrected).revision == 2


@pytest.mark.parametrize(
    "name,bad",
    [
        ("extra", True),
        ("revision", True),
        ("revision", "1"),
        ("revision", 0),
        ("revision", 2),
        ("predecessor_hash", "b" * 64),
        ("content_hash", "bad"),
        ("completed_at", "2026-10-16T00:00:00"),
        ("qualification", "QUALIFIED"),
        ("population_verification", "VERIFIED"),
        ("compatibility_posture", "VERIFIED"),
        ("product_name", "PortfolioCashAvailability"),
        ("schema_version", "2.0.0"),
        ("tenant_id", ""),
    ],
)
def test_completion_transport_refuses_authority_coercion_and_invalid_reference(name, bad):
    value = payload()
    value[name] = bad
    with pytest.raises(ValueError):
        PortfolioFinancialSourceCutCompletedEvent.model_validate_json(json.dumps(value))
