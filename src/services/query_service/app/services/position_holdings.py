from datetime import date, datetime
from decimal import Decimal
from typing import Any

from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, STALE, UNKNOWN

from ..dtos.position_dto import PortfolioPositionsResponse, Position
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..dtos.valuation_dto import ValuationData
from ..repositories.identifier_normalization import normalize_security_id
from .decimal_amounts import decimal_or_zero

HeldSinceRequest = tuple[int, str, int, date]


def should_fetch_fallback_valuation_map(
    *,
    db_results: list[tuple[Any, Any, Any]],
    history_supplements: list[tuple[Any, Any, Any]],
    snapshot_security_ids: set[str],
) -> bool:
    return bool(history_supplements or (db_results and not snapshot_security_ids))


def fallback_valuation_security_ids(
    history_supplements: list[tuple[Any, Any, Any]],
) -> list[str]:
    return sorted(
        {
            security_id
            for position_row, _instrument, _pos_state in history_supplements
            if (security_id := normalize_security_id(position_row.security_id))
        }
    )


def merge_snapshot_and_history_position_rows(
    *,
    snapshot_results: list[tuple[Any, Any, Any]],
    history_results: list[tuple[Any, Any, Any]],
) -> tuple[list[tuple[Any, Any, Any]], list[tuple[Any, Any, Any]], set[str]]:
    snapshot_results_by_security = {
        normalize_security_id(position_row.security_id): (position_row, instrument, pos_state)
        for position_row, instrument, pos_state in snapshot_results
    }
    merged_results = list(snapshot_results_by_security.values())
    history_supplements = [
        (position_row, instrument, pos_state)
        for position_row, instrument, pos_state in history_results
        if normalize_security_id(position_row.security_id) not in snapshot_results_by_security
    ]
    merged_results.extend(history_supplements)
    return merged_results, history_supplements, set(snapshot_results_by_security.keys())


def position_valuation_data(
    *,
    position_row: Any,
    is_snapshot_row: bool,
    fallback_valuation: dict[str, Any] | None,
) -> ValuationData:
    if is_snapshot_row:
        return ValuationData(
            market_price=position_row.market_price,
            market_value=position_row.market_value,
            unrealized_gain_loss=position_row.unrealized_gain_loss,
            market_value_local=position_row.market_value_local,
            unrealized_gain_loss_local=position_row.unrealized_gain_loss_local,
        )
    if fallback_valuation is not None:
        return ValuationData(
            market_price=fallback_valuation.get("market_price"),
            market_value=fallback_valuation.get("market_value"),
            unrealized_gain_loss=fallback_valuation.get("unrealized_gain_loss"),
            market_value_local=fallback_valuation.get("market_value_local"),
            unrealized_gain_loss_local=fallback_valuation.get("unrealized_gain_loss_local"),
        )
    # Maintain valuation continuity while snapshot backfill catches up.
    return ValuationData(
        market_price=None,
        market_value=position_row.cost_basis,
        unrealized_gain_loss=0,
        market_value_local=position_row.cost_basis_local,
        unrealized_gain_loss_local=0,
    )


def position_response_data(
    *,
    position_row: Any,
    instrument: Any,
    pos_state: Any,
    is_snapshot_row: bool,
    valuation: ValuationData,
) -> Position:
    return Position(
        security_id=normalize_security_id(position_row.security_id),
        quantity=position_row.quantity,
        cost_basis=position_row.cost_basis,
        cost_basis_local=position_row.cost_basis_local,
        instrument_name=instrument.name if instrument else "N/A",
        position_date=position_row.date if is_snapshot_row else position_row.position_date,
        asset_class=instrument.asset_class if instrument else None,
        isin=instrument.isin if instrument else None,
        currency=instrument.currency if instrument else None,
        sector=instrument.sector if instrument else None,
        country_of_risk=instrument.country_of_risk if instrument else None,
        product_type=instrument.product_type if instrument else None,
        rating=instrument.rating if instrument else None,
        liquidity_tier=instrument.liquidity_tier if instrument else None,
        valuation=valuation,
        reprocessing_status=pos_state.status if pos_state else None,
    )


def portfolio_position_rows_data(
    *,
    db_results: list[tuple[Any, Any, Any]],
    snapshot_security_ids: set[str],
    fallback_valuation_map: dict[str, dict[str, Any] | None],
) -> list[Position]:
    positions: list[Position] = []
    for position_row, instrument, pos_state in db_results:
        security_id = normalize_security_id(position_row.security_id)
        is_snapshot_row = security_id in snapshot_security_ids
        valuation = position_valuation_data(
            position_row=position_row,
            is_snapshot_row=is_snapshot_row,
            fallback_valuation=fallback_valuation_map.get(security_id),
        )
        positions.append(
            position_response_data(
                position_row=position_row,
                instrument=instrument,
                pos_state=pos_state,
                is_snapshot_row=is_snapshot_row,
                valuation=valuation,
            )
        )
    return positions


