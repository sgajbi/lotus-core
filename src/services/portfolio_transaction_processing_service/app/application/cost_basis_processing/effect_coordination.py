"""Coordinate settlement, reconciliation, and staging for processed cost effects."""

from collections.abc import Sequence
from dataclasses import replace

from portfolio_common.domain.tenant import TenantId
from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

from ...domain.transaction import BookedTransaction, should_generate_settlement_cash_leg
from ...domain.transaction.fx import FxContractInstrument
from ...domain.transaction.redemption import (
    REDEMPTION_TRANSACTION_TYPES,
    build_redemption_accrued_interest_component,
    neutralize_generated_redemption_accrued_interest,
    redemption_accrued_interest_transaction_id,
)
from ...ports import (
    CorporateActionReconciliationObserver,
    CorporateActionReconciliationRepository,
    CostBasisFxRatePort,
    CostBasisReferenceDataPort,
    CostBasisTransactionStatePort,
    CostProcessingEffectStagingPort,
    CostProcessingResult,
)
from ..corporate_action_reconciliation import CorporateActionReconciliationCoordinator
from ..errors import TransactionProcessingError, TransactionProcessingRejected
from ..settlement_processing import link_settlement_cash_leg


async def coordinate_cost_processing_effects(
    *,
    processed_transactions: Sequence[BookedTransaction],
    instrument_updates: Sequence[FxContractInstrument],
    source_epoch: int | None,
    tenant_id: TenantId,
    transaction_state: CostBasisTransactionStatePort,
    reconciliation_repository: CorporateActionReconciliationRepository,
    effect_stager: CostProcessingEffectStagingPort,
    correlation_id: str,
    corrected_transaction_id: str | None = None,
    reconciliation_observer: CorporateActionReconciliationObserver | None = None,
    portfolio_base_currency: str | None = None,
    fx_rates: CostBasisFxRatePort | None = None,
    incoming_transaction_id: str | None = None,
    incoming_source_fx_rate_missing: bool = False,
    reference_data: CostBasisReferenceDataPort | None = None,
) -> CostProcessingResult:
    """Link settlement, reconcile corporate actions, and stage domain-valued effects."""

    emitted_transactions: list[BookedTransaction] = []
    reconciliation = CorporateActionReconciliationCoordinator(
        reconciliation_repository,
        observer=reconciliation_observer,
    )
    for processed_transaction in processed_transactions:
        generated_cash_leg_id = f"{processed_transaction.transaction_id}-CASHLEG"
        requires_reference_context = (
            processed_transaction.transaction_id
            in {incoming_transaction_id, corrected_transaction_id}
            or processed_transaction.external_cash_transaction_id != generated_cash_leg_id
        )
        if requires_reference_context:
            (
                settlement_cash_currency,
                resolved_cash_instrument_id,
            ) = await _resolve_settlement_cash_context(
                transaction=processed_transaction,
                tenant_id=tenant_id,
                reference_data=reference_data,
            )
        else:
            settlement_cash_currency, resolved_cash_instrument_id = None, None
        linking = await link_settlement_cash_leg(
            product_leg=processed_transaction,
            transaction_lookup=transaction_state,
            transaction_persistence=transaction_state,
            reconcile_superseded_derived=(
                processed_transaction.transaction_id == corrected_transaction_id
            ),
            derive_fx_at_settlement=(
                incoming_source_fx_rate_missing
                and processed_transaction.transaction_id == incoming_transaction_id
            ),
            portfolio_base_currency=portfolio_base_currency,
            fx_rates=fx_rates,
            settlement_cash_currency=settlement_cash_currency,
            resolved_settlement_cash_instrument_id=resolved_cash_instrument_id,
        )
        await reconciliation.reconcile(
            linking.product_leg,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )
        emitted_transactions.append(
            _with_source_epoch(linking.product_leg, source_epoch=source_epoch)
        )
        accrued_interest = build_redemption_accrued_interest_component(linking.product_leg)
        transaction_type = normalize_transaction_control_code(linking.product_leg.transaction_type)
        reconcile_prior_interest = (
            transaction_type in REDEMPTION_TRANSACTION_TYPES
            or linking.product_leg.transaction_id == corrected_transaction_id
        )
        prior_interest = None
        correction_requires_prior_interest = (
            linking.product_leg.transaction_id == corrected_transaction_id
        )
        if reconcile_prior_interest and (
            accrued_interest is None or correction_requires_prior_interest
        ):
            prior_interest = await transaction_state.get_booked_transaction(
                redemption_accrued_interest_transaction_id(linking.product_leg.transaction_id),
                portfolio_id=linking.product_leg.portfolio_id,
            )
            if prior_interest is not None:
                accrued_interest = (
                    build_redemption_accrued_interest_component(
                        linking.product_leg,
                        include_zero=True,
                    )
                    if transaction_type in REDEMPTION_TRANSACTION_TYPES
                    else neutralize_generated_redemption_accrued_interest(
                        prior_interest,
                        corrected_source=linking.product_leg,
                    )
                )
        if accrued_interest is not None:
            fields_to_clear = (
                frozenset(
                    field_name
                    for field_name in (
                        "external_cash_transaction_id",
                        "linked_component_ids",
                    )
                    if getattr(accrued_interest, field_name) is None
                )
                if prior_interest is not None
                else frozenset()
            )
            await transaction_state.upsert_generated_booked_transaction(
                accrued_interest,
                fields_to_clear=fields_to_clear,
            )
            emitted_transactions.append(
                _with_source_epoch(accrued_interest, source_epoch=source_epoch)
            )
        if linking.generated_cash_leg is not None:
            emitted_transactions.append(
                _with_source_epoch(linking.generated_cash_leg, source_epoch=source_epoch)
            )

    staged_transactions = tuple(emitted_transactions)
    staged_instruments = tuple(instrument_updates)
    await effect_stager.stage_processed_transactions(
        staged_transactions,
        correlation_id=correlation_id,
    )
    await effect_stager.stage_instrument_updates(
        staged_instruments,
        correlation_id=correlation_id,
    )
    return CostProcessingResult(
        processed_transactions=staged_transactions,
        instrument_update_count=len(staged_instruments),
    )


