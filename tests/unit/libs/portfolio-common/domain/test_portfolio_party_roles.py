from portfolio_common.domain.portfolio_party_roles import (
    PORTFOLIO_MANAGER_ROLE_TYPES,
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)


def test_portfolio_party_role_vocabulary_distinguishes_banking_capacities() -> None:
    assert {role.value for role in PortfolioPartyRoleType} == {
        "relationship_manager",
        "investment_advisor",
        "portfolio_manager",
        "discretionary_portfolio_manager",
        "assistant_rm",
        "service_officer",
        "external_asset_manager",
        "temporary_coverage_delegate",
    }


def test_portfolio_party_role_scope_vocabulary_is_responsibility_based() -> None:
    assert {scope.value for scope in PortfolioPartyRoleScope} == {
        "relationship_coverage",
        "investment_advice",
        "portfolio_management",
        "client_service",
    }


def test_portfolio_manager_roles_do_not_include_advisory_or_relationship_coverage() -> None:
    assert PORTFOLIO_MANAGER_ROLE_TYPES == {
        PortfolioPartyRoleType.PORTFOLIO_MANAGER,
        PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER,
    }
    assert PortfolioPartyRoleType.INVESTMENT_ADVISOR not in PORTFOLIO_MANAGER_ROLE_TYPES
    assert PortfolioPartyRoleType.RELATIONSHIP_MANAGER not in PORTFOLIO_MANAGER_ROLE_TYPES


def test_role_quality_status_has_explicit_non_accepted_states() -> None:
    assert {status.value for status in PortfolioPartyRoleQualityStatus} == {
        "accepted",
        "pending_review",
        "quarantined",
        "rejected",
    }
