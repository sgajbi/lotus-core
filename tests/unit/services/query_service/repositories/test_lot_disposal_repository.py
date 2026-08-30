"""Verify bounded, fail-closed latest-version lot-disposal receipt reads."""

from copy import deepcopy
from dataclasses import fields
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import (
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
)
from portfolio_common.domain.calculation_lineage import (
    build_calculation_lineage,
    canonical_content_hash,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
    LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
    cost_basis_allocation_content_hash,
    cost_basis_receipt_semantic_hash,
    lot_disposal_lineage_input_payload,
    lot_disposal_lineage_output_payload,
    receipt_version_content_hash,
)
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.lot_disposal_dto import LotDisposalAllocationResponse
from src.services.query_service.app.repositories.lot_disposal_records import (
    LotDisposalAllocationReadRecord,
    LotDisposalReceiptReadRecord,
)
from src.services.query_service.app.repositories.lot_disposal_repository import (
    _AMORTIZED_EVIDENCE_FIELDS,
    CorruptLotDisposalReadModelError,
    LotDisposalRepository,
    _allocation_payload,
    _allocation_record,
    _amortized_cost_evidence_payload,
    _receipt_semantic_payload,
    _verify_allocation,
    _verify_destination,
    _verify_header_shape,
    _verify_lifecycle,
    _verify_receipt_integrity,
)


@pytest.mark.asyncio
async def test_latest_receipt_uses_two_scoped_full_chain_queries() -> None:
    receipt = MagicMock(receipt_id="RECEIPT-1", allocation_count=2)
    receipt.receipt_version = 1
    receipt.destination_type = "INTERNAL_LOT"
    receipt.target_transaction_id = "EXCHANGE-IN-001"
    receipt.target_lot_id = "LOT-EXCHANGE-IN-001"
    receipt.target_instrument_id = "BOND-2"
    receipt.external_destination_reference = None
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
            "src.services.query_service.app.repositories.lot_disposal_repository."
            "verify_cost_basis_receipt_version_chain"
        ) as verify_chain,
        patch(
            "src.services.query_service.app.repositories.lot_disposal_repository."
            "_verify_receipt_integrity"
        ) as verify,
    ):
        resolved = await LotDisposalRepository(session).get_latest_receipt(
            portfolio_id="P1",
            transaction_id="RED-001",
        )

    assert resolved is not None
    mapped_receipt, mapped_allocations = resolved
    assert isinstance(mapped_receipt, LotDisposalReceiptReadRecord)
    assert mapped_receipt.receipt_id == "RECEIPT-1"
    assert mapped_receipt.allocation_count == 2
    assert mapped_receipt.destination_type == "INTERNAL_LOT"
    assert mapped_receipt.target_transaction_id == "EXCHANGE-IN-001"
    assert mapped_receipt.target_lot_id == "LOT-EXCHANGE-IN-001"
    assert all(isinstance(row, LotDisposalAllocationReadRecord) for row in mapped_allocations)
    assert [row.source_lot_id for row in mapped_allocations] == ["LOT-1", "LOT-2"]
    assert session.scalars.await_count == 2
    receipt_statement = session.scalars.await_args_list[0].args[0]
    allocation_statement = session.scalars.await_args_list[1].args[0]
    compiled_receipts = str(receipt_statement.compile(compile_kwargs={"literal_binds": True}))
    compiled_allocations = str(allocation_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "lot_disposal_receipts.portfolio_id = 'P1'" in compiled_receipts
    assert "lot_disposal_receipts.disposal_transaction_id = 'RED-001'" in compiled_receipts
    assert "ORDER BY lot_disposal_receipts.receipt_version" in compiled_receipts
    assert "lot_disposal_allocations.receipt_version <= 1" in compiled_allocations
    assert (
        "ORDER BY lot_disposal_allocations.receipt_version, "
        "lot_disposal_allocations.allocation_ordinal" in compiled_allocations
    )
    verify_chain.assert_called_once_with((receipt,))
    verify.assert_called_once_with(receipt, [first, second], predecessor_hash=None)


@pytest.mark.asyncio
async def test_latest_receipt_rejects_tampered_middle_version_at_depth_sixty_four() -> None:
    canonical_receipt, canonical_allocation = _valid_evidence()
    receipts: list[LotDisposalReceiptRecord] = []
    allocations: list[LotDisposalAllocationRecord] = []
    previous_hash: str | None = None
    for version in range(1, 65):
        receipt = deepcopy(canonical_receipt)
        allocation = deepcopy(canonical_allocation)
        receipt.receipt_version = version
        receipt.previous_receipt_content_hash = previous_hash
        receipt.receipt_content_hash = receipt_version_content_hash(
            receipt_id=receipt.receipt_id,
            semantic_content_hash=receipt.semantic_content_hash,
            receipt_version=version,
            previous_receipt_content_hash=previous_hash,
        )
        allocation.receipt_version = version
        receipts.append(receipt)
        allocations.append(allocation)
        previous_hash = receipt.receipt_content_hash
    allocations[31].allocation_content_hash = "0" * 64

    receipt_result = MagicMock()
    receipt_result.all.return_value = receipts
    allocation_result = MagicMock()
    allocation_result.all.return_value = allocations
    session = AsyncMock(spec=AsyncSession)
    session.scalars = AsyncMock(side_effect=[receipt_result, allocation_result])

    with pytest.raises(CorruptLotDisposalReadModelError, match="chain is corrupt"):
        await LotDisposalRepository(session).get_latest_receipt(
            portfolio_id="P1",
            transaction_id="EXCHANGE-OUT-001",
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
    repository = LotDisposalRepository(session)

    assert await repository.portfolio_exists(tenant_id="tenant-a", portfolio_id="P1") is True
    assert await repository.portfolio_exists(tenant_id="tenant-a", portfolio_id="MISSING") is False
    assert await repository.get_latest_receipt(portfolio_id="P1", transaction_id="UNKNOWN") is None

    assert session.execute.await_count == 2
    session.scalars.assert_awaited_once()


def test_amortized_evidence_contract_has_lossless_query_projection() -> None:
    persisted_evidence_fields = set(_AMORTIZED_EVIDENCE_FIELDS)
    read_record_fields = {field.name for field in fields(LotDisposalAllocationReadRecord)}
    response_fields = set(LotDisposalAllocationResponse.model_fields)

    assert persisted_evidence_fields <= read_record_fields
    assert persisted_evidence_fields <= response_fields


def test_integrity_accepts_complete_canonical_evidence() -> None:
    receipt, allocation = _valid_evidence()

    _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)


def test_integrity_fails_closed_on_missing_allocation_rows() -> None:
    receipt, _ = _valid_evidence()

    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [], predecessor_hash=None)

    assert "allocation count mismatch" in str(error.value.__cause__)


