"""Owning PostgreSQL reader proof: no synthetic source or read-side mutation."""

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import OutboxEvent, Portfolio, ProcessedEvent, Transaction
from portfolio_common.domain.tenant import TenantId
from portfolio_common.domain.transaction.payload_identity import (
    transaction_payload_pre_upstream_fingerprint,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.application.transaction_economics.performance_policy import (  # noqa: E501
    build_performance_component_economics_totals,
)
from src.services.query_control_plane_service.app.application.transaction_economics.performance_rows import (  # noqa: E501
    build_performance_component_economics_rows,
)
from src.services.query_control_plane_service.app.infrastructure.transaction_economics_sources import (  # noqa: E501
    SqlAlchemyTransactionEconomicsReader,
)
from tests.test_support.fx_source_evidence import TENANT, fx_source_fixture

pytestmark = pytest.mark.asyncio


def _portfolio() -> Portfolio:
    return Portfolio(
        portfolio_id="QCP-FX-PORT",
        tenant_id=TENANT.value,
        base_currency="USD",
        open_date=date(2026, 1, 1),
        risk_exposure="BALANCED",
        investment_time_horizon="LONG_TERM",
        portfolio_type="discretionary",
        booking_center_code="Singapore",
        client_id="QCP-FX-CLIENT",
        is_leverage_allowed=False,
        status="active",
    )


def _outbox(raw) -> OutboxEvent:
    return OutboxEvent(
        aggregate_type="RawTransaction",
        aggregate_id="QCP-FX-PORT",
        event_type="RawTransactionPersisted",
        topic="raw-transactions-persisted",
        payload=raw,
        status="PENDING",
    )


async def _read(session: AsyncSession, tenant: TenantId = TENANT):
    return await SqlAlchemyTransactionEconomicsReader(
        session
    ).list_performance_component_economics_evidence(
        portfolio_id="QCP-FX-PORT",
        tenant_id=tenant,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        as_of_date=date(2026, 4, 2),
        limit=10,
    )


async def _durable_snapshot(session: AsyncSession):
    ledger = (await session.execute(select(Transaction.__table__))).mappings().all()
    outbox = (await session.execute(select(OutboxEvent.__table__))).mappings().all()
    fences = (await session.execute(select(ProcessedEvent.__table__))).mappings().all()
    return deepcopy((ledger, outbox, fences))


@pytest.mark.parametrize(
    "case,local,base",
    [
        ("qualified_zero", Decimal("0"), Decimal("0")),
        ("qualified_positive", Decimal("12"), Decimal("12")),
        ("qualified_negative", Decimal("-12"), Decimal("-12")),
        ("missing_local", None, Decimal("12")),
        ("missing_base", Decimal("0"), None),
        ("missing_both", None, None),
        ("missing_raw", Decimal("0"), Decimal("0")),
        ("missing_receipt", Decimal("0"), Decimal("0")),
        ("tampered_receipt", Decimal("12"), Decimal("12")),
        ("foreign_raw", Decimal("12"), Decimal("12")),
        ("duplicate_raw", Decimal("0"), Decimal("0")),
        ("wrong_aggregate", Decimal("0"), Decimal("0")),
        ("tampered_raw", Decimal("0"), Decimal("0")),
        ("none_mode", Decimal("12"), Decimal("12")),
    ],
)
async def test_historical_fx_reader_qualifies_original_presence_without_mutation(
    clean_db, async_db_session: AsyncSession, case, local, base
):
    raw, _, ledger = fx_source_fixture(
        local, base, mode="NONE" if case == "none_mode" else "UPSTREAM_PROVIDED"
    )
    if local is None or base is None:
        ledger.payload_fingerprint = transaction_payload_pre_upstream_fingerprint(raw)
    if case == "missing_receipt":
        ledger.calculation_lineage = None
    if case == "tampered_receipt":
        ledger.calculation_lineage["output_content_hash"] = "f" * 64
    if case == "foreign_raw":
        raw["tenant_id"] = "FOREIGN"
    if case == "tampered_raw":
        raw["realized_fx_pnl_base"] = "12"
    source = _outbox(raw)
    if case == "wrong_aggregate":
        source.aggregate_id = "FOREIGN-PORT"
    async_db_session.add_all(
        [
            _portfolio(),
            ledger,
            ProcessedEvent(
                event_id="QCP-FX-RETAINED-FENCE",
                portfolio_id="QCP-FX-PORT",
                tenant_id=TENANT.value,
                service_name="persistence_service",
                payload_fingerprint=ledger.payload_fingerprint,
            ),
        ]
    )
    if case != "missing_raw":
        async_db_session.add(source)
    if case == "duplicate_raw":
        async_db_session.add(_outbox(raw))
    await async_db_session.commit()
    before = await _durable_snapshot(async_db_session)

    assert await _read(async_db_session, TenantId("FOREIGN")) == []
    first = build_performance_component_economics_rows(await _read(async_db_session))[0]
    assert first == build_performance_component_economics_rows(await _read(async_db_session))[0]
    async with AsyncSession(bind=async_db_session.bind, expire_on_commit=False) as reloaded:
        independent = build_performance_component_economics_rows(await _read(reloaded))[0]
        assert independent == first
        assert await _durable_snapshot(reloaded) == before
    assert await _durable_snapshot(async_db_session) == before
    assert await async_db_session.scalar(select(func.count()).select_from(ProcessedEvent)) == len(
        before[2]
    )
    if case.startswith("qualified_"):
        assert (first.realized_fx_pnl_local, first.realized_fx_pnl_base) == (local, base)
        assert first.fx_pnl_evidence_reason == "FX_SOURCE_QUALIFIED"
    elif case.startswith("missing_") and case in {"missing_local", "missing_base", "missing_both"}:
        assert (first.realized_fx_pnl_local, first.realized_fx_pnl_base) == (local, base)
        assert first.fx_pnl_evidence_reason == "FX_SOURCE_INCOMPLETE"
    elif case == "none_mode":
        assert (first.realized_fx_pnl_local, first.realized_fx_pnl_base) == (
            Decimal("0"),
            Decimal("0"),
        )
        assert first.fx_pnl_evidence_reason == "FX_SOURCE_NOT_APPLICABLE"
    else:
        assert first.realized_fx_pnl_local is None and first.realized_fx_pnl_base is None
        assert first.realized_total_pnl_local is None and first.realized_total_pnl_base is None


async def test_mixed_historical_fx_postgresql_total_withholds_incomplete_base(
    clean_db, async_db_session: AsyncSession
):
    raw, _, qualified = fx_source_fixture(Decimal("12"), Decimal("12"))
    _, _, unknown = fx_source_fixture(None, None)
    unknown.transaction_id = "QCP-FX-UNKNOWN"
    unknown.calculation_lineage = None
    async_db_session.add_all([_portfolio(), qualified, unknown, _outbox(raw)])
    await async_db_session.commit()
    before = await _durable_snapshot(async_db_session)
    rows = build_performance_component_economics_rows(await _read(async_db_session))
    totals = {
        item.component_family: item
        for item in build_performance_component_economics_totals(
            rows, portfolio_base_currency="USD"
        )
    }
    assert totals["realized_fx_pnl"].amount is None
    assert totals["realized_fx_pnl"].evidence_count == 1
    assert totals["realized_fx_pnl"].missing_evidence_count == 1
    assert totals["realized_total_pnl"].amount is None
    assert await _durable_snapshot(async_db_session) == before
