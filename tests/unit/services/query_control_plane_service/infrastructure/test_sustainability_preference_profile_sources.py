"""Query and mapping tests for the sustainability preference SQL adapter."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure import (
    sustainability_preference_profile_sources,
)

Reader = (
    sustainability_preference_profile_sources.SqlAlchemySustainabilityPreferenceProfileSourceReader
)


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


def _row():
    timestamp = datetime(2026, 5, 3, 9, tzinfo=UTC)
    return SimpleNamespace(
        preference_framework="LOTUS_SUSTAINABILITY_V1",
        preference_code="MIN_SUSTAINABLE_ALLOCATION",
        preference_status="active",
        preference_source="client_mandate",
        minimum_allocation="0.2000000000",
        maximum_allocation=" ",
        applies_to_asset_classes=["equity", ""],
        exclusion_codes=["THERMAL_COAL"],
        positive_tilt_codes=[],
        effective_from=date(2026, 1, 1),
        effective_to=None,
        preference_version="2",
        source_record_id="preference:2",
        observed_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )


@pytest.mark.asyncio
async def test_selects_latest_active_preference_and_maps_values() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([_row()])
    reader = Reader(session)

    records = await reader.list_preferences(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        as_of_date=date(2026, 5, 3),
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        include_inactive_preferences=False,
    )

    assert str(records[0].minimum_allocation) == "0.2000000000"
    assert records[0].maximum_allocation is None
    assert records[0].applies_to_asset_classes == ("equity",)
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert (
        "row_number() OVER (PARTITION BY sustainability_preference_profiles.preference_framework"
        in sql
    )
    assert "sustainability_preference_profiles.preference_status = 'active'" in sql
    assert "sustainability_preference_profiles.mandate_id IS NULL" in sql


@pytest.mark.asyncio
async def test_inactive_filter_is_removed_only_when_requested() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([])
    reader = Reader(session)

    await reader.list_preferences(
        portfolio_id="P1",
        client_id="C1",
        as_of_date=date(2026, 5, 3),
        mandate_id=None,
        include_inactive_preferences=True,
    )

    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "sustainability_preference_profiles.preference_status = 'active'" not in sql
