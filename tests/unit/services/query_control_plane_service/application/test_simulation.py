"""Test generic simulation behavior through application ports."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.query_control_plane_service.app.application.simulation import (
    CreateSimulationSessionCommand,
    SimulationChangeCommand,
    SimulationChangeNotFoundError,
    SimulationMutationInvalidError,
    SimulationPortfolioNotFoundError,
    SimulationService,
    SimulationSessionNotFoundError,
)
from src.services.query_control_plane_service.app.domain.simulation import (
    SimulationChange,
    SimulationInstrument,
    SimulationPositionBaseline,
    SimulationSession,
)
from src.services.query_control_plane_service.app.domain.simulation_effects import (
    transaction_quantity_effect,
)

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 7, 1, 8, 30, tzinfo=timezone.utc)


class _FixedClock:
    def utc_now(self) -> datetime:
        return NOW


class _SequenceIdGenerator:
    def __init__(self, *values: str) -> None:
        self._values = iter(values)

    def new_id(self) -> str:
        return next(self._values)

    def new_hex(self) -> str:
        return self.new_id()


def _session(*, status: str = "ACTIVE", version: int = 2, expires_at=None):
    return SimulationSession(
        session_id="S1",
        portfolio_id="P1",
        status=status,
        version=version,
        created_by="tester",
        created_at=NOW,
        expires_at=expires_at or NOW + timedelta(hours=4),
    )


def _change(
    *,
    security_id: str = "SEC_AAPL_US",
    transaction_type: str = "BUY",
    quantity: Decimal | None = Decimal("10"),
    amount: Decimal | None = None,
) -> SimulationChange:
    return SimulationChange(
        change_id="C1",
        session_id="S1",
        portfolio_id="P1",
        security_id=security_id,
        transaction_type=transaction_type,
        quantity=quantity,
        price=None,
        amount=amount,
        currency="USD",
        effective_date=date(2026, 7, 1),
        metadata={"source": "test"},
        created_at=NOW,
    )


def _baseline(
    *,
    security_id: str = "SEC_AAPL_US",
    quantity: Decimal = Decimal("100"),
    cost_basis: Decimal | None = Decimal("1000"),
    cost_basis_local: Decimal | None = Decimal("1000"),
) -> SimulationPositionBaseline:
    return SimulationPositionBaseline(
        security_id=security_id,
        position_date=date(2025, 9, 10),
        quantity=quantity,
        cost_basis=cost_basis,
        cost_basis_local=cost_basis_local,
        instrument_name="Apple",
        asset_class="Equity",
    )


@pytest.fixture
def dependencies():
    store = AsyncMock()
    baseline_reader = AsyncMock()
    unit_of_work = AsyncMock()
    store.get_session.return_value = _session()
    store.get_changes.return_value = [_change()]
    baseline_reader.portfolio_exists.return_value = True
    baseline_reader.get_current_positions.return_value = [_baseline()]
    baseline_reader.get_instruments.return_value = [
        SimulationInstrument(
            security_id="SEC_AAPL_US",
            name="Apple",
            asset_class="Equity",
        )
    ]
    return store, baseline_reader, unit_of_work


def _service(dependencies, *ids: str) -> SimulationService:
    store, baseline_reader, unit_of_work = dependencies
    return SimulationService(
        store=store,
        baseline_reader=baseline_reader,
        unit_of_work=unit_of_work,
        clock=_FixedClock(),
        id_generator=_SequenceIdGenerator(*(ids or ("ID-1", "ID-2"))),
    )


async def test_create_session_stages_and_returns_committed_state(dependencies):
    store, _, unit_of_work = dependencies
    service = _service(dependencies, "SIM-SESSION-1")

    result = await service.create_session(
        CreateSimulationSessionCommand(portfolio_id="P1", created_by="tester", ttl_hours=24)
    )

    store.stage_session.assert_awaited_once_with(
        session_id="SIM-SESSION-1",
        portfolio_id="P1",
        created_by="tester",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    unit_of_work.commit.assert_awaited_once()
    assert result.session.session_id == "S1"


async def test_create_session_rejects_unknown_portfolio(dependencies):
    store, baseline_reader, unit_of_work = dependencies
    baseline_reader.portfolio_exists.return_value = False

    with pytest.raises(SimulationPortfolioNotFoundError, match="Portfolio with id P404 not found"):
        await _service(dependencies).create_session(
            CreateSimulationSessionCommand(portfolio_id="P404", created_by=None, ttl_hours=24)
        )

    store.stage_session.assert_not_awaited()
    unit_of_work.commit.assert_not_awaited()


async def test_mutation_commit_failure_rolls_back(dependencies):
    _, _, unit_of_work = dependencies
    unit_of_work.commit.side_effect = RuntimeError("commit failed")

    with pytest.raises(RuntimeError, match="commit failed"):
        await _service(dependencies, "C2").add_changes(
            "S1",
            [
                SimulationChangeCommand(
                    security_id="SEC_MSFT_US",
                    transaction_type="BUY",
                    quantity=Decimal("2"),
                    price=None,
                    amount=None,
                    currency="USD",
                    effective_date=None,
                    metadata=None,
                )
            ],
        )

    unit_of_work.rollback.assert_awaited_once()


async def test_get_session_rejects_missing_session(dependencies):
    store, _, _ = dependencies
    store.get_session.return_value = None

    with pytest.raises(SimulationSessionNotFoundError, match="Simulation session S404 not found"):
        await _service(dependencies).get_session("S404")


async def test_get_session_returns_current_state(dependencies):
    result = await _service(dependencies).get_session("S1")
    assert result.session == _session()


async def test_close_session_increments_version(dependencies):
    store, _, unit_of_work = dependencies
    store.get_session.side_effect = [_session(version=3), _session(status="CLOSED", version=4)]

    result = await _service(dependencies).close_session("S1")

    store.stage_session_close.assert_awaited_once_with("S1", version=4)
    unit_of_work.commit.assert_awaited_once()
    assert result.session.status == "CLOSED"
    assert result.session.version == 4


async def test_add_changes_returns_versioned_records(dependencies):
    store, _, _ = dependencies
    store.get_session.side_effect = [_session(version=2), _session(version=3)]
    store.get_changes.return_value = [_change(security_id="SEC_MSFT_US")]

    result = await _service(dependencies, "C2").add_changes(
        "S1",
        [
            SimulationChangeCommand(
                security_id="SEC_MSFT_US",
                transaction_type="BUY",
                quantity=Decimal("5"),
                price=Decimal("100"),
                amount=None,
                currency="USD",
                effective_date=date(2026, 7, 1),
                metadata={"source": "unit"},
            )
        ],
    )

    assert result.version == 3
    assert result.changes[0].security_id == "SEC_MSFT_US"
    staged = store.stage_changes.await_args.kwargs
    assert staged["version"] == 3
    assert staged["changes"][0]["change_id"] == "C2"


@pytest.mark.parametrize(
    ("session", "message"),
    [
        (_session(status="CLOSED"), "is not active"),
        (_session(expires_at=NOW - timedelta(seconds=1)), "is expired"),
    ],
)
async def test_add_changes_rejects_inactive_or_expired_session(dependencies, session, message):
    store, _, _ = dependencies
    store.get_session.return_value = session

    with pytest.raises(SimulationMutationInvalidError, match=message):
        await _service(dependencies).add_changes("S1", [])


async def test_delete_change_returns_remaining_versioned_changes(dependencies):
    store, _, unit_of_work = dependencies
    store.get_session.side_effect = [_session(version=2), _session(version=3)]
    store.stage_change_delete.return_value = True
    store.get_changes.return_value = [_change(security_id="SEC_MSFT_US")]

    result = await _service(dependencies).delete_change("S1", "C1")

    store.stage_change_delete.assert_awaited_once_with("S1", "C1", version=3)
    unit_of_work.commit.assert_awaited_once()
    assert result.version == 3


async def test_delete_missing_change_rolls_back(dependencies):
    store, _, unit_of_work = dependencies
    store.stage_change_delete.return_value = False

    with pytest.raises(SimulationChangeNotFoundError, match="Simulation change C404 not found"):
        await _service(dependencies).delete_change("S1", "C404")

    unit_of_work.rollback.assert_awaited_once()
    unit_of_work.commit.assert_not_awaited()


async def test_projected_positions_apply_change_delta(dependencies):
    result = await _service(dependencies).get_projected_positions("S1")

    assert result.baseline_as_of == date(2025, 9, 10)
    assert result.positions[0].baseline_quantity == Decimal("100")
    assert result.positions[0].proposed_quantity == Decimal("110")
    assert result.positions[0].delta_quantity == Decimal("10")


async def test_projected_positions_preserve_missing_optional_costs(dependencies):
    _, baseline_reader, _ = dependencies
    baseline_reader.get_current_positions.return_value = [
        _baseline(cost_basis=None, cost_basis_local=None)
    ]

    result = await _service(dependencies).get_projected_positions("S1")

    assert result.positions[0].cost_basis is None
    assert result.positions[0].cost_basis_local is None


async def test_projected_positions_add_and_enrich_new_security(dependencies):
    store, baseline_reader, _ = dependencies
    store.get_changes.return_value = [_change(security_id=" SEC_MSFT_US ")]
    baseline_reader.get_instruments.return_value = [
        SimulationInstrument("SEC_MSFT_US", "Microsoft", "Equity"),
        SimulationInstrument("SEC_AAPL_US", "Apple", "Equity"),
    ]

    result = await _service(dependencies).get_projected_positions("S1")

    microsoft = next(row for row in result.positions if row.security_id == "SEC_MSFT_US")
    assert microsoft.instrument_name == "Microsoft"
    assert microsoft.baseline_quantity == 0
    assert microsoft.proposed_quantity == 10


async def test_projected_positions_filter_non_positive_results(dependencies):
    store, _, _ = dependencies
    store.get_changes.return_value = [_change(transaction_type="SELL", quantity=Decimal("100"))]

    result = await _service(dependencies).get_projected_positions("S1")

    assert result.positions == []


async def test_projected_summary_counts_baseline_and_delta(dependencies):
    result = await _service(dependencies).get_projected_summary("S1")

    assert result.total_baseline_positions == 1
    assert result.total_proposed_positions == 1
    assert result.net_delta_quantity == Decimal("10")


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "amount", "expected"),
    [
        ("BUY", "10", None, Decimal("10")),
        ("SELL", "10", None, Decimal("-10")),
        ("DEPOSIT", None, "25", Decimal("25")),
        ("WITHDRAWAL", None, "25", Decimal("-25")),
        ("DIVIDEND", "10", "25", Decimal("0")),
    ],
)
async def test_transaction_quantity_effect_rules(transaction_type, quantity, amount, expected):
    assert (
        transaction_quantity_effect(
            transaction_type=transaction_type,
            quantity=quantity,
            amount=amount,
        )
        == expected
    )
