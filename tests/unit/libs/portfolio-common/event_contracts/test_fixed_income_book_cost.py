"""Prove the fixed-income book-cost authority event contract."""

from copy import deepcopy

import pytest
from portfolio_common.event_contracts.fixed_income_book_cost import (
    FixedIncomeBookCostAuthorityEvent,
)
from pydantic import ValidationError


def _header() -> dict[str, object]:
    return {
        "scope": {
            "tenant_id": " TENANT_001 ",
            "legal_book_id": " BOOK_001 ",
            "portfolio_id": " PORTFOLIO_001 ",
            "security_id": " SECURITY_001 ",
            "lot_id": " LOT_001 ",
        },
        "source": {
            "source_system": " fixed-income-master ",
            "source_record_id": " LOT_001-COST ",
            "source_revision": " revision-1 ",
            "source_version": 1,
            "observed_at": "2026-08-02T10:15:00+08:00",
        },
        "status": "ACTIVE",
        "valid_from": "2026-08-01",
        "valid_to": None,
    }


def _event(authority: dict[str, object]) -> dict[str, object]:
    return {
        "event_type": "fixed_income.book_cost.authority.received",
        "schema_version": "1.0.0",
        "authority": authority,
    }


def _basis_authority() -> dict[str, object]:
    return {
        "authority_type": "CLEAN_COST_BASIS",
        "header": _header(),
        "currency": " usd ",
        "initial_clean_cost_local": "980000.0000000000",
        "fees_in_basis_local": "1000.0000000000",
        "redemption_value_local": "1000000.0000000000",
        "discount_origin": "MARKET_DISCOUNT",
    }


def test_event_normalizes_exact_scope_and_preserves_decimal_strings() -> None:
    event = FixedIncomeBookCostAuthorityEvent.model_validate(_event(_basis_authority()))

    assert event.partition_key == ("TENANT_001|BOOK_001|PORTFOLIO_001|SECURITY_001|LOT_001")
    payload = event.model_dump(mode="json")
    assert payload["authority"]["currency"] == "USD"
    assert payload["authority"]["initial_clean_cost_local"] == "980000.0000000000"
    assert len(event.content_hash()) == 64


@pytest.mark.parametrize(
    "authority",
    [
        {
            "authority_type": "POLICY_ASSIGNMENT",
            "header": _header(),
            "policy_id": "EFFECTIVE_YIELD_BOOK_COST",
            "policy_version": 1,
            "assignment_reason": "Governed effective-yield accounting policy.",
        },
        {
            "authority_type": "AMORTIZATION_SCHEDULE",
            "header": _header(),
            "schedule_version": 1,
            "year_fraction_method_id": "ACTUAL_ACTUAL_ICMA",
            "year_fraction_method_version": 1,
            "periods": [
                {
                    "period_start_date": "2026-08-01",
                    "period_end_date": "2027-02-01",
                    "year_fraction": "0.5",
                    "cash_coupon_local": "20000",
                    "supplied_period_rate": None,
                },
                {
                    "period_start_date": "2027-02-01",
                    "period_end_date": "2027-08-01",
                    "year_fraction": "0.5",
                    "cash_coupon_local": "20000",
                    "supplied_period_rate": None,
                },
            ],
        },
        {
            "authority_type": "EFFECTIVE_YIELD",
            "header": _header(),
            "annual_yield": "0.045",
            "yield_application": "ANNUAL_EFFECTIVE",
        },
    ],
)
def test_event_accepts_each_non_basis_authority_family(
    authority: dict[str, object],
) -> None:
    event = FixedIncomeBookCostAuthorityEvent.model_validate(_event(authority))

    assert event.authority.authority_type == authority["authority_type"]


def test_event_hash_changes_when_economic_input_changes() -> None:
    first = FixedIncomeBookCostAuthorityEvent.model_validate(_event(_basis_authority()))
    changed = _basis_authority()
    changed["fees_in_basis_local"] = "1001.0000000000"
    second = FixedIncomeBookCostAuthorityEvent.model_validate(_event(changed))

    assert first.content_hash() != second.content_hash()


