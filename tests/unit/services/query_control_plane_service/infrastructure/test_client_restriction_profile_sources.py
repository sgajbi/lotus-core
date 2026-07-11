"""Query and mapping tests for the client restriction SQL source adapter."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure import (
    client_restriction_profile_sources,
)

SqlAlchemyClientRestrictionProfileSourceReader = (
    client_restriction_profile_sources.SqlAlchemyClientRestrictionProfileSourceReader
)


class _Result:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


def _binding_row() -> SimpleNamespace:
    return SimpleNamespace(
        client_id="CIF_SG_000184",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 7, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def _restriction_row() -> SimpleNamespace:
    return SimpleNamespace(
        restriction_scope="asset_class",
        restriction_code="NO_PRIVATE_CREDIT_BUY",
        restriction_status="active",
        restriction_source="client_mandate",
        applies_to_buy=True,
        applies_to_sell=False,
        instrument_ids=None,
        asset_classes=["private_credit", ""],
        issuer_ids=[],
        country_codes=[],
        effective_from=date(2026, 1, 1),
        effective_to=None,
        restriction_version=2,
        source_record_id="client-restriction:2",
        observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_resolves_effective_discretionary_binding_and_maps_record() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([_binding_row()])
    reader = SqlAlchemyClientRestrictionProfileSourceReader(session)

    binding = await reader.resolve_mandate_binding(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date=date(2026, 5, 3),
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
    )

    assert binding is not None
    assert binding.client_id == "CIF_SG_000184"
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_mandate_bindings.mandate_type = 'discretionary'" in sql
    assert "portfolio_mandate_bindings.effective_from <= '2026-05-03'" in sql
    assert "portfolio_mandate_bindings.effective_to >= '2026-05-03'" in sql
    assert "portfolio_mandate_bindings.mandate_id = 'MANDATE_PB_SG_GLOBAL_BAL_001'" in sql


@pytest.mark.asyncio
async def test_selects_latest_active_restriction_per_scope_and_code() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([_restriction_row()])
    reader = SqlAlchemyClientRestrictionProfileSourceReader(session)

    restrictions = await reader.list_restrictions(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        as_of_date=date(2026, 5, 3),
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        include_inactive_restrictions=False,
    )

    assert restrictions[0].asset_classes == ("private_credit",)
    assert restrictions[0].instrument_ids == ()
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "row_number() OVER (PARTITION BY client_restriction_profiles.restriction_scope" in sql
    assert "client_restriction_profiles.restriction_status = 'active'" in sql
    assert "client_restriction_profiles.mandate_id IS NULL" in sql
    assert "client_restriction_profiles.mandate_id = 'MANDATE_PB_SG_GLOBAL_BAL_001'" in sql


@pytest.mark.asyncio
async def test_inactive_filter_is_omitted_only_when_explicitly_requested() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([])
    reader = SqlAlchemyClientRestrictionProfileSourceReader(session)

    await reader.list_restrictions(
        portfolio_id="P1",
        client_id="C1",
        as_of_date=date(2026, 5, 3),
        mandate_id=None,
        include_inactive_restrictions=True,
    )

    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "client_restriction_profiles.restriction_status = 'active'" not in sql
