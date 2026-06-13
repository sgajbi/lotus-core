"""
FILE: src/core/valuation.py
"""

from decimal import Decimal
from types import SimpleNamespace
from typing import Dict, List, Optional

from src.services.query_service.app.advisory_simulation.allocation_contract import (
    ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS,
)
from src.services.query_service.app.advisory_simulation.models import (
    AllocationMetric,
    EngineOptions,
    MarketDataSnapshot,
    Money,
    PortfolioSnapshot,
    Position,
    PositionSummary,
    ProposalAllocationView,
    ShelfEntry,
    SimulatedState,
    ValuationMode,
)
from src.services.query_service.app.advisory_simulation.precision_policy import to_decimal
from src.services.query_service.app.services.allocation_calculator import (
    AllocationInputRow,
    calculate_allocation_views,
)


def get_fx_rate(market_data: MarketDataSnapshot, from_ccy: str, to_ccy: str) -> Optional[Decimal]:
    """
    Returns the FX rate to convert from_ccy -> to_ccy.
    Returns 1.0 if currencies match.
    Returns None if rate is missing.
    """
    if from_ccy == to_ccy:
        return Decimal("1.0")

    pair = f"{from_ccy}/{to_ccy}"
    direct = next((r.rate for r in market_data.fx_rates if r.pair == pair), None)
    if direct:
        return to_decimal(direct)

    pair_inv = f"{to_ccy}/{from_ccy}"
    inverse = next((r.rate for r in market_data.fx_rates if r.pair == pair_inv), None)
    if inverse:
        return Decimal("1.0") / to_decimal(inverse)

    return None


class ValuationService:
    """
    Central authority for valuing positions and cash based on the configured mode.
    """

    @staticmethod
    def value_position(
        position: Position,
        market_data: MarketDataSnapshot,
        base_ccy: str,
        options: EngineOptions,
        dq_log: Dict[str, List[str]],
    ) -> PositionSummary:
        """
        Calculates position value based on options.valuation_mode.
        """
        price_ent = next(
            (p for p in market_data.prices if p.instrument_id == position.instrument_id), None
        )

        price_val = Decimal("0")
        currency = base_ccy

        if price_ent:
            price_val = price_ent.price
            currency = price_ent.currency

        mv_instr_ccy = Decimal("0")

        is_trust = options.valuation_mode == ValuationMode.TRUST_SNAPSHOT
        if is_trust and position.market_value:
            trusted_value = position.market_value
            price_currency = price_ent.currency if price_ent is not None else trusted_value.currency
            trust_is_base_authority = (
                trusted_value.currency == base_ccy and price_currency != base_ccy
            )
            if trust_is_base_authority:
                currency = price_currency
                mv_instr_ccy = (
                    position.quantity * price_val if price_ent is not None else Decimal("0")
                )
                mv_base = trusted_value.amount
            else:
                mv_instr_ccy = trusted_value.amount
                currency = trusted_value.currency
                rate = get_fx_rate(market_data, currency, base_ccy)
                if rate is None:
                    mv_base = Decimal("0")
                else:
                    mv_base = mv_instr_ccy * rate
        else:
            mv_instr_ccy = position.quantity * price_val
            rate = get_fx_rate(market_data, currency, base_ccy)
            if rate is None:
                mv_base = Decimal("0")
            else:
                mv_base = mv_instr_ccy * rate

        return PositionSummary(
            instrument_id=position.instrument_id,
            quantity=position.quantity,
            instrument_currency=currency,
            price=Money(amount=price_val, currency=currency) if price_ent else None,
            value_in_instrument_ccy=Money(amount=mv_instr_ccy, currency=currency),
            value_in_base_ccy=Money(amount=mv_base, currency=base_ccy),
            weight=Decimal("0"),
        )


def _shelf_by_instrument(shelf: List[ShelfEntry]) -> Dict[str, ShelfEntry]:
    return {entry.instrument_id: entry for entry in shelf}


