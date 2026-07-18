"""Governed private-banking roles assigned to a portfolio."""

from __future__ import annotations

from enum import StrEnum


class PortfolioPartyRoleType(StrEnum):
    """Capacity in which a party serves a portfolio or its client relationship."""

    RELATIONSHIP_MANAGER = "relationship_manager"
    INVESTMENT_ADVISOR = "investment_advisor"
    PORTFOLIO_MANAGER = "portfolio_manager"
    DISCRETIONARY_PORTFOLIO_MANAGER = "discretionary_portfolio_manager"
    ASSISTANT_RM = "assistant_rm"
    SERVICE_OFFICER = "service_officer"
    EXTERNAL_ASSET_MANAGER = "external_asset_manager"
    TEMPORARY_COVERAGE_DELEGATE = "temporary_coverage_delegate"


class PortfolioPartyRoleScope(StrEnum):
    """Responsibility boundary covered by a portfolio party-role assignment."""

    RELATIONSHIP_COVERAGE = "relationship_coverage"
    INVESTMENT_ADVICE = "investment_advice"
    PORTFOLIO_MANAGEMENT = "portfolio_management"
    CLIENT_SERVICE = "client_service"


class PortfolioPartyRoleQualityStatus(StrEnum):
    """Data-quality disposition applied by the authoritative source pipeline."""

    ACCEPTED = "accepted"
    PENDING_REVIEW = "pending_review"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


PORTFOLIO_MANAGER_ROLE_TYPES = frozenset(
    {
        PortfolioPartyRoleType.PORTFOLIO_MANAGER,
        PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER,
    }
)
