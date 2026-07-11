"""Contract parity tests for QCP-owned transaction-economics products."""

from datetime import date

import pytest
from pydantic import ValidationError

from src.services.query_control_plane_service.app.contracts.common import IntegrationWindow
from src.services.query_control_plane_service.app.contracts.performance_component_economics import (
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
)
from src.services.query_control_plane_service.app.contracts.transaction_cost_curve import (
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
)


@pytest.mark.parametrize(
    ("response_contract", "product_name"),
    [
        (TransactionCostCurveResponse, "TransactionCostCurve"),
        (PerformanceComponentEconomicsResponse, "PerformanceComponentEconomics"),
    ],
)
def test_transaction_economics_responses_declare_product_identity(
    response_contract: type, product_name: str
) -> None:
    assert response_contract.model_fields["product_name"].default == product_name
    assert response_contract.model_fields["product_version"].default == "v1"


def test_transaction_cost_curve_request_normalizes_filters() -> None:
    request = TransactionCostCurveRequest(
        as_of_date=date(2026, 5, 3),
        window=IntegrationWindow(start_date=date(2026, 4, 1), end_date=date(2026, 5, 3)),
        security_ids=[" SEC-US-IBM "],
        transaction_types=[" buy "],
    )

    assert request.security_ids == ["SEC-US-IBM"]
    assert request.transaction_types == ["BUY"]


def test_transaction_cost_curve_request_rejects_duplicate_security_ids() -> None:
    with pytest.raises(ValidationError, match="security_ids must not contain duplicates"):
        TransactionCostCurveRequest(
            as_of_date=date(2026, 5, 3),
            window=IntegrationWindow(start_date=date(2026, 4, 1), end_date=date(2026, 5, 3)),
            security_ids=["SEC-US-IBM", "SEC-US-IBM"],
        )


def test_performance_component_economics_rejects_unbounded_window() -> None:
    with pytest.raises(ValidationError, match="window must be 366 days or less"):
        PerformanceComponentEconomicsRequest(
            as_of_date=date(2026, 5, 3),
            window=IntegrationWindow(start_date=date(2025, 1, 1), end_date=date(2026, 5, 3)),
        )


def test_performance_component_economics_normalizes_transaction_types() -> None:
    request = PerformanceComponentEconomicsRequest(
        as_of_date=date(2026, 5, 3),
        window=IntegrationWindow(start_date=date(2026, 4, 1), end_date=date(2026, 5, 3)),
        transaction_types=[" dividend ", "interest"],
    )

    assert request.transaction_types == ["DIVIDEND", "INTEREST"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-04-30", "end_date": "2026-04-01"},
            },
            "window.end_date must be on or after window.start_date",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-04-01", "end_date": "2026-04-30"},
                "security_ids": ["EQ_US_AAPL", " "],
            },
            "security_ids must not contain blank identifiers",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-04-01", "end_date": "2026-04-30"},
                "security_ids": ["EQ_US_AAPL", "EQ_US_AAPL"],
            },
            "security_ids must not contain duplicates",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-04-01", "end_date": "2026-04-30"},
                "transaction_types": ["BUY", " "],
            },
            "transaction_types must not contain blank values",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-04-01", "end_date": "2026-04-30"},
                "transaction_types": ["buy", "BUY"],
            },
            "transaction_types must not contain duplicates",
        ),
    ],
)
def test_transaction_cost_curve_request_rejects_invalid_scope(payload, message) -> None:
    with pytest.raises(ValidationError, match=message):
        TransactionCostCurveRequest(**payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-05-03", "end_date": "2026-05-01"},
            },
            "window.end_date must be on or after window.start_date",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-05-01", "end_date": "2026-05-03"},
                "security_ids": ["EQ_US_AAPL", ""],
            },
            "security_ids must not contain blank values",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-05-01", "end_date": "2026-05-03"},
                "security_ids": ["EQ_US_AAPL", "EQ_US_AAPL"],
            },
            "security_ids must not contain duplicates",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-05-01", "end_date": "2026-05-03"},
                "transaction_types": ["BUY", " "],
            },
            "transaction_types must not contain blank values",
        ),
    ],
)
def test_performance_component_economics_request_rejects_invalid_scope(payload, message) -> None:
    with pytest.raises(ValidationError, match=message):
        PerformanceComponentEconomicsRequest(**payload)
