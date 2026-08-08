"""Verify immutable lot-disposal allocation contracts and conservation."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import (
    calculation_lineage_binds_output,
    canonical_content_hash,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
    LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
    lot_disposal_lineage_input_payload,
    lot_disposal_lineage_output_payload,
)
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AmortizedCostAllocationEvidence,
    LotDisposalResult,
    SourceLotDisposalAllocation,
    TransactionLotDisposal,
    source_lot_disposal_allocation_payload,
)
from src.services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (  # noqa: E501
    allocate_recognized_lot_book_cost,
    materialize_active_lot_amortized_cost_profile,
)
from tests.test_support.fixed_income_book_cost import resolved_fixed_income_book_cost_inputs


def _allocation(
    *,
    source_transaction_id: str = "BUY_001",
    ordinal: int = 1,
    quantity: str = "2",
    local: str = "20",
    base: str = "22",
) -> SourceLotDisposalAllocation:
    return SourceLotDisposalAllocation(
        source_lot_id=f"LOT-{source_transaction_id}",
        source_transaction_id=source_transaction_id,
        source_acquisition_date=date(2026, 1, 2),
        allocation_ordinal=ordinal,
        consumed_quantity=Decimal(quantity),
        consumed_cost_local=Decimal(local),
        consumed_cost_base=Decimal(base),
    )


def _amortized_cost_evidence() -> AmortizedCostAllocationEvidence:
    profile = materialize_active_lot_amortized_cost_profile(
        resolved_fixed_income_book_cost_inputs(),
        profile_version=1,
    )
    projection = allocate_recognized_lot_book_cost(
        profile,
        disposal_date=date(2027, 1, 1),
        original_quantity=Decimal("10"),
        open_quantity_before=Decimal("10"),
        consumed_quantity=Decimal("2"),
        book_cost_fx_rate_to_base=Decimal("1.1"),
    )
    return AmortizedCostAllocationEvidence(
        profile_id=projection.profile_id,
        profile_version=projection.profile_version,
        profile_content_hash=projection.profile_content_hash,
        currency=projection.currency,
        disposal_date=projection.disposal_date,
        recognized_through_date=projection.recognized_through_date,
        original_quantity=projection.original_quantity,
        open_quantity_before=projection.open_quantity_before,
        consumed_quantity=projection.consumed_quantity,
        residual_quantity=projection.residual_quantity,
        scheduled_cost_local=projection.scheduled_cost_local,
        current_cost_local=projection.current_cost_local,
        current_cost_base=projection.current_cost_base,
        consumed_cost_local=projection.consumed_cost_local,
        residual_cost_local=projection.residual_cost_local,
        book_cost_fx_rate_to_base=projection.book_cost_fx_rate_to_base,
        consumed_cost_base=projection.consumed_cost_base,
        residual_cost_base=projection.residual_cost_base,
        retained_rounding_residual_local=projection.retained_rounding_residual_local,
        retained_rounding_residual_base=projection.retained_rounding_residual_base,
        calculation_lineage=projection.calculation_lineage,
    )


def test_result_requires_exact_source_lot_conservation() -> None:
    allocations = (
        _allocation(),
        _allocation(
            source_transaction_id="BUY_002",
            ordinal=2,
            quantity="3",
            local="36",
            base="39",
        ),
    )

    result = LotDisposalResult(
        cost_base=Decimal("61"),
        cost_local=Decimal("56"),
        consumed_quantity=Decimal("5"),
        allocations=allocations,
    )

    assert result.allocations == allocations
    assert result.allocations[0].source_lot_id == "LOT-BUY_001"
    assert result.allocations[0].source_acquisition_date == date(2026, 1, 2)
    assert result.legacy_tuple() == (
        Decimal("61"),
        Decimal("56"),
        Decimal("5"),
        None,
    )
    assert result.calculation_lineage is not None
    assert result.calculation_lineage.algorithm_id == LOT_DISPOSAL_LINEAGE_ALGORITHM_ID
    assert result.calculation_lineage.algorithm_version == LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION
    assert (
        result.calculation_lineage.numeric_output_policy
        == COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity()
    )
    assert result.calculation_lineage.input_content_hash == canonical_content_hash(
        lot_disposal_lineage_input_payload(
            [source_lot_disposal_allocation_payload(allocation) for allocation in allocations]
        )
    )
    assert calculation_lineage_binds_output(
        result.calculation_lineage,
        output_payload=lot_disposal_lineage_output_payload(
            consumed_cost_base=result.cost_base,
            consumed_cost_local=result.cost_local,
            consumed_quantity=result.consumed_quantity,
        ),
    )


def test_allocation_carries_complete_amortized_cost_evidence_without_changing_legacy_payload() -> (
    None
):
    legacy = _allocation()
    assert source_lot_disposal_allocation_payload(legacy) == {
        "allocation_ordinal": 1,
        "consumed_cost_base": Decimal("22"),
        "consumed_cost_local": Decimal("20"),
        "consumed_quantity": Decimal("2"),
        "source_acquisition_date": date(2026, 1, 2),
        "source_lot_id": "LOT-BUY_001",
        "source_transaction_id": "BUY_001",
    }

    evidence = _amortized_cost_evidence()
    allocation = SourceLotDisposalAllocation(
        source_lot_id="LOT-BUY_001",
        source_transaction_id="BUY_001",
        source_acquisition_date=date(2026, 1, 2),
        allocation_ordinal=1,
        consumed_quantity=evidence.consumed_quantity,
        consumed_cost_local=evidence.consumed_cost_local,
        consumed_cost_base=evidence.consumed_cost_base,
        amortized_cost_evidence=evidence,
    )

    payload = source_lot_disposal_allocation_payload(allocation)
    assert payload["amortized_cost_evidence"] == evidence.semantic_payload()


def test_amortized_evidence_lineage_survives_ledger_scale_round_trip() -> None:
    evidence = _amortized_cost_evidence()

    persisted = replace(
        evidence,
        original_quantity=Decimal("10.0000000000"),
        open_quantity_before=Decimal("10.0000000000"),
        consumed_quantity=Decimal("2.0000000000"),
    )

    assert persisted.calculation_lineage == evidence.calculation_lineage
    assert persisted.output_payload() == evidence.output_payload()


def test_allocation_rejects_amortized_cost_evidence_that_does_not_match_consumed_cost() -> None:
    with pytest.raises(ValueError, match="must match allocated"):
        SourceLotDisposalAllocation(
            source_lot_id="LOT-BUY_001",
            source_transaction_id="BUY_001",
            source_acquisition_date=date(2026, 1, 2),
            allocation_ordinal=1,
            consumed_quantity=Decimal("2"),
            consumed_cost_local=Decimal("21"),
            consumed_cost_base=Decimal("22"),
            amortized_cost_evidence=_amortized_cost_evidence(),
        )


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    (
        ("consumed_quantity", Decimal("4"), "quantity"),
        ("cost_local", Decimal("55"), "local cost"),
        ("cost_base", Decimal("60"), "base cost"),
    ),
)
def test_result_rejects_nonconserving_aggregates(
    field_name: str,
    value: Decimal,
    message: str,
) -> None:
    values = {
        "cost_base": Decimal("22"),
        "cost_local": Decimal("20"),
        "consumed_quantity": Decimal("2"),
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=message):
        LotDisposalResult(
            **values,
            allocations=(_allocation(),),
        )


def test_failed_result_cannot_carry_economics() -> None:
    with pytest.raises(ValueError, match="cannot carry economics"):
        LotDisposalResult(
            cost_base=Decimal("1"),
            cost_local=Decimal(0),
            consumed_quantity=Decimal(0),
            allocations=(),
            error_reason="insufficient quantity",
        )

    assert LotDisposalResult.failed("insufficient quantity").calculation_lineage is None
    assert LotDisposalResult.empty().calculation_lineage is None


def test_allocation_requires_contiguous_positive_ordinals() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        LotDisposalResult(
            cost_base=Decimal("22"),
            cost_local=Decimal("20"),
            consumed_quantity=Decimal("2"),
            allocations=(_allocation(ordinal=2),),
        )

    with pytest.raises(ValueError, match="positive"):
        _allocation(quantity="0")


@pytest.mark.parametrize(
    ("overrides", "exception_type", "message"),
    (
        ({"source_lot_id": 42}, TypeError, "source_lot_id must be a string"),
        ({"source_transaction_id": "  "}, ValueError, "source_transaction_id must be nonblank"),
        (
            {"source_acquisition_date": datetime(2026, 1, 2)},
            TypeError,
            "source_acquisition_date must be a date",
        ),
        ({"allocation_ordinal": "1"}, TypeError, "allocation_ordinal must be an integer"),
        ({"allocation_ordinal": True}, TypeError, "allocation_ordinal must be an integer"),
        ({"allocation_ordinal": 0}, ValueError, "allocation_ordinal must be positive"),
        ({"consumed_quantity": "2"}, TypeError, "consumed_quantity must be a Decimal"),
        ({"consumed_quantity": Decimal("Infinity")}, ValueError, "must be finite"),
        ({"consumed_cost_local": Decimal("-1")}, ValueError, "must be non-negative"),
    ),
)
def test_source_lot_allocation_rejects_malformed_identity_and_economics(
    overrides: dict[str, object],
    exception_type: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {
        "source_lot_id": "LOT-BUY_001",
        "source_transaction_id": "BUY_001",
        "source_acquisition_date": date(2026, 1, 2),
        "allocation_ordinal": 1,
        "consumed_quantity": Decimal("2"),
        "consumed_cost_local": Decimal("20"),
        "consumed_cost_base": Decimal("22"),
    }
    values.update(overrides)

    with pytest.raises(exception_type, match=message):
        SourceLotDisposalAllocation(**values)  # type: ignore[arg-type]


def test_result_rejects_invalid_allocation_collection_and_empty_success() -> None:
    with pytest.raises(TypeError, match="allocations must be a tuple"):
        LotDisposalResult(
            cost_base=Decimal("22"),
            cost_local=Decimal("20"),
            consumed_quantity=Decimal("2"),
            allocations=[_allocation()],  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="zero-quantity disposal results must be empty"):
        LotDisposalResult(
            cost_base=Decimal("1"),
            cost_local=Decimal(0),
            consumed_quantity=Decimal(0),
            allocations=(),
        )

    with pytest.raises(ValueError, match="successful disposal must carry"):
        LotDisposalResult(
            cost_base=Decimal("22"),
            cost_local=Decimal("20"),
            consumed_quantity=Decimal("2"),
            allocations=(),
        )


@pytest.mark.parametrize(
    ("error_reason", "exception_type", "message"),
    (
        (7, TypeError, "error_reason must be a string or None"),
        ("  ", ValueError, "error_reason must be nonblank"),
    ),
)
def test_failed_result_rejects_malformed_error_reason(
    error_reason: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        LotDisposalResult(
            cost_base=Decimal(0),
            cost_local=Decimal(0),
            consumed_quantity=Decimal(0),
            allocations=(),
            error_reason=error_reason,  # type: ignore[arg-type]
        )


def test_result_rejects_duplicate_source_lot_allocations() -> None:
    with pytest.raises(ValueError, match="source lot can appear only once"):
        LotDisposalResult(
            cost_base=Decimal("44"),
            cost_local=Decimal("40"),
            consumed_quantity=Decimal("4"),
            allocations=(_allocation(), _allocation(ordinal=2)),
        )


def test_transaction_disposal_requires_successful_positive_result() -> None:
    successful = LotDisposalResult(
        cost_base=Decimal("22"),
        cost_local=Decimal("20"),
        consumed_quantity=Decimal("2"),
        allocations=(_allocation(),),
    )

    evidence = TransactionLotDisposal(
        disposal_transaction_id=" SELL_001 ",
        result=successful,
    )

    assert evidence.disposal_transaction_id == "SELL_001"
    with pytest.raises(ValueError, match="successful positive"):
        TransactionLotDisposal(
            disposal_transaction_id="SELL_002",
            result=LotDisposalResult.failed("insufficient holdings"),
        )


@pytest.mark.parametrize(
    ("transaction_id", "result", "exception_type", "message"),
    (
        (7, LotDisposalResult.empty(), TypeError, "must be a string"),
        ("  ", LotDisposalResult.empty(), ValueError, "must be nonblank"),
        ("SELL_003", object(), TypeError, "must be a LotDisposalResult"),
    ),
)
def test_transaction_disposal_rejects_malformed_binding(
    transaction_id: object,
    result: object,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        TransactionLotDisposal(
            disposal_transaction_id=transaction_id,  # type: ignore[arg-type]
            result=result,  # type: ignore[arg-type]
        )
