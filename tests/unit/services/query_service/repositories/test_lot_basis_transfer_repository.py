"""Verify bounded latest-version lot basis-transfer receipt queries."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.domain.calculation_lineage import (
    build_calculation_lineage,
    canonical_content_hash,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    basis_transfer_lineage_input_payload,
    basis_transfer_lineage_output_payload,
    canonical_cost_basis_output_payload,
    cost_basis_allocation_content_hash,
    cost_basis_receipt_semantic_hash,
    receipt_version_content_hash,
)
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.lot_basis_transfer_records import (
    LotBasisTransferAllocationReadRecord,
    LotBasisTransferReceiptReadRecord,
)
from src.services.query_service.app.repositories.lot_basis_transfer_repository import (
    CorruptLotBasisTransferReadModelError,
    LotBasisTransferRepository,
    _allocation_payload,
    _receipt_semantic_payload,
    _verify_lifecycle,
    _verify_receipt_integrity,
)


def test_shared_cost_basis_payload_canonicalizes_set_members() -> None:
    assert canonical_cost_basis_output_payload({"amounts": {Decimal("1")}}) == {
        "amounts": {Decimal("1.0000000000")}
    }


@pytest.mark.asyncio
async def test_latest_receipt_uses_two_scoped_full_chain_queries() -> None:
    receipt = MagicMock(receipt_id="RECEIPT-1", allocation_count=2)
    receipt.receipt_version = 1
    first = MagicMock(source_lot_id="LOT-1")
    second = MagicMock(source_lot_id="LOT-2")
    first.receipt_version = 1
    second.receipt_version = 1
    receipt_result = MagicMock()
    receipt_result.all.return_value = [receipt]
    allocation_result = MagicMock()
    allocation_result.all.return_value = [first, second]
    session = AsyncMock(spec=AsyncSession)
    session.scalars = AsyncMock(side_effect=[receipt_result, allocation_result])

    with (
        patch(
            "src.services.query_service.app.repositories.lot_basis_transfer_repository."
            "verify_cost_basis_receipt_version_chain"
        ) as verify_chain,
        patch(
            "src.services.query_service.app.repositories.lot_basis_transfer_repository."
            "_verify_receipt_integrity"
        ) as verify,
    ):
        resolved = await LotBasisTransferRepository(session).get_latest_receipt(
            portfolio_id="P1",
            source_transaction_id="DEMERGER-OUT-001",
        )

    assert resolved is not None
    mapped_receipt, mapped_allocations = resolved
    assert isinstance(mapped_receipt, LotBasisTransferReceiptReadRecord)
    assert mapped_receipt.receipt_id == "RECEIPT-1"
    assert all(isinstance(row, LotBasisTransferAllocationReadRecord) for row in mapped_allocations)
    assert [row.source_lot_id for row in mapped_allocations] == ["LOT-1", "LOT-2"]
    assert session.scalars.await_count == 2
    receipt_statement = session.scalars.await_args_list[0].args[0]
    allocation_statement = session.scalars.await_args_list[1].args[0]
    compiled_receipts = str(receipt_statement.compile(compile_kwargs={"literal_binds": True}))
    compiled_allocations = str(allocation_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "lot_basis_transfer_receipts.portfolio_id = 'P1'" in compiled_receipts
    assert (
        "lot_basis_transfer_receipts.source_transaction_id = 'DEMERGER-OUT-001'"
        in compiled_receipts
    )
    assert "ORDER BY lot_basis_transfer_receipts.receipt_version" in compiled_receipts
    assert "lot_basis_transfer_allocations.receipt_version <= 1" in compiled_allocations
    assert (
        "ORDER BY lot_basis_transfer_allocations.receipt_version, "
        "lot_basis_transfer_allocations.allocation_ordinal" in compiled_allocations
    )
    verify_chain.assert_called_once_with((receipt,))
    verify.assert_called_once()


@pytest.mark.asyncio
async def test_latest_receipt_rejects_tampered_middle_transfer_at_depth_sixty_four() -> None:
    canonical_receipt, canonical_allocation = _valid_evidence()
    headers: list[MagicMock] = []
    mapped_receipts: list[LotBasisTransferReceiptReadRecord] = []
    allocation_rows: list[MagicMock] = []
    mapped_allocations: list[LotBasisTransferAllocationReadRecord] = []
    previous_hash: str | None = None
    for version in range(1, 65):
        content_hash = receipt_version_content_hash(
            receipt_id=canonical_receipt.receipt_id,
            semantic_content_hash=canonical_receipt.semantic_content_hash,
            receipt_version=version,
            previous_receipt_content_hash=previous_hash,
        )
        header = MagicMock()
        header.receipt_id = canonical_receipt.receipt_id
        header.receipt_version = version
        header.previous_receipt_content_hash = previous_hash
        header.receipt_content_hash = content_hash
        headers.append(header)
        mapped_receipts.append(
            replace(
                canonical_receipt,
                receipt_version=version,
                previous_receipt_content_hash=previous_hash,
                receipt_content_hash=content_hash,
            )
        )
        allocation_row = MagicMock()
        allocation_row.receipt_version = version
        allocation_rows.append(allocation_row)
        mapped_allocations.append(canonical_allocation)
        previous_hash = content_hash
    mapped_allocations[31] = replace(
        canonical_allocation,
        allocation_content_hash="0" * 64,
    )

    receipt_result = MagicMock()
    receipt_result.all.return_value = headers
    allocation_result = MagicMock()
    allocation_result.all.return_value = allocation_rows
    session = AsyncMock(spec=AsyncSession)
    session.scalars = AsyncMock(side_effect=[receipt_result, allocation_result])

    with (
        patch(
            "src.services.query_service.app.repositories.lot_basis_transfer_repository."
            "_receipt_record",
            side_effect=mapped_receipts,
        ),
        patch(
            "src.services.query_service.app.repositories.lot_basis_transfer_repository."
            "_allocation_record",
            side_effect=mapped_allocations,
        ),
        pytest.raises(CorruptLotBasisTransferReadModelError, match="chain is corrupt"),
    ):
        await LotBasisTransferRepository(session).get_latest_receipt(
            portfolio_id="P1",
            source_transaction_id="DEMERGER-OUT-001",
        )

    assert session.scalars.await_count == 2


@pytest.mark.asyncio
async def test_portfolio_existence_and_absent_receipt_are_bounded() -> None:
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.side_effect = ["P1", None]
    empty_scalar_result = MagicMock()
    empty_scalar_result.all.return_value = []
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=[scalar_result, scalar_result])
    session.scalars = AsyncMock(return_value=empty_scalar_result)
    repository = LotBasisTransferRepository(session)

    assert await repository.portfolio_exists(tenant_id="tenant-a", portfolio_id="P1") is True
    assert await repository.portfolio_exists(tenant_id="tenant-a", portfolio_id="MISSING") is False
    assert (
        await repository.get_latest_receipt(
            portfolio_id="P1",
            source_transaction_id="UNKNOWN",
        )
        is None
    )
    assert session.execute.await_count == 2
    session.scalars.assert_awaited_once()


def test_latest_receipt_fails_closed_on_missing_allocation_rows() -> None:
    receipt, allocation = _valid_evidence()

    with pytest.raises(CorruptLotBasisTransferReadModelError, match="corrupt"):
        _verify_receipt_integrity(receipt, [], predecessor_hash=None)


def test_latest_receipt_accepts_strict_lineage_bound_to_persisted_evidence() -> None:
    receipt, allocation = _valid_evidence()

    _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)


def test_voided_receipt_requires_strict_transaction_lineage_without_transfer_lineage() -> None:
    receipt, _ = _valid_evidence()
    voided = _rehash_receipt(
        replace(
            receipt,
            status="VOIDED",
            void_reason="SUPERSEDED",
            transferred_cost_local=Decimal(0),
            transferred_cost_base=Decimal(0),
            allocation_count=0,
            basis_transfer_calculation_lineage=None,
        ),
        [],
    )

    _verify_receipt_integrity(voided, [], predecessor_hash=None)


def test_latest_receipt_fails_closed_on_tampered_allocation_hash() -> None:
    receipt, allocation = _valid_evidence()
    tampered = replace(allocation, allocation_content_hash="0" * 64)

    with pytest.raises(CorruptLotBasisTransferReadModelError, match="corrupt"):
        _verify_receipt_integrity(receipt, [tampered], predecessor_hash=None)


def test_latest_receipt_verifies_immediate_predecessor_hash() -> None:
    receipt, allocation = _valid_evidence()
    predecessor_hash = "e" * 64
    receipt = replace(
        receipt,
        receipt_version=2,
        previous_receipt_content_hash=predecessor_hash,
        receipt_content_hash=receipt_version_content_hash(
            receipt_id=receipt.receipt_id,
            semantic_content_hash=receipt.semantic_content_hash,
            receipt_version=2,
            previous_receipt_content_hash=predecessor_hash,
        ),
    )

    _verify_receipt_integrity(receipt, [allocation], predecessor_hash=predecessor_hash)
    with pytest.raises(CorruptLotBasisTransferReadModelError, match="corrupt"):
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash="f" * 64)


def test_integrity_rejects_identity_order_uniqueness_and_hash_drift() -> None:
    receipt, allocation = _valid_evidence()
    _assert_corrupt(
        replace(receipt, receipt_id="lot-basis-transfer:wrong"), [allocation], "identity"
    )
    _assert_corrupt(replace(receipt, allocation_count=2), [allocation], "allocation count")
    _assert_corrupt(
        receipt,
        [replace(allocation, allocation_ordinal=2)],
        "ordinals are not contiguous",
    )
    _assert_corrupt(
        replace(receipt, allocation_count=2),
        [allocation, replace(allocation, allocation_ordinal=2)],
        "source lot occurs more than once",
    )
    _assert_corrupt(
        replace(receipt, transferred_cost_local=Decimal("24")),
        [allocation],
        "receipt basis does not reconcile",
    )
    _assert_corrupt(
        replace(receipt, semantic_content_hash="0" * 64),
        [allocation],
        "semantic content hash mismatch",
    )
    _assert_corrupt(
        replace(receipt, previous_receipt_content_hash="e" * 64),
        [allocation],
        "first receipt version has a predecessor",
    )
    _assert_corrupt(
        replace(receipt, receipt_content_hash="0" * 64),
        [allocation],
        "receipt content hash mismatch",
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"transferred_cost_local": Decimal("24")}, "source lot basis does not reconcile"),
        ({"transferred_cost_base": Decimal("17")}, "source lot basis does not reconcile"),
    ],
)
def test_integrity_rejects_nonconserving_source_lot_basis(
    changes: dict[str, object],
    reason: str,
) -> None:
    receipt, allocation = _valid_evidence()
    tampered = replace(allocation, **changes)
    _assert_corrupt(receipt, [tampered], reason)


@pytest.mark.parametrize(
    ("lineage_field", "lineage_payload", "reason"),
    [
        (
            "transaction_calculation_lineage",
            {"algorithm_id": "transaction-cost"},
            "algorithm_version must be an integer",
        ),
        (
            "basis_transfer_calculation_lineage",
            {"algorithm_id": "basis-transfer"},
            "algorithm_version must be an integer",
        ),
    ],
)
def test_integrity_rejects_malformed_lineage_payloads(
    lineage_field: str,
    lineage_payload: dict[str, object],
    reason: str,
) -> None:
    receipt, allocation = _valid_evidence()
    tampered = _rehash_receipt(
        replace(receipt, **{lineage_field: lineage_payload}),
        [allocation],
    )

    _assert_corrupt(tampered, [allocation], reason)


@pytest.mark.parametrize(
    "lineage_field",
    ["transaction_calculation_lineage", "basis_transfer_calculation_lineage"],
)
def test_integrity_rejects_missing_required_lineage(lineage_field: str) -> None:
    receipt, allocation = _valid_evidence()
    tampered = _rehash_receipt(
        replace(receipt, **{lineage_field: None}),
        [allocation],
    )

    _assert_corrupt(tampered, [allocation], "calculation lineage is required")


def test_integrity_rejects_rehashed_allocation_not_bound_to_lineage_inputs() -> None:
    receipt, allocation = _valid_evidence()
    tampered = replace(allocation, retained_quantity=Decimal("74"))
    tampered = replace(
        tampered,
        allocation_content_hash=cost_basis_allocation_content_hash(
            receipt_id=receipt.receipt_id,
            payload=_allocation_payload(tampered),
        ),
    )
    rehashed_receipt = _rehash_receipt(receipt, [tampered])

    _assert_corrupt(
        rehashed_receipt,
        [tampered],
        "basis-transfer lineage does not bind persisted inputs",
    )


def test_integrity_rejects_lineage_not_bound_to_persisted_outputs() -> None:
    receipt, allocation = _valid_evidence()
    wrong_output_lineage = build_calculation_lineage(
        algorithm_id="cost-basis-lot-basis-transfer-allocation",
        algorithm_version=1,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=basis_transfer_lineage_input_payload([allocation]),
        output_payload={"transferred_cost_local": Decimal(0)},
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    ).lineage_payload()
    tampered = _rehash_receipt(
        replace(receipt, basis_transfer_calculation_lineage=wrong_output_lineage),
        [allocation],
    )

    _assert_corrupt(
        tampered,
        [allocation],
        "basis-transfer lineage does not bind persisted outputs",
    )


@pytest.mark.parametrize(
    ("algorithm_id", "include_numeric_policy", "reason"),
    [
        ("wrong-basis-transfer", True, "algorithm identity is unsupported"),
        (
            "cost-basis-lot-basis-transfer-allocation",
            False,
            "numeric policy is unsupported",
        ),
    ],
)
def test_integrity_rejects_unsupported_basis_transfer_lineage_contract(
    algorithm_id: str,
    include_numeric_policy: bool,
    reason: str,
) -> None:
    receipt, allocation = _valid_evidence()
    lineage = build_calculation_lineage(
        algorithm_id=algorithm_id,
        algorithm_version=1,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=basis_transfer_lineage_input_payload([allocation]),
        output_payload=basis_transfer_lineage_output_payload(
            [allocation],
            transferred_cost_base=receipt.transferred_cost_base,
            transferred_cost_local=receipt.transferred_cost_local,
        ),
        numeric_output_policy=(
            COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity() if include_numeric_policy else None
        ),
    ).lineage_payload()
    tampered = _rehash_receipt(
        replace(receipt, basis_transfer_calculation_lineage=lineage),
        [allocation],
    )

    _assert_corrupt(tampered, [allocation], reason)


@pytest.mark.parametrize(
    ("receipt_changes", "reason"),
    [
        ({"basis_transfer_calculation_lineage": None}, "lacks allocations"),
        ({"void_reason": "incorrect"}, "active receipt has a void reason"),
        (
            {"transferred_cost_local": Decimal(0), "transferred_cost_base": Decimal(0)},
            "active receipt lacks basis movement",
        ),
        ({"status": "UNKNOWN"}, "unknown receipt status"),
    ],
)
def test_lifecycle_rejects_inconsistent_active_or_unknown_state(
    receipt_changes: dict[str, object],
    reason: str,
) -> None:
    receipt, allocation = _valid_evidence()
    with pytest.raises(ValueError, match=reason):
        _verify_lifecycle(replace(receipt, **receipt_changes), [allocation])


def test_lifecycle_accepts_closed_void_and_rejects_void_with_economics() -> None:
    receipt, allocation = _valid_evidence()
    voided = replace(
        receipt,
        status="VOIDED",
        transferred_cost_local=Decimal(0),
        transferred_cost_base=Decimal(0),
        basis_transfer_calculation_lineage=None,
        void_reason="SUPERSEDED",
    )

    _verify_lifecycle(voided, [])
    with pytest.raises(ValueError, match="voided receipt carries invalid economics"):
        _verify_lifecycle(voided, [allocation])


def _valid_evidence() -> tuple[
    LotBasisTransferReceiptReadRecord,
    LotBasisTransferAllocationReadRecord,
]:
    allocation = LotBasisTransferAllocationReadRecord(
        allocation_ordinal=1,
        source_lot_id="LOT-BUY-001",
        source_transaction_id="BUY-001",
        source_acquisition_date=date(2026, 1, 1),
        retained_quantity=Decimal("75"),
        source_cost_local_before=Decimal("100"),
        source_cost_base_before=Decimal("75"),
        transferred_cost_local=Decimal("25"),
        transferred_cost_base=Decimal("18.75"),
        retained_cost_local=Decimal("75"),
        retained_cost_base=Decimal("56.25"),
        allocation_content_hash="",
    )
    identity_hash = canonical_content_hash(
        {
            "portfolio_id": "P1",
            "source_security_id": "BOND-1",
            "source_transaction_id": "DEMERGER-OUT-001",
        }
    )
    receipt_id = f"lot-basis-transfer:{identity_hash}"
    allocation = replace(
        allocation,
        allocation_content_hash=cost_basis_allocation_content_hash(
            receipt_id=receipt_id,
            payload=_allocation_payload(allocation),
        ),
    )
    transaction_lineage = build_calculation_lineage(
        algorithm_id="transaction-cost",
        algorithm_version=1,
        intermediate_precision=38,
        input_payload={"source_transaction_id": "DEMERGER-OUT-001"},
        output_payload={"cost": Decimal("100")},
    ).lineage_payload()
    receipt = LotBasisTransferReceiptReadRecord(
        receipt_id=receipt_id,
        receipt_version=1,
        source_transaction_id="DEMERGER-OUT-001",
        target_transaction_id="DEMERGER-IN-001",
        target_lot_id="LOT-DEMERGER-IN-001",
        portfolio_id="P1",
        source_instrument_id="BOND-1",
        source_security_id="BOND-1",
        target_instrument_id="EQUITY-1",
        transfer_timestamp=datetime(2026, 8, 4, tzinfo=UTC),
        transaction_type="DEMERGER_OUT",
        cost_basis_method="FIFO",
        calculation_policy_id="CORPORATE_ACTION_FIFO_POLICY",
        calculation_policy_version="1.0.0",
        status="ACTIVE",
        void_reason=None,
        transferred_cost_local=Decimal("25"),
        transferred_cost_base=Decimal("18.75"),
        allocation_count=1,
        semantic_content_hash="",
        previous_receipt_content_hash=None,
        receipt_content_hash="",
        transaction_calculation_lineage=transaction_lineage,
        basis_transfer_calculation_lineage=None,
    )
    receipt = replace(
        receipt,
        basis_transfer_calculation_lineage=build_calculation_lineage(
            algorithm_id="cost-basis-lot-basis-transfer-allocation",
            algorithm_version=1,
            intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
            input_payload=basis_transfer_lineage_input_payload([allocation]),
            output_payload=basis_transfer_lineage_output_payload(
                [allocation],
                transferred_cost_base=receipt.transferred_cost_base,
                transferred_cost_local=receipt.transferred_cost_local,
            ),
            numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
        ).lineage_payload(),
    )
    semantic_hash = cost_basis_receipt_semantic_hash(
        _receipt_semantic_payload(receipt, [allocation])
    )
    return (
        replace(
            receipt,
            semantic_content_hash=semantic_hash,
            receipt_content_hash=receipt_version_content_hash(
                receipt_id=receipt_id,
                semantic_content_hash=semantic_hash,
                receipt_version=1,
                previous_receipt_content_hash=None,
            ),
        ),
        allocation,
    )


def _assert_corrupt(
    receipt: LotBasisTransferReceiptReadRecord,
    allocations: list[LotBasisTransferAllocationReadRecord],
    reason: str,
) -> None:
    with pytest.raises(CorruptLotBasisTransferReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, allocations, predecessor_hash=None)

    assert reason in str(error.value.__cause__)


def _rehash_receipt(
    receipt: LotBasisTransferReceiptReadRecord,
    allocations: list[LotBasisTransferAllocationReadRecord],
) -> LotBasisTransferReceiptReadRecord:
    semantic_hash = cost_basis_receipt_semantic_hash(
        _receipt_semantic_payload(receipt, allocations)
    )
    return replace(
        receipt,
        semantic_content_hash=semantic_hash,
        receipt_content_hash=receipt_version_content_hash(
            receipt_id=receipt.receipt_id,
            semantic_content_hash=semantic_hash,
            receipt_version=receipt.receipt_version,
            previous_receipt_content_hash=receipt.previous_receipt_content_hash,
        ),
    )
