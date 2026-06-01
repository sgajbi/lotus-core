from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    ModelPortfolioTargetRequest,
)
from src.services.query_service.app.services.model_portfolio_targets import (
    build_model_portfolio_target_response,
)


def _definition() -> SimpleNamespace:
    return SimpleNamespace(
        model_portfolio_id="MODEL_SG_BALANCED_DPM",
        model_portfolio_version="2026.03",
        display_name="Singapore Balanced DPM Model",
        base_currency="SGD",
        risk_profile="balanced",
        mandate_type="discretionary",
        rebalance_frequency="monthly",
        approval_status="approved",
        approved_at=datetime(2026, 3, 20, 9, 0, 0),
        effective_from=date(2026, 3, 25),
        effective_to=None,
        source_system="investment_office_model_system",
        source_record_id="model_sg_balanced_202603",
        observed_at=datetime(2026, 3, 20, 9, 0, 0),
    )


def _target(instrument_id: str, target_weight: str) -> SimpleNamespace:
    return SimpleNamespace(
        instrument_id=instrument_id,
        target_weight=Decimal(target_weight),
        min_weight=None,
        max_weight=None,
        target_status="active",
        quality_status="accepted",
        source_record_id=f"target:{instrument_id}",
        observed_at=datetime(2026, 3, 21, 9, 0, 0),
    )


def test_build_model_portfolio_target_response_marks_ready_when_weights_sum_to_one() -> None:
    response = build_model_portfolio_target_response(
        definition=_definition(),
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 3, 31)),
        target_rows=[
            _target("EQ_US_AAPL", "0.6000000000"),
            _target("FI_US_TREASURY_10Y", "0.4000000000"),
        ],
    )

    assert response.product_name == "DpmModelPortfolioTarget"
    assert response.model_portfolio_version == "2026.03"
    assert response.supportability.state == "READY"
    assert response.supportability.total_target_weight == Decimal("1.0000000000")
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == datetime(2026, 3, 21, 9, 0, 0)
    assert response.lineage == {
        "source_system": "investment_office_model_system",
        "source_record_id": "model_sg_balanced_202603",
        "contract_version": "rfc_087_v1",
    }


def test_build_model_portfolio_target_response_degrades_when_weights_miss_one() -> None:
    response = build_model_portfolio_target_response(
        definition=_definition(),
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 3, 31)),
        target_rows=[_target("EQ_US_AAPL", "0.5000000000")],
    )

    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "MODEL_TARGET_WEIGHTS_NOT_ONE"
    assert response.supportability.total_target_weight == Decimal("0.5000000000")


def test_build_model_portfolio_target_response_marks_empty_incomplete() -> None:
    response = build_model_portfolio_target_response(
        definition=_definition(),
        request=ModelPortfolioTargetRequest(as_of_date=date(2026, 3, 31)),
        target_rows=[],
    )

    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "MODEL_TARGETS_EMPTY"
    assert response.supportability.target_count == 0
    assert response.data_quality_status == "UNKNOWN"
