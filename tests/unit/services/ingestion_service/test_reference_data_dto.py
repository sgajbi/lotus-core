from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.reference_data_dto import (
    DiscretionaryMandateBindingIngestionRequest,
    DiscretionaryMandateBindingRecord,
    ModelPortfolioTargetIngestionRequest,
    ModelPortfolioTargetRecord,
)


def _target_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
        "model_portfolio_version": "2026.03",
        "instrument_id": "EQ_US_AAPL",
        "target_weight": "0.1200000000",
        "min_weight": "0.0800000000",
        "max_weight": "0.1600000000",
        "target_status": "active",
        "effective_from": "2026-03-25",
    }
    record.update(overrides)
    return record


def _mandate_binding(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        "client_id": "CIF_SG_000184",
        "mandate_type": "discretionary",
        "discretionary_authority_status": "active",
        "booking_center_code": "Singapore",
        "jurisdiction_code": "SG",
        "model_portfolio_id": "MODEL_PB_SG_GLOBAL_BAL_DPM",
        "policy_pack_id": "POLICY_DPM_SG_BALANCED_V1",
        "risk_profile": "balanced",
        "investment_horizon": "long_term",
        "tax_awareness_allowed": True,
        "settlement_awareness_required": True,
        "rebalance_frequency": "monthly",
        "rebalance_bands": {
            "default_band": "0.0250000000",
            "cash_reserve_weight": "0.0200000000",
        },
        "effective_from": "2026-04-01",
    }
    record.update(overrides)
    return record


def test_model_portfolio_target_record_validates_target_band_order() -> None:
    with pytest.raises(ValidationError, match="min_weight must be less than or equal"):
        ModelPortfolioTargetRecord.model_validate(_target_record(min_weight="0.1300000000"))

    with pytest.raises(ValidationError, match="max_weight must be greater than or equal"):
        ModelPortfolioTargetRecord.model_validate(_target_record(max_weight="0.1100000000"))


def test_model_portfolio_target_ingestion_request_rejects_duplicate_targets() -> None:
    duplicate = _target_record()

    with pytest.raises(ValidationError, match="duplicate target records"):
        ModelPortfolioTargetIngestionRequest.model_validate(
            {"model_portfolio_targets": [duplicate, dict(duplicate)]}
        )


def test_model_portfolio_target_ingestion_request_accepts_distinct_instruments() -> None:
    request = ModelPortfolioTargetIngestionRequest.model_validate(
        {
            "model_portfolio_targets": [
                _target_record(instrument_id="EQ_US_AAPL"),
                _target_record(instrument_id="FI_US_TREASURY_10Y"),
            ]
        }
    )

    assert [target.instrument_id for target in request.model_portfolio_targets] == [
        "EQ_US_AAPL",
        "FI_US_TREASURY_10Y",
    ]


def test_mandate_binding_record_validates_effective_window() -> None:
    with pytest.raises(ValidationError, match="effective_to must be on or after"):
        DiscretionaryMandateBindingRecord.model_validate(
            _mandate_binding(effective_from="2026-04-10", effective_to="2026-04-01")
        )


def test_mandate_binding_ingestion_rejects_duplicate_effective_bindings() -> None:
    duplicate = _mandate_binding()

    with pytest.raises(ValidationError, match="duplicate binding records"):
        DiscretionaryMandateBindingIngestionRequest.model_validate(
            {"mandate_bindings": [duplicate, dict(duplicate)]}
        )


def test_mandate_binding_ingestion_accepts_versioned_corrections() -> None:
    request = DiscretionaryMandateBindingIngestionRequest.model_validate(
        {
            "mandate_bindings": [
                _mandate_binding(binding_version=1),
                _mandate_binding(binding_version=2),
            ]
        }
    )

    assert [binding.binding_version for binding in request.mandate_bindings] == [1, 2]
