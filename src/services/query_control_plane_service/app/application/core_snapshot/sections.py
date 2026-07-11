"""Project internal position values into requested public snapshot sections."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ...contracts.core_snapshot import (
    CoreSnapshotInstrumentEnrichmentRecord,
    CoreSnapshotPortfolioTotals,
    CoreSnapshotSection,
    CoreSnapshotSections,
)
from .calculations import assign_projected_weights, build_delta_section
from .errors import CoreSnapshotUnavailableSectionError


def build_core_snapshot_sections(
    *,
    requested_sections: list[CoreSnapshotSection],
    baseline_positions: dict[str, dict[str, Any]],
    projected_positions: dict[str, dict[str, Any]] | None,
    baseline_total: Decimal,
    projected_total: Decimal,
) -> CoreSnapshotSections:
    sections_payload = CoreSnapshotSections()
    _populate_baseline_sections(
        sections_payload=sections_payload,
        requested_sections=requested_sections,
        baseline_positions=baseline_positions,
    )
    _populate_projected_positions_section(
        sections_payload=sections_payload,
        requested_sections=requested_sections,
        projected_positions=projected_positions,
        projected_total=projected_total,
    )
    _populate_delta_section(
        sections_payload=sections_payload,
        requested_sections=requested_sections,
        baseline_positions=baseline_positions,
        projected_positions=projected_positions,
        baseline_total=baseline_total,
        projected_total=projected_total,
    )
    _populate_portfolio_totals_section(
        sections_payload=sections_payload,
        requested_sections=requested_sections,
        baseline_total=baseline_total,
        projected_positions=projected_positions,
        projected_total=projected_total,
    )
    _populate_instrument_enrichment_section(
        sections_payload=sections_payload,
        requested_sections=requested_sections,
        baseline_positions=baseline_positions,
    )
    return sections_payload


def _populate_baseline_sections(
    *,
    sections_payload: CoreSnapshotSections,
    requested_sections: list[CoreSnapshotSection],
    baseline_positions: dict[str, dict[str, Any]],
) -> None:
    if CoreSnapshotSection.POSITIONS_BASELINE in requested_sections:
        sections_payload.positions_baseline = [
            item["position_record"] for item in baseline_positions.values()
        ]
    if CoreSnapshotSection.PORTFOLIO_STATE in requested_sections:
        sections_payload.portfolio_state = [
            item["position_record"] for item in baseline_positions.values()
        ]


def _populate_projected_positions_section(
    *,
    sections_payload: CoreSnapshotSections,
    requested_sections: list[CoreSnapshotSection],
    projected_positions: dict[str, dict[str, Any]] | None,
    projected_total: Decimal,
) -> None:
    if CoreSnapshotSection.POSITIONS_PROJECTED not in requested_sections:
        return
    if projected_positions is None:
        raise CoreSnapshotUnavailableSectionError("positions_projected unavailable")
    assign_projected_weights(projected_positions, projected_total)
    sections_payload.positions_projected = [
        item["position_record"] for item in projected_positions.values()
    ]


def _populate_delta_section(
    *,
    sections_payload: CoreSnapshotSections,
    requested_sections: list[CoreSnapshotSection],
    baseline_positions: dict[str, dict[str, Any]],
    projected_positions: dict[str, dict[str, Any]] | None,
    baseline_total: Decimal,
    projected_total: Decimal,
) -> None:
    if CoreSnapshotSection.POSITIONS_DELTA not in requested_sections:
        return
    if projected_positions is None:
        raise CoreSnapshotUnavailableSectionError("positions_delta unavailable")
    sections_payload.positions_delta = build_delta_section(
        baseline_positions=baseline_positions,
        projected_positions=projected_positions,
        baseline_total=baseline_total,
        projected_total=projected_total,
    )


def _populate_portfolio_totals_section(
    *,
    sections_payload: CoreSnapshotSections,
    requested_sections: list[CoreSnapshotSection],
    baseline_total: Decimal,
    projected_positions: dict[str, dict[str, Any]] | None,
    projected_total: Decimal,
) -> None:
    if CoreSnapshotSection.PORTFOLIO_TOTALS not in requested_sections:
        return
    sections_payload.portfolio_totals = CoreSnapshotPortfolioTotals(
        baseline_total_market_value_base=baseline_total,
        projected_total_market_value_base=(
            projected_total if projected_positions is not None else None
        ),
        delta_total_market_value_base=(
            projected_total - baseline_total if projected_positions is not None else None
        ),
    )


def _populate_instrument_enrichment_section(
    *,
    sections_payload: CoreSnapshotSections,
    requested_sections: list[CoreSnapshotSection],
    baseline_positions: dict[str, dict[str, Any]],
) -> None:
    if CoreSnapshotSection.INSTRUMENT_ENRICHMENT not in requested_sections:
        return
    sections_payload.instrument_enrichment = [
        _core_snapshot_instrument_enrichment(item) for item in baseline_positions.values()
    ]


def _core_snapshot_instrument_enrichment(
    item: dict[str, Any],
) -> CoreSnapshotInstrumentEnrichmentRecord:
    return CoreSnapshotInstrumentEnrichmentRecord(
        security_id=item["security_id"],
        isin=item["isin"],
        asset_class=item["asset_class"],
        sector=item["sector"],
        country_of_risk=item["country_of_risk"],
        instrument_name=item["instrument_name"],
        issuer_id=item["issuer_id"],
        issuer_name=item["issuer_name"],
        ultimate_parent_issuer_id=item["ultimate_parent_issuer_id"],
        ultimate_parent_issuer_name=item["ultimate_parent_issuer_name"],
        liquidity_tier=item["liquidity_tier"],
    )