def test_integrity_fails_closed_on_tampered_header() -> None:
    receipt, allocation = _valid_evidence()
    receipt.instrument_id = "TAMPERED-BOND"

    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)

    assert "semantic content hash mismatch" in str(error.value.__cause__)


def test_integrity_fails_closed_on_tampered_allocation_hash() -> None:
    receipt, allocation = _valid_evidence()
    allocation.allocation_content_hash = "0" * 64

    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)

    assert "allocation content hash mismatch" in str(error.value.__cause__)


def test_integrity_fails_closed_when_header_does_not_conserve_allocations() -> None:
    receipt, allocation = _valid_evidence()
    receipt.consumed_cost_local = Decimal("24.99")

    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)

    assert "economics do not reconcile" in str(error.value.__cause__)


def test_integrity_rejects_rehashed_allocation_not_bound_to_disposal_lineage() -> None:
    receipt, allocation = _valid_evidence()
    allocation.source_transaction_id = "BUY-TAMPERED"
    allocation.allocation_content_hash = cost_basis_allocation_content_hash(
        receipt_id=receipt.receipt_id,
        payload=_allocation_payload(receipt, allocation),
    )
    _rehash_receipt(receipt, [allocation])

    _assert_corrupt(receipt, [allocation], "lineage does not bind persisted inputs")


def test_integrity_rejects_disposal_lineage_not_bound_to_persisted_outputs() -> None:
    receipt, allocation = _valid_evidence()
    receipt.disposal_calculation_lineage = build_calculation_lineage(
        algorithm_id=LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
        algorithm_version=LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=lot_disposal_lineage_input_payload(
            [_allocation_payload(receipt, allocation)]
        ),
        output_payload={"consumed_quantity": Decimal("24")},
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    ).lineage_payload()
    _rehash_receipt(receipt, [allocation])

    _assert_corrupt(receipt, [allocation], "lineage does not bind persisted outputs")


