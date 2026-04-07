from __future__ import annotations

import pytest

from src.services.query_service.app.advisory_simulation.allocation_contract import (
    ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS,
    ADVISORY_SIMULATION_ALLOCATION_LENS_CONTRACT_VERSION,
    ALLOCATION_DIMENSIONS_RESERVED_FOR_RISK_OR_DRILLDOWN,
    AllocationLensContract,
    advisory_proposal_allocation_lens_contract,
    validate_advisory_proposal_allocation_lens_contract,
)
from src.services.query_service.app.dtos.reporting_dto import AllocationDimension


def test_advisory_proposal_allocation_contract_classifies_every_live_dimension() -> None:
    contract = advisory_proposal_allocation_lens_contract()

    assert set(contract.proposal_dimensions).isdisjoint(contract.reserved_dimensions)
    assert set(contract.proposal_dimensions) | set(contract.reserved_dimensions) == set(
        contract.live_reporting_dimensions
    )


def test_advisory_proposal_allocation_contract_exposes_curated_front_office_subset() -> None:
    contract = advisory_proposal_allocation_lens_contract()

    assert contract.contract_version == ADVISORY_SIMULATION_ALLOCATION_LENS_CONTRACT_VERSION
    assert contract.proposal_dimensions == (
        "asset_class",
        "currency",
        "sector",
        "country",
        "region",
        "product_type",
        "rating",
    )


def test_advisory_proposal_allocation_contract_reserves_issuer_dimensions_for_risk() -> None:
    contract = advisory_proposal_allocation_lens_contract()

    assert contract.reserved_dimensions == (
        "issuer_id",
        "issuer_name",
        "ultimate_parent_issuer_id",
        "ultimate_parent_issuer_name",
    )


def test_advisory_proposal_allocation_contract_fails_when_reporting_dimensions_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drifted_contract = AllocationLensContract(
        contract_version=ADVISORY_SIMULATION_ALLOCATION_LENS_CONTRACT_VERSION,
        proposal_dimensions=ADVISORY_PROPOSAL_ALLOCATION_DIMENSIONS,
        reserved_dimensions=ALLOCATION_DIMENSIONS_RESERVED_FOR_RISK_OR_DRILLDOWN,
        live_reporting_dimensions=(
            *advisory_proposal_allocation_lens_contract().live_reporting_dimensions,
            "strategy",  # type: ignore[misc]
        ),
    )
    monkeypatch.setattr(
        "src.services.query_service.app.advisory_simulation.allocation_contract."
        "advisory_proposal_allocation_lens_contract",
        lambda: drifted_contract,
    )

    with pytest.raises(ValueError, match="missing=\\['strategy'\\]"):
        validate_advisory_proposal_allocation_lens_contract()


def test_advisory_proposal_allocation_contract_uses_live_reporting_literal() -> None:
    contract = advisory_proposal_allocation_lens_contract()

    # Type-level guard: the public contract stays aligned to the reporting DTO literal.
    _: tuple[AllocationDimension, ...] = contract.proposal_dimensions
    _: tuple[AllocationDimension, ...] = contract.reserved_dimensions
