import json
from pathlib import Path

from src.services.query_service.app.precision_policy import (
    ROUNDING_POLICY_VERSION,
    quantize_fx_rate,
    quantize_money,
    quantize_performance,
    quantize_price,
    quantize_quantity,
    quantize_ratio,
    quantize_risk,
)


def test_rounding_golden_vectors() -> None:
    fixture = Path(__file__).resolve().parents[3] / "fixtures" / "rounding-golden-vectors.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assert ROUNDING_POLICY_VERSION == payload["policy_version"]
    quantizers = {
        "money": quantize_money,
        "price": quantize_price,
        "fx_rate": quantize_fx_rate,
        "quantity": quantize_quantity,
        "ratio": quantize_ratio,
        "performance": quantize_performance,
        "risk": quantize_risk,
    }
    for semantic, quantizer in quantizers.items():
        actual = [str(quantizer(value)) for value in payload["vectors"][semantic]]
        assert actual == payload["expected"][semantic]
