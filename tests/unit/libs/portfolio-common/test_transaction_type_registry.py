from pathlib import Path

import pytest
from portfolio_common.transaction_type_registry import (
    INCOME_RECOGNITION_TRANSACTION_TYPES,
    MIGRATION_ONLY,
    TARGET_NOT_IMPLEMENTED,
    TARGET_NOT_IMPLEMENTED_TRANSACTION_TYPES,
    TRANSACTION_TYPE_CODES,
    TRANSACTION_TYPE_REGISTRY,
    get_transaction_type_definition,
    is_production_booking_transaction_type,
    is_registered_transaction_type,
    production_transaction_types_for_lifecycle_families,
    production_transaction_types_for_position_effects,
    require_registered_transaction_type,
)

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CASH_INFLOW_TRANSACTION_TYPES as COST_SORTCASH_INFLOW_TRANSACTION_TYPES,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CASH_OUTFLOW_TRANSACTION_TYPES as COST_SORTCASH_OUTFLOW_TRANSACTION_TYPES,
)
from src.services.portfolio_transaction_processing_service.app.domain.position.reducer import (
    CASH_POSITION_DELTA_TRANSACTION_TYPES,
    POSITION_TRANSFER_INFLOW_TRANSACTION_TYPES,
    POSITION_TRANSFER_TRANSACTION_TYPES,
    SAME_INSTRUMENT_CORPORATE_ACTION_TYPES,
    SAME_INSTRUMENT_QUANTITY_DECREASE_TYPES,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    GENERATED_CASH_LEG_TRANSACTION_TYPES,
    PORTFOLIO_LEVEL_CASH_FLOW_TRANSACTION_TYPES,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    FX_BUSINESS_TRANSACTION_TYPES,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    linkage as fx_linkage,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    TRANSFER_INFLOW_TRANSACTION_TYPES,
    TRANSFER_OUTFLOW_TRANSACTION_TYPES,
)
from src.services.query_service.app.services.position_flow_effects import (
    CASH_POSITION_DECREASE_TRANSACTION_TYPES,
    CASH_POSITION_INCREASE_TRANSACTION_TYPES,
    POSITION_DECREASE_TRANSACTION_TYPES,
    POSITION_INCREASE_TRANSACTION_TYPES,
)


def test_cost_domain_does_not_define_second_transaction_type_vocabulary() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    duplicate_vocabulary = (
        repository_root
        / "src/services/portfolio_transaction_processing_service/app/domain/cost_basis"
        / "transaction_type.py"
    )

    assert not duplicate_vocabulary.exists()


def test_registry_classifies_local_position_and_cashflow_rule_table_types() -> None:
    local_rule_table_types = (
        TRANSFER_INFLOW_TRANSACTION_TYPES
        | TRANSFER_OUTFLOW_TRANSACTION_TYPES
        | COST_SORTCASH_INFLOW_TRANSACTION_TYPES
        | COST_SORTCASH_OUTFLOW_TRANSACTION_TYPES
        | CASH_POSITION_DELTA_TRANSACTION_TYPES
        | POSITION_TRANSFER_TRANSACTION_TYPES
        | POSITION_TRANSFER_INFLOW_TRANSACTION_TYPES
        | GENERATED_CASH_LEG_TRANSACTION_TYPES
        | SAME_INSTRUMENT_CORPORATE_ACTION_TYPES
        | SAME_INSTRUMENT_QUANTITY_DECREASE_TYPES
        | POSITION_INCREASE_TRANSACTION_TYPES
        | POSITION_DECREASE_TRANSACTION_TYPES
        | CASH_POSITION_INCREASE_TRANSACTION_TYPES
        | CASH_POSITION_DECREASE_TRANSACTION_TYPES
    )

    assert local_rule_table_types <= TRANSACTION_TYPE_CODES


def test_position_transfer_inflow_rule_table_matches_registry_inflow_effects() -> None:
    inflow_lot_behaviors = {
        "preserve_or_restate_lot",
        "transfer_basis_in",
        "basis_allocation_in",
        "open_rights_lot",
        "open_lot",
    }
    registry_inflows = {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.lifecycle_family in {"transfer", "corporate_action", "rights"}
        and definition.position_effect == "increase"
        and definition.lot_behavior in inflow_lot_behaviors
    }

    assert POSITION_TRANSFER_INFLOW_TRANSACTION_TYPES == registry_inflows


def test_cashflow_transfer_sign_rule_tables_match_registry_effects() -> None:
    transfer_signing_families = {"transfer", "corporate_action", "rights"}
    fallback_signed_types = {"CASH_IN_LIEU"}
    registry_inflows = {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed
        and definition.lifecycle_family in transfer_signing_families
        and definition.position_effect == "increase"
        and code not in fallback_signed_types
    } | {"RIGHTS_REFUND"}
    registry_outflows = {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed
        and definition.lifecycle_family in transfer_signing_families
        and definition.position_effect == "decrease"
        and code not in fallback_signed_types
    }

    assert TRANSFER_INFLOW_TRANSACTION_TYPES == registry_inflows
    assert TRANSFER_OUTFLOW_TRANSACTION_TYPES == registry_outflows


def test_fx_business_transaction_types_are_registry_derived_once() -> None:
    registry_fx_business_types = {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed and definition.lifecycle_family == "fx"
    }

    assert FX_BUSINESS_TRANSACTION_TYPES == registry_fx_business_types
    assert FX_BUSINESS_TRANSACTION_TYPES == production_transaction_types_for_lifecycle_families(
        "fx"
    )
    assert fx_linkage.FX_BUSINESS_TRANSACTION_TYPES is FX_BUSINESS_TRANSACTION_TYPES