@pytest.mark.parametrize(
    ("algorithm_id", "algorithm_version", "numeric_policy", "reason"),
    [
        ("wrong-disposal", 2, True, "algorithm identity is unsupported"),
        (
            LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
            1,
            True,
            "algorithm identity is unsupported",
        ),
        (
            LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
            LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
            False,
            "numeric policy is unsupported",
        ),
    ],
)
def test_integrity_rejects_unsupported_disposal_lineage_contract(
    algorithm_id: str,
    algorithm_version: int,
    numeric_policy: bool,
    reason: str,
) -> None:
    receipt, allocation = _valid_evidence()
    receipt.disposal_calculation_lineage = build_calculation_lineage(
        algorithm_id=algorithm_id,
        algorithm_version=algorithm_version,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=lot_disposal_lineage_input_payload(
            [_allocation_payload(receipt, allocation)]
        ),
        output_payload=lot_disposal_lineage_output_payload(
            consumed_cost_base=receipt.consumed_cost_base,
            consumed_cost_local=receipt.consumed_cost_local,
            consumed_quantity=receipt.consumed_quantity,
        ),
        numeric_output_policy=(
            COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity() if numeric_policy else None
        ),
    ).lineage_payload()
    _rehash_receipt(receipt, [allocation])

    _assert_corrupt(receipt, [allocation], reason)


def test_integrity_fails_closed_on_partial_amortized_cost_evidence() -> None:
    receipt, allocation = _valid_evidence()
    allocation.amortized_cost_profile_id = "PROFILE-1"

    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash=None)

    assert "only partially persisted" in str(error.value.__cause__)


def test_integrity_verifies_immediate_predecessor_hash() -> None:
    receipt, allocation = _valid_evidence()
    predecessor_hash = "e" * 64
    receipt.receipt_version = 2
    receipt.previous_receipt_content_hash = predecessor_hash
    receipt.receipt_content_hash = receipt_version_content_hash(
        receipt_id=receipt.receipt_id,
        semantic_content_hash=receipt.semantic_content_hash,
        receipt_version=2,
        previous_receipt_content_hash=predecessor_hash,
    )
    allocation.receipt_version = 2

    _verify_receipt_integrity(receipt, [allocation], predecessor_hash=predecessor_hash)
    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, [allocation], predecessor_hash="f" * 64)

    assert "predecessor chain mismatch" in str(error.value.__cause__)


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("receipt_id", " ", "canonical nonblank text"),
        ("receipt_version", 0, "receipt version must be positive"),
        ("cost_basis_method", "LIFO", "unsupported cost basis method"),
        ("calculation_policy_version", None, "calculation policy identity is incomplete"),
        ("disposal_timestamp", datetime(2026, 8, 4), "timezone-aware"),
        ("transaction_calculation_lineage", None, "transaction calculation lineage is required"),
    ],
)
def test_header_shape_rejects_noncanonical_supportability_fields(
    field_name: str,
    value: object,
    reason: str,
) -> None:
    receipt, _ = _valid_evidence()
    setattr(receipt, field_name, value)

    with pytest.raises(ValueError, match=reason):
        _verify_header_shape(receipt)


