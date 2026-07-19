from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from portfolio_common.domain.valuation.assignments import (
    OverlappingValuationPolicyAssignmentError,
    ValuationPolicyAssignmentError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)
from src.services.ingestion_service.app.services.valuation_policy_assignment_write_guard import (
    ValuationPolicyAssignmentWriteGuard,
)


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "tenant_id": "LOTUS_PB_SG",
        "legal_book_id": "SG_PRIVATE_BANK_BOOK",
        "security_id": "BOND_US_CORP_2031",
        "policy_id": "CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL",
        "policy_version": 1,
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "assignment_status": "ACTIVE",
        "assignment_version": 1,
        "source_system": "security_master",
        "source_record_id": "VALPOL-BOND_US_CORP_2031-SG",
        "source_revision": "rev-001",
        "observed_at": datetime(2026, 1, 2, tzinfo=UTC),
        "assignment_reason": "Clean-price fixed-rate bond treatment.",
    }
    record.update(overrides)
    return record


def _db_with_rows(rows: list[object]) -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    scalar_result = Mock()
    scalar_result.all.return_value = rows
    db.scalars.return_value = scalar_result
    return db


@pytest.mark.asyncio
async def test_write_guard_locks_distinct_scopes_in_deterministic_order() -> None:
    db = _db_with_rows([])
    records = [
        _record(tenant_id="TENANT_Z", security_id="SEC_Z"),
        _record(tenant_id="TENANT_A", security_id="SEC_A"),
        _record(
            tenant_id="TENANT_A",
            security_id="SEC_A",
            assignment_version=2,
            source_revision="rev-002",
            assignment_status="RETIRED",
        ),
    ]

    await ValuationPolicyAssignmentWriteGuard(db).validate(records)  # type: ignore[arg-type]

    lock_keys = [call.args[1]["lock_key"] for call in db.execute.await_args_list]
    assert lock_keys == [
        "instrument-valuation-policy-assignment:TENANT_A:SG_PRIVATE_BANK_BOOK:SEC_A",
        "instrument-valuation-policy-assignment:TENANT_Z:SG_PRIVATE_BANK_BOOK:SEC_Z",
    ]
    db.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_guard_rejects_overlap_with_durable_history() -> None:
    existing = SimpleNamespace(
        **_record(
            source_record_id="EXISTING-AUTHORITY",
            source_revision="existing-rev-001",
        )
    )
    db = _db_with_rows([existing])
    incoming = _record(
        source_record_id="NEW-AUTHORITY",
        source_revision="incoming-rev-001",
        valid_from=date(2026, 7, 1),
    )

    with pytest.raises(OverlappingValuationPolicyAssignmentError, match="windows overlap"):
        await ValuationPolicyAssignmentWriteGuard(db).validate([incoming])  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_write_guard_rejects_duplicate_source_versions_before_locking() -> None:
    db = _db_with_rows([])
    duplicate = _record()

    with pytest.raises(ValuationPolicyAssignmentError, match="duplicate source versions"):
        await ValuationPolicyAssignmentWriteGuard(db).validate(  # type: ignore[arg-type]
            [duplicate, dict(duplicate)]
        )

    db.execute.assert_not_awaited()
    db.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_guard_rejects_unknown_policy_before_locking() -> None:
    db = _db_with_rows([])

    with pytest.raises(ValuationPolicyAssignmentError, match="unsupported valuation policy"):
        await ValuationPolicyAssignmentWriteGuard(db).validate(  # type: ignore[arg-type]
            [_record(policy_id="UNKNOWN_POLICY")]
        )

    db.execute.assert_not_awaited()
    db.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_guard_accepts_latest_correction_that_retires_existing_authority() -> None:
    existing = SimpleNamespace(**_record())
    db = _db_with_rows([existing])
    correction = _record(
        assignment_version=2,
        source_revision="rev-002",
        assignment_status="RETIRED",
        observed_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    await ValuationPolicyAssignmentWriteGuard(db).validate([correction])  # type: ignore[arg-type]

    db.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingestion_service_validates_and_commits_assignment_batch_atomically() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)  # type: ignore[arg-type]
    service._upsert_many = AsyncMock()  # type: ignore[method-assign]
    records = [_record()]

    with patch.object(
        ValuationPolicyAssignmentWriteGuard,
        "validate",
        new=AsyncMock(),
    ) as validate:
        await service.upsert_instrument_valuation_policy_assignments(records)

    validate.assert_awaited_once_with(records)
    service._upsert_many.assert_awaited_once()
    kwargs = service._upsert_many.await_args.kwargs
    assert kwargs["records"] == records
    assert kwargs["conflict_columns"] == [
        "tenant_id",
        "legal_book_id",
        "security_id",
        "source_system",
        "source_record_id",
        "assignment_version",
    ]
    assert kwargs["update_columns"] == [
        "policy_id",
        "policy_version",
        "valid_from",
        "valid_to",
        "assignment_status",
        "source_revision",
        "observed_at",
        "assignment_reason",
    ]
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingestion_service_rolls_back_when_assignment_authority_is_invalid() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)  # type: ignore[arg-type]
    service._upsert_many = AsyncMock()  # type: ignore[method-assign]
    failure = OverlappingValuationPolicyAssignmentError("overlapping authority")

    with (
        patch.object(
            ValuationPolicyAssignmentWriteGuard,
            "validate",
            new=AsyncMock(side_effect=failure),
        ),
        pytest.raises(OverlappingValuationPolicyAssignmentError, match="overlapping authority"),
    ):
        await service.upsert_instrument_valuation_policy_assignments([_record()])

    service._upsert_many.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingestion_service_skips_empty_assignment_batch_without_transaction() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)  # type: ignore[arg-type]

    await service.upsert_instrument_valuation_policy_assignments([])

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_not_awaited()
