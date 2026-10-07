"""Registered request shapes preserve exact independent facts and reject caller authority."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.portfolio_source_observation_dto import (
    CashAvailabilityObservationIngestionRequest,
    CashAvailabilityObservationRecord,
    FundingInvestmentObservationRecord,
)

pytestmark = pytest.mark.unit


def _payload(**changes):
    return {
        "portfolio_id": "synthetic-portfolio",
        "source_system": "synthetic-producer",
        "source_record_id": "synthetic-record",
        "source_version": 1,
        "source_cut_id": "synthetic-cut",
        "definition_version": "v1",
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "observed_at": datetime(2026, 1, 1, tzinfo=UTC),
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "coverage": "complete",
        "coverage_scope": "declared-accounts",
        "content_hash": "0" * 64,
        **changes,
    }


def _cash(**changes):
    return _payload(
        currency="SGD",
        settled_amount="10.01",
        encumbered_amount=None,
        available_amount="0",
        **changes,
    )


def test_lineage_maps_exactly_and_hash_is_bound_to_authenticated_tenant():
    record = CashAvailabilityObservationRecord.model_validate(_cash())
    fact = record._fact("synthetic-tenant")
    verified = record.model_copy(update={"content_hash": fact.content_hash})
    assert verified.to_observation("synthetic-tenant") == fact
    assert fact.settled == Decimal("10.01")
    assert fact.encumbered is None
    assert fact.available == Decimal("0")
    assert fact.envelope.producer_id == record.source_system
    assert fact.envelope.source_revision == record.source_version
    with pytest.raises(ObservationConflict, match="HASH_MISMATCH"):
        verified.to_observation("foreign-tenant")


@pytest.mark.parametrize(
    "field", ["tenant_id", "qualified", "approved", "quality_status", "producer_id"]
)
def test_caller_authority_and_alternative_identity_are_forbidden(field):
    with pytest.raises(ValidationError):
        CashAvailabilityObservationRecord.model_validate({**_cash(), field: "caller-value"})


@pytest.mark.parametrize("value", [True, 1, 1.5, float("nan"), "NaN", "Infinity"])
def test_inexact_nonfinite_cash_refuses(value):
    with pytest.raises(ValidationError):
        CashAvailabilityObservationRecord.model_validate({**_cash(), "available_amount": value})


@pytest.mark.parametrize("value", [0, 1, "true", "false"])
def test_funding_assertions_do_not_coerce_lifecycle_or_integer_flags(value):
    with pytest.raises(ValidationError):
        FundingInvestmentObservationRecord.model_validate(_payload(funded=value, invested=None))


@pytest.mark.parametrize(
    "funded,invested", [(True, False), (False, True), (False, False), (None, None)]
)
def test_funding_and_investment_are_independent_nullable_assertions(funded, invested):
    record = FundingInvestmentObservationRecord.model_validate(
        _payload(funded=funded, invested=invested)
    )
    assert record.funded is funded
    assert record.invested is invested


def test_duplicate_source_record_versions_refuse_entire_batch():
    original = _cash()
    correction = {
        **original,
        "source_version": 2,
        "predecessor_id": "0" * 64,
        "expected_head_hash": "0" * 64,
    }
    with pytest.raises(ValidationError, match="one revision"):
        CashAvailabilityObservationIngestionRequest.model_validate(
            {"observations": [original, correction]}
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"source_version": True},
        {"source_system": " trailing "},
        {"effective_to": date(2026, 1, 1)},
        {"observed_at": datetime(2026, 1, 1)},
        {"source_version": 2},
        {"predecessor_id": "0" * 64},
    ],
)
def test_invalid_envelope_refuses_before_any_command(changes):
    with pytest.raises(ValidationError):
        CashAvailabilityObservationRecord.model_validate({**_cash(), **changes})
