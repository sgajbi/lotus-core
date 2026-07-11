"""Tests for persistence-independent DPM readiness evidence."""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.domain.dpm_source_readiness import (
    FxRateEvidence,
    PortfolioTaxLotEvidence,
)


def test_tax_lot_evidence_is_immutable_and_keeps_decimal_precision() -> None:
    evidence = PortfolioTaxLotEvidence(
        portfolio_id="portfolio-1",
        security_id="security-1",
        instrument_id="instrument-1",
        lot_id="lot-1",
        open_quantity=Decimal("100.0000000001"),
        original_quantity=Decimal("125.0000000001"),
        acquisition_date=date(2026, 4, 10),
        lot_cost_base=Decimal("1000.1234567890"),
        lot_cost_local=Decimal("900.1234567890"),
        source_transaction_id="transaction-1",
        source_system="position_lot_state",
        calculation_policy_id="average_cost",
        calculation_policy_version="v1",
        local_currency="SGD",
        updated_at=None,
    )

    assert evidence.open_quantity == Decimal("100.0000000001")
    with pytest.raises(FrozenInstanceError):
        evidence.lot_id = "changed"  # type: ignore[misc]


def test_fx_rate_evidence_uses_domain_currency_pair_language() -> None:
    evidence = FxRateEvidence(
        from_currency="USD",
        to_currency="SGD",
        rate_date=date(2026, 4, 10),
        rate=Decimal("1.3512345678"),
        created_at=None,
        updated_at=None,
    )

    assert (evidence.from_currency, evidence.to_currency) == ("USD", "SGD")
