from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.reference_data_dto import (
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
