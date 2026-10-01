"""Predicates that prove a valuation snapshot consumed current source economics."""

from sqlalchemy import or_

from .database_models import DailyPositionSnapshot, MarketPrice


def snapshot_requires_price_revaluation():
    """Match a snapshot whose durable state does not prove current-price consumption."""

    return or_(
        DailyPositionSnapshot.id.is_(None),
        DailyPositionSnapshot.valuation_status != "VALUED_CURRENT",
        DailyPositionSnapshot.market_price.is_distinct_from(MarketPrice.price),
        DailyPositionSnapshot.valuation_source_currency.is_distinct_from(MarketPrice.currency),
        DailyPositionSnapshot.updated_at < MarketPrice.updated_at,
    )