def test_destination_accepts_absent_and_external_transfer_identity() -> None:
    receipt, _ = _valid_evidence()
    receipt.destination_type = None
    receipt.target_transaction_id = None
    receipt.target_lot_id = None
    receipt.target_instrument_id = None
    _verify_destination(receipt)
    assert "destination" not in _receipt_semantic_payload(receipt, [])

    receipt.destination_type = "EXTERNAL_TRANSFER"
    receipt.external_destination_reference = "CUSTODIAN-TRANSFER-1"
    _verify_destination(receipt)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"target_transaction_id": None}, "internal destination identity is incomplete"),
        ({"target_lot_id": "LOT-WRONG"}, "internal destination lot identity mismatch"),
        (
            {"external_destination_reference": "EXT"},
            "internal destination has an external reference",
        ),
        (
            {
                "destination_type": "EXTERNAL_TRANSFER",
                "target_transaction_id": None,
                "target_lot_id": None,
                "target_instrument_id": None,
                "external_destination_reference": " ",
            },
            "external destination reference is missing",
        ),
        (
            {"destination_type": "EXTERNAL_TRANSFER", "external_destination_reference": "EXT"},
            "external destination has internal target identity",
        ),
        ({"destination_type": "UNKNOWN"}, "unknown disposal destination type"),
    ],
)
def test_destination_rejects_ambiguous_or_incomplete_identity(
    changes: dict[str, object],
    reason: str,
) -> None:
    receipt, _ = _valid_evidence()
    for field_name, value in changes.items():
        setattr(receipt, field_name, value)

    with pytest.raises(ValueError, match=reason):
        _verify_destination(receipt)


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("portfolio_id", "P2", "allocation scope differs"),
        ("consumed_quantity", Decimal("0"), "quantity must be finite and positive"),
        ("consumed_quantity", Decimal("NaN"), "quantity must be finite and positive"),
        ("consumed_cost_local", Decimal("-1"), "must be finite and non-negative"),
        ("consumed_cost_base", Decimal("Infinity"), "must be finite and non-negative"),
    ],
)
def test_allocation_rejects_invalid_scope_and_economics(
    field_name: str,
    value: object,
    reason: str,
) -> None:
    receipt, allocation = _valid_evidence()
    setattr(allocation, field_name, value)

    with pytest.raises(ValueError, match=reason):
        _verify_allocation(receipt, allocation)


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("consumed_quantity", Decimal("0"), "positive allocations"),
        ("disposal_calculation_lineage", None, "lacks disposal lineage"),
        ("disposal_calculation_lineage", {}, "algorithm_id must be a string"),
        ("void_reason", "incorrect", "active receipt has a void reason"),
        ("status", "UNKNOWN", "unknown receipt status"),
    ],
)
def test_lifecycle_rejects_inconsistent_active_or_unknown_state(
    field_name: str,
    value: object,
    reason: str,
) -> None:
    receipt, allocation = _valid_evidence()
    setattr(receipt, field_name, value)

    with pytest.raises((TypeError, ValueError), match=reason):
        _verify_lifecycle(receipt, [allocation])


def test_lifecycle_accepts_closed_void_and_rejects_void_with_economics() -> None:
    receipt, allocation = _valid_evidence()
    receipt.status = "VOIDED"
    receipt.consumed_quantity = Decimal(0)
    receipt.consumed_cost_local = Decimal(0)
    receipt.consumed_cost_base = Decimal(0)
    receipt.disposal_calculation_lineage = None
    receipt.void_reason = "SUPERSEDED"

    _verify_lifecycle(receipt, [])
    with pytest.raises(ValueError, match="voided receipt carries invalid economics"):
        _verify_lifecycle(receipt, [allocation])


def test_integrity_rejects_identity_order_uniqueness_and_version_hash_drift() -> None:
    receipt, allocation = _valid_evidence()
    receipt.receipt_id = "lot-disposal:wrong"
    _assert_corrupt(receipt, [allocation], "receipt identity mismatch")

    receipt, allocation = _valid_evidence()
    allocation.allocation_ordinal = 2
    _assert_corrupt(receipt, [allocation], "allocation ordinals are not contiguous")

    receipt, allocation = _valid_evidence()
    duplicate = _valid_evidence()[1]
    duplicate.allocation_ordinal = 2
    receipt.allocation_count = 2
    _assert_corrupt(receipt, [allocation, duplicate], "source lot occurs more than once")

    receipt, allocation = _valid_evidence()
    receipt.previous_receipt_content_hash = "e" * 64
    _assert_corrupt(receipt, [allocation], "first receipt version has a predecessor")

    receipt, allocation = _valid_evidence()
    receipt.receipt_content_hash = "0" * 64
    _assert_corrupt(receipt, [allocation], "receipt content hash mismatch")


