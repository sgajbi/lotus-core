"""SQL adapter tests for approved models and DPM mandate populations."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_control_plane_service.app.infrastructure import (
    dpm_portfolio_population_sources,
)


def _mandate_row() -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        mandate_id="MANDATE_001",
        client_id="CIF_SG_GLOBAL_BAL_001",
        booking_center_code="Singapore",
        jurisdiction_code="SG",
        discretionary_authority_status="active",
        model_portfolio_id="MODEL_A",
        policy_pack_id="POLICY_A",
        mandate_objective="balanced_growth_income",
        risk_profile="balanced",
        investment_horizon="medium_term",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        binding_version=7,
        source_record_id="mandate:1",
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 7, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


def _session_returning(*rows: object) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    result.scalars.return_value.first.return_value = rows[0] if rows else None
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_resolve_approved_model_maps_effective_source_record() -> None:
    row = SimpleNamespace(
        model_portfolio_id="MODEL_A",
        model_portfolio_version="2026.05",
        approval_status="approved",
        approved_at=datetime(2026, 5, 1, 8, tzinfo=UTC),
        effective_from=date(2026, 5, 1),
        effective_to=None,
        source_system="lotus-core",
        source_record_id="model:1",
        observed_at=datetime(2026, 5, 1, 8, tzinfo=UTC),
        created_at=datetime(2026, 5, 1, 7, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 9, tzinfo=UTC),
    )
    session = _session_returning(row)

    model = await dpm_portfolio_population_sources.SqlAlchemyDpmPortfolioPopulationReader(
        session
    ).resolve_approved_model(model_portfolio_id="MODEL_A", as_of_date=date(2026, 5, 3))

    assert model is not None
    assert model.model_portfolio_version == "2026.05"
    sql = str(session.execute.await_args.args[0])
    assert "model_portfolio_definitions.approval_status" in sql
    assert "model_portfolio_definitions.effective_from" in sql
    assert "ORDER BY model_portfolio_definitions.effective_from DESC" in sql


@pytest.mark.asyncio
async def test_affected_mandates_use_effective_discretionary_population_predicates() -> None:
    session = _session_returning(_mandate_row())
    reader = dpm_portfolio_population_sources.SqlAlchemyDpmPortfolioPopulationReader(session)

    records = await reader.list_affected_mandates(
        model_portfolio_id="MODEL_A",
        as_of_date=date(2026, 5, 3),
        booking_center_code="Singapore",
        include_inactive_mandates=False,
    )

    assert records[0].binding_version == 7
    sql = str(session.execute.await_args.args[0])
    assert "portfolio_mandate_bindings.mandate_type" in sql
    assert "portfolio_mandate_bindings.model_portfolio_id IN" in sql
    assert "portfolio_mandate_bindings.booking_center_code" in sql
    assert "portfolio_mandate_bindings.discretionary_authority_status" in sql
    assert "ORDER BY portfolio_mandate_bindings.portfolio_id ASC" in sql


@pytest.mark.asyncio
async def test_universe_applies_cursor_and_fetch_limit() -> None:
    session = _session_returning(_mandate_row())
    reader = dpm_portfolio_population_sources.SqlAlchemyDpmPortfolioPopulationReader(session)

    await reader.list_universe_candidates(
        as_of_date=date(2026, 5, 3),
        booking_center_code=None,
        model_portfolio_ids=("MODEL_A", "MODEL_B"),
        include_inactive_mandates=True,
        after_sort_key=("PB_000", "MANDATE_000"),
        limit=251,
    )

    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert "portfolio_mandate_bindings.model_portfolio_id IN" in sql
    assert (
        "(portfolio_mandate_bindings.portfolio_id, portfolio_mandate_bindings.mandate_id) >" in sql
    )
    assert "portfolio_mandate_bindings.discretionary_authority_status =" not in sql
    assert statement._limit_clause.value == 251
