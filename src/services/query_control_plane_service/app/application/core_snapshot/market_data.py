"""Resolve effective-dated market data required by snapshot valuation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, cast

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.decimal_amount import decimal_or_none

from ...ports.core_snapshot import CoreSnapshotSourceReader
from .errors import CoreSnapshotUnavailableSectionError


@dataclass(frozen=True, slots=True)
class MarketDataObservation:
    """One normalized price or FX observation used by snapshot valuation."""

    observation_type: Literal["MARKET_PRICE", "FX_RATE"]
    source_key: str
    value: Decimal
    effective_as_of_date: date
    currency: str | None = None
    evidence_timestamp: datetime | None = None

    def lineage_payload(self) -> dict[str, object]:
        return {
            "observation_type": self.observation_type,
            "source_key": self.source_key,
            "value": self.value,
            "effective_as_of_date": self.effective_as_of_date,
            "currency": self.currency,
        }


@dataclass(frozen=True, slots=True)
class ResolvedFxRate:
    """An FX value with the exact source date that made it authoritative."""

    value: Decimal
    effective_as_of_date: date | None
    from_currency: str
    to_currency: str
    evidence_timestamp: datetime | None = None

    def lineage_payload(self) -> dict[str, object]:
        return {
            "observation_type": "FX_RATE",
            "source_key": f"{self.from_currency}/{self.to_currency}",
            "value": self.value,
            "effective_as_of_date": self.effective_as_of_date,
            "evidence_type": (
                "SOURCE_OBSERVATION"
                if self.effective_as_of_date is not None
                else "CURRENCY_IDENTITY"
            ),
        }

    def observation(self) -> MarketDataObservation | None:
        if self.effective_as_of_date is None:
            return None
        return MarketDataObservation(
            observation_type="FX_RATE",
            source_key=f"{self.from_currency}/{self.to_currency}",
            value=self.value,
            effective_as_of_date=self.effective_as_of_date,
            evidence_timestamp=self.evidence_timestamp,
        )


async def get_fx_rate_or_raise(
    *,
    source_reader: CoreSnapshotSourceReader,
    from_currency: str,
    to_currency: str,
    as_of_date: date,
) -> ResolvedFxRate:
    normalized_from_currency = normalize_currency_code(from_currency)
    normalized_to_currency = normalize_currency_code(to_currency)
    if normalized_from_currency == normalized_to_currency:
        return ResolvedFxRate(
            value=Decimal(1),
            effective_as_of_date=None,
            from_currency=normalized_from_currency,
            to_currency=normalized_to_currency,
        )
    rates = await source_reader.get_fx_rates(
        from_currency=normalized_from_currency,
        to_currency=normalized_to_currency,
        start_date=date.min,
        end_date=as_of_date,
    )
    pair = f"{normalized_from_currency}/{normalized_to_currency}"
    message = f"missing FX rate {pair} on or before {as_of_date.isoformat()}"
    if not rates:
        raise CoreSnapshotUnavailableSectionError(message)
    latest_rate = rates[-1]
    return ResolvedFxRate(
        value=required_decimal(latest_rate.rate, message=message),
        effective_as_of_date=latest_rate.rate_date,
        from_currency=normalized_from_currency,
        to_currency=normalized_to_currency,
        evidence_timestamp=latest_rate.evidence_timestamp,
    )


def required_decimal(value: Any, *, message: str) -> Decimal:
    resolved_value = decimal_or_none(value)
    if resolved_value is None:
        raise CoreSnapshotUnavailableSectionError(message)
    return cast(Decimal, resolved_value)