def test_complete_amortized_cost_evidence_is_verified_and_bound_to_lineage() -> None:
    receipt, allocation = _valid_evidence()
    _add_valid_amortized_evidence(receipt, allocation)

    payload = _amortized_cost_evidence_payload(receipt, allocation)
    allocation_payload = _allocation_payload(receipt, allocation)

    assert payload is not None
    assert payload["profile_id"] == "PROFILE-1"
    assert payload["consumed_quantity"] == Decimal("25")
    assert allocation_payload["amortized_cost_evidence"] == payload
    read_record = _allocation_record(allocation)
    assert read_record.amortized_cost_currency == "USD"
    assert read_record.amortized_cost_original_quantity == Decimal("100")
    assert read_record.amortized_cost_open_quantity_before == Decimal("25")
    assert read_record.amortized_cost_residual_quantity == Decimal("0")
    assert read_record.amortized_cost_scheduled_local == Decimal("25")
    assert read_record.amortized_cost_current_local == Decimal("25")
    assert read_record.amortized_cost_current_base == Decimal("18.75")
    assert read_record.amortized_cost_residual_local == Decimal("0")
    assert read_record.amortized_cost_book_fx_rate_to_base == Decimal("0.75")
    assert read_record.amortized_cost_residual_base == Decimal("0")
    assert read_record.amortized_cost_retained_rounding_local == Decimal("0")
    assert read_record.amortized_cost_retained_rounding_base == Decimal("0")


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("amortized_cost_profile_id", " ", "profile id is invalid"),
        ("amortized_cost_profile_version", 0, "profile version is invalid"),
        ("amortized_cost_profile_content_hash", "bad", "SHA-256"),
        ("amortized_cost_currency", "usd", "currency is invalid"),
        ("amortized_cost_recognized_through", date(2027, 1, 1), "recognition date is invalid"),
        ("amortized_cost_current_local", Decimal("NaN"), "must be a finite Decimal"),
        ("amortized_cost_original_quantity", Decimal("0"), "quantity or FX evidence is invalid"),
        ("amortized_cost_open_quantity_before", Decimal("26"), "quantity does not conserve"),
        ("amortized_cost_residual_local", Decimal("1"), "local cost does not conserve"),
        ("amortized_cost_residual_base", Decimal("1"), "base cost does not conserve"),
        (
            "amortized_cost_calculation_lineage",
            build_calculation_lineage(
                algorithm_id="amortized-cost-disposal",
                algorithm_version=1,
                intermediate_precision=38,
                input_payload={"source": "amortized-cost-disposal"},
                output_payload={"wrong": "output"},
            ).lineage_payload(),
            "lineage does not bind",
        ),
    ],
)
def test_amortized_cost_evidence_rejects_unusable_or_unreconciled_values(
    field_name: str,
    value: object,
    reason: str,
) -> None:
    receipt, allocation = _valid_evidence()
    _add_valid_amortized_evidence(receipt, allocation)
    setattr(allocation, field_name, value)

    with pytest.raises((TypeError, ValueError), match=reason):
        _amortized_cost_evidence_payload(receipt, allocation)


def _valid_evidence() -> tuple[LotDisposalReceiptRecord, LotDisposalAllocationRecord]:
    timestamp = datetime(2026, 8, 4, 10, 30, tzinfo=UTC)
    transaction_lineage = _lineage("transaction-cost", output={"cost": "100"})
    identity_hash = canonical_content_hash(
        {
            "disposal_transaction_id": "EXCHANGE-OUT-001",
            "portfolio_id": "P1",
            "security_id": "BOND-1",
        }
    )
    receipt_id = f"lot-disposal:{identity_hash}"
    receipt = LotDisposalReceiptRecord(
        receipt_id=receipt_id,
        receipt_version=1,
        disposal_transaction_id="EXCHANGE-OUT-001",
        portfolio_id="P1",
        instrument_id="BOND-1",
        security_id="BOND-1",
        disposal_timestamp=timestamp,
        transaction_type="EXCHANGE_OUT",
        destination_type="INTERNAL_LOT",
        target_transaction_id="EXCHANGE-IN-001",
        target_lot_id="LOT-EXCHANGE-IN-001",
        target_instrument_id="BOND-2",
        external_destination_reference=None,
        cost_basis_method="FIFO",
        calculation_policy_id="CORPORATE_ACTION_FIFO_POLICY",
        calculation_policy_version="1.0.0",
        status="ACTIVE",
        void_reason=None,
        consumed_quantity=Decimal("25"),
        consumed_cost_local=Decimal("25"),
        consumed_cost_base=Decimal("18.75"),
        allocation_count=1,
        transaction_calculation_lineage=transaction_lineage,
        disposal_calculation_lineage=None,
        semantic_content_hash="",
        previous_receipt_content_hash=None,
        receipt_content_hash="",
    )
    allocation = LotDisposalAllocationRecord(
        receipt_id=receipt_id,
        receipt_version=1,
        portfolio_id="P1",
        security_id="BOND-1",
        allocation_ordinal=1,
        source_lot_id="LOT-BUY-001",
        source_transaction_id="BUY-001",
        source_acquisition_date=date(2026, 1, 1),
        consumed_quantity=Decimal("25"),
        consumed_cost_local=Decimal("25"),
        consumed_cost_base=Decimal("18.75"),
        allocation_content_hash="",
    )
    allocation.allocation_content_hash = cost_basis_allocation_content_hash(
        receipt_id=receipt_id,
        payload=_allocation_payload(receipt, allocation),
    )
    receipt.disposal_calculation_lineage = _valid_disposal_lineage(receipt, [allocation])
    _rehash_receipt(receipt, [allocation])
    return receipt, allocation


