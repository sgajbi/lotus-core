"""Unit contracts for corporate-action event-graph persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import CorporateActionEventRecord
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
ConflictingCorporateActionManifestError = port_module.ConflictingCorporateActionManifestError
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
    repository._advance_event = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda *_args, **_kwargs: calls.append("advance")
    )

    outcome = await repository.append_manifest(manifest)

    assert outcome is CorporateActionManifestAppendOutcome.APPENDED
    assert calls == ["lock", "event", "manifest", "nodes", "edges", "advance"]
    node_args = repository._insert_nodes.await_args.args
    assert node_args[0] == 101
    assert node_args[2] == {"CA-SOURCE-001": 0, "CA-TARGET-001": 1}
    repository._advance_event.assert_awaited_once_with(
        event,
        manifest_version=1,
        readiness_status=CorporateActionManifestReadinessStatus.AWAITING_CHILDREN,
    )


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