def _priced_instrument_ids(market_data: MarketDataSnapshot) -> set[str]:
    return {price.instrument_id for price in market_data.prices}


def _record_missing_position_inputs(
    *,
    summary: PositionSummary,
    base_ccy: str,
    market_data: MarketDataSnapshot,
    dq_log: Dict[str, List[str]],
) -> None:
    if summary.instrument_currency == base_ccy:
        return
    rate = get_fx_rate(market_data, summary.instrument_currency, base_ccy)
    if rate is None:
        dq_log.setdefault("fx_missing", []).append(f"{summary.instrument_currency}/{base_ccy}")


def _cash_value_in_base(
    *,
    cash_balance: Money,
    base_ccy: str,
    market_data: MarketDataSnapshot,
    dq_log: Dict[str, List[str]] | None = None,
) -> Decimal:
    if cash_balance.currency == base_ccy:
        return cash_balance.amount
    rate = get_fx_rate(market_data, cash_balance.currency, base_ccy)
    if rate:
        return cash_balance.amount * rate
    if dq_log is not None:
        dq_log.setdefault("fx_missing", []).append(f"{cash_balance.currency}/{base_ccy}")
    return Decimal("0")


def _position_summaries(
    *,
    portfolio: PortfolioSnapshot,
    market_data: MarketDataSnapshot,
    base_ccy: str,
    options: EngineOptions,
    dq_log: Dict[str, List[str]],
) -> List[PositionSummary]:
    priced_ids = _priced_instrument_ids(market_data)
    summaries: List[PositionSummary] = []
    for position in portfolio.positions:
        if position.instrument_id not in priced_ids:
            dq_log.setdefault("price_missing", []).append(position.instrument_id)
        summary = ValuationService.value_position(position, market_data, base_ccy, options, dq_log)
        _record_missing_position_inputs(
            summary=summary,
            base_ccy=base_ccy,
            market_data=market_data,
            dq_log=dq_log,
        )
        summaries.append(summary)
    return summaries


def _total_base_value(
    *,
    position_summaries: List[PositionSummary],
    portfolio: PortfolioSnapshot,
    market_data: MarketDataSnapshot,
    base_ccy: str,
    dq_log: Dict[str, List[str]],
) -> Decimal:
    position_total = sum(
        (summary.value_in_base_ccy.amount for summary in position_summaries),
        Decimal("0"),
    )
    cash_total = sum(
        (
            _cash_value_in_base(
                cash_balance=cash_balance,
                base_ccy=base_ccy,
                market_data=market_data,
                dq_log=dq_log,
            )
            for cash_balance in portfolio.cash_balances
        ),
        Decimal("0"),
    )
    return position_total + cash_total


def _safe_total_value(total_value: Decimal) -> Decimal:
    if total_value == 0:
        return Decimal("1")
    return total_value


def _allocation_instrument_from_summary(
    summary: PositionSummary,
    shelf_entry: ShelfEntry | None,
) -> SimpleNamespace:
    attributes = shelf_entry.attributes if shelf_entry else {}
    return SimpleNamespace(
        asset_class=summary.asset_class,
        currency=summary.instrument_currency,
        sector=attributes.get("sector"),
        country_of_risk=attributes.get("country"),
        product_type=attributes.get("product_type"),
        rating=attributes.get("rating"),
        issuer_id=shelf_entry.issuer_id if shelf_entry else None,
        issuer_name=attributes.get("issuer_name"),
        ultimate_parent_issuer_id=attributes.get("ultimate_parent_issuer_id"),
        ultimate_parent_issuer_name=attributes.get("ultimate_parent_issuer_name"),
    )


