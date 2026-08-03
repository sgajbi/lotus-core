"""Apply effective fixed-income carrying amounts to calculated lot disposals."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import date, timezone
from decimal import Decimal
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.domain.transaction.numeric_policy import (
    TRANSACTION_COST_LEDGER_OUTPUT_V1,
)

from ...domain.cost_basis import (
    AmortizedCostAllocationEvidence,
    CostBasisTransaction,
    LotDisposalResult,
    SourceLotDisposalAllocation,
    TransactionLotDisposal,
    transaction_cost_output_payload,
)
from ...domain.fixed_income_book_cost import (
    LotAmortizedCostProfileVersion,
    LotBookCostAuthorityScope,
    allocate_recognized_lot_book_cost,
)
from ...ports import (
    CostBasisPortfolioReference,
    EffectiveLotAmortizedCostProfileRequest,
    LotAmortizedCostProfilePort,
)
from .calculation_result import CostBasisCalculationResult

_TRANSACTION_OVERLAY_ALGORITHM_ID = "fixed-income-amortized-cost-transaction-overlay"
_TRANSACTION_OVERLAY_ALGORITHM_VERSION = 1


async def apply_effective_amortized_cost_to_disposals(
    calculation: CostBasisCalculationResult,
    *,
    portfolio: CostBasisPortfolioReference,
    cost_basis_method: CostBasisMethod,
    profiles: LotAmortizedCostProfilePort,
) -> CostBasisCalculationResult:
    """Replace original-cost disposal economics only when an exact profile decision exists."""

    if not calculation.disposals or portfolio.tenant_id is None:
        return calculation
    if portfolio.legal_book_id is None:
        raise ValueError("portfolio accounting scope is incomplete")

    transactions_by_id = {
        **calculation.source_transactions,
        **{transaction.transaction_id: transaction for transaction in calculation.processed},
    }
    requests_by_allocation: dict[tuple[str, int], EffectiveLotAmortizedCostProfileRequest] = {}
    for disposal in calculation.disposals:
        transaction = _required_transaction(transactions_by_id, disposal.disposal_transaction_id)
        disposal_date = _utc_business_date(transaction)
        for allocation in disposal.result.allocations:
            requests_by_allocation[
                (disposal.disposal_transaction_id, allocation.allocation_ordinal)
            ] = EffectiveLotAmortizedCostProfileRequest(
                scope=LotBookCostAuthorityScope(
                    tenant_id=portfolio.tenant_id,
                    legal_book_id=portfolio.legal_book_id,
                    portfolio_id=transaction.portfolio_id,
                    security_id=transaction.security_id,
                    lot_id=allocation.source_lot_id,
                ),
                effective_date=disposal_date,
            )

    effective_profiles = await profiles.effective_as_of_many(tuple(requests_by_allocation.values()))
    if not effective_profiles:
        return calculation
    if cost_basis_method is not CostBasisMethod.FIFO:
        raise ValueError("lot-level amortized cost requires FIFO source-lot identity")

    processed = [transaction.model_copy() for transaction in calculation.processed]
    transactions_by_id = {
        **calculation.source_transactions,
        **{transaction.transaction_id: transaction for transaction in processed},
    }
    remaining_quantity_by_source = _initial_open_quantities(
        calculation.source_transactions.values()
    )
    decorated_disposals: list[TransactionLotDisposal] = []
    for disposal in calculation.disposals:
        transaction = _required_transaction(transactions_by_id, disposal.disposal_transaction_id)
        allocations = tuple(
            _decorate_allocation(
                allocation,
                request=requests_by_allocation[
                    (disposal.disposal_transaction_id, allocation.allocation_ordinal)
                ],
                profile=effective_profiles.get(
                    requests_by_allocation[
                        (disposal.disposal_transaction_id, allocation.allocation_ordinal)
                    ]
                ),
                source_transaction=_required_transaction(
                    transactions_by_id, allocation.source_transaction_id
                ),
                remaining_quantity_by_source=remaining_quantity_by_source,
            )
            for allocation in disposal.result.allocations
        )
        decorated_result = LotDisposalResult(
            cost_base=sum(
                (allocation.consumed_cost_base for allocation in allocations), Decimal(0)
            ),
            cost_local=sum(
                (allocation.consumed_cost_local for allocation in allocations), Decimal(0)
            ),
            consumed_quantity=disposal.result.consumed_quantity,
            allocations=allocations,
        )
        decorated = TransactionLotDisposal(
            disposal_transaction_id=disposal.disposal_transaction_id,
            result=decorated_result,
        )
        if decorated != disposal:
            _apply_transaction_overlay(transaction, previous=disposal, current=decorated)
        decorated_disposals.append(decorated)

    return replace(
        calculation,
        processed=processed,
        disposals=tuple(decorated_disposals),
    )


def _decorate_allocation(
    allocation: SourceLotDisposalAllocation,
    *,
    request: EffectiveLotAmortizedCostProfileRequest,
    profile: LotAmortizedCostProfileVersion | None,
    source_transaction: CostBasisTransaction,
    remaining_quantity_by_source: dict[str, Decimal],
) -> SourceLotDisposalAllocation:
    open_quantity_before = remaining_quantity_by_source.get(allocation.source_transaction_id)
    if open_quantity_before is None:
        raise ValueError(
            "amortized disposal cannot resolve pre-disposal source-lot quantity: "
            f"{allocation.source_transaction_id}"
        )
    remaining_quantity_by_source[allocation.source_transaction_id] = (
        TRANSACTION_COST_LEDGER_OUTPUT_V1.subtract(
            open_quantity_before,
            allocation.consumed_quantity,
            field_name="amortized_source_lot_remaining_quantity",
        )
    )
    if profile is None:
        return allocation
    if profile.scope != request.scope:
        raise ValueError("effective amortized-cost profile does not match requested lot scope")
    if profile.currency != source_transaction.trade_currency.strip().upper():
        raise ValueError("amortized-cost profile currency does not match source-lot currency")

    original_quantity = getattr(
        source_transaction,
        "source_lot_order_quantity",
        source_transaction.quantity,
    )
    projection = allocate_recognized_lot_book_cost(
        profile,
        disposal_date=request.effective_date,
        original_quantity=original_quantity,
        open_quantity_before=open_quantity_before,
        consumed_quantity=allocation.consumed_quantity,
        book_cost_fx_rate_to_base=_book_cost_fx_rate(source_transaction),
    )
    evidence = AmortizedCostAllocationEvidence(
        profile_id=projection.profile_id,
        profile_version=projection.profile_version,
        profile_content_hash=projection.profile_content_hash,
        currency=projection.currency,
        disposal_date=projection.disposal_date,
        recognized_through_date=projection.recognized_through_date,
        original_quantity=projection.original_quantity,
        open_quantity_before=projection.open_quantity_before,
        consumed_quantity=projection.consumed_quantity,
        residual_quantity=projection.residual_quantity,
        scheduled_cost_local=projection.scheduled_cost_local,
        current_cost_local=projection.current_cost_local,
        current_cost_base=projection.current_cost_base,
        consumed_cost_local=projection.consumed_cost_local,
        residual_cost_local=projection.residual_cost_local,
        book_cost_fx_rate_to_base=projection.book_cost_fx_rate_to_base,
        consumed_cost_base=projection.consumed_cost_base,
        residual_cost_base=projection.residual_cost_base,
        retained_rounding_residual_local=projection.retained_rounding_residual_local,
        retained_rounding_residual_base=projection.retained_rounding_residual_base,
        calculation_lineage=projection.calculation_lineage,
    )
    return replace(
        allocation,
        consumed_cost_local=evidence.consumed_cost_local,
        consumed_cost_base=evidence.consumed_cost_base,
        amortized_cost_evidence=evidence,
    )


def _initial_open_quantities(
    source_transactions: Iterable[CostBasisTransaction],
) -> dict[str, Decimal]:
    return {
        transaction.transaction_id: transaction.quantity
        for transaction in source_transactions
        if transaction.transaction_type == "BUY" and transaction.quantity > Decimal(0)
    }


def _book_cost_fx_rate(source_transaction: CostBasisTransaction) -> Decimal:
    local_cost = source_transaction.net_cost_local
    base_cost = source_transaction.net_cost
    if (
        local_cost is None
        or base_cost is None
        or local_cost <= Decimal(0)
        or base_cost <= Decimal(0)
    ):
        raise ValueError("source lot is missing positive local/base book cost for FX preservation")
    with TRANSACTION_COST_LEDGER_OUTPUT_V1.arithmetic_context():
        rate = base_cost / local_cost
    return cast(
        Decimal,
        TRANSACTION_COST_LEDGER_OUTPUT_V1.normalize(
            rate,
            field_name="book_cost_fx_rate_to_base",
        ),
    )


def _apply_transaction_overlay(
    transaction: CostBasisTransaction,
    *,
    previous: TransactionLotDisposal,
    current: TransactionLotDisposal,
) -> None:
    if transaction.transaction_type != "SELL":
        raise ValueError("amortized-cost transaction overlay currently supports SELL only")
    previous_lineage = getattr(transaction, "calculation_lineage", None)
    if not isinstance(previous_lineage, CalculationLineage):
        raise ValueError("calculated SELL is missing transaction calculation lineage")
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    transaction.realized_gain_loss_local = _adjust_realized_value(
        transaction.realized_gain_loss_local,
        previous_cost=previous.result.cost_local,
        current_cost=current.result.cost_local,
        field_name="realized_gain_loss_local",
    )
    transaction.realized_gain_loss = _adjust_realized_value(
        transaction.realized_gain_loss,
        previous_cost=previous.result.cost_base,
        current_cost=current.result.cost_base,
        field_name="realized_gain_loss",
    )
    _adjust_optional_realized_fields(
        transaction,
        previous_local=previous.result.cost_local,
        current_local=current.result.cost_local,
        previous_base=previous.result.cost_base,
        current_base=current.result.cost_base,
    )
    transaction.net_cost_local = policy.normalize(
        -current.result.cost_local, field_name="net_cost_local"
    )
    transaction.net_cost = policy.normalize(-current.result.cost_base, field_name="net_cost")
    transaction.gross_cost = policy.normalize(-current.result.cost_base, field_name="gross_cost")
    transaction.set_calculated_field(
        "calculation_lineage",
        build_calculation_lineage(
            algorithm_id=_TRANSACTION_OVERLAY_ALGORITHM_ID,
            algorithm_version=_TRANSACTION_OVERLAY_ALGORITHM_VERSION,
            intermediate_precision=policy.working_precision,
            input_payload={
                "amortized_disposal_lineage": (
                    current.result.calculation_lineage.lineage_payload()
                    if current.result.calculation_lineage is not None
                    else None
                ),
                "previous_transaction_lineage": previous_lineage.lineage_payload(),
            },
            output_payload=transaction_cost_output_payload(transaction),
            numeric_output_policy=policy.lineage_identity(),
        ),
    )


def _adjust_realized_value(
    value: Decimal | None,
    *,
    previous_cost: Decimal,
    current_cost: Decimal,
    field_name: str,
) -> Decimal:
    if value is None:
        raise ValueError(f"calculated SELL is missing {field_name}")
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    return cast(
        Decimal,
        policy.subtract(
            policy.add(value, previous_cost, field_name=field_name),
            current_cost,
            field_name=field_name,
        ),
    )


def _adjust_optional_realized_fields(
    transaction: CostBasisTransaction,
    *,
    previous_local: Decimal,
    current_local: Decimal,
    previous_base: Decimal,
    current_base: Decimal,
) -> None:
    for field_name, previous_cost, current_cost in (
        ("realized_capital_pnl_local", previous_local, current_local),
        ("realized_total_pnl_local", previous_local, current_local),
        ("realized_capital_pnl_base", previous_base, current_base),
        ("realized_total_pnl_base", previous_base, current_base),
    ):
        value = getattr(transaction, field_name, None)
        if value is not None:
            transaction.set_calculated_field(
                field_name,
                _adjust_realized_value(
                    value,
                    previous_cost=previous_cost,
                    current_cost=current_cost,
                    field_name=field_name,
                ),
            )


def _required_transaction(
    transactions_by_id: dict[str, CostBasisTransaction],
    transaction_id: str,
) -> CostBasisTransaction:
    transaction = transactions_by_id.get(transaction_id)
    if transaction is None:
        raise ValueError(f"calculated timeline is missing transaction {transaction_id}")
    return transaction


def _utc_business_date(transaction: CostBasisTransaction) -> date:
    timestamp = transaction.transaction_date
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("amortized disposal requires a timezone-aware transaction timestamp")
    return cast(date, timestamp.astimezone(timezone.utc).date())
