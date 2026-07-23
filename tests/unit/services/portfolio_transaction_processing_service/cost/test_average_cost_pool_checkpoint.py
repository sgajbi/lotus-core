from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AVERAGE_COST_POOL_STATE_VERSION,
    AverageCostPoolCheckpoint,
    AverageCostPoolTransition,
    OpenLotState,
)


def test_checkpoint_aggregates_source_states_and_uses_last_positive_source() -> None:
    checkpoint = AverageCostPoolCheckpoint.from_open_lot_states(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        states_by_source_transaction_id={
            "BUY-1": OpenLotState(
                quantity=Decimal("4"),
                cost_local=Decimal("40"),
                cost_base=Decimal("44"),
            ),
            "BUY-2": OpenLotState(
                quantity=Decimal(0),
                cost_local=Decimal(0),
                cost_base=Decimal(0),
            ),
            "BUY-3": OpenLotState(
                quantity=Decimal("6"),
                cost_local=Decimal("72"),
                cost_base=Decimal("78"),
            ),
        },
    )

    assert checkpoint.representative_source_transaction_id == "BUY-3"
    aggregate_state = checkpoint.as_open_lot_state()
    assert (
        aggregate_state.quantity,
        aggregate_state.cost_local,
        aggregate_state.cost_base,
    ) == (
        Decimal("10"),
        Decimal("112"),
        Decimal("122"),
    )
    assert checkpoint.state_version == AVERAGE_COST_POOL_STATE_VERSION


def test_checkpoint_allows_fully_closed_pool_without_representative_source() -> None:
    checkpoint = AverageCostPoolCheckpoint.from_open_lot_states(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        states_by_source_transaction_id={
            "BUY-1": OpenLotState(
                quantity=Decimal(0),
                cost_local=Decimal(0),
                cost_base=Decimal(0),
            )
        },
    )

    assert checkpoint.representative_source_transaction_id is None
    assert checkpoint.quantity == Decimal(0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity": Decimal("-1")},
        {"cost_local": Decimal("-1")},
        {"cost_base": Decimal("-1")},
        {"quantity": Decimal("1"), "representative_source_transaction_id": None},
        {"quantity": Decimal(0), "cost_local": Decimal("1")},
        {"quantity": Decimal(0), "cost_base": Decimal("1")},
    ],
)
def test_checkpoint_rejects_inconsistent_pool_state(overrides: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "representative_source_transaction_id": "BUY-1",
        "quantity": Decimal("1"),
        "cost_local": Decimal("10"),
        "cost_base": Decimal("11"),
    }
    payload.update(overrides)

    with pytest.raises(ValueError):
        AverageCostPoolCheckpoint(**payload)


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field_name", ["quantity", "cost_local", "cost_base"])
def test_checkpoint_rejects_non_finite_financial_values(
    field_name: str,
    value: str,
) -> None:
    payload: dict[str, object] = {
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "representative_source_transaction_id": "BUY-1",
        "quantity": Decimal("1"),
        "cost_local": Decimal("10"),
        "cost_base": Decimal("11"),
    }
    payload[field_name] = Decimal(value)

    with pytest.raises(ValueError, match="must be a finite Decimal"):
        AverageCostPoolCheckpoint(**payload)


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field_name", ["quantity", "cost_local", "cost_base"])
def test_transition_rejects_non_finite_open_lot_state(
    field_name: str,
    value: str,
) -> None:
    state_values = {
        "quantity": Decimal("1"),
        "cost_local": Decimal("10"),
        "cost_base": Decimal("11"),
    }
    state_values[field_name] = Decimal(value)

    with pytest.raises(ValueError, match="must be a finite Decimal"):
        AverageCostPoolTransition(
            before=_open_checkpoint(),
            existing_sources_after=OpenLotState(**state_values),
            explicit_sources_after={},
        )


def test_checkpoint_compatibility_requires_version_and_book_identity() -> None:
    checkpoint = AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-1",
        quantity=Decimal("1"),
        cost_local=Decimal("10"),
        cost_base=Decimal("11"),
    )

    assert checkpoint.is_compatible(portfolio_id="P1", instrument_id="I1", security_id="S1")
    assert not checkpoint.is_compatible(portfolio_id="P2", instrument_id="I1", security_id="S1")
    assert not checkpoint.is_compatible(portfolio_id="P1", instrument_id="I2", security_id="S1")
    assert not checkpoint.is_compatible(portfolio_id="P1", instrument_id="I1", security_id="S2")
    assert not AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-1",
        quantity=Decimal("1"),
        cost_local=Decimal("10"),
        cost_base=Decimal("11"),
        state_version="stale",
    ).is_compatible(portfolio_id="P1", instrument_id="I1", security_id="S1")


def _open_state(quantity: str, cost_local: str, cost_base: str) -> OpenLotState:
    return OpenLotState(
        quantity=Decimal(quantity),
        cost_local=Decimal(cost_local),
        cost_base=Decimal(cost_base),
    )


def _open_checkpoint() -> AverageCostPoolCheckpoint:
    return AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-2",
        quantity=Decimal("15"),
        cost_local=Decimal("180"),
        cost_base=Decimal("195"),
    )


def test_disposal_transition_preserves_existing_representative_and_reduces_pool() -> None:
    transition = AverageCostPoolTransition(
        before=_open_checkpoint(),
        existing_sources_after=_open_state("9", "108", "117"),
        explicit_sources_after={},
    )

    assert transition.after == AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-2",
        quantity=Decimal("9"),
        cost_local=Decimal("108"),
        cost_base=Decimal("117"),
    )


def test_opening_transition_adds_explicit_source_and_promotes_its_lineage() -> None:
    transition = AverageCostPoolTransition(
        before=_open_checkpoint(),
        existing_sources_after=_open_state("15", "180", "195"),
        explicit_sources_after={"BUY-3": _open_state("5", "70", "75")},
    )

    assert transition.after.representative_source_transaction_id == "BUY-3"
    assert transition.after.quantity == Decimal("20")
    assert transition.after.cost_local == Decimal("250")
    assert transition.after.cost_base == Decimal("270")


def test_full_close_transition_removes_representative_lineage() -> None:
    transition = AverageCostPoolTransition(
        before=_open_checkpoint(),
        existing_sources_after=_open_state("0", "0", "0"),
        explicit_sources_after={},
    )

    assert transition.after.representative_source_transaction_id is None
    assert transition.after.quantity == Decimal(0)


@pytest.mark.parametrize(
    ("existing_after", "explicit_after"),
    [
        (_open_state("16", "180", "195"), {}),
        (_open_state("15", "181", "195"), {}),
        (_open_state("15", "180", "196"), {}),
        (_open_state("0", "1", "0"), {}),
        (_open_state("15", "180", "195"), {" ": _open_state("1", "1", "1")}),
        (_open_state("15", "180", "195"), {"BUY-2": _open_state("1", "1", "1")}),
    ],
)
def test_transition_rejects_invalid_source_allocation(
    existing_after: OpenLotState,
    explicit_after: dict[str, OpenLotState],
) -> None:
    with pytest.raises(ValueError):
        AverageCostPoolTransition(
            before=_open_checkpoint(),
            existing_sources_after=existing_after,
            explicit_sources_after=explicit_after,
        )
