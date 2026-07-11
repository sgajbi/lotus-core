"""Query and mapping tests for the client tax-profile SQL adapter."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure import client_tax_profile_sources

Reader = client_tax_profile_sources.SqlAlchemyClientTaxProfileSourceReader


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


def _row():
    timestamp = datetime(2026, 5, 3, 9, tzinfo=UTC)
    return SimpleNamespace(
        tax_profile_id="TAX_PROFILE_SG_001",
        tax_residency_country="SG",
        booking_tax_jurisdiction="SG",
        tax_status="TAXABLE",
        profile_status="active",
        withholding_tax_rate="0.1500000000",
        capital_gains_tax_applicable=False,
        income_tax_applicable=True,
        treaty_codes=["US_SG_TREATY", ""],
        eligible_account_types=["DPM"],
        effective_from=date(2026, 1, 1),
        effective_to=None,
        profile_version="2",
        source_record_id="tax-profile:2",
        observed_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )


@pytest.mark.asyncio
async def test_selects_latest_active_profile_and_maps_values() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([_row()])
    reader = Reader(session)

    records = await reader.list_profiles(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        as_of_date=date(2026, 5, 3),
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        include_inactive_profiles=False,
    )

    assert str(records[0].withholding_tax_rate) == "0.1500000000"
    assert records[0].treaty_codes == ("US_SG_TREATY",)
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "row_number() OVER (PARTITION BY client_tax_profiles.tax_profile_id" in sql
    assert "client_tax_profiles.profile_status = 'active'" in sql
    assert "client_tax_profiles.mandate_id IS NULL" in sql


@pytest.mark.asyncio
async def test_inactive_filter_is_removed_only_when_requested() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([])
    reader = Reader(session)
    await reader.list_profiles(
        portfolio_id="P1",
        client_id="C1",
        as_of_date=date(2026, 5, 3),
        mandate_id=None,
        include_inactive_profiles=True,
    )
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "client_tax_profiles.profile_status = 'active'" not in sql
