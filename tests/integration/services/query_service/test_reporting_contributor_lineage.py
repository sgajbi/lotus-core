"""PostgreSQL proof for allocation look-through contributor source lineage."""

from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import Instrument, InstrumentLookthroughComponent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.query_service.app.repositories.reporting_repository import ReportingRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def lookthrough_lineage_records(clean_db, db_engine) -> dict[str, int]:  # noqa: ARG001
    with Session(db_engine) as session:
        session.add(
            Instrument(
                security_id="ALLOC_COMPONENT_1",
                name="Allocation Component",
                isin="XS0000000801",
                currency="USD",
                product_type="Bond",
                asset_class="Fixed Income",
                sector="Government",
                country_of_risk="US",
            )
        )
        active = InstrumentLookthroughComponent(
            parent_security_id=" ALLOC_PARENT_1 ",
            component_security_id=" ALLOC_COMPONENT_1 ",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            component_weight=Decimal("0.625"),
            source_system="fund-master",
            source_record_id="ALLOC-PARENT-1-COMPONENT-1",
        )
        expired = InstrumentLookthroughComponent(
            parent_security_id="ALLOC_PARENT_1",
            component_security_id="ALLOC_COMPONENT_OLD",
            effective_from=date(2025, 1, 1),
            effective_to=date(2025, 12, 31),
            component_weight=Decimal("0.375"),
            source_system="fund-master",
            source_record_id="ALLOC-PARENT-1-EXPIRED",
        )
        session.add_all([active, expired])
        session.flush()
        record_ids = {"active": int(active.id), "expired": int(expired.id)}
        session.commit()
        return record_ids


async def test_reporting_repository_preserves_exact_active_component_lineage(
    lookthrough_lineage_records: dict[str, int],
    async_db_session: AsyncSession,
) -> None:
    rows = await ReportingRepository(async_db_session).list_instrument_lookthrough_components(
        parent_security_ids=["ALLOC_PARENT_1"],
        as_of_date=date(2026, 3, 27),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.component_record_id == lookthrough_lineage_records["active"]
    assert row.parent_security_id == "ALLOC_PARENT_1"
    assert row.component_security_id == "ALLOC_COMPONENT_1"
    assert row.effective_from == date(2026, 1, 1)
    assert row.effective_to is None
    assert row.component_weight == Decimal("0.6250000000")
    assert row.source_system == "fund-master"
    assert row.source_record_id == "ALLOC-PARENT-1-COMPONENT-1"
    assert row.component_instrument is not None
    assert row.component_instrument.security_id == "ALLOC_COMPONENT_1"
    assert row.component_record_id != lookthrough_lineage_records["expired"]