def _cash_allocation_instrument(base_ccy: str) -> SimpleNamespace:
    return SimpleNamespace(
        asset_class="CASH",
        currency=base_ccy,
        sector=None,
        country_of_risk=None,
        product_type="Cash",
        rating=None,
        issuer_id=None,
        issuer_name=None,
        ultimate_parent_issuer_id=None,
        ultimate_parent_issuer_name=None,
    )


def _position_allocation_row(
    *,
    summary: PositionSummary,
    shelf_entry: ShelfEntry | None,
) -> AllocationInputRow:
    return AllocationInputRow(
        instrument=_allocation_instrument_from_summary(summary, shelf_entry),
        snapshot=SimpleNamespace(security_id=summary.instrument_id),
        market_value_reporting_currency=summary.value_in_base_ccy.amount,
    )


def _cash_allocation_row(
    *,
    cash_balance: Money,
    base_ccy: str,
    market_data: MarketDataSnapshot,
) -> AllocationInputRow:
    return AllocationInputRow(
        instrument=_cash_allocation_instrument(cash_balance.currency),
        snapshot=SimpleNamespace(security_id=f"CASH_{cash_balance.currency}"),
        market_value_reporting_currency=_cash_value_in_base(
            cash_balance=cash_balance,
            base_ccy=base_ccy,
            market_data=market_data,
        ),
    )


def _apply_position_allocation_metadata(
    *,
    summary: PositionSummary,
    shelf_entry: ShelfEntry | None,
    total_value: Decimal,
    allocation_attributes: Dict[str, Dict[str, Decimal]],
) -> None:
    summary.weight = summary.value_in_base_ccy.amount / total_value
    if shelf_entry is None:
        return

    summary.asset_class = shelf_entry.asset_class
    for attr_key, attr_val in shelf_entry.attributes.items():
        attribute_bucket = allocation_attributes.setdefault(attr_key, {})
        attribute_bucket[attr_val] = (
            attribute_bucket.get(attr_val, Decimal("0")) + summary.value_in_base_ccy.amount
        )


def _position_allocation_rows(
    *,
    position_summaries: List[PositionSummary],
    shelf_by_id: Dict[str, ShelfEntry],
    total_value: Decimal,
) -> tuple[List[AllocationInputRow], Dict[str, Dict[str, Decimal]]]:
    allocation_attributes: Dict[str, Dict[str, Decimal]] = {}
    allocation_rows: List[AllocationInputRow] = []
    for summary in position_summaries:
        shelf_entry = shelf_by_id.get(summary.instrument_id)
        _apply_position_allocation_metadata(
            summary=summary,
            shelf_entry=shelf_entry,
            total_value=total_value,
            allocation_attributes=allocation_attributes,
        )
        allocation_rows.append(_position_allocation_row(summary=summary, shelf_entry=shelf_entry))
    return allocation_rows, allocation_attributes


def _cash_allocation_rows(
    *,
    portfolio: PortfolioSnapshot,
    base_ccy: str,
    market_data: MarketDataSnapshot,
) -> List[AllocationInputRow]:
    return [
        _cash_allocation_row(
            cash_balance=cash_balance,
            base_ccy=base_ccy,
            market_data=market_data,
        )
        for cash_balance in portfolio.cash_balances
    ]


def _display_bucket_key(*, dimension: str, bucket_key: str) -> str:
    if dimension == "asset_class":
        if bucket_key == "CASH":
            return "Cash"
        return bucket_key.title()
    return bucket_key


def _asset_class_allocation_metrics(
    *,
    rows: List[AllocationInputRow],
    base_ccy: str,
) -> List[AllocationMetric]:
    allocation = calculate_allocation_views(rows=rows, dimensions=["asset_class"])
    if not allocation.views:
        return []
    return [
        AllocationMetric(
            key=bucket.dimension_value,
            weight=bucket.weight,
            value=Money(amount=bucket.market_value_reporting_currency, currency=base_ccy),
        )
        for bucket in allocation.views[0].buckets
    ]