def test_event_normalizes_observation_instant_before_hashing() -> None:
    offset_payload = _event(_basis_authority())
    utc_authority = _basis_authority()
    utc_header = utc_authority["header"]
    assert isinstance(utc_header, dict)
    utc_source = utc_header["source"]
    assert isinstance(utc_source, dict)
    utc_source["observed_at"] = "2026-08-02T02:15:00Z"

    offset_event = FixedIncomeBookCostAuthorityEvent.model_validate(offset_payload)
    utc_event = FixedIncomeBookCostAuthorityEvent.model_validate(_event(utc_authority))

    assert offset_event.authority.header.source.observed_at.isoformat() == (
        "2026-08-02T02:15:00+00:00"
    )
    assert offset_event.content_hash() == utc_event.content_hash()


@pytest.mark.parametrize("coercible_version", ["1", 1.0])
@pytest.mark.parametrize(
    ("authority_type", "version_path"),
    [
        ("CLEAN_COST_BASIS", ("header", "source", "source_version")),
        ("POLICY_ASSIGNMENT", ("policy_version",)),
        ("AMORTIZATION_SCHEDULE", ("schedule_version",)),
        ("AMORTIZATION_SCHEDULE", ("year_fraction_method_version",)),
    ],
)
def test_event_rejects_coercible_non_integer_versions(
    authority_type: str,
    version_path: tuple[str, ...],
    coercible_version: object,
) -> None:
    authorities: dict[str, dict[str, object]] = {
        "CLEAN_COST_BASIS": _basis_authority(),
        "POLICY_ASSIGNMENT": {
            "authority_type": "POLICY_ASSIGNMENT",
            "header": _header(),
            "policy_id": "EFFECTIVE_YIELD_BOOK_COST",
            "policy_version": 1,
            "assignment_reason": "Governed effective-yield accounting policy.",
        },
        "AMORTIZATION_SCHEDULE": {
            "authority_type": "AMORTIZATION_SCHEDULE",
            "header": _header(),
            "schedule_version": 1,
            "year_fraction_method_id": "ACTUAL_ACTUAL_ICMA",
            "year_fraction_method_version": 1,
            "periods": [
                {
                    "period_start_date": "2026-08-01",
                    "period_end_date": "2027-02-01",
                    "year_fraction": "0.5",
                    "cash_coupon_local": "20000",
                }
            ],
        },
    }
    authority = authorities[authority_type]
    target = authority
    for component in version_path[:-1]:
        nested = target[component]
        assert isinstance(nested, dict)
        target = nested
    target[version_path[-1]] = coercible_version

    with pytest.raises(ValidationError):
        FixedIncomeBookCostAuthorityEvent.model_validate(_event(authority))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("header", "scope", "tenant_id"), " "),
        (("header", "valid_to"), "2026-07-31"),
        (("header", "source", "source_version"), 0),
        (("header", "source", "observed_at"), "2026-08-02T10:15:00"),
        (("discount_origin",), "AT_PAR"),
    ],
)
def test_basis_authority_rejects_incomplete_or_contradictory_evidence(
    path: tuple[str, ...],
    value: object,
) -> None:
    authority = deepcopy(_basis_authority())
    target: dict[str, object] = authority
    for component in path[:-1]:
        nested = target[component]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        FixedIncomeBookCostAuthorityEvent.model_validate(_event(authority))


def test_schedule_rejects_gap_between_authoritative_periods() -> None:
    authority = {
        "authority_type": "AMORTIZATION_SCHEDULE",
        "header": _header(),
        "schedule_version": 1,
        "year_fraction_method_id": "ACTUAL_ACTUAL_ICMA",
        "year_fraction_method_version": 1,
        "periods": [
            {
                "period_start_date": "2026-08-01",
                "period_end_date": "2027-02-01",
                "year_fraction": "0.5",
                "cash_coupon_local": "20000",
            },
            {
                "period_start_date": "2027-02-02",
                "period_end_date": "2027-08-01",
                "year_fraction": "0.5",
                "cash_coupon_local": "20000",
            },
        ],
    }

    with pytest.raises(ValidationError, match="periods must be contiguous and ordered"):
        FixedIncomeBookCostAuthorityEvent.model_validate(_event(authority))


def test_event_rejects_unknown_fields_and_unsupported_schema_versions() -> None:
    payload = _event(_basis_authority())
    payload["schema_version"] = "2.0.0"
    payload["untrusted_claim"] = "production-certified"

    with pytest.raises(ValidationError):
        FixedIncomeBookCostAuthorityEvent.model_validate(payload)
