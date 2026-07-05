from decimal import Decimal

import pytest

from src.services.query_service.app.dtos.core_snapshot_dto import (
    CoreSnapshotPositionRecord,
    CoreSnapshotSection,
)
from src.services.query_service.app.services.core_snapshot_errors import (
    CoreSnapshotUnavailableSectionError,
)
from src.services.query_service.app.services.core_snapshot_sections import (
    build_core_snapshot_sections,
)


def test_core_snapshot_sections_builds_baseline_totals_and_enrichment() -> None:
    baseline_positions = {
        "SEC_AAPL_US": _position_item(
            security_id="SEC_AAPL_US",
            quantity=Decimal("10"),
            market_value_base=Decimal("100"),
            weight=Decimal("1"),
        )
    }

    sections = build_core_snapshot_sections(
        requested_sections=[
            CoreSnapshotSection.PORTFOLIO_STATE,
            CoreSnapshotSection.POSITIONS_BASELINE,
            CoreSnapshotSection.PORTFOLIO_TOTALS,
            CoreSnapshotSection.INSTRUMENT_ENRICHMENT,
        ],
        baseline_positions=baseline_positions,
        projected_positions=None,
        baseline_total=Decimal("100"),
        projected_total=Decimal("0"),
    )

    assert sections.portfolio_state is not None
    assert sections.positions_baseline is not None
    assert sections.portfolio_state == sections.positions_baseline
    assert sections.portfolio_totals is not None
    assert sections.portfolio_totals.baseline_total_market_value_base == Decimal("100")
    assert sections.portfolio_totals.projected_total_market_value_base is None
    assert sections.portfolio_totals.delta_total_market_value_base is None
    assert sections.instrument_enrichment is not None
    assert sections.instrument_enrichment[0].security_id == "SEC_AAPL_US"
    assert sections.instrument_enrichment[0].issuer_id == "ISSUER_SEC_AAPL_US"
    assert sections.positions_projected is None
    assert sections.positions_delta is None


def test_core_snapshot_sections_builds_projected_delta_and_totals() -> None:
    baseline_positions = {
        "SEC_AAPL_US": _position_item(
            security_id="SEC_AAPL_US",
            quantity=Decimal("10"),
            market_value_base=Decimal("100"),
            weight=Decimal("1"),
        )
    }
    projected_positions = {
        "SEC_AAPL_US": _position_item(
            security_id="SEC_AAPL_US",
            quantity=Decimal("15"),
            market_value_base=Decimal("150"),
            weight=Decimal("0"),
        )
    }

    sections = build_core_snapshot_sections(
        requested_sections=[
            CoreSnapshotSection.POSITIONS_PROJECTED,
            CoreSnapshotSection.POSITIONS_DELTA,
            CoreSnapshotSection.PORTFOLIO_TOTALS,
        ],
        baseline_positions=baseline_positions,
        projected_positions=projected_positions,
        baseline_total=Decimal("100"),
        projected_total=Decimal("150"),
    )

    assert sections.positions_projected is not None
    assert sections.positions_projected[0].quantity == Decimal("15")
    assert sections.positions_projected[0].weight == Decimal("1")
    assert sections.positions_delta is not None
    assert sections.positions_delta[0].delta_quantity == Decimal("5")
    assert sections.positions_delta[0].delta_market_value_base == Decimal("50")
    assert sections.portfolio_totals is not None
    assert sections.portfolio_totals.projected_total_market_value_base == Decimal("150")
    assert sections.portfolio_totals.delta_total_market_value_base == Decimal("50")


@pytest.mark.parametrize(
    ("requested_section", "message"),
    [
        (CoreSnapshotSection.POSITIONS_PROJECTED, "positions_projected unavailable"),
        (CoreSnapshotSection.POSITIONS_DELTA, "positions_delta unavailable"),
    ],
)
def test_core_snapshot_sections_raise_when_projection_section_unavailable(
    requested_section: CoreSnapshotSection,
    message: str,
) -> None:
    with pytest.raises(CoreSnapshotUnavailableSectionError, match=message):
        build_core_snapshot_sections(
            requested_sections=[requested_section],
            baseline_positions={},
            projected_positions=None,
            baseline_total=Decimal("0"),
            projected_total=Decimal("0"),
        )


def _position_item(
    *,
    security_id: str,
    quantity: Decimal,
    market_value_base: Decimal,
    weight: Decimal,
) -> dict[str, object]:
    return {
        "security_id": security_id,
        "quantity": quantity,
        "market_value_base": market_value_base,
        "market_value_local": market_value_base,
        "currency": "USD",
        "position_record": CoreSnapshotPositionRecord(
            security_id=security_id,
            quantity=quantity,
            market_value_base=market_value_base,
            market_value_local=market_value_base,
            weight=weight,
            currency="USD",
        ),
        "isin": f"ISIN_{security_id}",
        "asset_class": "Equity",
        "sector": "Technology",
        "country_of_risk": "US",
        "instrument_name": f"Instrument {security_id}",
        "issuer_id": f"ISSUER_{security_id}",
        "issuer_name": f"Issuer {security_id}",
        "ultimate_parent_issuer_id": f"PARENT_{security_id}",
        "ultimate_parent_issuer_name": f"Parent {security_id}",
        "liquidity_tier": "L2",
    }
