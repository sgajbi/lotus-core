from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LotBasisTransferResult,
    SourceLotBasisTransferAllocation,
    TransactionLotBasisTransfer,
)


def _allocation(
    *,
    ordinal: int = 1,
    source_lot_id: str = "LOT-BUY-1",
    local: str = "30",
    base: str = "33",
) -> SourceLotBasisTransferAllocation:
    return SourceLotBasisTransferAllocation(
        allocation_ordinal=ordinal,
        source_lot_id=source_lot_id,
        source_transaction_id=source_lot_id.removeprefix("LOT-"),
        source_acquisition_date=date(2026, 1, ordinal),
        retained_quantity=Decimal("100"),
        source_cost_local_before=Decimal(local) + Decimal("70"),
        source_cost_base_before=Decimal(base) + Decimal("77"),
        transferred_cost_local=Decimal(local),
        transferred_cost_base=Decimal(base),
        retained_cost_local=Decimal("70"),
        retained_cost_base=Decimal("77"),
    )


def test_basis_transfer_result_conserves_ordered_source_lot_economics() -> None:
    result = LotBasisTransferResult(
        transferred_cost_local=Decimal("50"),
        transferred_cost_base=Decimal("55"),
        allocations=(
            _allocation(local="30", base="33"),
            _allocation(ordinal=2, source_lot_id="LOT-BUY-2", local="20", base="22"),
        ),
    )

    evidence = TransactionLotBasisTransfer(
        source_transaction_id="DEMERGER-OUT-1",
        target_transaction_id="DEMERGER-IN-1",
        target_lot_id="LOT-DEMERGER-IN-1",
        result=result,
    )

    assert evidence.result.allocations[1].source_transaction_id == "BUY-2"
    assert evidence.result.calculation_lineage is not None
    assert (
        evidence.result.calculation_lineage.algorithm_id
        == "cost-basis-lot-basis-transfer-allocation"
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"transferred_cost_local": Decimal("49")}, "local basis does not reconcile"),
        ({"transferred_cost_base": Decimal("54")}, "base basis does not reconcile"),
        (
            {
                "allocations": (
                    _allocation(ordinal=2),
                    _allocation(ordinal=1, source_lot_id="LOT-BUY-2"),
                )
            },
            "ordinals must be contiguous",
        ),
        (
            {"allocations": (_allocation(), _allocation(ordinal=2))},
            "source lot can appear only once",
        ),
    ],
)
def test_basis_transfer_result_rejects_nonconserved_or_ambiguous_evidence(
    change: dict[str, object],
    message: str,
) -> None:
    valid = LotBasisTransferResult(
        transferred_cost_local=Decimal("30"),
        transferred_cost_base=Decimal("33"),
        allocations=(_allocation(),),
    )

    with pytest.raises(ValueError, match=message):
        replace(valid, **change)


def test_failed_basis_transfer_cannot_carry_economics() -> None:
    failed = LotBasisTransferResult.failed("insufficient source basis")

    assert failed.error_reason == "insufficient source basis"
    with pytest.raises(ValueError, match="failed basis transfers cannot carry economics"):
        replace(failed, transferred_cost_local=Decimal("1"))


@pytest.mark.parametrize(
    "change",
    [
        {"retained_quantity": Decimal("NaN")},
        {"retained_quantity": Decimal("0")},
        {
            "transferred_cost_local": Decimal("0"),
            "transferred_cost_base": Decimal("0"),
        },
        {"transferred_cost_base": Decimal("-1")},
        {"retained_cost_local": Decimal("69")},
        {"retained_cost_base": Decimal("76")},
    ],
)
def test_basis_transfer_allocation_rejects_invalid_amounts(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(_allocation(), **change)


def test_transaction_basis_transfer_requires_distinct_source_and_target() -> None:
    result = LotBasisTransferResult(
        transferred_cost_local=Decimal("30"),
        transferred_cost_base=Decimal("33"),
        allocations=(_allocation(),),
    )

    with pytest.raises(ValueError, match="must differ"):
        TransactionLotBasisTransfer(
            source_transaction_id="SAME",
            target_transaction_id="SAME",
            target_lot_id="LOT-SAME",
            result=result,
        )

    with pytest.raises(ValueError, match="must derive"):
        TransactionLotBasisTransfer(
            source_transaction_id="SOURCE",
            target_transaction_id="TARGET",
            target_lot_id="LOT-WRONG",
            result=result,
        )
