from typing import Any

from ..DTOs.business_date_dto import BusinessDate
from ..DTOs.fx_rate_dto import FxRate
from ..DTOs.instrument_dto import Instrument
from ..DTOs.market_price_dto import MarketPrice
from ..DTOs.portfolio_dto import Portfolio
from ..DTOs.transaction_dto import Transaction

RawIngestionEventPayload = dict[str, Any]


def business_date_event_payload(business_date: BusinessDate) -> RawIngestionEventPayload:
    return business_date.model_dump()


def portfolio_event_payload(portfolio: Portfolio) -> RawIngestionEventPayload:
    return portfolio.model_dump()


def transaction_event_payload(transaction: Transaction) -> RawIngestionEventPayload:
    return transaction.model_dump()


def instrument_event_payload(instrument: Instrument) -> RawIngestionEventPayload:
    return instrument.model_dump()


def market_price_event_payload(price: MarketPrice) -> RawIngestionEventPayload:
    return price.model_dump()


def fx_rate_event_payload(rate: FxRate) -> RawIngestionEventPayload:
    return rate.model_dump()
