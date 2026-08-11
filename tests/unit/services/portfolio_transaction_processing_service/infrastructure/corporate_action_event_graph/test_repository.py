"""Unit contracts for corporate-action event-graph persistence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import (
    CorporateActionChildObservationRecord,
    CorporateActionEventRecord,
)
from portfolio_common.domain.calculation_lineage import FinancialSourceReference

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.corporate_action_event_graph import (  # noqa: E501
    repository as repository_module,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    corporate_action_event_graph as port_module,
)

CorporateActionEventChild = corporate_action.CorporateActionEventChild
CorporateActionManifestReadinessStatus = corporate_action.CorporateActionManifestReadinessStatus
CorporateActionParentManifest = corporate_action.CorporateActionParentManifest
SqlAlchemyCorporateActionEventGraphRepository = (
    repository_module.SqlAlchemyCorporateActionEventGraphRepository
)
_manifest_json_payload = repository_module._manifest_json_payload
_child_from_observation = repository_module._child_from_observation
_require_valid_manifest_chain = repository_module._require_valid_manifest_chain
ConflictingCorporateActionManifestError = port_module.ConflictingCorporateActionManifestError
CorporateActionBookScopeError = port_module.CorporateActionBookScopeError
CorporateActionManifestAppendOutcome = port_module.CorporateActionManifestAppendOutcome

pytestmark = pytest.mark.unit


def _session_mock() -> AsyncMock:
    session = AsyncMock()
    nested = MagicMock()
    nested.__aenter__ = AsyncMock(return_value=nested)
    nested.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=nested)
    return session


def _manifest(*, version: int = 1, source_revision: str = "1") -> CorporateActionParentManifest:
    source = CorporateActionEventChild(
        transaction_id="CA-SOURCE-001",
        transaction_type="DEMERGER_OUT",
        child_role="SOURCE_POSITION_REDUCE",
        instrument_id="SOURCE-SEC",
        source_instrument_id="SOURCE-SEC",
    )
    target = CorporateActionEventChild(
        transaction_id="CA-TARGET-001",
        transaction_type="DEMERGER_IN",
        child_role="TARGET_POSITION_ADD",
        dependency_transaction_ids=(source.transaction_id,),
        instrument_id="TARGET-SEC",
        source_instrument_id="SOURCE-SEC",
        target_instrument_id="TARGET-SEC",
    )
    return CorporateActionParentManifest(
        corporate_action_event_id="CA-EVENT-001",
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-01",
        portfolio_id="CA-PORT-001",
        linked_transaction_group_id="CA-GROUP-001",
        parent_event_reference="CA-PARENT-001",
        corporate_action_type="DEMERGER",
        version=version,
        completion_declared=True,
        expected_children=(target, source),
        source_reference=FinancialSourceReference(
            source_system="custodian-ca",
            source_record_id="SOURCE-CA-001",
            source_revision=source_revision,
            source_content_hash="a" * 64,
            observed_at=datetime(2026, 8, 9, 9, tzinfo=timezone(timedelta(hours=8))),
        ),
    )


def _event_record(*, current_manifest_version: int | None) -> MagicMock:
    event = MagicMock(spec=CorporateActionEventRecord)
    event.id = 41
    event.tenant_id = "TENANT-SG"
    event.legal_book_id = "PB-SG-01"
    event.portfolio_id = "CA-PORT-001"
    event.corporate_action_event_id = "CA-EVENT-001"
    event.linked_transaction_group_id = "CA-GROUP-001"
    event.parent_event_reference = "CA-PARENT-001"
    event.current_manifest_version = current_manifest_version
    event.last_observation_sequence = 0
    event.state_version = current_manifest_version or 0
    return event


@pytest.mark.asyncio
async def test_event_lock_uses_stable_portfolio_and_parent_identity() -> None:
    session = _session_mock()
    repository = SqlAlchemyCorporateActionEventGraphRepository(session)

    await repository._acquire_event_locks(_manifest())

    assert session.execute.await_count == 2
    assert [call.args[1]["lock_identity"] for call in session.execute.await_args_list] == [
        "corporate-action-event-id:CA-PORT-001:CA-EVENT-001",
        "corporate-action-parent:CA-PORT-001:CA-GROUP-001:CA-PARENT-001",
    ]
    assert all(
        str(call.args[0]) == "SELECT pg_advisory_xact_lock(hashtextextended(:lock_identity, 0))"
        for call in session.execute.await_args_list
    )


@pytest.mark.asyncio
async def test_new_manifest_source_scope_must_match_governed_portfolio_book() -> None:
    session = _session_mock()
    scope_result = MagicMock()
    scope_result.one_or_none.return_value = SimpleNamespace(
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-01",
    )
    session.execute.return_value = scope_result
    repository = SqlAlchemyCorporateActionEventGraphRepository(session)

    with pytest.raises(CorporateActionBookScopeError, match="does not match"):
        await repository._create_event(replace(_manifest(), tenant_id="TENANT-OTHER"))


@pytest.mark.asyncio
async def test_existing_event_source_scope_cannot_be_rebound() -> None:
    session = _session_mock()
    repository = SqlAlchemyCorporateActionEventGraphRepository(session)
    repository._event_candidates = AsyncMock(  # type: ignore[method-assign]
        return_value=(_event_record(current_manifest_version=None),)
    )

    with pytest.raises(ConflictingCorporateActionManifestError, match="bound differently"):
        await repository._resolve_event(
            replace(_manifest(), legal_book_id="PB-OTHER-01"),
            conflict_error=ConflictingCorporateActionManifestError,
        )


@pytest.mark.asyncio
async def test_append_serializes_then_bulk_persists_and_advances_one_state() -> None:
    calls: list[str] = []
    session = _session_mock()
    repository = SqlAlchemyCorporateActionEventGraphRepository(session)
    event = _event_record(current_manifest_version=None)
    manifest = _manifest()
    repository._acquire_event_locks = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda *_args: calls.append("lock")
    )
    repository._event_candidates = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda *_args: calls.append("event") or (event,)
    )
    repository._manifest_candidates = AsyncMock(return_value=())  # type: ignore[method-assign]
    repository._current_manifest = AsyncMock(return_value=None)  # type: ignore[method-assign]
    repository._insert_manifest = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda **_kwargs: calls.append("manifest") or 101
    )
    repository._insert_nodes = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda *_args: calls.append("nodes")
    )
    repository._insert_edges = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda *_args: calls.append("edges")
    )
    repository._latest_observed_children = AsyncMock(  # type: ignore[method-assign]
        return_value=()
    )

    async def advance_event(event_record, **_kwargs) -> None:
        calls.append("advance")
        event_record.state_version += 1

    repository._advance_event = AsyncMock(  # type: ignore[method-assign]
        side_effect=advance_event
    )
    repository._insert_readiness_evaluation = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda **_kwargs: calls.append("evaluation")
    )

    outcome = await repository.append_manifest(manifest)

    assert outcome is CorporateActionManifestAppendOutcome.APPENDED
    assert calls == [
        "lock",
        "event",
        "manifest",
        "nodes",
        "edges",
        "advance",
        "evaluation",
    ]
    node_args = repository._insert_nodes.await_args.args
    assert node_args[0] == 101
    assert node_args[2] == {"CA-SOURCE-001": 0, "CA-TARGET-001": 1}
    repository._advance_event.assert_awaited_once_with(
        event,
        manifest_version=1,
        readiness_status=CorporateActionManifestReadinessStatus.AWAITING_CHILDREN,
    )
    assert repository._insert_readiness_evaluation.await_args.kwargs["state_version"] == 1


@pytest.mark.asyncio
async def test_exact_manifest_retry_is_unchanged_without_child_rewrites() -> None:
    session = _session_mock()
    repository = SqlAlchemyCorporateActionEventGraphRepository(session)
    event = _event_record(current_manifest_version=1)
    manifest = _manifest()
    existing = MagicMock()
    repository._acquire_event_locks = AsyncMock()  # type: ignore[method-assign]
    repository._event_candidates = AsyncMock(  # type: ignore[method-assign]
        return_value=(event,)
    )
    existing.manifest_version = 1
    repository._manifest_candidates = AsyncMock(  # type: ignore[method-assign]
        return_value=(existing,)
    )
    repository._manifest_from_record = AsyncMock(  # type: ignore[method-assign]
        return_value=manifest
    )
    repository._insert_manifest = AsyncMock()  # type: ignore[method-assign]

    outcome = await repository.append_manifest(manifest)

    assert outcome is CorporateActionManifestAppendOutcome.UNCHANGED
    repository._insert_manifest.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_manifest_version_with_different_content_fails_closed() -> None:
    session = _session_mock()
    repository = SqlAlchemyCorporateActionEventGraphRepository(session)
    event = _event_record(current_manifest_version=1)
    repository._acquire_event_locks = AsyncMock()  # type: ignore[method-assign]
    repository._event_candidates = AsyncMock(  # type: ignore[method-assign]
        return_value=(event,)
    )
    existing = MagicMock()
    existing.manifest_version = 1
    repository._manifest_candidates = AsyncMock(  # type: ignore[method-assign]
        return_value=(existing,)
    )
    repository._manifest_from_record = AsyncMock(  # type: ignore[method-assign]
        return_value=_manifest(source_revision="prior")
    )

    with pytest.raises(ConflictingCorporateActionManifestError, match="different content"):
        await repository.append_manifest(_manifest())


def test_manifest_json_payload_uses_canonical_timezone_text() -> None:
    payload = _manifest_json_payload(_manifest())
    source = payload["source_reference"]

    assert isinstance(source, dict)
    assert source["observed_at"] == "2026-08-09T01:00:00+00:00"


def test_observation_reconstruction_rejects_relational_identity_drift() -> None:
    child = _manifest().expected_children[0]
    record = MagicMock(spec=CorporateActionChildObservationRecord)
    record.transaction_id = "CA-DIFFERENT-001"
    record.observed_payload = child.lineage_payload()
    record.observed_content_hash = child.content_hash

    with pytest.raises(ConflictingCorporateActionManifestError, match="identity is inconsistent"):
        _child_from_observation(record)


def test_manifest_chain_accepts_root_and_contiguous_successor() -> None:
    root = _manifest_record(version=1, record_id=11, content_hash="a" * 64)
    successor = _manifest_record(
        version=2,
        record_id=12,
        content_hash="b" * 64,
        previous_id=11,
        previous_hash="a" * 64,
    )

    _require_valid_manifest_chain(root, (root,))
    _require_valid_manifest_chain(successor, (root, successor))


def test_manifest_chain_rejects_incorrect_predecessor_hash() -> None:
    root = _manifest_record(version=1, record_id=11, content_hash="a" * 64)
    successor = _manifest_record(
        version=2,
        record_id=12,
        content_hash="b" * 64,
        previous_id=11,
        previous_hash="f" * 64,
    )

    with pytest.raises(ConflictingCorporateActionManifestError, match="chain is inconsistent"):
        _require_valid_manifest_chain(successor, (root, successor))


def _manifest_record(
    *,
    version: int,
    record_id: int,
    content_hash: str,
    previous_id: int | None = None,
    previous_hash: str | None = None,
) -> MagicMock:
    record = MagicMock(spec=repository_module.CorporateActionManifestVersionRecord)
    record.id = record_id
    record.manifest_version = version
    record.manifest_content_hash = content_hash
    record.previous_manifest_id = previous_id
    record.previous_manifest_content_hash = previous_hash
    return record
