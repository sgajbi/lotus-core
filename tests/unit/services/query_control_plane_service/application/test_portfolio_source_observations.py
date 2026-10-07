"""Historical independent facts remain diagnostic and cannot fabricate authority."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationCoverage,
    ObservationEnvelope,
)
from pydantic import ValidationError

from src.services.query_control_plane_service.app.application.portfolio_source_observations import (
    PortfolioSourceObservationsService,
)
from src.services.query_control_plane_service.app.contracts.portfolio_source_observations import (
    ObservationSelector,
    PortfolioSourceObservationsRequest,
)
from src.services.query_control_plane_service.app.ports.portfolio_source_observations import (
    PersistedSourceObservation,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_verified_diagnostic_example_binds_complete_actual_service_serialization():
    from portfolio_common.logging_utils import correlation_id_var

    root = next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "pyproject.toml").is_file()
    )
    catalog = json.loads((root / "docs/standards/verified-api-examples.v1.json").read_text())
    example = next(
        row
        for row in catalog["examples"]
        if row["id"] == "portfolio-source-observations-diagnostic"
    )
    assert example["dynamicFieldPointers"] == ["/generated_at"]
    token = correlation_id_var.set("synthetic-correlation")
    try:
        record = _record()
        request = PortfolioSourceObservationsRequest.model_validate(example["request"]["body"])
        result = await PortfolioSourceObservationsService(_Reader(record)).query(
            tenant_id="tenant-synthetic",
            portfolio_id=example["request"]["path"]["portfolio_id"],
            request=request,
        )
    finally:
        correlation_id_var.reset(token)
    actual = result.model_dump(mode="json")
    assert datetime.fromisoformat(actual["generated_at"]).tzinfo is not None
    actual["generated_at"] = example["response"]["body"]["generated_at"]
    assert actual == example["response"]["body"]


def _record(**changes):
    envelope = ObservationEnvelope(
        "tenant-synthetic",
        "portfolio-synthetic",
        "producer-synthetic",
        "record-synthetic",
        1,
        "cut-original",
        "v1",
        date(2026, 1, 1),
        date(2026, 2, 1),
        datetime(2026, 3, 1, tzinfo=UTC),
        datetime(2026, 3, 1, tzinfo=UTC),
        ObservationCoverage.COMPLETE,
        "declared-accounts",
    )
    fact = CashAvailabilityObservation(
        replace(envelope, **changes), "SGD", Decimal("10"), None, Decimal("0")
    )
    return PersistedSourceObservation(
        fact, fact.content_hash, datetime(2026, 3, 2, tzinfo=UTC), "receipt-original", "unqualified"
    )


def _pin(record):
    return ObservationSelector(
        producer_id=record.fact.envelope.producer_id,
        source_record_id=record.fact.envelope.source_record_id,
        observation_id=record.observation_id,
        content_hash=record.fact.content_hash,
        source_cut_id=record.fact.envelope.source_cut_id,
        source_version=record.fact.envelope.source_revision,
    )


class _Reader:
    def __init__(self, cash, funding=None):
        self.cash = cash
        self.funding = funding
        self.requests = []

    async def read_snapshot(self, **scope):
        self.requests.append(scope)
        return self.cash, self.funding


async def _query(record, selector, as_of_date=date(2026, 1, 15)):
    reader = _Reader(record)
    result = await PortfolioSourceObservationsService(reader).query(
        tenant_id="tenant-synthetic",
        portfolio_id="portfolio-synthetic",
        request=PortfolioSourceObservationsRequest(as_of_date=as_of_date, cash=selector),
    )
    assert len(reader.requests) == 1
    return result


async def test_late_observed_original_remains_readable_without_authority_or_joined_cut():
    record = _record()
    result = await _query(record, _pin(record))
    assert result.cash.observation_id == record.observation_id
    assert result.cash.available_amount == Decimal("0")
    assert result.cash.encumbered_amount is None
    assert result.cash.observed_at.date() > result.as_of_date
    assert not result.cash.latest_restated
    assert result.authoritative_state == result.compatibility == "UNAVAILABLE"
    assert result.source_cut_id is None and not result.source_evidence_current
    assert "SOURCE_PRODUCER_UNQUALIFIED" in result.reason_codes


async def test_latest_requires_explicit_opt_in_and_marks_restatement():
    record = _record()
    selector = ObservationSelector(
        producer_id="producer-synthetic", source_record_id="record-synthetic", latest_restated=True
    )
    result = await _query(record, selector)
    assert result.cash.latest_restated
    assert result.authoritative_state == "UNAVAILABLE"


@pytest.mark.parametrize(
    "changes",
    [
        {"content_hash": "f" * 64},
        {"source_cut_id": "different-cut"},
        {"source_version": 2},
        {"observation_id": "f" * 64},
    ],
)
async def test_partial_or_wrong_immutable_pin_cannot_silently_read_latest(changes):
    record = _record()
    result = await _query(record, _pin(record).model_copy(update=changes))
    assert result.cash is None
    assert "CASH_AVAILABILITY_IMMUTABLE_PIN_MISMATCH" in result.reason_codes


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": "foreign"},
        {"portfolio_id": "foreign"},
        {"producer_id": "foreign"},
        {"source_record_id": "foreign"},
    ],
)
async def test_foreign_port_result_cannot_escape_tenant_and_source_scope(changes):
    original = _record()
    result = await _query(_record(**changes), _pin(original))
    assert result.cash is None


async def test_business_window_is_half_open_and_missing_selector_is_not_latest():
    record = _record()
    assert (await _query(record, _pin(record), date(2026, 2, 1))).cash is None
    assert (await _query(record, None)).cash is None


async def test_partial_coverage_is_truthful_and_not_quality_approval():
    record = _record(coverage=ObservationCoverage.PARTIAL)
    result = await _query(record, _pin(record))
    assert result.cash.coverage == "partial"
    assert result.cash.qualification == "unqualified"
    assert "CASH_AVAILABILITY_COVERAGE_PARTIAL" in result.reason_codes


async def test_selector_refuses_mixed_latest_and_pin_and_missing_pin():
    with pytest.raises(ValidationError):
        ObservationSelector(producer_id="producer", source_record_id="record")
    with pytest.raises(ValidationError):
        ObservationSelector(
            producer_id="producer",
            source_record_id="record",
            latest_restated=True,
            observation_id="f" * 64,
        )


async def test_owning_router_preserves_unavailable_degradation_and_admitted_scope():
    from fastapi import Request
    from portfolio_common.domain.tenant import TenantContext, TenantId

    from src.services.query_control_plane_service.app.routers.portfolio_source_observations import (
        query_portfolio_source_observations,
        router,
    )

    reader = _Reader(None)
    http_request = Request({"type": "http"})
    http_request.state.tenant_context = TenantContext(
        tenant_id=TenantId("tenant-synthetic"), identity_verified=True
    )
    request = PortfolioSourceObservationsRequest(as_of_date=date(2026, 1, 15))
    response = await query_portfolio_source_observations(
        request=request,
        http_request=http_request,
        portfolio_id="portfolio-synthetic",
        service=PortfolioSourceObservationsService(reader),
    )
    route = router.routes[0]
    body = route.response_model.model_validate(response).model_dump(mode="json")
    assert body["cash"] is None and body["funding_investment"] is None
    assert body["degradation"]["status"] == "UNAVAILABLE"
    assert body["degradation"]["reason_codes"] == sorted(body["reason_codes"])
    assert {detail["section"] for detail in body["degradation"]["details"]} == {
        "product",
        "cash",
        "funding_investment",
    }
    assert reader.requests == [
        {"tenant_id": "tenant-synthetic", "portfolio_id": "portfolio-synthetic", "request": request}
    ]


@pytest.mark.parametrize("family", ["cash", "funding_investment"])
@pytest.mark.parametrize(
    "scenario, suffix",
    [
        ("complete", None),
        ("no_selector", "OBSERVATION_UNAVAILABLE"),
        ("no_record", "OBSERVATION_UNAVAILABLE"),
        ("tenant_id", "SOURCE_SCOPE_MISMATCH"),
        ("portfolio_id", "SOURCE_SCOPE_MISMATCH"),
        ("producer_id", "SOURCE_SCOPE_MISMATCH"),
        ("source_record_id", "SOURCE_SCOPE_MISMATCH"),
        ("wrong_family", "SOURCE_SCOPE_MISMATCH"),
        ("before_window", "BUSINESS_DATE_UNAVAILABLE"),
        ("end_window", "BUSINESS_DATE_UNAVAILABLE"),
        ("record_hash", "SOURCE_EVIDENCE_INVALID"),
        ("qualification", "SOURCE_EVIDENCE_INVALID"),
        ("observation_id", "IMMUTABLE_PIN_MISMATCH"),
        ("content_hash", "IMMUTABLE_PIN_MISMATCH"),
        ("source_cut_id", "IMMUTABLE_PIN_MISMATCH"),
        ("source_version", "IMMUTABLE_PIN_MISMATCH"),
        ("partial", "COVERAGE_PARTIAL"),
        ("missing", "COVERAGE_MISSING"),
    ],
)
async def test_degradation_serialization_matches_each_family_projection(family, scenario, suffix):
    original = _record()
    if family == "funding_investment":
        fact = FundingInvestmentObservation(original.fact.envelope, False, None)
        original = replace(original, fact=fact, observation_id=fact.content_hash)
    record, selector = original, _pin(original)
    as_of_date = date(2026, 1, 15)
    if scenario == "no_selector":
        selector = None
    elif scenario == "no_record":
        record = None
    elif scenario in ("tenant_id", "portfolio_id", "producer_id", "source_record_id"):
        fact = replace(
            original.fact, envelope=replace(original.fact.envelope, **{scenario: "foreign"})
        )
        record = replace(original, fact=fact, observation_id=fact.content_hash)
    elif scenario == "wrong_family":
        fact = (
            FundingInvestmentObservation(original.fact.envelope, False, None)
            if family == "cash"
            else _record().fact
        )
        record = replace(original, fact=fact, observation_id=fact.content_hash)
    elif scenario in ("before_window", "end_window"):
        as_of_date = date(2025, 12, 31) if scenario == "before_window" else date(2026, 2, 1)
    elif scenario == "record_hash":
        record = replace(original, observation_id="f" * 64)
    elif scenario == "qualification":
        record = replace(original, qualification="qualified")
    elif scenario in ("observation_id", "content_hash", "source_cut_id", "source_version"):
        value = 2 if scenario == "source_version" else "f" * 64
        selector = selector.model_copy(update={scenario: value})
    elif scenario in ("partial", "missing"):
        fact = replace(
            original.fact,
            envelope=replace(original.fact.envelope, coverage=ObservationCoverage(scenario)),
        )
        record = replace(original, fact=fact, observation_id=fact.content_hash)
        selector = _pin(record)
    reader = _Reader(record if family == "cash" else None, record if family != "cash" else None)
    result = await PortfolioSourceObservationsService(reader).query(
        tenant_id="tenant-synthetic",
        portfolio_id="portfolio-synthetic",
        request=PortfolioSourceObservationsRequest(as_of_date=as_of_date, **{family: selector}),
    )
    body = result.model_dump(mode="json")
    assert body["degradation"]["status"] == body["data_quality_status"] == "UNAVAILABLE"
    assert (
        body["freshness_status"]
        == body["authoritative_state"]
        == body["compatibility"]
        == "UNAVAILABLE"
    )
    assert body["source_cut_id"] is None and body["source_evidence_current"] is False
    assert body["degradation"]["reason_codes"] == sorted(set(body["reason_codes"]))
    details = {detail["reason_code"]: detail for detail in body["degradation"]["details"]}
    assert set(details) == set(body["reason_codes"])
    for detail in details.values():
        assert detail["source_kind"] == detail["freshness_status"] == "UNAVAILABLE"
        assert detail["source_product_name"] == body["product_name"]
        assert detail["source_product_version"] == body["product_version"]
        assert detail["source_as_of_date"] is None
        assert detail["latest_evidence_timestamp"] is None
        assert detail["record_key"] is None
    prefix = "CASH_AVAILABILITY" if family == "cash" else "FUNDING_INVESTMENT"
    if suffix:
        reason = f"{prefix}_{suffix}"
        assert details[reason]["section"] == family
        assert details[reason]["affected_fields"] == [family]
    assert details["SOURCE_PRODUCER_UNQUALIFIED"]["affected_fields"] == [
        "authoritative_state",
        "cash",
        "funding_investment",
    ]
    assert details["JOINED_SOURCE_CUT_COMPATIBILITY_UNPROVEN"]["affected_fields"] == [
        "compatibility"
    ]
    if scenario in ("complete", "partial", "missing"):
        assert body[family]["qualification"] == "unqualified"
        if family == "cash":
            assert body[family]["available_amount"] == "0"
            assert body[family]["encumbered_amount"] is None
        else:
            assert body[family]["funded"] is False
            assert body[family]["invested"] is None
    else:
        assert body[family] is None
