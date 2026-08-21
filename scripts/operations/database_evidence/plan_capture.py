"""Capture and explain exact SQL emitted by production repository methods."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.ext.asyncio import AsyncSession

from .contract import DatabaseEvidenceContractError


@dataclass(frozen=True, slots=True)
class CapturedDatabaseStatement:
    """Ephemeral SQL and binds that must never cross into retained evidence."""

    sql: str
    parameters: object


async def capture_single_production_statement(
    session: AsyncSession,
    operation: Callable[[], Awaitable[object]],
    *,
    statement_prefix: str = "SELECT",
) -> CapturedDatabaseStatement:
    """Execute an operation and retain its one matching statement only in memory."""

    captured: list[CapturedDatabaseStatement] = []
    bind = session.bind
    if bind is None:
        raise DatabaseEvidenceContractError("capture_session_unbound")
    normalized_prefix = statement_prefix.strip().upper()
    if not normalized_prefix or not normalized_prefix.isalpha():
        raise DatabaseEvidenceContractError("capture_statement_prefix_invalid")

    def capture_statement(
        _connection,
        _cursor,
        statement: str,
        parameters: object,
        _context,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith(normalized_prefix):
            captured.append(CapturedDatabaseStatement(statement, parameters))

    sqlalchemy_event.listen(bind.sync_engine, "before_cursor_execute", capture_statement)
    try:
        await operation()
    finally:
        sqlalchemy_event.remove(bind.sync_engine, "before_cursor_execute", capture_statement)
    if len(captured) != 1:
        raise DatabaseEvidenceContractError("capture_statement_cardinality_invalid")
    return captured[0]


async def explain_captured_statement(
    session: AsyncSession,
    captured: CapturedDatabaseStatement,
) -> object:
    """Run PostgreSQL JSON EXPLAIN without returning SQL or bind data."""

    if not captured.sql.lstrip().upper().startswith("SELECT"):
        raise DatabaseEvidenceContractError("explain_non_read_statement_forbidden")
    connection = await session.connection()
    result = await connection.exec_driver_sql(
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {captured.sql}",
        captured.parameters,
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise DatabaseEvidenceContractError("explain_plan_missing")
    return plan


async def capture_and_explain_rolled_back_mutation(
    session: AsyncSession,
    operation: Callable[[], Awaitable[object]],
) -> object:
    """Explain exact production UPDATE SQL while rolling back both executions."""

    if session.in_transaction():
        raise DatabaseEvidenceContractError("mutation_capture_requires_clean_session")
    async with session.begin():
        capture_savepoint = await session.begin_nested()
        try:
            captured = await capture_single_production_statement(
                session,
                operation,
                statement_prefix="UPDATE",
            )
        finally:
            await capture_savepoint.rollback()

        explain_savepoint = await session.begin_nested()
        try:
            connection = await session.connection()
            result = await connection.exec_driver_sql(
                f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {captured.sql}",
                captured.parameters,
            )
            plan = result.scalar_one_or_none()
            if plan is None:
                raise DatabaseEvidenceContractError("explain_plan_missing")
        finally:
            await explain_savepoint.rollback()
    return plan
