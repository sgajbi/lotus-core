"""Resolve simulation-adjusted positions and effective-dated market values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.identifiers import normalize_lookup_identifier

from ...domain.core_snapshot import CoreSnapshotInstrument
from ...domain.simulation import SimulationChange
from ...ports.core_snapshot import CoreSnapshotSourceReader
from ...ports.simulation import SimulationStore
from .calculations import CORE_SNAPSHOT_INTERMEDIATE_PRECISION
from .errors import CoreSnapshotUnavailableSectionError
from .market_data import (
    MarketDataObservation,
    ResolvedFxRate,
    get_fx_rate_or_raise,
    required_decimal,
)
from .projected_positions import (
    apply_baseline_projected_values,
    apply_projected_position_changes,
    baseline_projected_positions,
    filtered_projected_positions,
    missing_projected_security_ids,
    new_projected_position,
)


@dataclass(frozen=True, slots=True)
class ProjectedPositionsResolution:
    positions: dict[str, dict[str, Any]]
    market_data_observations: tuple[MarketDataObservation, ...]


@dataclass(frozen=True, slots=True)
class _ResolvedProjectedValue:
    local_value: Decimal
    currency: str
    observation: MarketDataObservation


class CoreSnapshotProjectedPositionResolver:
    def __init__(
        self,
        *,
        simulation_store: SimulationStore,
        source_reader: CoreSnapshotSourceReader,
    ) -> None:
        self._simulation_store = simulation_store
        self._source_reader = source_reader

    async def resolve_projected_positions(
        self,
        *,
        session_id: str,
        as_of_date: date,
        portfolio_base_currency: str,
        portfolio_to_reporting_fx: Decimal,
        baseline_positions: dict[str, dict[str, Any]],
        include_zero: bool,
        include_cash: bool,
    ) -> ProjectedPositionsResolution:
        projected = baseline_projected_positions(baseline_positions)

        normalized_changes = await self._normalized_simulation_changes(session_id)
        await self._seed_missing_projected_instruments(projected, normalized_changes)
        apply_projected_position_changes(projected, normalized_changes)
        observations = await self._value_projected_positions(
            projected=projected,
            as_of_date=as_of_date,
            portfolio_base_currency=portfolio_base_currency,
            portfolio_to_reporting_fx=portfolio_to_reporting_fx,
            include_cash=include_cash,
            include_zero=include_zero,
        )
        filtered = filtered_projected_positions(
            projected,
            include_cash=include_cash,
            include_zero=include_zero,
        )

        return ProjectedPositionsResolution(
            positions=dict(sorted(filtered.items(), key=lambda item: item[0])),
            market_data_observations=tuple(
                sorted(
                    observations,
                    key=lambda item: (
                        item.observation_type,
                        item.source_key,
                        item.effective_as_of_date,
                    ),
                )
            ),
        )

    async def _normalized_simulation_changes(
        self, session_id: str
    ) -> list[tuple[str, SimulationChange]]:
        changes = await self._simulation_store.get_changes(session_id)
        return [self._normalized_simulation_change(change) for change in changes]

    @staticmethod
    def _normalized_simulation_change(
        change: SimulationChange,
    ) -> tuple[str, SimulationChange]:
        security_id = normalize_lookup_identifier(change.security_id)
        if not security_id:
            raise CoreSnapshotUnavailableSectionError(
                "positions_projected unavailable: simulation change missing security_id"
            )
        return security_id, change

    async def _seed_missing_projected_instruments(
        self,
        projected: dict[str, dict[str, Any]],
        normalized_changes: list[tuple[str, SimulationChange]],
    ) -> None:
        missing_security_ids = missing_projected_security_ids(projected, normalized_changes)
        if not missing_security_ids:
            return
        instrument_map = await self._projected_instrument_map(missing_security_ids)
        for security_id in missing_security_ids:
            projected[security_id] = new_projected_position(
                security_id,
                self._required_projected_instrument(security_id, instrument_map),
            )

    async def _projected_instrument_map(
        self, security_ids: list[str]
    ) -> dict[str, CoreSnapshotInstrument]:
        instruments = await self._source_reader.get_instruments(security_ids)
        return {
            security_id: item
            for item in instruments
            if (security_id := normalize_lookup_identifier(item.security_id))
        }

    @staticmethod
    def _required_projected_instrument(
        security_id: str,
        instrument_map: dict[str, CoreSnapshotInstrument],
    ) -> CoreSnapshotInstrument:
        instrument = instrument_map.get(security_id)
        if instrument is None:
            raise CoreSnapshotUnavailableSectionError(
                f"positions_projected unavailable: missing instrument {security_id}"
            )
        return instrument

    async def _value_projected_positions(
        self,
        *,
        projected: dict[str, dict[str, Any]],
        as_of_date: date,
        portfolio_base_currency: str,
        portfolio_to_reporting_fx: Decimal,
        include_cash: bool,
        include_zero: bool,
    ) -> None:
        price_required = apply_baseline_projected_values(
            projected,
            include_cash=include_cash,
            include_zero=include_zero,
        )
        if price_required:
            return await self._apply_priced_projected_values(
                price_required=price_required,
                projected=projected,
                as_of_date=as_of_date,
                portfolio_base_currency=portfolio_base_currency,
                portfolio_to_reporting_fx=portfolio_to_reporting_fx,
            )
        return ()

    async def _apply_priced_projected_values(
        self,
        *,
        price_required: dict[str, tuple[dict[str, Any], Decimal]],
        projected: dict[str, dict[str, Any]],
        as_of_date: date,
        portfolio_base_currency: str,
        portfolio_to_reporting_fx: Decimal,
    ) -> tuple[MarketDataObservation, ...]:
        priced_values = await self._priced_projected_local_values(
            price_required=price_required,
            as_of_date=as_of_date,
        )
        market_to_portfolio_fx = await self._market_to_portfolio_fx_rates(
            market_currencies={item.currency for item in priced_values.values()},
            portfolio_base_currency=portfolio_base_currency,
            as_of_date=as_of_date,
        )
        with localcontext() as context:
            context.prec = CORE_SNAPSHOT_INTERMEDIATE_PRECISION
            for security_id, priced_value in priced_values.items():
                entry = projected[security_id]
                market_fx = market_to_portfolio_fx[priced_value.currency]
                portfolio_value = priced_value.local_value * market_fx.value
                entry["market_value_local"] = priced_value.local_value
                entry["market_value_base"] = portfolio_value * portfolio_to_reporting_fx
        fx_observations = tuple(
            observation
            for rate in market_to_portfolio_fx.values()
            if (observation := rate.observation()) is not None
        )
        return tuple(item.observation for item in priced_values.values()) + fx_observations

    async def _priced_projected_local_values(
        self,
        *,
        price_required: dict[str, tuple[dict[str, Any], Decimal]],
        as_of_date: date,
    ) -> dict[str, _ResolvedProjectedValue]:
        priced_values: dict[str, _ResolvedProjectedValue] = {}
        for security_id, _entry_and_quantity in price_required.items():
            priced_values[security_id] = await self._priced_projected_local_value(
                security_id=security_id,
                quantity=price_required[security_id][1],
                as_of_date=as_of_date,
            )
        return priced_values

    async def _priced_projected_local_value(
        self,
        *,
        security_id: str,
        quantity: Decimal,
        as_of_date: date,
    ) -> _ResolvedProjectedValue:
        prices = await self._source_reader.get_prices(security_id=security_id, end_date=as_of_date)
        if not prices:
            raise CoreSnapshotUnavailableSectionError(
                f"positions_projected unavailable: missing market price for {security_id}"
            )
        latest_price = prices[-1]
        missing_price_message = (
            f"positions_projected unavailable: missing market price for {security_id}"
        )
        with localcontext() as context:
            context.prec = CORE_SNAPSHOT_INTERMEDIATE_PRECISION
            local_value = (
                required_decimal(
                    latest_price.price,
                    message=missing_price_message,
                )
                * quantity
            )
        price = required_decimal(latest_price.price, message=missing_price_message)
        currency = normalize_currency_code(str(latest_price.currency))
        return _ResolvedProjectedValue(
            local_value=local_value,
            currency=currency,
            observation=MarketDataObservation(
                observation_type="MARKET_PRICE",
                source_key=security_id,
                value=price,
                effective_as_of_date=latest_price.price_date,
                currency=currency,
            ),
        )

    async def _market_to_portfolio_fx_rates(
        self,
        *,
        market_currencies: set[str],
        portfolio_base_currency: str,
        as_of_date: date,
    ) -> dict[str, ResolvedFxRate]:
        market_to_portfolio_fx: dict[str, ResolvedFxRate] = {}
        for market_currency in sorted(market_currencies):
            market_to_portfolio_fx[market_currency] = await get_fx_rate_or_raise(
                source_reader=self._source_reader,
                from_currency=market_currency,
                to_currency=portfolio_base_currency,
                as_of_date=as_of_date,
            )
        return market_to_portfolio_fx
