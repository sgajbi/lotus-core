from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..repositories.currency_codes import normalize_currency_code
from ..repositories.identifier_normalization import normalize_security_id
from .core_snapshot_errors import CoreSnapshotUnavailableSectionError
from .core_snapshot_market_data import get_fx_rate_or_raise, required_decimal
from .core_snapshot_projected_positions import (
    apply_baseline_projected_values,
    apply_projected_position_changes,
    baseline_projected_positions,
    filtered_projected_positions,
    missing_projected_security_ids,
    new_projected_position,
)


class CoreSnapshotProjectedPositionResolver:
    def __init__(
        self,
        *,
        simulation_repo: Any,
        instrument_repo: Any,
        price_repo: Any,
        fx_repo: Any,
    ) -> None:
        self._simulation_repo = simulation_repo
        self._instrument_repo = instrument_repo
        self._price_repo = price_repo
        self._fx_repo = fx_repo

    async def resolve_projected_positions(
        self,
        *,
        session_id: str,
        as_of_date: Any,
        portfolio_base_currency: str,
        portfolio_to_reporting_fx: Decimal,
        baseline_positions: dict[str, dict[str, Any]],
        include_zero: bool,
        include_cash: bool,
    ) -> dict[str, dict[str, Any]]:
        projected = baseline_projected_positions(baseline_positions)

        normalized_changes = await self._normalized_simulation_changes(session_id)
        await self._seed_missing_projected_instruments(projected, normalized_changes)
        apply_projected_position_changes(projected, normalized_changes)
        await self._value_projected_positions(
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

        return dict(sorted(filtered.items(), key=lambda item: item[0]))

    async def _normalized_simulation_changes(self, session_id: str) -> list[tuple[str, Any]]:
        changes = await self._simulation_repo.get_changes(session_id)
        return [self._normalized_simulation_change(change) for change in changes]

    @staticmethod
    def _normalized_simulation_change(change: Any) -> tuple[str, Any]:
        security_id = normalize_security_id(change.security_id)
        if not security_id:
            raise CoreSnapshotUnavailableSectionError(
                "positions_projected unavailable: simulation change missing security_id"
            )
        return security_id, change

    async def _seed_missing_projected_instruments(
        self,
        projected: dict[str, dict[str, Any]],
        normalized_changes: list[tuple[str, Any]],
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

    async def _projected_instrument_map(self, security_ids: list[str]) -> dict[str, Any]:
        instruments = await self._instrument_repo.get_by_security_ids(security_ids)
        return {
            security_id: item
            for item in instruments
            if (security_id := normalize_security_id(item.security_id))
        }

    @staticmethod
    def _required_projected_instrument(
        security_id: str,
        instrument_map: dict[str, Any],
    ) -> Any:
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
        as_of_date: Any,
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
            await self._apply_priced_projected_values(
                price_required=price_required,
                projected=projected,
                as_of_date=as_of_date,
                portfolio_base_currency=portfolio_base_currency,
                portfolio_to_reporting_fx=portfolio_to_reporting_fx,
            )

    async def _apply_priced_projected_values(
        self,
        *,
        price_required: dict[str, tuple[dict[str, Any], Decimal]],
        projected: dict[str, dict[str, Any]],
        as_of_date: Any,
        portfolio_base_currency: str,
        portfolio_to_reporting_fx: Decimal,
    ) -> None:
        priced_values = await self._priced_projected_local_values(
            price_required=price_required,
            as_of_date=as_of_date,
        )
        market_to_portfolio_fx = await self._market_to_portfolio_fx_rates(
            market_currencies={
                market_currency for _value, market_currency in priced_values.values()
            },
            portfolio_base_currency=portfolio_base_currency,
            as_of_date=as_of_date,
        )
        for security_id, (local_value, market_currency) in priced_values.items():
            entry = projected[security_id]
            portfolio_value = local_value * market_to_portfolio_fx[market_currency]
            entry["market_value_local"] = local_value
            entry["market_value_base"] = portfolio_value * portfolio_to_reporting_fx

    async def _priced_projected_local_values(
        self,
        *,
        price_required: dict[str, tuple[dict[str, Any], Decimal]],
        as_of_date: Any,
    ) -> dict[str, tuple[Decimal, str]]:
        priced_values: dict[str, tuple[Decimal, str]] = {}
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
        as_of_date: Any,
    ) -> tuple[Decimal, str]:
        prices = await self._price_repo.get_prices(security_id=security_id, end_date=as_of_date)
        if not prices:
            raise CoreSnapshotUnavailableSectionError(
                f"positions_projected unavailable: missing market price for {security_id}"
            )
        latest_price = prices[-1]
        missing_price_message = (
            f"positions_projected unavailable: missing market price for {security_id}"
        )
        local_value = (
            required_decimal(
                latest_price.price,
                message=missing_price_message,
            )
            * quantity
        )
        return local_value, normalize_currency_code(str(latest_price.currency))

    async def _market_to_portfolio_fx_rates(
        self,
        *,
        market_currencies: set[str],
        portfolio_base_currency: str,
        as_of_date: Any,
    ) -> dict[str, Decimal]:
        market_to_portfolio_fx = {}
        for market_currency in sorted(market_currencies):
            market_to_portfolio_fx[market_currency] = await get_fx_rate_or_raise(
                fx_repo=self._fx_repo,
                from_currency=market_currency,
                to_currency=portfolio_base_currency,
                as_of_date=as_of_date,
            )
        return market_to_portfolio_fx