def _proposal_allocation_views(
    *,
    rows: List[AllocationInputRow],
    base_ccy: str,
) -> List[ProposalAllocationView]:
    allocation = calculate_allocation_views(
        rows=rows,
        dimensions=list(ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS),
    )
    return [
        ProposalAllocationView.model_validate(
            {
                "dimension": view.dimension,
                "total_value": {
                    "amount": view.total_market_value_reporting_currency,
                    "currency": base_ccy,
                },
                "buckets": [
                    {
                        "key": _display_bucket_key(
                            dimension=view.dimension,
                            bucket_key=bucket.dimension_value,
                        ),
                        "weight": bucket.weight,
                        "value": {
                            "amount": bucket.market_value_reporting_currency,
                            "currency": base_ccy,
                        },
                        "position_count": bucket.position_count,
                    }
                    for bucket in view.buckets
                ],
            }
        )
        for view in allocation.views
    ]


def _instrument_allocation_metrics(
    position_summaries: List[PositionSummary],
) -> List[AllocationMetric]:
    return [
        AllocationMetric(
            key=summary.instrument_id, weight=summary.weight, value=summary.value_in_base_ccy
        )
        for summary in position_summaries
    ]


def _attribute_allocation_metrics(
    *,
    allocation_attributes: Dict[str, Dict[str, Decimal]],
    total_value: Decimal,
    base_ccy: str,
) -> Dict[str, List[AllocationMetric]]:
    return {
        attr_key: [
            AllocationMetric(
                key=attr_value,
                weight=attr_amount / total_value,
                value=Money(amount=attr_amount, currency=base_ccy),
            )
            for attr_value, attr_amount in value_map.items()
        ]
        for attr_key, value_map in allocation_attributes.items()
    }


def build_simulated_state(
    portfolio: PortfolioSnapshot,
    market_data: MarketDataSnapshot,
    shelf: List[ShelfEntry],
    dq_log: Dict[str, List[str]],
    warnings: List[str],
    options: Optional[EngineOptions] = None,
) -> SimulatedState:
    """
    Constructs a full valuation of the portfolio.
    """
    if options is None:
        options = EngineOptions()

    base_ccy = portfolio.base_currency
    pos_summaries = _position_summaries(
        portfolio=portfolio,
        market_data=market_data,
        base_ccy=base_ccy,
        options=options,
        dq_log=dq_log,
    )
    total_val = _total_base_value(
        position_summaries=pos_summaries,
        portfolio=portfolio,
        market_data=market_data,
        base_ccy=base_ccy,
        dq_log=dq_log,
    )
    total_val_safe = _safe_total_value(total_val)

    shelf_by_id = _shelf_by_instrument(shelf)
    allocation_rows, alloc_attr_map = _position_allocation_rows(
        position_summaries=pos_summaries,
        shelf_by_id=shelf_by_id,
        total_value=total_val_safe,
    )
    allocation_rows.extend(
        _cash_allocation_rows(
            portfolio=portfolio,
            base_ccy=base_ccy,
            market_data=market_data,
        )
    )

    alloc_instr = _instrument_allocation_metrics(pos_summaries)
    allocation_views = _proposal_allocation_views(rows=allocation_rows, base_ccy=base_ccy)
    alloc_asset_class = _asset_class_allocation_metrics(rows=allocation_rows, base_ccy=base_ccy)
    alloc_by_attr = _attribute_allocation_metrics(
        allocation_attributes=alloc_attr_map,
        total_value=total_val_safe,
        base_ccy=base_ccy,
    )

    return SimulatedState(
        total_value=Money(amount=total_val, currency=base_ccy),
        cash_balances=portfolio.cash_balances,
        positions=pos_summaries,
        allocation_by_asset_class=alloc_asset_class,
        allocation_by_instrument=alloc_instr,
        allocation=alloc_instr,
        allocation_by_attribute=alloc_by_attr,
        allocation_views=allocation_views,
    )
