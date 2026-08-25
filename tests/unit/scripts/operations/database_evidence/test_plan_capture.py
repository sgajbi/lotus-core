from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.operations.database_evidence.contract import DatabaseEvidenceContractError
from scripts.operations.database_evidence.plan_capture import (
    CapturedDatabaseStatement,
    capture_and_explain_rolled_back_mutation,
    capture_and_explain_rolled_back_statement,
    capture_single_production_statement,
    explain_captured_statement,
)


@pytest.mark.asyncio
async def test_capture_rejects_unbound_session_without_running_operation() -> None:
    session = AsyncMock()
    session.bind = None
    operation = AsyncMock()

    with pytest.raises(DatabaseEvidenceContractError, match="capture_session_unbound"):
        await capture_single_production_statement(session, operation)

    operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_explain_rejects_mutating_statement_without_database_io() -> None:
    session = AsyncMock()

    with pytest.raises(
        DatabaseEvidenceContractError,
        match="explain_non_read_statement_forbidden",
    ):
        await explain_captured_statement(
            session,
            CapturedDatabaseStatement("UPDATE jobs SET status = 'x'", ()),
        )

    session.connection.assert_not_awaited()


@pytest.mark.asyncio
async def test_mutation_capture_rejects_existing_caller_transaction() -> None:
    session = AsyncMock()
    session.in_transaction = MagicMock(return_value=True)
    operation = AsyncMock()

    with pytest.raises(
        DatabaseEvidenceContractError,
        match="mutation_capture_requires_clean_session",
    ):
        await capture_and_explain_rolled_back_mutation(session, operation)

    operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_statement_capture_rejects_empty_marker_without_running_operation() -> None:
    session = AsyncMock()
    session.in_transaction = MagicMock(return_value=False)
    operation = AsyncMock()

    with pytest.raises(
        DatabaseEvidenceContractError,
        match="capture_statement_marker_invalid",
    ):
        await capture_and_explain_rolled_back_statement(
            session,
            operation,
            statement_prefix="WITH",
            statement_marker="  ",
        )

    operation.assert_not_awaited()
