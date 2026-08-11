"""Prove book-scoped corporate-action support reads against PostgreSQL."""

import runpy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.database_models import Portfolio
from portfolio_common.domain.calculation_lineage import FinancialSourceReference
from sqlalchemy import Engine, inspect, text
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.corporate_action_event_graph import (  # noqa: E501
    SqlAlchemyCorporateActionEventGraphRepository,
)
from src.services.query_control_plane_service.app.infrastructure.corporate_action_support_reader import (  # noqa: E501
    SqlAlchemyCorporateActionSupportReader,
)

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 8, 11, 4, 30, tzinfo=UTC)
MIGRATION_DIRECTORY = Path(__file__).resolve().parents[4] / "alembic" / "versions"
MIGRATIONS = (
    MIGRATION_DIRECTORY / "c152b2c3d519_feat_add_corporate_action_event_graph.py",
    MIGRATION_DIRECTORY / "c153b2c3d520_feat_add_corporate_action_execution_releases.py",
    MIGRATION_DIRECTORY / "c154b2c3d521_perf_index_corporate_action_support.py",
    MIGRATION_DIRECTORY / "c155b2c3d522_fix_forward_corporate_action_authority.py",
)


def _apply_support_migrations(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        inspector = inspect(connection)
        for path in MIGRATIONS:
            migration: dict[str, Any] = runpy.run_path(str(path))
            table_names = inspector.get_table_names()
            if path.name.startswith("c152") and "corporate_action_events" in table_names:
                continue
            release_exists = "corporate_action_execution_releases" in table_names
            if path.name.startswith("c153") and release_exists:
                continue
            if path.name.startswith("c154") and any(
                index["name"] == "ix_ca_event_book_scope_updated"
                for index in inspector.get_indexes("corporate_action_events")
            ):
                continue
            if (
                path.name.startswith("c155")
                and connection.scalar(
                    text("SELECT to_regprocedure('enforce_ca_manifest_payload_book_scope()')")
                )
                is not None
            ):
                continue
            migration["upgrade"].__globals__["op"] = operations
            migration["upgrade"]()
            inspector = inspect(connection)


async def _add_event(
    session: AsyncSession,
    *,
    event_suffix: str,
    completion_declared: bool,
) -> None:
    source = corporate_action.CorporateActionEventChild(
        transaction_id=f"CA-SOURCE-{event_suffix}",
        transaction_type="DEMERGER_OUT",
        child_role="SOURCE_POSITION_REDUCE",
        instrument_id="SOURCE-SEC",
        source_instrument_id="SOURCE-SEC",
    )
    target = corporate_action.CorporateActionEventChild(
        transaction_id=f"CA-TARGET-{event_suffix}",
        transaction_type="DEMERGER_IN",
        child_role="TARGET_POSITION_ADD",
        dependency_transaction_ids=(source.transaction_id,),
        instrument_id="TARGET-SEC",
        source_instrument_id="SOURCE-SEC",
        target_instrument_id="TARGET-SEC",
    )
    manifest = corporate_action.CorporateActionParentManifest(
        corporate_action_event_id=f"CA-{event_suffix}",
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-01",
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        linked_transaction_group_id=f"CA-GROUP-{event_suffix}",
        parent_event_reference=f"CA-PARENT-{event_suffix}",
        corporate_action_type="DEMERGER",
        version=1,
        completion_declared=completion_declared,
        expected_children=(source, target),
        source_reference=FinancialSourceReference(
            source_system="custodian-ca",
            source_record_id=f"SOURCE-{event_suffix}",
            source_revision="1",
            source_content_hash="a" * 64,
            observed_at=NOW,
        ),
    )
    repository = SqlAlchemyCorporateActionEventGraphRepository(session)
    await repository.append_manifest(manifest)


async def test_reader_is_book_scoped_state_aware_and_two_statement_bounded(
    clean_db,
    db_engine: Engine,
    async_db_session: AsyncSession,
) -> None:
    _apply_support_migrations(db_engine)
    async_db_session.add(
        Portfolio(
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            tenant_id="TENANT-SG",
            legal_book_id="PB-SG-01",
            base_currency="SGD",
            open_date=date(2020, 1, 1),
            risk_exposure="MODERATE",
            investment_time_horizon="LONG_TERM",
            portfolio_type="DISCRETIONARY",
            booking_center_code="SG",
            client_id="CLIENT-CANONICAL",
            is_leverage_allowed=False,
            status="ACTIVE",
        )
    )
    await async_db_session.flush()
    await _add_event(
        async_db_session,
        event_suffix="CHILDREN",
        completion_declared=True,
    )
    await _add_event(
        async_db_session,
        event_suffix="COMPLETION",
        completion_declared=False,
    )
    await async_db_session.commit()

    reader = SqlAlchemyCorporateActionSupportReader(async_db_session)
    support_selects: list[str] = []

    def _count_support_selects(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        normalized = statement.lower()
        if normalized.lstrip().startswith("select") and "corporate_action_events" in normalized:
            support_selects.append(normalized)

    sync_engine = async_db_session.bind.sync_engine
    sqlalchemy_event.listen(sync_engine, "before_cursor_execute", _count_support_selects)
    try:
        page = await reader.list_current(
            tenant_id="TENANT-SG",
            legal_book_id="PB-SG-01",
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            corporate_action_event_id=None,
            readiness_status=None,
            execution_status=None,
            skip=0,
            limit=100,
        )
    finally:
        sqlalchemy_event.remove(sync_engine, "before_cursor_execute", _count_support_selects)

    assert len(support_selects) == 2
    assert page.total == 2
    assert {item.corporate_action_event_id for item in page.items} == {
        "CA-CHILDREN",
        "CA-COMPLETION",
    }
    by_id = {item.corporate_action_event_id: item for item in page.items}
    assert by_id["CA-CHILDREN"].execution_release is None
    assert by_id["CA-CHILDREN"].readiness.finding_count == 1
    assert by_id["CA-CHILDREN"].readiness.finding_reason_codes == (
        "CA_MANIFEST_MISSING_EXPECTED_CHILD",
    )

    wrong_tenant = await reader.list_current(
        tenant_id="TENANT-OTHER",
        legal_book_id="PB-SG-01",
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        corporate_action_event_id=None,
        readiness_status=None,
        execution_status=None,
        skip=0,
        limit=100,
    )
    wrong_book = await reader.list_current(
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-OTHER",
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        corporate_action_event_id=None,
        readiness_status=None,
        execution_status=None,
        skip=0,
        limit=100,
    )
    awaiting_completion = await reader.list_current(
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-01",
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        corporate_action_event_id=None,
        readiness_status="AWAITING_COMPLETION",
        execution_status=None,
        skip=0,
        limit=100,
    )
    no_failed_releases = await reader.list_current(
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-01",
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        corporate_action_event_id=None,
        readiness_status=None,
        execution_status="FAILED",
        skip=0,
        limit=100,
    )

    assert wrong_tenant.total == 0
    assert wrong_tenant.scope_exists is False
    assert wrong_book.total == 0
    assert wrong_book.scope_exists is False
    assert awaiting_completion.total == 1
    assert awaiting_completion.items[0].corporate_action_event_id == "CA-COMPLETION"
    assert no_failed_releases.total == 0
    assert no_failed_releases.scope_exists is True
