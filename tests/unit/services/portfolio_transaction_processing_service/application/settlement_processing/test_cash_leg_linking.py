"""Application tests for settlement cash-leg validation, generation, and linking."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.infrastructure.persistence.transaction_identity_guard import (
    GeneratedTransactionIdentityCollisionError,
)

from src.services.portfolio_transaction_processing_service.app.application import (
    settlement_processing,
)
from src.services.portfolio_transaction_processing_service.app.application.errors import (
    FxRateNotFoundError,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    EffectiveFxRate,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
    build_generated_settlement_cash_leg,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisFxRatePort,
    SettlementTransactionLookupPort,
    SettlementTransactionPersistencePort,
)

pytestmark = pytest.mark.asyncio

link_settlement_cash_leg = settlement_processing.link_settlement_cash_leg


def _product_leg(**overrides: object) -> BookedTransaction:
    transaction = BookedTransaction(
        transaction_id="DIV-GENERATED-01",
        portfolio_id="PORT-001",
        instrument_id="FUND-001",
        security_id="FUND-001",
        transaction_date=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 3, 7, 12, 0, tzinfo=UTC),
        transaction_type="DIVIDEND",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("25"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-USD-001",
        settlement_cash_instrument_id="CASH-USD",
        economic_event_id="EVT-001",
        linked_transaction_group_id="GROUP-001",
    )
    return replace(transaction, **overrides)


def _persistence():
    persistence = AsyncMock(spec=SettlementTransactionPersistencePort)
    persistence.upsert_generated_booked_transaction.side_effect = lambda transaction: replace(
        transaction, epoch=None
    )
    return persistence


async def test_generated_cash_leg_is_persisted_before_linked_product_leg() -> None:
    product_leg = _product_leg()
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    persistence = _persistence()

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
    )

    assert result.product_leg.external_cash_transaction_id == "DIV-GENERATED-01-CASHLEG"
    assert result.generated_cash_leg is not None
    assert result.generated_cash_leg.transaction_id == "DIV-GENERATED-01-CASHLEG"
    assert result.generated_cash_leg.originating_transaction_id == product_leg.transaction_id
    assert result.product_leg.economic_event_id == result.generated_cash_leg.economic_event_id
    assert (
        result.product_leg.linked_transaction_group_id
        == result.generated_cash_leg.linked_transaction_group_id
    )
    assert product_leg.external_cash_transaction_id is None
    persistence.upsert_generated_booked_transaction.assert_awaited_once_with(
        result.generated_cash_leg
    )
    persistence.upsert_booked_transaction.assert_awaited_once_with(result.product_leg)
    lookup.get_booked_transaction.assert_not_awaited()


async def test_linking_carries_actual_stored_pnl_and_admitted_source_epoch():
    product = _product_leg(tenant_id="tenant-test", epoch=7)
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    persistence = _persistence()

    def canonical_result(proposed):
        assert proposed.realized_gain_loss is None
        assert proposed.realized_gain_loss_local is None
        return replace(
            proposed,
            epoch=None,
            realized_gain_loss=Decimal("0"),
            realized_gain_loss_local=Decimal("0"),
        )

    persistence.upsert_generated_booked_transaction.side_effect = canonical_result
    result = await link_settlement_cash_leg(
        product_leg=product,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
    )
    proposed = persistence.upsert_generated_booked_transaction.await_args.args[0]
    assert proposed.realized_gain_loss is None
    assert result.generated_cash_leg == replace(canonical_result(proposed), epoch=7)
    assert result.generated_cash_leg.calculation_lineage == proposed.calculation_lineage
    assert product.epoch == 7
    persistence.upsert_generated_booked_transaction.assert_awaited_once()
    persistence.upsert_booked_transaction.assert_awaited_once()
    lookup.get_booked_transaction.assert_not_awaited()


@pytest.mark.parametrize(
    "damage", ["missing", "key", "portfolio", "security", "tenant", "material", "effect", "lineage"]
)
async def test_linking_refuses_invalid_persisted_generated_authority(damage):
    product = _product_leg(tenant_id="tenant-test")
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    persistence = _persistence()

    def invalid_result(proposed):
        if damage == "missing":
            return None
        changes = {
            "key": {"transaction_id": "FOREIGN"},
            "portfolio": {"portfolio_id": "FOREIGN"},
            "security": {"security_id": "FOREIGN"},
            "tenant": {"tenant_id": "FOREIGN"},
            "material": {"gross_transaction_amount": Decimal("999")},
            "effect": {"net_cost_local": Decimal("999")},
            "lineage": {"calculation_lineage": None},
        }
        return replace(proposed, **changes[damage])

    persistence.upsert_generated_booked_transaction.side_effect = invalid_result
    with pytest.raises(ValueError, match="Generated cash persistence returned"):
        await link_settlement_cash_leg(
            product_leg=product,
            transaction_lookup=lookup,
            transaction_persistence=persistence,
        )
    persistence.upsert_generated_booked_transaction.assert_awaited_once()
    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_neutralization_refuses_changed_explicit_zero_pnl():
    original = _product_leg(
        transaction_id="REDEMPTION-CORRECTED-01",
        transaction_type="MATURITY_REDEMPTION",
        principal_proceeds_local=Decimal("100"),
        tenant_id="tenant-test",
    )
    prior_cash_leg = build_generated_settlement_cash_leg(original)
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = prior_cash_leg
    persistence = _persistence()
    persistence.upsert_generated_booked_transaction.side_effect = lambda transaction: replace(
        transaction, realized_gain_loss=Decimal("1")
    )
    with pytest.raises(ValueError, match="effects or lineage"):
        await link_settlement_cash_leg(
            product_leg=replace(
                original, embedded_tax_amount_local=Decimal("99"), trade_fee=Decimal("1")
            ),
            transaction_lookup=lookup,
            transaction_persistence=persistence,
            reconcile_superseded_derived=True,
        )
    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_missing_source_fx_uses_settlement_date_reference_rate() -> None:
    product_leg = _product_leg(
        trade_currency="XTS",
        currency="XTS",
        transaction_fx_rate=Decimal("2.0"),
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = None
    persistence = _persistence()
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.return_value = [
        EffectiveFxRate(effective_date=date(2026, 3, 7), rate=Decimal("2.5"))
    ]

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
        derive_fx_at_settlement=True,
        portfolio_base_currency="USD",
        fx_rates=fx_rates,
    )

    assert result.generated_cash_leg is not None
    assert result.generated_cash_leg.transaction_fx_rate == Decimal("2.5")
    assert result.generated_cash_leg.net_cost_local == Decimal("25")
    assert result.generated_cash_leg.net_cost == Decimal("62.5")
    fx_rates.get_fx_rate_window.assert_awaited_once_with(
        from_currency="XTS",
        to_currency="USD",
        start_date=date(2026, 3, 7),
        end_date=date(2026, 3, 7),
    )


async def test_missing_source_fx_replay_preserves_existing_generated_rate() -> None:
    product_leg = _product_leg(
        trade_currency="XTS",
        currency="XTS",
        transaction_fx_rate=Decimal("2.5"),
    )
    existing = build_generated_settlement_cash_leg(
        replace(product_leg, transaction_fx_rate=Decimal("2.25"))
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = existing
    persistence = _persistence()
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
        derive_fx_at_settlement=True,
        portfolio_base_currency="USD",
        fx_rates=fx_rates,
    )

    assert result.generated_cash_leg is not None
    assert result.generated_cash_leg.transaction_fx_rate == Decimal("2.25")
    fx_rates.get_fx_rate_window.assert_not_awaited()


async def test_rebuild_preserves_linked_generated_rate_without_transient_source_flag() -> None:
    product_leg = _product_leg(
        trade_currency="XTS",
        currency="XTS",
        transaction_fx_rate=Decimal("2.0"),
        external_cash_transaction_id="DIV-GENERATED-01-CASHLEG",
    )
    existing = build_generated_settlement_cash_leg(
        replace(product_leg, transaction_fx_rate=Decimal("2.5"))
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = existing
    persistence = _persistence()

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
    )

    assert result.generated_cash_leg is not None
    assert result.generated_cash_leg.transaction_fx_rate == Decimal("2.5")
    generated = persistence.upsert_generated_booked_transaction.await_args.args[0]
    assert generated.transaction_fx_rate == Decimal("2.5")


async def test_rebuild_fails_closed_when_linked_cross_currency_child_is_missing() -> None:
    product_leg = _product_leg(
        trade_currency="XTS",
        currency="XTS",
        transaction_fx_rate=Decimal("2.0"),
        external_cash_transaction_id="DIV-GENERATED-01-CASHLEG",
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = None
    persistence = _persistence()

    with pytest.raises(FxRateNotFoundError, match="Booked generated settlement FX"):
        await link_settlement_cash_leg(
            product_leg=product_leg,
            transaction_lookup=lookup,
            transaction_persistence=persistence,
            portfolio_base_currency="USD",
        )

    persistence.upsert_generated_booked_transaction.assert_not_awaited()
    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_rebuild_recovers_missing_same_currency_child_with_explicit_instrument() -> None:
    product_leg = _product_leg(
        trade_currency="USD",
        currency="USD",
        transaction_fx_rate=Decimal("1.0"),
        external_cash_transaction_id="DIV-GENERATED-01-CASHLEG",
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = None
    persistence = _persistence()

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
        portfolio_base_currency="USD",
    )

    assert result.generated_cash_leg is not None
    assert result.generated_cash_leg.transaction_fx_rate == Decimal(1)


async def test_rebuild_fails_closed_without_mapped_security_or_linked_child() -> None:
    product_leg = replace(
        _product_leg(
            trade_currency="USD",
            currency="USD",
            transaction_fx_rate=Decimal("1.0"),
            external_cash_transaction_id="DIV-GENERATED-01-CASHLEG",
        ),
        settlement_cash_account_id="ACCOUNT-USD-01",
        settlement_cash_instrument_id=None,
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = None
    persistence = _persistence()

    with pytest.raises(FxRateNotFoundError, match="Booked generated settlement FX"):
        await link_settlement_cash_leg(
            product_leg=product_leg,
            transaction_lookup=lookup,
            transaction_persistence=persistence,
            portfolio_base_currency="USD",
        )

    persistence.upsert_generated_booked_transaction.assert_not_awaited()


async def test_authorized_correction_rederives_missing_source_fx_at_settlement() -> None:
    product_leg = _product_leg(
        trade_currency="XTS",
        currency="XTS",
        transaction_fx_rate=Decimal("2.5"),
    )
    existing = build_generated_settlement_cash_leg(
        replace(product_leg, transaction_fx_rate=Decimal("2.25"))
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = existing
    persistence = _persistence()
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.return_value = [
        EffectiveFxRate(effective_date=date(2026, 3, 7), rate=Decimal("2.75"))
    ]

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
        reconcile_superseded_derived=True,
        derive_fx_at_settlement=True,
        portfolio_base_currency="USD",
        fx_rates=fx_rates,
    )

    assert result.generated_cash_leg is not None
    assert result.generated_cash_leg.transaction_fx_rate == Decimal("2.75")


async def test_missing_settlement_fx_fails_before_generated_cash_persistence() -> None:
    product_leg = _product_leg(
        trade_currency="XTS",
        currency="XTS",
        transaction_fx_rate=Decimal("2.0"),
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = None
    persistence = _persistence()
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)
    fx_rates.get_fx_rate_window.return_value = []

    with pytest.raises(FxRateNotFoundError, match="XTS->USD on 2026-03-07"):
        await link_settlement_cash_leg(
            product_leg=product_leg,
            transaction_lookup=lookup,
            transaction_persistence=persistence,
            derive_fx_at_settlement=True,
            portfolio_base_currency="USD",
            fx_rates=fx_rates,
        )

    persistence.upsert_generated_booked_transaction.assert_not_awaited()
    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_same_currency_missing_source_fx_derives_one_without_reference_lookup() -> None:
    product_leg = _product_leg(
        trade_currency="USD",
        currency="USD",
        transaction_fx_rate=None,
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = None
    persistence = _persistence()
    fx_rates = AsyncMock(spec=CostBasisFxRatePort)

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
        derive_fx_at_settlement=True,
        portfolio_base_currency="USD",
        fx_rates=fx_rates,
    )

    assert result.generated_cash_leg is not None
    assert result.generated_cash_leg.transaction_fx_rate == Decimal(1)
    assert result.generated_cash_leg.net_cost == Decimal("25")
    fx_rates.get_fx_rate_window.assert_not_awaited()


async def test_generated_cash_collision_prevents_product_leg_mutation() -> None:
    product_leg = _product_leg()
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    persistence = _persistence()
    persistence.upsert_generated_booked_transaction.side_effect = (
        GeneratedTransactionIdentityCollisionError("DIV-GENERATED-01-CASHLEG")
    )

    with pytest.raises(
        GeneratedTransactionIdentityCollisionError,
        match="generated_transaction_identity_collision",
    ):
        await link_settlement_cash_leg(
            product_leg=product_leg,
            transaction_lookup=lookup,
            transaction_persistence=persistence,
        )

    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_generated_linkage_identity_is_persisted_on_both_legs() -> None:
    product_leg = _product_leg(
        economic_event_id=None,
        linked_transaction_group_id=None,
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    persistence = _persistence()

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
    )

    assert result.generated_cash_leg is not None
    assert result.product_leg.economic_event_id == ("EVT-DIVIDEND-PORT-001-DIV-GENERATED-01")
    assert result.product_leg.linked_transaction_group_id == (
        "LTG-DIVIDEND-PORT-001-DIV-GENERATED-01"
    )
    assert result.product_leg.economic_event_id == result.generated_cash_leg.economic_event_id
    assert (
        result.product_leg.linked_transaction_group_id
        == result.generated_cash_leg.linked_transaction_group_id
    )


async def test_upstream_provided_product_leg_is_validated_without_generated_writes() -> None:
    cash_leg = _product_leg(
        transaction_id="CASH-001",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_type="ADJUSTMENT",
        cash_entry_mode=None,
        external_cash_transaction_id=None,
    )
    product_leg = _product_leg(
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id=cash_leg.transaction_id,
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = cash_leg
    persistence = _persistence()

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
    )

    assert result.product_leg is product_leg
    assert result.generated_cash_leg is None
    lookup.get_booked_transaction.assert_awaited_once_with(
        cash_leg.transaction_id,
        portfolio_id=product_leg.portfolio_id,
    )
    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_non_cash_linking_transaction_remains_unchanged() -> None:
    product_leg = _product_leg(cash_entry_mode=None)
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    persistence = _persistence()

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
    )

    assert result.product_leg is product_leg
    assert result.generated_cash_leg is None
    lookup.get_booked_transaction.assert_not_awaited()
    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_correction_neutralizes_obsolete_generated_cash_leg() -> None:
    original = _product_leg(
        transaction_id="REDEMPTION-CORRECTED-01",
        transaction_type="MATURITY_REDEMPTION",
        principal_proceeds_local=Decimal("100"),
    )
    prior_cash_leg = build_generated_settlement_cash_leg(original)
    corrected = replace(
        original,
        embedded_tax_amount_local=Decimal("99"),
        trade_fee=Decimal("1"),
        external_cash_transaction_id=prior_cash_leg.transaction_id,
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = prior_cash_leg
    persistence = _persistence()

    result = await link_settlement_cash_leg(
        product_leg=corrected,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
        reconcile_superseded_derived=True,
    )

    assert result.product_leg.external_cash_transaction_id is None
    assert result.generated_cash_leg is not None
    assert result.generated_cash_leg.transaction_id == prior_cash_leg.transaction_id
    assert result.generated_cash_leg.gross_transaction_amount == Decimal(0)
    assert result.generated_cash_leg.gross_cost == Decimal(0)
    assert result.generated_cash_leg.net_cost == Decimal(0)
    assert result.generated_cash_leg.net_cost_local == Decimal(0)
    assert result.generated_cash_leg.realized_gain_loss == Decimal(0)
    assert result.generated_cash_leg.realized_gain_loss_local == Decimal(0)
    assert result.generated_cash_leg.transaction_fx_rate == prior_cash_leg.transaction_fx_rate
    assert result.generated_cash_leg.transaction_fx_rate_origin == (
        prior_cash_leg.transaction_fx_rate_origin
    )
    assert result.generated_cash_leg.calculation_lineage is not None
    assert (
        result.generated_cash_leg.calculation_lineage.algorithm_id
        == "generated-settlement-cash-neutralization"
    )
    assert result.generated_cash_leg.calculation_lineage.numeric_output_policy is not None
    assert (
        result.generated_cash_leg.calculation_lineage.numeric_output_policy.policy_id
        == "transaction-cost-ledger-output@1.0.0"
    )
    alternate_correction = replace(
        corrected,
        embedded_tax_amount_local=Decimal("98"),
        trade_fee=Decimal("2"),
    )
    alternate_lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    alternate_lookup.get_booked_transaction.return_value = prior_cash_leg
    alternate_result = await link_settlement_cash_leg(
        product_leg=alternate_correction,
        transaction_lookup=alternate_lookup,
        transaction_persistence=_persistence(),
        reconcile_superseded_derived=True,
    )
    assert alternate_result.generated_cash_leg is not None
    assert alternate_result.generated_cash_leg.gross_transaction_amount == Decimal(0)
    assert alternate_result.generated_cash_leg.calculation_lineage is not None
    assert (
        alternate_result.generated_cash_leg.calculation_lineage.input_content_hash
        != result.generated_cash_leg.calculation_lineage.input_content_hash
    )
    persistence.upsert_generated_booked_transaction.assert_awaited_once_with(
        result.generated_cash_leg
    )
    persistence.upsert_booked_transaction.assert_awaited_once_with(
        result.product_leg,
        fields_to_clear=frozenset({"external_cash_transaction_id"}),
    )