async def _resolve_settlement_cash_context(
    *,
    transaction: BookedTransaction,
    tenant_id: TenantId,
    reference_data: CostBasisReferenceDataPort | None,
) -> tuple[str | None, str | None]:
    """Resolve authoritative generated-cash context for one rebuilt product leg."""

    if not should_generate_settlement_cash_leg(transaction):
        return None, None
    if reference_data is None:
        raise _settlement_dependency_unavailable(transaction, "reference_data_port")

    cash_account_id = str(transaction.settlement_cash_account_id or "").strip()
    settlement_at = transaction.settlement_date or transaction.transaction_date
    cash_account = await reference_data.get_settlement_cash_account_reference(
        portfolio_id=transaction.portfolio_id,
        tenant_id=tenant_id.value,
        cash_account_id=cash_account_id,
        as_of_date=settlement_at.date(),
    )
    if cash_account is None:
        raise _settlement_dependency_unavailable(transaction, "cash_account_mapping")

    supplied_security_id = str(transaction.settlement_cash_instrument_id or "").strip()
    if supplied_security_id and supplied_security_id != cash_account.security_id:
        raise TransactionProcessingRejected(
            reason_code="settlement_cash_instrument_mapping_mismatch",
            detail={
                "transaction_id": transaction.transaction_id,
                "cash_account_id": cash_account.cash_account_id,
                "supplied_security_id": supplied_security_id,
                "mapped_security_id": cash_account.security_id,
            },
            retryable=False,
        )

    if cash_account.instrument_product_type.strip().upper() != "CASH":
        raise TransactionProcessingRejected(
            reason_code="settlement_cash_instrument_not_cash",
            detail={
                "transaction_id": transaction.transaction_id,
                "cash_account_id": cash_account.cash_account_id,
                "mapped_security_id": cash_account.security_id,
                "product_type": cash_account.instrument_product_type,
            },
            retryable=False,
        )

    account_currency = cash_account.account_currency.strip().upper()
    instrument_currency = cash_account.instrument_currency.strip().upper()
    if account_currency != instrument_currency:
        raise TransactionProcessingRejected(
            reason_code="settlement_cash_account_currency_mismatch",
            detail={
                "transaction_id": transaction.transaction_id,
                "cash_account_id": cash_account.cash_account_id,
                "account_currency": account_currency,
                "instrument_currency": instrument_currency,
            },
            retryable=False,
        )
    return account_currency, cash_account.security_id


def _settlement_dependency_unavailable(
    transaction: BookedTransaction,
    dependency: str,
) -> TransactionProcessingError:
    return TransactionProcessingError(
        reason_code="cost_dependency_unavailable",
        detail={
            "portfolio_id": transaction.portfolio_id,
            "transaction_id": transaction.transaction_id,
            "dependency_error": dependency,
        },
        retryable=True,
    )


def _with_source_epoch(
    transaction: BookedTransaction,
    *,
    source_epoch: int | None,
) -> BookedTransaction:
    if source_epoch is None:
        return transaction
    return replace(transaction, epoch=source_epoch)
