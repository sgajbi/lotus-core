from src.services.query_service.app.services.control_code_normalization import (
    normalize_control_code,
)


def test_normalize_control_code_uppercases_trimmed_values() -> None:
    assert normalize_control_code(" cash ") == "CASH"


def test_normalize_control_code_uses_default_for_blankish_values() -> None:
    assert normalize_control_code(None, default="UNCLASSIFIED") == "UNCLASSIFIED"
    assert normalize_control_code("", default="UNKNOWN") == "UNKNOWN"
    assert normalize_control_code(0, default="UNKNOWN") == "UNKNOWN"
