from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class PortfolioTaxLotReadRecord:
    portfolio_id: str
    security_id: str
    instrument_id: str
    lot_id: str
    open_quantity: Decimal
    original_quantity: Decimal
    acquisition_date: date
    lot_cost_base: Decimal
    lot_cost_local: Decimal
    source_transaction_id: str
    source_system: str | None
    calculation_policy_id: str | None
    calculation_policy_version: str | None
    local_currency: str | None
    updated_at: datetime | None