def _assert_corrupt(
    receipt: LotDisposalReceiptRecord,
    allocations: list[LotDisposalAllocationRecord],
    reason: str,
) -> None:
    with pytest.raises(CorruptLotDisposalReadModelError, match="corrupt") as error:
        _verify_receipt_integrity(receipt, allocations, predecessor_hash=None)

    assert reason in str(error.value.__cause__)


def _valid_disposal_lineage(
    receipt: LotDisposalReceiptRecord,
    allocations: list[LotDisposalAllocationRecord],
) -> dict[str, object]:
    return build_calculation_lineage(
        algorithm_id=LOT_DISPOSAL_LINEAGE_ALGORITHM_ID,
        algorithm_version=LOT_DISPOSAL_LINEAGE_ALGORITHM_VERSION,
        intermediate_precision=COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision,
        input_payload=lot_disposal_lineage_input_payload(
            [_allocation_payload(receipt, allocation) for allocation in allocations]
        ),
        output_payload=lot_disposal_lineage_output_payload(
            consumed_cost_base=receipt.consumed_cost_base,
            consumed_cost_local=receipt.consumed_cost_local,
            consumed_quantity=receipt.consumed_quantity,
        ),
        numeric_output_policy=COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity(),
    ).lineage_payload()


def _rehash_receipt(
    receipt: LotDisposalReceiptRecord,
    allocations: list[LotDisposalAllocationRecord],
) -> None:
    receipt.semantic_content_hash = cost_basis_receipt_semantic_hash(
        _receipt_semantic_payload(receipt, allocations)
    )
    receipt.receipt_content_hash = receipt_version_content_hash(
        receipt_id=receipt.receipt_id,
        semantic_content_hash=receipt.semantic_content_hash,
        receipt_version=receipt.receipt_version,
        previous_receipt_content_hash=receipt.previous_receipt_content_hash,
    )


def _add_valid_amortized_evidence(
    receipt: LotDisposalReceiptRecord,
    allocation: LotDisposalAllocationRecord,
) -> None:
    allocation.amortized_cost_profile_id = "PROFILE-1"
    allocation.amortized_cost_profile_version = 1
    allocation.amortized_cost_profile_content_hash = "a" * 64
    allocation.amortized_cost_currency = "USD"
    allocation.amortized_cost_recognized_through = receipt.disposal_timestamp.date()
    allocation.amortized_cost_original_quantity = Decimal("100")
    allocation.amortized_cost_open_quantity_before = Decimal("25")
    allocation.amortized_cost_residual_quantity = Decimal("0")
    allocation.amortized_cost_scheduled_local = Decimal("25")
    allocation.amortized_cost_current_local = Decimal("25")
    allocation.amortized_cost_current_base = Decimal("18.75")
    allocation.amortized_cost_residual_local = Decimal("0")
    allocation.amortized_cost_book_fx_rate_to_base = Decimal("0.75")
    allocation.amortized_cost_residual_base = Decimal("0")
    allocation.amortized_cost_retained_rounding_local = Decimal("0")
    allocation.amortized_cost_retained_rounding_base = Decimal("0")
    allocation.amortized_cost_calculation_lineage = _lineage(
        "amortized-cost-disposal",
        output={
            "consumed_cost_base": Decimal("18.75"),
            "consumed_cost_local": Decimal("25"),
            "consumed_quantity": Decimal("25"),
            "current_cost_base": Decimal("18.75"),
            "current_cost_local": Decimal("25"),
            "open_quantity_before": Decimal("25"),
            "recognized_through_date": receipt.disposal_timestamp.date(),
            "residual_cost_base": Decimal("0"),
            "residual_cost_local": Decimal("0"),
            "residual_quantity": Decimal("0"),
            "retained_rounding_residual_base": Decimal("0"),
            "retained_rounding_residual_local": Decimal("0"),
            "scheduled_cost_local": Decimal("25"),
        },
    )


def _lineage(algorithm_id: str, *, output: dict[str, object]) -> dict[str, object]:
    return build_calculation_lineage(
        algorithm_id=algorithm_id,
        algorithm_version=1,
        intermediate_precision=38,
        input_payload={"source": algorithm_id},
        output_payload=output,
    ).lineage_payload()
