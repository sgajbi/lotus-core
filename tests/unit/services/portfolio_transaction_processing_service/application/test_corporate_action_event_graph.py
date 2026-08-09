"""Application contracts for corporate-action parent-graph UoWs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application.corporate_action_event_graph import (  # noqa: E501
    RegisterCorporateActionChildObservationUseCase,
    RegisterCorporateActionManifestUseCase,
)
from src.services.portfolio_transaction_processing_service.app.ports.corporate_action_event_graph import (  # noqa: E501
    CorporateActionManifestAppendOutcome,
)

pytestmark = pytest.mark.unit


class _UnitOfWork:
    def __init__(self) -> None:
        self.event_graph = AsyncMock()
        self.commit = AsyncMock()
        self.exited_with: type[BaseException] | None = None

    async def __aenter__(self) -> _UnitOfWork:
        return self

    async def __aexit__(self, exc_type, _exc_value, _traceback) -> None:
        self.exited_with = exc_type


@pytest.mark.asyncio
async def test_manifest_use_case_commits_exact_repository_outcome() -> None:
    unit_of_work = _UnitOfWork()
    manifest = MagicMock()
    unit_of_work.event_graph.append_manifest.return_value = (
        CorporateActionManifestAppendOutcome.APPENDED
    )
    use_case = RegisterCorporateActionManifestUseCase(lambda: unit_of_work)

    outcome = await use_case.execute(manifest)

    assert outcome is CorporateActionManifestAppendOutcome.APPENDED
    unit_of_work.event_graph.append_manifest.assert_awaited_once_with(manifest)
    unit_of_work.commit.assert_awaited_once_with()
    assert unit_of_work.exited_with is None


@pytest.mark.asyncio
async def test_child_observation_use_case_commits_decision() -> None:
    unit_of_work = _UnitOfWork()
    observation = MagicMock()
    decision = MagicMock()
    unit_of_work.event_graph.observe_child.return_value = decision
    use_case = RegisterCorporateActionChildObservationUseCase(lambda: unit_of_work)

    assert await use_case.execute(observation) is decision

    unit_of_work.event_graph.observe_child.assert_awaited_once_with(observation)
    unit_of_work.commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_repository_failure_exits_without_commit() -> None:
    unit_of_work = _UnitOfWork()
    unit_of_work.event_graph.append_manifest.side_effect = RuntimeError("write failed")
    use_case = RegisterCorporateActionManifestUseCase(lambda: unit_of_work)

    with pytest.raises(RuntimeError, match="write failed"):
        await use_case.execute(MagicMock())

    unit_of_work.commit.assert_not_awaited()
    assert unit_of_work.exited_with is RuntimeError
