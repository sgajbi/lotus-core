"""Prove deterministic domain-owned event partition identities."""

import pytest
from portfolio_common.domain.eventing import (
    PartitionKeyScope,
    business_calendar_partition_key,
    currency_pair_partition_key,
    original_message_partition_key,
    portfolio_partition_key,
    portfolio_security_partition_key,
    security_partition_key,
)


def test_portfolio_key_preserves_existing_single_component_identity() -> None:
    key = portfolio_partition_key(" PB_SG_GLOBAL_BAL_001 ")

    assert key.scope is PartitionKeyScope.PORTFOLIO
    assert key.components == ("PB_SG_GLOBAL_BAL_001",)
    assert key.value == "PB_SG_GLOBAL_BAL_001"


def test_position_key_is_stable_across_dates_epochs_and_event_types() -> None:
    normal = portfolio_security_partition_key("PORT_001", "SEC_BOND_001")
    backdated = portfolio_security_partition_key("PORT_001", "SEC_BOND_001")
    correction = portfolio_security_partition_key("PORT_001", "SEC_BOND_001")

    assert normal.scope is PartitionKeyScope.PORTFOLIO_SECURITY
    assert normal.value == "PORT_001|SEC_BOND_001"
    assert {normal.value, backdated.value, correction.value} == {"PORT_001|SEC_BOND_001"}


def test_independent_positions_receive_independent_partition_identities() -> None:
    first = portfolio_security_partition_key("PORT_001", "SEC_A")
    second = portfolio_security_partition_key("PORT_001", "SEC_B")
    third = portfolio_security_partition_key("PORT_002", "SEC_A")

    assert len({first.value, second.value, third.value}) == 3


def test_tenant_is_included_when_source_owned_tenant_identity_is_available() -> None:
    key = portfolio_security_partition_key(
        "PORT_001",
        "SEC_A",
        tenant_id="TENANT_BANK_A",
        tenant_required=True,
    )

    assert key.tenant_id == "TENANT_BANK_A"
    assert key.value == "TENANT_BANK_A|PORT_001|SEC_A"


def test_required_tenant_identity_fails_closed_instead_of_using_a_fallback() -> None:
    with pytest.raises(
        ValueError,
        match="tenant_id is required for portfolio_security partition keys",
    ):
        portfolio_security_partition_key(
            "PORT_001",
            "SEC_A",
            tenant_required=True,
        )


@pytest.mark.parametrize(
    ("key", "expected_scope", "expected_value"),
    [
        (security_partition_key(" SEC_A "), PartitionKeyScope.SECURITY, "SEC_A"),
        (
            currency_pair_partition_key("usd", "sgd"),
            PartitionKeyScope.CURRENCY_PAIR,
            "USD|SGD",
        ),
        (
            business_calendar_partition_key("global"),
            PartitionKeyScope.BUSINESS_CALENDAR,
            "GLOBAL",
        ),
        (
            original_message_partition_key("PORT_001|SEC_A"),
            PartitionKeyScope.ORIGINAL_MESSAGE,
            "PORT_001|SEC_A",
        ),
    ],
)
def test_partition_key_families_are_deterministic(key, expected_scope, expected_value) -> None:
    assert key.scope is expected_scope
    assert key.value == expected_value


@pytest.mark.parametrize("invalid_value", ["", "   ", "PORT|SEC", "PORT\nSEC"])
def test_partition_key_components_reject_ambiguous_or_control_values(invalid_value: str) -> None:
    with pytest.raises(ValueError):
        portfolio_partition_key(invalid_value)
