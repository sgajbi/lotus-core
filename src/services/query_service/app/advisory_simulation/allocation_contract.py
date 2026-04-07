from __future__ import annotations

from dataclasses import dataclass
from typing import get_args

from src.services.query_service.app.dtos.reporting_dto import AllocationDimension

ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS: tuple[AllocationDimension, ...] = (
    "asset_class",
    "currency",
    "sector",
    "country",
    "region",
    "product_type",
    "rating",
)

ALLOCATION_DIMENSIONS_RESERVED_FOR_RISK_OR_DRILLDOWN: tuple[AllocationDimension, ...] = (
    "issuer_id",
    "issuer_name",
    "ultimate_parent_issuer_id",
    "ultimate_parent_issuer_name",
)

ADVISORY_SIMULATION_ALLOCATION_LENS_CONTRACT_VERSION = "advisory-simulation.v1"


@dataclass(frozen=True, slots=True)
class AllocationLensContract:
    contract_version: str
    proposal_dimensions: tuple[AllocationDimension, ...]
    reserved_dimensions: tuple[AllocationDimension, ...]
    live_reporting_dimensions: tuple[AllocationDimension, ...]


def live_reporting_allocation_dimensions() -> tuple[AllocationDimension, ...]:
    return get_args(AllocationDimension)


def advisory_proposal_allocation_lens_contract() -> AllocationLensContract:
    live_dimensions = live_reporting_allocation_dimensions()
    return AllocationLensContract(
        contract_version=ADVISORY_SIMULATION_ALLOCATION_LENS_CONTRACT_VERSION,
        proposal_dimensions=ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS,
        reserved_dimensions=ALLOCATION_DIMENSIONS_RESERVED_FOR_RISK_OR_DRILLDOWN,
        live_reporting_dimensions=live_dimensions,
    )


def validate_advisory_proposal_allocation_lens_contract() -> None:
    contract = advisory_proposal_allocation_lens_contract()
    classified_dimensions = set(contract.proposal_dimensions) | set(contract.reserved_dimensions)
    live_dimensions = set(contract.live_reporting_dimensions)
    if classified_dimensions != live_dimensions:
        missing = sorted(live_dimensions - classified_dimensions)
        extra = sorted(classified_dimensions - live_dimensions)
        raise ValueError(
            "Advisory proposal allocation lens contract is out of sync with live "
            f"reporting allocation dimensions. missing={missing}; extra={extra}"
        )
