from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ReportingCurrencySupportQuery:
    portfolio_id: str
    reporting_currency: str
    as_of_date: date
    tenant_id: str


@dataclass(frozen=True, slots=True)
class FxSupportEvidence:
    source_currency: str
    rate_date: date | None
    rate_available: bool


@dataclass(frozen=True, slots=True)
class ReportingCurrencySupportResult:
    portfolio_id: str
    tenant_id: str | None
    reporting_currency: str
    as_of_date: date
    status: str
    reason_code: str
    source_currencies: tuple[str, ...] = ()
    missing_source_currencies: tuple[str, ...] = ()
    fx_evidence: tuple[FxSupportEvidence, ...] = ()
    observed_selector_currency: bool | None = None
