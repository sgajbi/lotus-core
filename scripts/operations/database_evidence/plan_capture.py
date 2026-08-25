"""Capture and explain exact SQL emitted by production repository methods."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from .contract import DatabaseEvidenceContractError


@dataclass(frozen=True, slots=True)
class CapturedDatabaseStatement:
    """Ephemeral SQL and binds that must never cross into retained evidence."""

    sql: str
    parameters: object


class _StatementCaptured(Exception):
    """Stop a production operation before its selected statement executes."""

    def __init__(self, statement: CapturedDatabaseStatement) -> None:
        super().__init__("production_statement_captured")
        self.statement = statement


class _PlanCaptured(Exception):
    """Carry an analyzed plan across the mandatory transaction rollback."""

    def __init__(self, plan: object) -> None:
        super().__init__("analyzed_plan_captured")
        self.plan = plan


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
        raise DatabaseEvidenceContractError(
            f"capture_statement_cardinality_invalid:{len(captured)}"
        )
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
    operation: Callable[[AsyncSession], Awaitable[object]],
) -> object:
    """Explain exact production UPDATE SQL while rolling back both executions."""

    return await capture_and_explain_rolled_back_statement(
        session,
        operation,
        statement_prefix="UPDATE",
    )


async def capture_and_explain_rolled_back_statement(
    session: AsyncSession,
    operation: Callable[[AsyncSession], Awaitable[object]],
    *,
    statement_prefix: str,
    statement_marker: str | None = None,
) -> object:
    """Explain one production statement while rolling back both executions."""

    normalized_prefix = statement_prefix.strip().upper()
    if not normalized_prefix or not normalized_prefix.isalpha():
        raise DatabaseEvidenceContractError("capture_statement_prefix_invalid")
    normalized_marker = statement_marker.strip().upper() if statement_marker is not None else None
    if normalized_marker == "":
        raise DatabaseEvidenceContractError("capture_statement_marker_invalid")
    if session.in_transaction():
        raise DatabaseEvidenceContractError("mutation_capture_requires_clean_session")
    bind = session.bind
    if not isinstance(bind, AsyncEngine):
        raise DatabaseEvidenceContractError("capture_session_unbound")

    async with bind.connect() as connection:

        def stop_before_execution(
            _connection,
            _cursor,
            statement: str,
            parameters: object,
            _context,
            _executemany: bool,
        ) -> None:
            normalized_statement = statement.lstrip().upper()
            if normalized_statement.startswith(normalized_prefix) and (
                normalized_marker is None or normalized_marker in normalized_statement
            ):
                raise _StatementCaptured(CapturedDatabaseStatement(statement, parameters))

        sqlalchemy_event.listen(
            connection.sync_connection,
            "before_cursor_execute",
            stop_before_execution,
        )
        try:
            async with AsyncSession(bind=connection, expire_on_commit=False) as evidence_session:
                try:
                    await operation(evidence_session)
                except _StatementCaptured as captured_error:
                    captured = captured_error.statement
                else:
                    raise DatabaseEvidenceContractError("capture_statement_cardinality_invalid:0")
        finally:
            sqlalchemy_event.remove(
                connection.sync_connection,
                "before_cursor_execute",
                stop_before_execution,
            )

        if connection.in_transaction():
            await connection.rollback()
        try:
            async with connection.begin():
                result = await connection.exec_driver_sql(
                    f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {captured.sql}",
                    captured.parameters,
                )
                plan = result.scalar_one_or_none()
                if plan is None:
                    raise DatabaseEvidenceContractError("explain_plan_missing")
                raise _PlanCaptured(plan)
        except _PlanCaptured as captured_plan:
            return captured_plan.plan