@pytest.mark.parametrize(
    "position_effect",
    ["increase", "decrease", "cash_increase", "cash_decrease"],
)
def test_position_effect_selector_returns_production_registry_codes(position_effect: str) -> None:
    expected = frozenset(
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed and definition.position_effect == position_effect
    )

    assert production_transaction_types_for_position_effects(position_effect) == expected


def test_position_effect_selector_normalizes_and_combines_effects() -> None:
    assert (
        production_transaction_types_for_position_effects(" INCREASE ", "cash_increase")
        == POSITION_INCREASE_TRANSACTION_TYPES | CASH_POSITION_INCREASE_TRANSACTION_TYPES
    )


def test_portfolio_flow_no_auto_generate_types_are_registry_derived() -> None:
    registry_portfolio_flow_types = {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed
        and definition.lifecycle_family in {"cash_movement", "expense", "transfer"}
    }

    assert PORTFOLIO_LEVEL_CASH_FLOW_TRANSACTION_TYPES == registry_portfolio_flow_types
    assert (
        PORTFOLIO_LEVEL_CASH_FLOW_TRANSACTION_TYPES
        == production_transaction_types_for_lifecycle_families(
            "cash_movement", "expense", "transfer"
        )
    )


def test_auto_generated_adjustment_cash_leg_types_are_registry_derived_and_implemented() -> None:
    registry_auto_generate_types = {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed
        and definition.lifecycle_family in {"trade", "income"}
        and definition.cash_effect in {"inflow", "outflow"}
        and definition.settlement_behavior == "requires_cash_leg"
    }

    assert GENERATED_CASH_LEG_TRANSACTION_TYPES == registry_auto_generate_types


def test_cost_sort_cash_dependency_sets_are_registry_compatible() -> None:
    assert COST_SORTCASH_INFLOW_TRANSACTION_TYPES <= {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed
        and (
            definition.position_effect in {"increase", "cash_increase"}
            or definition.cash_effect == "inflow"
        )
    }
    assert COST_SORTCASH_OUTFLOW_TRANSACTION_TYPES <= {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed
        and (
            definition.position_effect in {"decrease", "cash_decrease"}
            or definition.cash_effect == "outflow"
        )
    }
    assert COST_SORTCASH_INFLOW_TRANSACTION_TYPES & COST_SORTCASH_OUTFLOW_TRANSACTION_TYPES == set()


def test_other_is_registered_only_as_migration_type_not_production_booking() -> None:
    definition = require_registered_transaction_type("OTHER")

    assert definition.calculation_support_status == MIGRATION_ONLY
    assert not definition.production_booking_allowed
    assert not is_production_booking_transaction_type("OTHER")


def test_rfc_target_redemption_and_conversion_types_are_explicitly_not_implemented() -> None:
    expected_target_types = {
        "MATURITY_REDEMPTION",
        "CALL_REDEMPTION",
        "PARTIAL_REDEMPTION",
        "AMORTIZATION",
        "ACCRETION",
        "CONVERSION_EVENT",
        "CONVERSION_OUT",
        "CONVERSION_IN",
        "EXERCISE_OUT",
        "EXERCISE_IN",
        "STRIKE_PAYMENT",
    }

    assert expected_target_types == TARGET_NOT_IMPLEMENTED_TRANSACTION_TYPES
    for transaction_type in expected_target_types:
        definition = require_registered_transaction_type(transaction_type)
        assert definition.calculation_support_status == TARGET_NOT_IMPLEMENTED
        assert not definition.production_booking_allowed


def test_registry_definitions_are_normalized_and_complete() -> None:
    assert TRANSACTION_TYPE_REGISTRY
    for code, definition in TRANSACTION_TYPE_REGISTRY.items():
        assert code == code.upper()
        assert definition.code == code
        assert definition.lifecycle_family
        assert definition.economic_role
        assert definition.position_effect
        assert definition.cash_effect
        assert definition.lot_behavior
        assert definition.settlement_behavior
        assert definition.income_behavior
        assert definition.calculation_support_status


def test_registry_mapping_is_read_only() -> None:
    with pytest.raises(TypeError):
        TRANSACTION_TYPE_REGISTRY["NEW_TYPE"] = require_registered_transaction_type("BUY")


def test_income_recognition_types_are_explicit_and_exclude_cash_consideration() -> None:
    assert INCOME_RECOGNITION_TRANSACTION_TYPES == {"DIVIDEND", "INTEREST"}
    assert require_registered_transaction_type("DIVIDEND").income_behavior == (
        "distribution_income"
    )
    assert require_registered_transaction_type("INTEREST").income_behavior == "interest_income"
    assert require_registered_transaction_type("CASH_CONSIDERATION").income_behavior == "none"


def test_every_production_income_family_type_has_income_behavior() -> None:
    assert {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed and definition.lifecycle_family == "income"
    } == INCOME_RECOGNITION_TRANSACTION_TYPES


def test_registry_lookup_normalizes_codes_and_rejects_unknowns() -> None:
    assert is_registered_transaction_type(" buy ")
    assert get_transaction_type_definition(" buy ").code == "BUY"

    with pytest.raises(ValueError, match="Unknown transaction type: NOT_A_TYPE"):
        require_registered_transaction_type("not_a_type")
