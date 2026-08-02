"""Verify API-to-event mapping for fixed-income book-cost authority."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.fixed_income_book_cost_authority_dto import (
    FixedIncomeBookCostAuthorityIngestionRequest,
)


def _header(*, source_record_id: str, source_version: int = 1) -> dict[str, object]:
    return {
        "scope": {
            "tenant_id": "TENANT_001",
            "legal_book_id": "BOOK_001",
            "portfolio_id": "PORTFOLIO_001",
            "security_id": "SECURITY_001",
            "lot_id": "LOT_001",
        },
        "source": {
            "source_system": "fixed-income-master",
            "source_record_id": source_record_id,
            "source_revision": f"revision-{source_version}",
            "source_version": source_version,
            "observed_at": "2026-08-02T10:15:00+08:00",
        },
        "status": "ACTIVE",
        "valid_from": "2026-08-01",
        "valid_to": None,
    }


def _authorities() -> list[dict[str, object]]:
    return [
        {
            "authority_type": "POLICY_ASSIGNMENT",
            "header": _header(source_record_id="LOT_001-POLICY"),
            "policy_id": "EFFECTIVE_YIELD_BOOK_COST",
            "policy_version": 1,
            "assignment_reason": "Governed effective-yield accounting policy.",
        },
        {
            "authority_type": "CLEAN_COST_BASIS",
            "header": _header(source_record_id="LOT_001-BASIS"),
            "currency": "USD",
            "initial_clean_cost_local": "980000",
            "fees_in_basis_local": "1000",
            "redemption_value_local": "1000000",
            "discount_origin": "MARKET_DISCOUNT",
        },
        {
            "authority_type": "AMORTIZATION_SCHEDULE",
            "header": _header(source_record_id="LOT_001-SCHEDULE"),
            "schedule_version": 1,
            "year_fraction_method_id": "ACTUAL_ACTUAL_ICMA",
            "year_fraction_method_version": 1,
            "periods": [
                {
                    "period_start_date": "2026-08-01",
                    "period_end_date": "2027-08-01",
                    "year_fraction": "1",
                    "cash_coupon_local": "40000",
                }
            ],
        },
        {
            "authority_type": "EFFECTIVE_YIELD",
            "header": _header(source_record_id="LOT_001-YIELD"),
            "annual_yield": "0.045",
            "yield_application": "ANNUAL_EFFECTIVE",
        },
    ]


def test_request_builds_server_owned_event_envelopes_for_every_authority_family() -> None:
    request = FixedIncomeBookCostAuthorityIngestionRequest.model_validate(
        {"authorities": _authorities()}
    )

    events = request.events()

    assert len(events) == 4
    assert {event.authority.authority_type for event in events} == {
        "POLICY_ASSIGNMENT",
        "CLEAN_COST_BASIS",
        "AMORTIZATION_SCHEDULE",
        "EFFECTIVE_YIELD",
    }
    assert {event.event_type for event in events} == {"fixed_income.book_cost.authority.received"}
    assert {event.schema_version for event in events} == {"1.0.0"}
    assert {event.partition_key for event in events} == {
        "TENANT_001|BOOK_001|PORTFOLIO_001|SECURITY_001|LOT_001"
    }


def test_request_accepts_newer_source_version_for_the_same_source_record() -> None:
    authorities = _authorities()
    correction = deepcopy(authorities[1])
    correction["header"] = _header(source_record_id="LOT_001-BASIS", source_version=2)
    correction["initial_clean_cost_local"] = "981000"

    request = FixedIncomeBookCostAuthorityIngestionRequest.model_validate(
        {"authorities": [authorities[1], correction]}
    )

    assert [event.authority.header.source.source_version for event in request.events()] == [1, 2]


def test_request_rejects_duplicate_source_version_before_publication() -> None:
    authority = _authorities()[1]

    with pytest.raises(ValidationError, match="duplicate source-version identities"):
        FixedIncomeBookCostAuthorityIngestionRequest.model_validate(
            {"authorities": [authority, deepcopy(authority)]}
        )


def test_request_rejects_caller_owned_event_metadata_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        FixedIncomeBookCostAuthorityIngestionRequest.model_validate(
            {
                "event_type": "caller.claimed.event",
                "schema_version": "99",
                "authorities": _authorities(),
            }
        )