def position_weight_base_value(position: Position) -> Decimal:
    if position.valuation is not None and position.valuation.market_value is not None:
        return decimal_or_zero(position.valuation.market_value)
    return decimal_or_zero(position.cost_basis)


def assign_position_weights(positions: list[Position]) -> None:
    total_market_value = Decimal(0)
    position_values: list[Decimal] = []
    for position in positions:
        base_value = position_weight_base_value(position)
        position_values.append(base_value)
        total_market_value += base_value

    if total_market_value > 0:
        for position, value in zip(positions, position_values):
            position.weight = value / total_market_value
    else:
        for position in positions:
            position.weight = Decimal(0)


def position_held_since_requests(
    *,
    db_results: list[tuple[Any, Any, Any]],
    positions: list[Position],
) -> list[HeldSinceRequest]:
    held_since_requests: list[HeldSinceRequest] = []
    for idx, ((position_row, _instrument, pos_state), position) in enumerate(
        zip(db_results, positions)
    ):
        epoch = getattr(pos_state, "epoch", None)
        if epoch is None:
            position.held_since_date = position.position_date
            continue
        held_since_requests.append(
            (
                idx,
                normalize_security_id(position_row.security_id),
                int(epoch),
                position.position_date,
            )
        )
    return held_since_requests


def held_since_security_epoch_pairs(
    held_since_requests: list[HeldSinceRequest],
) -> list[tuple[str, int]]:
    return [(security_id, epoch) for _idx, security_id, epoch, _default_date in held_since_requests]


def apply_held_since_dates(
    *,
    positions: list[Position],
    held_since_requests: list[HeldSinceRequest],
    held_since_map: dict[tuple[str, int], date],
) -> None:
    for idx, security_id, epoch, default_date in held_since_requests:
        positions[idx].held_since_date = held_since_map.get((security_id, epoch), default_date)


def position_requires_market_price_freshness(position: Position) -> bool:
    return (
        (position.asset_class or "").strip().upper() != "CASH"
        and position.valuation is not None
        and position.valuation.market_price is not None
    )


def market_price_freshness_security_ids(positions: list[Position]) -> list[str]:
    return sorted(
        {
            security_id
            for position in positions
            if position_requires_market_price_freshness(position)
            if (security_id := normalize_security_id(position.security_id))
        }
    )


def holdings_data_quality_status(
    *,
    positions: list[Position],
    history_supplements: list[tuple[Any, Any, Any]],
    response_as_of_date: date,
    latest_market_price_dates: dict[str, date],
) -> str:
    if not positions:
        return UNKNOWN
    normalized_statuses = [
        (position.reprocessing_status or "").strip().upper() for position in positions
    ]
    if any(not status for status in normalized_statuses):
        return UNKNOWN
    if any(status != "CURRENT" for status in normalized_statuses):
        return STALE
    if any(
        (
            latest_market_price_dates.get(normalize_security_id(position.security_id))
            != response_as_of_date
            if position_requires_market_price_freshness(position)
            else False
        )
        for position in positions
    ):
        return STALE
    if history_supplements:
        return PARTIAL
    return COMPLETE


def latest_holdings_evidence_timestamp(
    db_results: list[tuple[Any, Any, Any]],
) -> datetime | None:
    timestamps: list[datetime] = []
    for position_row, _instrument, pos_state in db_results:
        for candidate in (
            getattr(position_row, "updated_at", None),
            getattr(position_row, "created_at", None),
            getattr(pos_state, "updated_at", None),
            getattr(pos_state, "created_at", None),
        ):
            if isinstance(candidate, datetime):
                timestamps.append(candidate)
    return max(timestamps) if timestamps else None


def holdings_response_as_of_date(
    *,
    effective_as_of_date: date | None,
    positions: list[Position],
    today: date | None = None,
) -> date:
    if effective_as_of_date is not None:
        return effective_as_of_date
    fallback_today = today or date.today()
    return max((position.position_date for position in positions), default=fallback_today)


def portfolio_positions_response_data(
    *,
    portfolio_id: str,
    positions: list[Position],
    response_as_of_date: date,
    data_quality_status: str,
    latest_evidence_timestamp: datetime | None,
) -> PortfolioPositionsResponse:
    return PortfolioPositionsResponse(
        portfolio_id=portfolio_id,
        positions=positions,
        **source_data_product_runtime_metadata(
            as_of_date=response_as_of_date,
            data_quality_status=data_quality_status,
            latest_evidence_timestamp=latest_evidence_timestamp,
        ),
    )
