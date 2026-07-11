"""Query and mapping tests for the client tax-rule SQL adapter."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure import client_tax_rule_set_sources

Reader = client_tax_rule_set_sources.SqlAlchemyClientTaxRuleSetSourceReader


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
        rule_set_id="TAX_RULES_SG_2026",
        tax_year="2026",
        jurisdiction_code="SG",
        rule_code="US_DIVIDEND_WITHHOLDING",
        rule_category="withholding",
        rule_status="active",
        rule_source="tax_policy",
        applies_to_asset_classes=["equity", ""],
        applies_to_security_ids=[],
        applies_to_income_types=["dividend"],
        rate="0.3000000000",
        threshold_amount=" ",
        threshold_currency="USD",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        rule_version="3",
        source_record_id="tax-rule:3",
        observed_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )


@pytest.mark.asyncio
async def test_selects_latest_active_rule_and_maps_values() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([_row()])
    records = await Reader(session).list_rules(
        portfolio_id="P1",
        client_id="C1",
        as_of_date=date(2026, 5, 3),
        mandate_id="M1",
        include_inactive_rules=False,
    )
    assert records[0].tax_year == 2026
    assert records[0].rate == Decimal("0.3000000000")
    assert records[0].threshold_amount is None
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert (
        "row_number() OVER (PARTITION BY client_tax_rule_sets.rule_set_id, "
        "client_tax_rule_sets.jurisdiction_code, client_tax_rule_sets.rule_code"
    ) in sql
    assert "client_tax_rule_sets.rule_status = 'active'" in sql


@pytest.mark.asyncio
async def test_inactive_filter_is_removed_only_when_requested() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([])
    await Reader(session).list_rules(
        portfolio_id="P1",
        client_id="C1",
        as_of_date=date(2026, 5, 3),
        mandate_id=None,
        include_inactive_rules=True,
    )
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "client_tax_rule_sets.rule_status = 'active'" not in sql
