from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from src.services.ingestion_service.app.DTOs.instrument_dto import Instrument
from src.services.ingestion_service.app.DTOs.reference_data_benchmark_composition_dto import (
    BenchmarkCompositionRecord,
)
from src.services.ingestion_service.app.DTOs.reference_data_benchmark_return_series_dto import (
    BenchmarkReturnSeriesRecord,
)
from src.services.ingestion_service.app.DTOs.reference_data_index_price_series_dto import (
    IndexPriceSeriesRecord,
)
from src.services.ingestion_service.app.DTOs.reference_data_index_return_series_dto import (
    IndexReturnSeriesRecord,
)
from src.services.ingestion_service.app.DTOs.reference_data_risk_free_series_dto import (
    RiskFreeSeriesRecord,
)
from src.services.ingestion_service.app.DTOs.reference_data_support_dto import (
    InstrumentLookthroughComponentRecord,
)


def _benchmark_composition(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
        "index_id": "IDX_GLOBAL_EQUITY_TR",
        "composition_effective_from": "2026-01-01",
        "composition_weight": "0.6000000000",
    }
    payload.update(overrides)
    return payload


def _index_price(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "series_id": "series_idx_global_equity_price",
        "index_id": "IDX_GLOBAL_EQUITY_TR",
        "series_date": "2026-01-02",
        "index_price": "4567.1234000000",
        "series_currency": "USD",
        "value_convention": "official_close",
    }
    payload.update(overrides)
    return payload


def _index_return(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "series_id": "series_idx_global_equity_return",
        "index_id": "IDX_GLOBAL_EQUITY_TR",
        "series_date": "2026-01-02",
        "index_return": "-0.0150000000",
        "return_period": "1d",
        "return_convention": "total_return_index",
        "series_currency": "USD",
    }
    payload.update(overrides)
    return payload


def _benchmark_return(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "series_id": "series_bmk_global_balanced_return",
        "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
        "series_date": "2026-01-02",
        "benchmark_return": "-0.0065000000",
        "return_period": "1d",
        "return_convention": "total_return_index",
        "series_currency": "USD",
    }
    payload.update(overrides)
    return payload


def _risk_free(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "series_id": "rf_usd_sofr_3m",
        "risk_free_curve_id": "USD_SOFR_3M",
        "series_date": "2026-01-02",
        "value": "0.0350000000",
        "value_convention": "annualized_rate",
        "series_currency": "USD",
    }
    payload.update(overrides)
    return payload


def _lookthrough_component(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "parent_security_id": "FUND_GLOBAL_60_40",
        "component_security_id": "ETF_WORLD_EQUITY",
        "effective_from": "2026-01-01",
        "component_weight": "0.6000000000",
    }
    payload.update(overrides)
    return payload


def _instrument(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "security_id": "FXFWD_EURUSD_202609",
        "name": "EUR/USD Forward",
        "isin": "SYNTHETIC_FXFWD_EURUSD_202609",
        "currency": "USD",
        "product_type": "fx_forward",
        "buy_amount": "1000000.0000000000",
        "sell_amount": "1085000.0000000000",
        "contract_rate": "1.0850000000",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("record_type", "payload", "field_name"),
    [
        (
            BenchmarkCompositionRecord,
            _benchmark_composition(composition_weight="0.12345678901"),
            "composition_weight",
        ),
        (
            IndexPriceSeriesRecord,
            _index_price(index_price="1.12345678901"),
            "index_price",
        ),
        (
            IndexReturnSeriesRecord,
            _index_return(index_return="0.12345678901"),
            "index_return",
        ),
        (
            BenchmarkReturnSeriesRecord,
            _benchmark_return(benchmark_return="0.12345678901"),
            "benchmark_return",
        ),
        (
            RiskFreeSeriesRecord,
            _risk_free(value="0.12345678901"),
            "value",
        ),
        (
            InstrumentLookthroughComponentRecord,
            _lookthrough_component(component_weight="0.12345678901"),
            "component_weight",
        ),
        (
            Instrument,
            _instrument(contract_rate="1.12345678901"),
            "contract_rate",
        ),
    ],
)
def test_reference_numeric_fields_reject_excess_persistence_scale(
    record_type: type[BaseModel],
    payload: dict[str, object],
    field_name: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        record_type.model_validate(payload)

    error = exc_info.value.errors()[0]
    assert error["loc"] == (field_name,)
    assert "bounded-18-10-exact: excess_scale" in error["msg"]


@pytest.mark.parametrize("field_name", ["buy_amount", "sell_amount", "contract_rate"])
def test_instrument_numeric_fields_reject_nonpositive_source_facts(field_name: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Instrument.model_validate(_instrument(**{field_name: "0.0000000000"}))

    assert exc_info.value.errors()[0]["loc"] == (field_name,)


@pytest.mark.parametrize(
    ("record_type", "payload", "field_name"),
    [
        (
            IndexPriceSeriesRecord,
            _index_price(index_price="100000000.0000000000"),
            "index_price",
        ),
        (
            Instrument,
            _instrument(buy_amount="100000000.0000000000"),
            "buy_amount",
        ),
    ],
)
def test_reference_numeric_fields_reject_persistence_magnitude_overflow(
    record_type: type[BaseModel],
    payload: dict[str, object],
    field_name: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        record_type.model_validate(payload)

    error = exc_info.value.errors()[0]
    assert error["loc"] == (field_name,)
    assert "bounded-18-10-exact: magnitude_overflow" in error["msg"]


def test_reference_numeric_fields_accept_exact_storage_boundaries() -> None:
    price = IndexPriceSeriesRecord.model_validate(_index_price(index_price="99999999.9999999999"))
    instrument = Instrument.model_validate(_instrument(contract_rate="1.0850000000"))

    assert price.index_price == Decimal("99999999.9999999999")
    assert instrument.contract_rate == Decimal("1.0850000000")


@pytest.mark.parametrize(
    ("record_type", "field_name"),
    [
        (BenchmarkCompositionRecord, "composition_weight"),
        (IndexPriceSeriesRecord, "index_price"),
        (IndexReturnSeriesRecord, "index_return"),
        (BenchmarkReturnSeriesRecord, "benchmark_return"),
        (RiskFreeSeriesRecord, "value"),
        (InstrumentLookthroughComponentRecord, "component_weight"),
        (Instrument, "buy_amount"),
        (Instrument, "sell_amount"),
        (Instrument, "contract_rate"),
    ],
)
def test_reference_numeric_fields_publish_exact_openapi_contract(
    record_type: type[BaseModel],
    field_name: str,
) -> None:
    description = record_type.model_json_schema()["properties"][field_name]["description"]

    assert "NUMERIC(18,10)" in description
    assert "excess scale and magnitude overflow are rejected, not rounded" in description
