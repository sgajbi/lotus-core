"""Tests for deterministic financial input/calculation/output lineage."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum

import pytest
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    FinancialSourceReference,
    build_calculation_lineage,
    canonical_content_hash,
)


class _Basis(StrEnum):
    CLEAN = "CLEAN"


def _lineage(**overrides: object) -> CalculationLineage:
    values: dict[str, object] = {
        "algorithm_id": "SEGMENTED_GROSS_CONTRACTUAL_ACCRUAL",
        "algorithm_version": 1,
        "intermediate_precision": 50,
        "input_payload": {
            "principal": Decimal("1000000.00"),
            "rate": Decimal("0.0525"),
            "basis": _Basis.CLEAN,
            "effective_date": date(2026, 1, 1),
            "observed_at": datetime(2026, 1, 2, 8, tzinfo=UTC),
            "source_revisions": {"r2", "r1"},
        },
        "output_payload": {"gross_accrued_income": Decimal("13270.8333333333333333")},
    }
    values.update(overrides)
    return build_calculation_lineage(**values)  # type: ignore[arg-type]


def test_lineage_produces_distinct_valid_input_calculation_and_output_hashes() -> None:
    lineage = _lineage()

    assert lineage.algorithm_id == "SEGMENTED_GROSS_CONTRACTUAL_ACCRUAL"
    assert lineage.algorithm_version == 1
    assert lineage.intermediate_precision == 50
    assert len(lineage.input_content_hash) == 64
    assert len(lineage.calculation_content_hash) == 64
    assert len(lineage.output_content_hash) == 64
    assert (
        len(
            {
                lineage.input_content_hash,
                lineage.calculation_content_hash,
                lineage.output_content_hash,
            }
        )
        == 3
    )


def test_hashes_are_stable_across_mapping_and_set_order() -> None:
    first = canonical_content_hash({"b": {"z", "a"}, "a": Decimal("1.00")})
    second = canonical_content_hash({"a": Decimal("1.00"), "b": {"a", "z"}})

    assert first == second
    assert _lineage() == _lineage()


def test_aware_timestamps_are_normalized_to_the_same_utc_instant() -> None:
    singapore = timezone(timedelta(hours=8))
    utc_hash = canonical_content_hash({"observed_at": datetime(2026, 1, 2, 8, tzinfo=UTC)})
    singapore_hash = canonical_content_hash(
        {"observed_at": datetime(2026, 1, 2, 16, tzinfo=singapore)}
    )

    assert singapore_hash == utc_hash


def test_input_algorithm_and_output_changes_have_bounded_hash_impact() -> None:
    baseline = _lineage()
    changed_input = _lineage(input_payload={"principal": Decimal("900000")})
    changed_algorithm = _lineage(algorithm_version=2)
    changed_output = _lineage(output_payload={"gross_accrued_income": Decimal("1")})

    assert changed_input.input_content_hash != baseline.input_content_hash
    assert changed_input.calculation_content_hash != baseline.calculation_content_hash
    assert changed_input.output_content_hash != baseline.output_content_hash
    assert changed_algorithm.input_content_hash == baseline.input_content_hash
    assert changed_algorithm.calculation_content_hash != baseline.calculation_content_hash
    assert changed_algorithm.output_content_hash != baseline.output_content_hash
    assert changed_output.input_content_hash == baseline.input_content_hash
    assert changed_output.calculation_content_hash == baseline.calculation_content_hash
    assert changed_output.output_content_hash != baseline.output_content_hash


@pytest.mark.parametrize(
    ("payload", "error_type", "message"),
    [
        ({"amount": 1.5}, TypeError, "float values are prohibited"),
        ({"amount": Decimal("NaN")}, ValueError, "non-finite Decimal"),
        ({"observed_at": datetime(2026, 1, 1)}, ValueError, "timezone-aware"),
        ({1: "value"}, TypeError, "mapping keys"),
        ({"unsupported": object()}, TypeError, "unsupported calculation lineage value"),
    ],
)
def test_ambiguous_or_unsupported_lineage_values_fail_closed(
    payload: dict[object, object],
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        canonical_content_hash(payload)  # type: ignore[arg-type]


def test_lineage_value_rejects_invalid_digest_or_algorithm_metadata() -> None:
    valid_hash = "a" * 64
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        CalculationLineage("ALGORITHM", 1, 50, "ABC", valid_hash, valid_hash)
    with pytest.raises(ValueError, match="algorithm_version"):
        _lineage(algorithm_version=0)
    with pytest.raises(ValueError, match="intermediate_precision"):
        _lineage(intermediate_precision=0)


def _source_reference(**overrides: object) -> FinancialSourceReference:
    values: dict[str, object] = {
        "source_system": " approved-market-data ",
        "source_record_id": " PRICE-001 ",
        "source_revision": " revision-7 ",
        "source_content_hash": "a" * 64,
        "observed_at": datetime(2026, 7, 23, 4, 30, tzinfo=UTC),
    }
    values.update(overrides)
    return FinancialSourceReference(**values)  # type: ignore[arg-type]


def test_financial_source_reference_normalizes_stable_identity() -> None:
    reference = _source_reference()

    assert reference.source_system == "approved-market-data"
    assert reference.source_record_id == "PRICE-001"
    assert reference.source_revision == "revision-7"


@pytest.mark.parametrize("field_name", ["source_system", "source_record_id", "source_revision"])
@pytest.mark.parametrize("invalid_value", [None, 42, Decimal("1")])
def test_financial_source_reference_rejects_non_string_identity(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(TypeError, match=rf"{field_name} must be a string"):
        _source_reference(**{field_name: invalid_value})


@pytest.mark.parametrize("observed_at", [None, "2026-07-23T04:30:00Z", date(2026, 7, 23)])
def test_financial_source_reference_rejects_non_datetime_observation(
    observed_at: object,
) -> None:
    with pytest.raises(TypeError, match="observed_at must be a datetime"):
        _source_reference(observed_at=observed_at)
