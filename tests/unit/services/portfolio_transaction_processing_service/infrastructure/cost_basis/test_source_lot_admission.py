"""Verify absent-only source-lot admission and fail-closed durable identity checks."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from portfolio_common.database_models import Portfolio, PositionLotState
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy.dialects import postgresql

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.lot_state_mapper import (  # noqa: E501
    buy_lot_state_payload,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.lot_state_repository import (  # noqa: E501
    SqlAlchemyCostBasisLotRepository,
    acquisition_lot_parent_insert_statement,
)


def _candidate(**changes: object) -> CostBasisTransaction:
    values = dict(
        transaction_id="BUY-PARENT",
        portfolio_id="PORT-PARENT",
        instrument_id="INST-PARENT",
        security_id="SEC-PARENT",
        transaction_type="BUY",
        transaction_date=datetime(2026, 4, 9, tzinfo=timezone.utc),
        quantity=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        net_cost=Decimal("1000"),
        net_cost_local=Decimal("1000"),
        tenant_id="TENANT-PARENT",
    )
    values.update(changes)
    return CostBasisTransaction(**values)


def _session(candidate: CostBasisTransaction, *, inserted: bool = True) -> AsyncMock:
    source = DBTransaction(
        **{
            field: getattr(candidate, field)
            for field in (
                "transaction_id",
                "portfolio_id",
                "security_id",
                "instrument_id",
                "transaction_type",
                "transaction_date",
                "quantity",
            )
        }
    )
    portfolio = Portfolio(portfolio_id=candidate.portfolio_id, tenant_id=candidate.tenant_id)
    source_result = Mock()
    source_result.one_or_none.return_value = (source, portfolio)
    insert_result = Mock()
    insert_result.scalar_one_or_none.return_value = (
        f"LOT-{candidate.transaction_id}" if inserted else None
    )
    session = AsyncMock()
    session.execute.side_effect = [source_result, insert_result]
    return session


def test_parent_insert_reuses_canonical_payload_without_conflict_update() -> None:
    candidate = _candidate()
    statement = acquisition_lot_parent_insert_statement(candidate)
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "ON CONFLICT DO NOTHING RETURNING" in str(compiled)
    assert "DO UPDATE" not in str(compiled)
    assert compiled.params == buy_lot_state_payload(candidate)


@pytest.mark.asyncio
async def test_missing_parent_validates_locked_durable_source_before_insert() -> None:
    candidate = _candidate()
    session = _session(candidate)
    await SqlAlchemyCostBasisLotRepository(session).ensure_acquisition_lot_parent(
        candidate, tenant_id="TENANT-PARENT"
    )
    assert session.execute.await_count == 2
    source_sql = str(
        session.execute.await_args_list[0].args[0].compile(dialect=postgresql.dialect())
    )
    assert "JOIN portfolios" in source_sql
    assert "FOR UPDATE OF transactions, portfolios" in source_sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("portfolio_id", "FOREIGN"),
        ("security_id", "FOREIGN"),
        ("instrument_id", "FOREIGN"),
        ("quantity", Decimal("11")),
        ("transaction_type", "TRANSFER_IN"),
        ("transaction_date", datetime(2026, 4, 8, tzinfo=timezone.utc)),
    ],
)
async def test_candidate_scope_or_source_identity_mismatch_refuses_before_insert(
    field, value
) -> None:
    session = _session(_candidate())
    with pytest.raises(ValueError, match="durable source scope"):
        await SqlAlchemyCostBasisLotRepository(session).ensure_acquisition_lot_parent(
            _candidate(**{field: value}), tenant_id="TENANT-PARENT"
        )
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_portfolio_tenant_mismatch_and_missing_source_refuse_before_insert() -> None:
    for source in (
        None,
        (
            DBTransaction(
                **{
                    field: getattr(_candidate(), field)
                    for field in (
                        "transaction_id",
                        "portfolio_id",
                        "security_id",
                        "instrument_id",
                        "transaction_type",
                        "transaction_date",
                        "quantity",
                    )
                }
            ),
            Portfolio(portfolio_id="PORT-PARENT", tenant_id="FOREIGN"),
        ),
    ):
        session = AsyncMock()
        result = Mock()
        result.one_or_none.return_value = source
        session.execute.return_value = result
        with pytest.raises(ValueError, match="durable source"):
            await SqlAlchemyCostBasisLotRepository(session).ensure_acquisition_lot_parent(
                _candidate(), tenant_id="TENANT-PARENT"
            )
        assert session.execute.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": "FOREIGN"},
        {"tenant_id": " "},
        {"transaction_type": "SELL"},
        {"quantity": Decimal("0")},
    ],
)
async def test_ineligible_parent_refuses_without_sql(changes) -> None:
    session = AsyncMock()
    with pytest.raises(ValueError, match="eligible tenant-scoped source"):
        await SqlAlchemyCostBasisLotRepository(session).ensure_acquisition_lot_parent(
            _candidate(**changes), tenant_id="TENANT-PARENT"
        )
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "conflicting_field",
    [
        None,
        "lot_id",
        "source_transaction_id",
        "portfolio_id",
        "security_id",
        "instrument_id",
        "acquisition_date",
    ],
)
async def test_existing_parent_is_identity_checked_without_refresh(conflicting_field) -> None:
    candidate = _candidate()
    existing = PositionLotState(**buy_lot_state_payload(candidate))
    existing.open_quantity = Decimal("4")
    existing.lot_cost_local = Decimal("400")
    existing.lot_cost_base = Decimal("400")
    if conflicting_field is not None:
        setattr(existing, conflicting_field, "FOREIGN")
    before = dict(existing.__dict__)
    session = _session(candidate, inserted=False)
    source_result, insert_result = list(session.execute.side_effect)
    lot_result = Mock()
    lot_result.scalars.return_value.all.return_value = [existing]
    session.execute.side_effect = [source_result, insert_result, lot_result]
    repository = SqlAlchemyCostBasisLotRepository(session)
    if conflicting_field is None:
        await repository.ensure_acquisition_lot_parent(candidate, tenant_id="TENANT-PARENT")
    else:
        with pytest.raises(ValueError, match="durable source identity"):
            await repository.ensure_acquisition_lot_parent(candidate, tenant_id="TENANT-PARENT")
    assert existing.__dict__ == before
    assert session.execute.await_count == 3
