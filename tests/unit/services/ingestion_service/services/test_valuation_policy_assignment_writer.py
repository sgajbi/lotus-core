from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from portfolio_common.domain.valuation.assignments import (
    InstrumentValuationPolicyAssignment,
    OverlappingValuationPolicyAssignmentError,
    ValuationPolicyAssignmentError,
    ValuationPolicyAssignmentStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)
from src.services.ingestion_service.app.services.valuation_policy_assignment_writer import (
    ValuationPolicyAssignmentAuthorityChange,
    ValuationPolicyAssignmentWriter,
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


def _assignment(**overrides: object) -> InstrumentValuationPolicyAssignment:
    record = _record(**overrides)
    return InstrumentValuationPolicyAssignment(
        tenant_id=str(record["tenant_id"]),
        legal_book_id=str(record["legal_book_id"]),
        security_id=str(record["security_id"]),
        policy_id=str(record["policy_id"]),
        policy_version=int(record["policy_version"]),  # type: ignore[arg-type]
        valid_from=record["valid_from"],  # type: ignore[arg-type]
        valid_to=record["valid_to"],  # type: ignore[arg-type]
        assignment_status=ValuationPolicyAssignmentStatus(str(record["assignment_status"])),
        assignment_version=int(record["assignment_version"]),  # type: ignore[arg-type]
        source_system=str(record["source_system"]),
        source_record_id=str(record["source_record_id"]),
        source_revision=str(record["source_revision"]),
        observed_at=record["observed_at"],  # type: ignore[arg-type]
        assignment_reason=str(record["assignment_reason"]),
    )


def _db_with_rows(rows: list[object]) -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    scalar_result = Mock()
    scalar_result.all.return_value = rows
    db.scalars.return_value = scalar_result
    return db


@pytest.mark.asyncio
async def test_writer_locks_scopes_in_deterministic_order_and_returns_new_authority() -> None:
    db = _db_with_rows([])
    assignments = [
        _assignment(tenant_id="TENANT_Z", security_id="SEC_Z"),
        _assignment(tenant_id="TENANT_A", security_id="SEC_A"),
    ]

    changes = await ValuationPolicyAssignmentWriter(db).append_many(assignments)  # type: ignore[arg-type]

    lock_keys = [call.args[1]["lock_key"] for call in db.execute.await_args_list]
    assert lock_keys == [
        "instrument-valuation-policy-assignment:TENANT_A:SG_PRIVATE_BANK_BOOK:SEC_A",
        "instrument-valuation-policy-assignment:TENANT_Z:SG_PRIVATE_BANK_BOOK:SEC_Z",
    ]
    assert [(change.previous, change.accepted.scope_key) for change in changes] == [
        (None, ("TENANT_A", "SG_PRIVATE_BANK_BOOK", "SEC_A")),
        (None, ("TENANT_Z", "SG_PRIVATE_BANK_BOOK", "SEC_Z")),
    ]
    assert [change.affected_from for change in changes] == [
        date(2026, 1, 1),
        date(2026, 1, 1),
    ]
    db.add_all.assert_called_once()
    assert len(db.add_all.call_args.args[0]) == 2
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_writer_treats_exact_persisted_source_version_as_idempotent_noop() -> None:
    persisted = SimpleNamespace(**_record())
    db = _db_with_rows([persisted])

    assert await ValuationPolicyAssignmentWriter(db).append_many([_assignment()]) == ()  # type: ignore[arg-type]

    db.add_all.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_writer_rejects_divergent_same_source_version() -> None:
    persisted = SimpleNamespace(**_record())
    db = _db_with_rows([persisted])

    with pytest.raises(
        ValuationPolicyAssignmentError,
        match="conflicting payloads share one source record and assignment_version",
    ):
        await ValuationPolicyAssignmentWriter(db).append_many(  # type: ignore[arg-type]
            [_assignment(assignment_reason="Divergent same-version payload.")]
        )

    db.add_all.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_writer_rejects_stale_source_version() -> None:
    persisted = SimpleNamespace(
        **_record(
            assignment_version=2,
            source_revision="rev-002",
            observed_at=datetime(2026, 2, 1, tzinfo=UTC),
        )
    )
    db = _db_with_rows([persisted])

    with pytest.raises(
        ValuationPolicyAssignmentError,
        match="correction version must be newer",
    ):
        await ValuationPolicyAssignmentWriter(db).append_many([_assignment()])  # type: ignore[arg-type]

    db.add_all.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_writer_returns_bounded_revaluation_start_for_semantic_correction() -> None:
    previous = _assignment(valid_from=date(2026, 2, 1))
    db = _db_with_rows([SimpleNamespace(**_record(valid_from=date(2026, 2, 1)))])
    accepted = _assignment(
        assignment_version=2,
        source_revision="rev-002",
        valid_from=date(2026, 1, 15),
        observed_at=datetime(2026, 3, 1, tzinfo=UTC),
    )

    changes = await ValuationPolicyAssignmentWriter(db).append_many([accepted])  # type: ignore[arg-type]

    assert changes == (
        ValuationPolicyAssignmentAuthorityChange(previous=previous, accepted=accepted),
    )
    assert changes[0].affected_from == date(2026, 1, 15)


@pytest.mark.asyncio
async def test_writer_keeps_metadata_only_correction_auditable_without_revaluation() -> None:
    previous = _assignment()
    db = _db_with_rows([SimpleNamespace(**_record())])
    accepted = _assignment(
        assignment_version=2,
        source_revision="rev-002",
        observed_at=datetime(2026, 3, 1, tzinfo=UTC),
        assignment_reason="Reviewed source rationale with unchanged valuation semantics.",
    )

    changes = await ValuationPolicyAssignmentWriter(db).append_many([accepted])  # type: ignore[arg-type]

    assert changes[0].previous == previous
    assert changes[0].accepted == accepted
    assert changes[0].affected_from is None


@pytest.mark.asyncio
async def test_writer_rejects_overlap_with_durable_history() -> None:
    existing = SimpleNamespace(
        **_record(
            source_record_id="EXISTING-AUTHORITY",
            source_revision="existing-rev-001",
        )
    )
    db = _db_with_rows([existing])
    incoming = _assignment(
        source_record_id="NEW-AUTHORITY",
        source_revision="incoming-rev-001",
        valid_from=date(2026, 7, 1),
    )

    with pytest.raises(OverlappingValuationPolicyAssignmentError, match="windows overlap"):
        await ValuationPolicyAssignmentWriter(db).append_many([incoming])  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_writer_rejects_duplicate_source_versions_before_locking() -> None:
    db = _db_with_rows([])
    duplicate = _assignment()

    with pytest.raises(ValuationPolicyAssignmentError, match="duplicate source versions"):
        await ValuationPolicyAssignmentWriter(db).append_many([duplicate, duplicate])  # type: ignore[arg-type]

    db.execute.assert_not_awaited()
    db.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_writer_rejects_unknown_policy_before_locking() -> None:
    db = _db_with_rows([])

    with pytest.raises(ValuationPolicyAssignmentError, match="unsupported valuation policy"):
        await ValuationPolicyAssignmentWriter(db).append_many(  # type: ignore[arg-type]
            [_assignment(policy_id="UNKNOWN_POLICY")]
        )

    db.execute.assert_not_awaited()
    db.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingestion_service_appends_and_commits_assignment_batch_atomically() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)  # type: ignore[arg-type]
    records = [_record()]
    change = ValuationPolicyAssignmentAuthorityChange(
        previous=None,
        accepted=_assignment(),
    )

    with patch.object(
        ValuationPolicyAssignmentWriter,
        "append_many",
        new=AsyncMock(return_value=(change,)),
    ) as append_many:
        changes = await service.append_instrument_valuation_policy_assignments(records)

    append_many.assert_awaited_once_with([_assignment()])
    assert changes == (change,)
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingestion_service_rolls_back_when_assignment_authority_is_invalid() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)  # type: ignore[arg-type]
    failure = OverlappingValuationPolicyAssignmentError("overlapping authority")

    with (
        patch.object(
            ValuationPolicyAssignmentWriter,
            "append_many",
            new=AsyncMock(side_effect=failure),
        ),
        pytest.raises(OverlappingValuationPolicyAssignmentError, match="overlapping authority"),
    ):
        await service.append_instrument_valuation_policy_assignments([_record()])

    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingestion_service_skips_empty_assignment_batch_without_transaction() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)  # type: ignore[arg-type]

    assert await service.append_instrument_valuation_policy_assignments([]) == ()

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_not_awaited()
