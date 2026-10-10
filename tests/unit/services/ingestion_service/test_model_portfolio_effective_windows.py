"""Imported model windows share the existing inclusive validation contract."""

import pytest
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.reference_data_model_portfolio_definition_dto import (
    ModelPortfolioDefinitionRecord,
)
from src.services.ingestion_service.app.DTOs.reference_data_model_portfolio_target_dto import (
    ModelPortfolioTargetRecord,
)


@pytest.fixture(params=[ModelPortfolioDefinitionRecord, ModelPortfolioTargetRecord])
def model_record(request):
    values = {
        "model_portfolio_id": "WINDOW_MODEL",
        "model_portfolio_version": "v1",
        "effective_from": "2026-09-01",
        "source_system": "synthetic_model_feed",
        "source_record_id": "window-1",
    }
    if request.param is ModelPortfolioTargetRecord:
        values.update(instrument_id="WINDOW_EQ", target_weight="0.6000000000")
    else:
        values.update(
            display_name="Synthetic window model",
            base_currency="USD",
            risk_profile="balanced",
            mandate_type="discretionary",
        )
    return request.param, values


def test_reversed_model_window_has_stable_date_context(model_record):
    record_type, values = model_record
    with pytest.raises(ValidationError) as caught:
        record_type.model_validate({**values, "effective_to": "2026-08-31"})
    error = caught.value.errors()[0]
    assert error["type"] == "INVALID_EFFECTIVE_WINDOW"
    assert error["ctx"]["field_path"] == "effective_to"
    assert error["msg"] == "effective_to must be on or after effective_from."


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-09-01", None),
        ("2026-09-01", "2026-09-01"),
        ("2026-09-01", "2026-09-30"),
        ("2000-01-01", "2000-01-31"),
        ("2099-01-01", "2099-01-31"),
    ],
)
def test_inclusive_open_historical_and_future_model_windows(model_record, start, end):
    record_type, values = model_record
    record = record_type.model_validate({**values, "effective_from": start, "effective_to": end})
    assert record.effective_from.isoformat() == start
    assert (record.effective_to.isoformat() if record.effective_to else None) == end


def test_model_window_openapi_publishes_inclusive_and_open_ended_examples(model_record):
    record_type, _ = model_record
    from src.services.ingestion_service.app.main import app

    schema = app.openapi()["components"]["schemas"][record_type.__name__]
    end = schema["properties"]["effective_to"]
    assert "Inclusive" in end["description"]
    assert "equal dates form a valid one-day window" in end["description"]
    assert "2026-03-25" in end["examples"]
    assert None in end["examples"]
