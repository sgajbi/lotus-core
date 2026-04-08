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
        return Decimal(str(direct))

    pair_inv = f"{to_ccy}/{from_ccy}"
    inverse = next((r.rate for r in market_data.fx_rates if r.pair == pair_inv), None)
    if inverse:
        return Decimal("1.0") / Decimal(str(inverse))

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
    pos_summaries = []
    total_val = Decimal("0")

    for pos in portfolio.positions:
        has_price = any(p.instrument_id == pos.instrument_id for p in market_data.prices)
        if not has_price:
            dq_log.setdefault("price_missing", []).append(pos.instrument_id)

        summary = ValuationService.value_position(pos, market_data, base_ccy, options, dq_log)

        if summary.instrument_currency != base_ccy:
            rate = get_fx_rate(market_data, summary.instrument_currency, base_ccy)
            if rate is None:
                dq_log.setdefault("fx_missing", []).append(
                    f"{summary.instrument_currency}/{base_ccy}"
                )

        pos_summaries.append(summary)
        total_val += summary.value_in_base_ccy.amount

    for cash in portfolio.cash_balances:
        if cash.currency == base_ccy:
            total_val += cash.amount
        else:
            rate = get_fx_rate(market_data, cash.currency, base_ccy)
            if rate:
                total_val += cash.amount * rate
            else:
                dq_log.setdefault("fx_missing", []).append(f"{cash.currency}/{base_ccy}")

    if total_val == 0:
        total_val_safe = Decimal("1")
    else:
        total_val_safe = total_val

    # Aggregation containers
    alloc_attr_map: Dict[str, Dict[str, Decimal]] = {}
    allocation_rows: List[AllocationInputRow] = []
    shelf_by_id = _shelf_by_instrument(shelf)

    for p in pos_summaries:
        p.weight = p.value_in_base_ccy.amount / total_val_safe
        shelf_entry = shelf_by_id.get(p.instrument_id)

        if shelf_entry:
            p.asset_class = shelf_entry.asset_class
            # Attribute Aggregation
            for attr_key, attr_val in shelf_entry.attributes.items():
                if attr_key not in alloc_attr_map:
                    alloc_attr_map[attr_key] = {}
                alloc_attr_map[attr_key][attr_val] = (
                    alloc_attr_map[attr_key].get(attr_val, Decimal("0"))
                    + p.value_in_base_ccy.amount
                )

        allocation_rows.append(
            AllocationInputRow(
                instrument=_allocation_instrument_from_summary(p, shelf_entry),
                snapshot=SimpleNamespace(security_id=p.instrument_id),
                market_value_reporting_currency=p.value_in_base_ccy.amount,
            )
        )

    alloc_instr = [
        AllocationMetric(key=p.instrument_id, weight=p.weight, value=p.value_in_base_ccy)
        for p in pos_summaries
    ]

    for cash in portfolio.cash_balances:
        val = cash.amount
        if cash.currency != base_ccy:
            rate = get_fx_rate(market_data, cash.currency, base_ccy)
            if rate:
                val = cash.amount * rate
            else:
                val = Decimal("0")
        allocation_rows.append(
            AllocationInputRow(
                instrument=_cash_allocation_instrument(cash.currency),
                snapshot=SimpleNamespace(security_id=f"CASH_{cash.currency}"),
                market_value_reporting_currency=val,
            )
        )

    allocation_views = _proposal_allocation_views(rows=allocation_rows, base_ccy=base_ccy)
    alloc_asset_class = _asset_class_allocation_metrics(rows=allocation_rows, base_ccy=base_ccy)

    # Convert attribute map to model output
    alloc_by_attr = {}
    for attr_key, val_map in alloc_attr_map.items():
        metrics = []
        for val_key, val_amount in val_map.items():
            metrics.append(
                AllocationMetric(
                    key=val_key,
                    weight=val_amount / total_val_safe,
                    value=Money(amount=val_amount, currency=base_ccy),
                )
            )
        alloc_by_attr[attr_key] = metrics

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
