import pytest
from portfolio_common.consumer_error_evidence import validation_error_diagnostics
from pydantic import BaseModel, ConfigDict, ValidationError


class _BoundedEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    safe_field: int


def test_validation_error_diagnostics_retains_only_bounded_schema_identity() -> None:
    rejected_value = "SYNTHETIC_REDACTION_PROBE_7X"
    dynamic_key = "sensitive-" + ("x" * 80)

    with pytest.raises(ValidationError) as exc_info:
        _BoundedEvidenceModel.model_validate(
            {"safe_field": "not-an-integer", dynamic_key: rejected_value}
        )

    diagnostics = validation_error_diagnostics(exc_info.value)

    assert diagnostics == {
        "validation_error_count": 2,
        "validation_error_locations": ["safe_field", "<dynamic>"],
        "validation_error_types": ["int_parsing", "extra_forbidden"],
        "validation_errors_truncated": False,
    }
    assert rejected_value not in str(diagnostics)
    assert dynamic_key not in str(diagnostics)


def test_validation_error_diagnostics_masks_short_input_derived_locations() -> None:
    dynamic_key = "ACCOUNT-1234"

    with pytest.raises(ValidationError) as exc_info:
        _BoundedEvidenceModel.model_validate({"safe_field": 1, dynamic_key: "rejected"})

    diagnostics = validation_error_diagnostics(exc_info.value)

    assert diagnostics["validation_error_locations"] == ["<dynamic>"]
    assert dynamic_key not in str(diagnostics)


def test_validation_error_diagnostics_truncates_large_error_sets() -> None:
    rejected = {f"unexpected_{index}": index for index in range(25)}

    with pytest.raises(ValidationError) as exc_info:
        _BoundedEvidenceModel.model_validate(rejected)

    diagnostics = validation_error_diagnostics(exc_info.value)

    assert diagnostics["validation_error_count"] == 26
    assert len(diagnostics["validation_error_locations"]) == 20
    assert diagnostics["validation_error_types"] == ["missing", "extra_forbidden"]
    assert diagnostics["validation_errors_truncated"] is True
