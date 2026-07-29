"""Contract tests for Query Service calculation-lineage responses."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.services.query_service.app.dtos.calculation_lineage_dto import (
    CalculationLineageResponse,
)


def _lineage_payload() -> dict[str, object]:
    return {
        "algorithm_id": "POSITION_VALUATION",
        "algorithm_version": 1,
        "intermediate_precision": 64,
        "input_content_hash": "a" * 64,
        "calculation_content_hash": "b" * 64,
        "output_content_hash": "c" * 64,
    }


def _numeric_policy_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "position-valuation-ledger-output",
        "version": "1.0.0",
        "precision": 18,
        "scale": 10,
        "working_precision": 64,
        "rounding": "ROUND_HALF_EVEN",
    }
    payload.update(overrides)
    return payload


def test_calculation_lineage_preserves_complete_numeric_output_policy() -> None:
    response = CalculationLineageResponse.model_validate(
        {
            **_lineage_payload(),
            "numeric_output_policy": _numeric_policy_payload(),
        }
    )

    assert response.model_dump()["numeric_output_policy"] == _numeric_policy_payload()


def test_calculation_lineage_accepts_calculations_without_numeric_output_policy() -> None:
    response = CalculationLineageResponse.model_validate(_lineage_payload())

    assert response.numeric_output_policy is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": " "}, "identity fields must be nonblank"),
        ({"version": ""}, "identity fields must be nonblank"),
        ({"rounding": "\t"}, "identity fields must be nonblank"),
        ({"precision": 0}, "greater than or equal to 1"),
        ({"scale": -1}, "greater than or equal to 0"),
        ({"scale": 19}, "scale must be between zero and precision"),
        ({"working_precision": 17}, "working_precision must be at least precision"),
    ],
)
def test_calculation_lineage_rejects_invalid_numeric_output_policy(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        CalculationLineageResponse.model_validate(
            {
                **_lineage_payload(),
                "numeric_output_policy": _numeric_policy_payload(**overrides),
            }
        )
