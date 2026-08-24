"""Apply transaction-specific cost-basis and realized-P&L policies."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Callable, Protocol, cast

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
    calculation_lineage_binds_output,
    canonical_content_hash,
)
from portfolio_common.domain.cost_basis_receipt_integrity import (
    canonical_cost_basis_output_payload,
)
from portfolio_common.domain.decimal_amount import decimal_or_none
from portfolio_common.domain.transaction.numeric_policy import (
    TRANSACTION_COST_LEDGER_OUTPUT_V1,
)
from portfolio_common.domain.transaction.type_registry import (
    get_transaction_type_definition,
    is_production_booking_transaction_type,
)

from ...transaction.cash_instrument import is_cash_instrument
from ...transaction.fx import (
    FxCanonicalTransaction,
    FxTransactionSource,
    UnsupportedFxRealizedPnlModeError,
    build_fx_baseline_processing_update,
    validate_fx_transaction,
)
from ...transaction.redemption import (
    RedemptionCalculationError,
    RedemptionCalculationReasonCode,
    RedemptionTerms,
    assert_redemption_command_eligible,
    calculate_redemption_economics,
)
from ..corporate_action_cash_economics import (
    CorporateActionCashEconomics,
    CorporateActionCashEconomicsError,
    calculate_corporate_action_cash_economics,
)
from ..models.cost_basis_transaction import CostBasisTransaction
from .calculation_errors import CostCalculationErrorCollector
from .lot_disposition import LotDispositionEngine
from .lot_restatement import LotRestatementError

TRANSACTION_COST_CALCULATION_ALGORITHM_ID = "transaction-cost-basis-calculation"
TRANSACTION_COST_CALCULATION_ALGORITHM_VERSION = 2


class TransactionCostStrategy(Protocol):
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None: ...


InvariantErrorAdder = Callable[[CostCalculationErrorCollector, CostBasisTransaction, str], None]


ACCRUED_INTEREST_EXCLUDED_FROM_BOOK_COST_POLICIES = {
    "BUY_EXCLUDE_ACCRUED_INTEREST_FROM_BOOK_COST",
}
SELL_ALLOW_OVERSOLD_POLICIES = {
    "SELL_ALLOW_OVERSOLD_POLICY",
}
FX_BASELINE_TRANSACTION_TYPES = {"FX_SPOT", "FX_FORWARD", "FX_SWAP"}


def _is_accrued_interest_excluded_from_book_cost(transaction: CostBasisTransaction) -> bool:
    policy_id = _normalize_code(getattr(transaction, "calculation_policy_id", None))
    return policy_id in ACCRUED_INTEREST_EXCLUDED_FROM_BOOK_COST_POLICIES


def _add_buy_invariant_error(
    error_reporter: CostCalculationErrorCollector, transaction: CostBasisTransaction, message: str
) -> None:
    error_reporter.add_error(transaction.transaction_id, f"BUY invariant violation: {message}")


def _add_sell_invariant_error(
    error_reporter: CostCalculationErrorCollector, transaction: CostBasisTransaction, message: str
) -> None:
    error_reporter.add_error(transaction.transaction_id, f"SELL invariant violation: {message}")


def _add_redemption_invariant_error(
    error_reporter: CostCalculationErrorCollector,
    transaction: CostBasisTransaction,
    message: str,
) -> None:
    error_reporter.add_error(
        transaction.transaction_id,
        f"{_normalize_code(transaction.transaction_type)} invariant violation: {message}",
    )


def _add_dividend_invariant_error(
    error_reporter: CostCalculationErrorCollector, transaction: CostBasisTransaction, message: str
) -> None:
    error_reporter.add_error(transaction.transaction_id, f"DIVIDEND invariant violation: {message}")


def _add_interest_invariant_error(
    error_reporter: CostCalculationErrorCollector, transaction: CostBasisTransaction, message: str
) -> None:
    error_reporter.add_error(transaction.transaction_id, f"INTEREST invariant violation: {message}")


def _add_cash_consideration_invariant_error(
    error_reporter: CostCalculationErrorCollector, transaction: CostBasisTransaction, message: str
) -> None:
    error_reporter.add_error(
        transaction.transaction_id,
        f"CASH_CONSIDERATION invariant violation: {message}",
    )


def _add_cash_in_lieu_invariant_error(
    error_reporter: CostCalculationErrorCollector, transaction: CostBasisTransaction, message: str
) -> None:
    error_reporter.add_error(
        transaction.transaction_id,
        f"CASH_IN_LIEU invariant violation: {message}",
    )


def _add_adjustment_invariant_error(
    error_reporter: CostCalculationErrorCollector, transaction: CostBasisTransaction, message: str
) -> None:
    error_reporter.add_error(
        transaction.transaction_id,
        f"ADJUSTMENT invariant violation: {message}",
    )


def _normalize_decimal_field(value: object, field_name: str) -> Decimal:
    resolved_value = decimal_or_none(value)
    if resolved_value is None:
        raise ValueError(f"invalid decimal for {field_name}: {value!r}")
    return cast(Decimal, resolved_value)


def _is_cash_instrument(transaction: CostBasisTransaction) -> bool:
    return is_cash_instrument(
        product_type=getattr(transaction, "product_type", None),
        asset_class=getattr(transaction, "asset_class", None),
    )


def _cash_movement_amount(transaction: CostBasisTransaction) -> Decimal:
    gross_amount = _decimal_or_zero(
        transaction.gross_transaction_amount,
        field_name="gross_transaction_amount",
    )
    quantity_amount = _decimal_or_zero(transaction.quantity, field_name="quantity")
    movement_amount = gross_amount if not gross_amount.is_zero() else quantity_amount
    return abs(movement_amount)


def _normalize_cash_movement_inputs(transaction: CostBasisTransaction) -> None:
    """Canonicalize legacy blank cash amounts once before calculation and lineage."""

    transaction.gross_transaction_amount = _decimal_or_zero(
        transaction.gross_transaction_amount,
        field_name="gross_transaction_amount",
    )
    transaction.quantity = _decimal_or_zero(transaction.quantity, field_name="quantity")


def _cash_outflow_book_cost(transaction: CostBasisTransaction) -> Decimal:
    cash_amount = _cash_movement_amount(transaction)
    if _normalize_code(transaction.transaction_type) != "FEE":
        return cash_amount
    total_fees = transaction.fees.total_fees if transaction.fees else Decimal(0)
    return cast(
        Decimal,
        TRANSACTION_COST_LEDGER_OUTPUT_V1.add(
            cash_amount,
            total_fees,
            field_name="net_cost_local",
        ),
    )


def _decimal_or_zero(value: object, *, field_name: str) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal(0)
    return _normalize_decimal_field(value, field_name)


def _optional_transaction_decimal(
    transaction: CostBasisTransaction, field_name: str
) -> Decimal | None:
    value = getattr(transaction, field_name, None)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _normalize_decimal_field(value, field_name)


def _normalize_code(value: object) -> str:
    return str(value or "").strip().upper()


def _normalize_currency_code(currency_code: str) -> str:
    return _normalize_code(currency_code)


def _normalize_transaction_type(transaction_type: str) -> str:
    return str(transaction_type).strip().upper()


def _transaction_fx_rate_or_one(transaction: CostBasisTransaction) -> Decimal:
    return transaction.transaction_fx_rate or Decimal(1)


def _transaction_total_fees(transaction: CostBasisTransaction) -> Decimal:
    return transaction.fees.total_fees if transaction.fees else Decimal(0)


def _calculate_transaction_cash_economics(
    transaction: CostBasisTransaction,
) -> CorporateActionCashEconomics:
    return calculate_corporate_action_cash_economics(
        gross_proceeds_local=transaction.gross_transaction_amount,
        fees_local=_transaction_total_fees(transaction),
        allocated_cost_basis_local=_optional_transaction_decimal(
            transaction, "allocated_cost_basis_local"
        ),
        allocated_cost_basis_base=_optional_transaction_decimal(
            transaction, "allocated_cost_basis_base"
        ),
        local_currency=transaction.trade_currency,
        base_currency=transaction.portfolio_base_currency,
        transaction_fx_rate=_transaction_fx_rate_or_one(transaction),
        realized_capital_pnl_local=_optional_transaction_decimal(
            transaction, "realized_capital_pnl_local"
        ),
        realized_fx_pnl_local=_optional_transaction_decimal(transaction, "realized_fx_pnl_local"),
        realized_total_pnl_local=_optional_transaction_decimal(
            transaction, "realized_total_pnl_local"
        ),
        realized_capital_pnl_base=_optional_transaction_decimal(
            transaction, "realized_capital_pnl_base"
        ),
        realized_fx_pnl_base=_optional_transaction_decimal(transaction, "realized_fx_pnl_base"),
        realized_total_pnl_base=_optional_transaction_decimal(
            transaction, "realized_total_pnl_base"
        ),
    )


def _apply_zero_cost_fields(transaction: CostBasisTransaction) -> None:
    transaction.net_cost = Decimal(0)
    transaction.net_cost_local = Decimal(0)
    transaction.gross_cost = Decimal(0)


def _apply_zero_realized_pnl(transaction: CostBasisTransaction) -> None:
    transaction.realized_gain_loss = Decimal(0)
    transaction.realized_gain_loss_local = Decimal(0)


def _apply_no_realized_pnl(transaction: CostBasisTransaction) -> None:
    transaction.realized_gain_loss = None
    transaction.realized_gain_loss_local = None


def _has_non_zero_cost_fields(transaction: CostBasisTransaction) -> bool:
    return bool(transaction.net_cost != Decimal(0) or transaction.net_cost_local != Decimal(0))


def _has_non_zero_realized_pnl(transaction: CostBasisTransaction) -> bool:
    return bool(
        transaction.realized_gain_loss != Decimal(0)
        or transaction.realized_gain_loss_local != Decimal(0)
    )


def _normalized_price_or_error(
    transaction: CostBasisTransaction,
    error_reporter: CostCalculationErrorCollector,
    add_invariant_error: InvariantErrorAdder,
) -> Decimal | None:
    try:
        return _normalize_decimal_field(getattr(transaction, "price", Decimal(0)), "price")
    except ValueError as exc:
        add_invariant_error(error_reporter, transaction, str(exc))
        return None


def _validate_zero_quantity_and_price(
    transaction: CostBasisTransaction,
    error_reporter: CostCalculationErrorCollector,
    *,
    transaction_label: str,
    add_invariant_error: InvariantErrorAdder,
) -> bool:
    if transaction.quantity != Decimal(0):
        add_invariant_error(
            error_reporter, transaction, f"quantity_delta must be 0 for {transaction_label}."
        )
        return False

    price = _normalized_price_or_error(transaction, error_reporter, add_invariant_error)
    if price is None:
        return False

    if price != Decimal(0):
        add_invariant_error(
            error_reporter, transaction, f"price must be 0 for {transaction_label}."
        )
        return False
    return True


def _validate_zero_cost_and_realized_pnl(
    transaction: CostBasisTransaction,
    error_reporter: CostCalculationErrorCollector,
    *,
    realized_label: str,
    add_invariant_error: InvariantErrorAdder,
) -> bool:
    if _has_non_zero_cost_fields(transaction):
        add_invariant_error(error_reporter, transaction, "net_cost and net_cost_local must be 0.")
        return False

    if _has_non_zero_realized_pnl(transaction):
        add_invariant_error(
            error_reporter,
            transaction,
            f"realized capital/FX P&L must be explicit zero for {realized_label}.",
        )
        return False
    return True


def _apply_buy_cost_fields(transaction: CostBasisTransaction) -> None:
    total_fees_local = _transaction_total_fees(transaction)
    accrued_interest_local = transaction.accrued_interest or Decimal(0)
    fx_rate = _transaction_fx_rate_or_one(transaction)
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    transaction.gross_cost = policy.multiply(
        transaction.gross_transaction_amount,
        fx_rate,
        field_name="gross_cost",
    )

    transaction.net_cost_local = policy.add(
        transaction.gross_transaction_amount,
        total_fees_local,
        field_name="net_cost_local",
    )
    if not _is_accrued_interest_excluded_from_book_cost(transaction):
        transaction.net_cost_local = policy.add(
            transaction.net_cost_local,
            accrued_interest_local,
            field_name="net_cost_local",
        )

    transaction.net_cost = policy.multiply(
        transaction.net_cost_local,
        fx_rate,
        field_name="net_cost",
    )
    _apply_zero_realized_pnl(transaction)


def _validate_buy_cost_fields(
    transaction: CostBasisTransaction, error_reporter: CostCalculationErrorCollector
) -> bool:
    if transaction.quantity <= Decimal(0):
        _add_buy_invariant_error(error_reporter, transaction, "quantity_delta must be > 0.")
        return False
    if not _validate_non_negative_buy_costs(transaction, error_reporter):
        return False
    if _has_non_zero_realized_pnl(transaction):
        _add_buy_invariant_error(
            error_reporter, transaction, "realized P&L must be explicit zero for BUY."
        )
        return False
    return True


def _validate_non_negative_buy_costs(
    transaction: CostBasisTransaction, error_reporter: CostCalculationErrorCollector
) -> bool:
    if (
        transaction.gross_cost is None
        or transaction.net_cost_local is None
        or transaction.net_cost is None
    ):
        _add_buy_invariant_error(
            error_reporter,
            transaction,
            "gross_cost, book_cost_local, and book_cost_base must be calculated.",
        )
        return False
    if transaction.gross_cost < Decimal(0):
        _add_buy_invariant_error(error_reporter, transaction, "gross_cost must be >= 0.")
        return False
    if transaction.net_cost_local < Decimal(0):
        _add_buy_invariant_error(error_reporter, transaction, "book_cost_local must be >= 0.")
        return False
    if transaction.net_cost < Decimal(0):
        _add_buy_invariant_error(error_reporter, transaction, "book_cost_base must be >= 0.")
        return False
    return True


def _record_buy_lot(
    transaction: CostBasisTransaction,
    disposition_engine: LotDispositionEngine,
    error_reporter: CostCalculationErrorCollector,
) -> None:
    try:
        disposition_engine.add_buy_lot(transaction)
    except ValueError as e:
        error_reporter.add_error(transaction.transaction_id, str(e))


def _net_sell_proceeds_local(transaction: CostBasisTransaction) -> Decimal:
    return cast(
        Decimal,
        TRANSACTION_COST_LEDGER_OUTPUT_V1.subtract(
            transaction.gross_transaction_amount,
            _transaction_total_fees(transaction),
            field_name="net_sell_proceeds_local",
        ),
    )


def _validate_sell_quantity_and_proceeds(
    transaction: CostBasisTransaction,
    error_reporter: CostCalculationErrorCollector,
    *,
    net_sell_proceeds_local: Decimal,
    net_sell_proceeds_base: Decimal,
) -> bool:
    if net_sell_proceeds_local < Decimal(0):
        _add_sell_invariant_error(
            error_reporter,
            transaction,
            "net_sell_proceeds_local must be >= 0.",
        )
        return False
    if net_sell_proceeds_base < Decimal(0):
        _add_sell_invariant_error(
            error_reporter,
            transaction,
            "net_sell_proceeds_base must be >= 0.",
        )
        return False
    if transaction.quantity <= Decimal(0):
        _add_sell_invariant_error(error_reporter, transaction, "quantity_delta must be > 0.")
        return False
    return True


def _validate_disposal_availability(
    transaction: CostBasisTransaction,
    disposition_engine: LotDispositionEngine,
    error_reporter: CostCalculationErrorCollector,
    *,
    add_invariant_error: InvariantErrorAdder,
) -> bool:
    available_quantity = disposition_engine.get_available_quantity(
        transaction.portfolio_id, transaction.instrument_id
    )
    policy_id = _normalize_code(getattr(transaction, "calculation_policy_id", None))
    if transaction.quantity <= available_quantity:
        return True
    if policy_id in SELL_ALLOW_OVERSOLD_POLICIES:
        add_invariant_error(
            error_reporter,
            transaction,
            "oversold policy is configured but not supported in current engine.",
        )
    else:
        add_invariant_error(
            error_reporter,
            transaction,
            "sell quantity exceeds available holdings under strict oversell policy.",
        )
    return False


def _consume_disposal_cost_basis(
    transaction: CostBasisTransaction,
    disposition_engine: LotDispositionEngine,
    error_reporter: CostCalculationErrorCollector,
    *,
    add_invariant_error: InvariantErrorAdder,
) -> tuple[Decimal, Decimal, Decimal] | None:
    cogs_base, cogs_local, consumed_quantity, error_reason = (
        disposition_engine.consume_sell_quantity(transaction)
    )

    if error_reason:
        error_reporter.add_error(transaction.transaction_id, error_reason)
        return None
    if consumed_quantity <= Decimal(0):
        add_invariant_error(error_reporter, transaction, "consumed_quantity must be > 0.")
        return None
    if cogs_base < Decimal(0) or cogs_local < Decimal(0):
        add_invariant_error(
            error_reporter,
            transaction,
            "disposed cost basis must be non-negative.",
        )
        return None
    return cogs_base, cogs_local, consumed_quantity


def _apply_sell_disposal_fields(
    transaction: CostBasisTransaction,
    *,
    net_sell_proceeds_local: Decimal,
    net_sell_proceeds_base: Decimal,
    cogs_base: Decimal,
    cogs_local: Decimal,
) -> None:
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
    transaction.realized_gain_loss_local = policy.subtract(
        net_sell_proceeds_local,
        cogs_local,
        field_name="realized_gain_loss_local",
    )
    transaction.realized_gain_loss = policy.subtract(
        net_sell_proceeds_base,
        cogs_base,
        field_name="realized_gain_loss",
    )
    transaction.net_cost = policy.normalize(-cogs_base, field_name="net_cost")
    transaction.net_cost_local = policy.normalize(-cogs_local, field_name="net_cost_local")
    transaction.gross_cost = policy.normalize(-cogs_base, field_name="gross_cost")


def _validate_sell_disposal_fields(
    transaction: CostBasisTransaction, error_reporter: CostCalculationErrorCollector
) -> bool:
    if transaction.net_cost is None or transaction.net_cost_local is None:
        _add_sell_invariant_error(
            error_reporter,
            transaction,
            "net_cost and net_cost_local must be calculated for SELL disposal.",
        )
        return False
    if transaction.net_cost <= Decimal(0) and transaction.net_cost_local <= Decimal(0):
        return True
    _add_sell_invariant_error(
        error_reporter,
        transaction,
        "net_cost and net_cost_local must be <= 0 for SELL disposal.",
    )
    return False


def _resolve_interest_direction(
    transaction: CostBasisTransaction,
    error_reporter: CostCalculationErrorCollector,
) -> str | None:
    raw_direction = getattr(transaction, "interest_direction", None)
    direction = "INCOME" if raw_direction in (None, "") else _normalize_code(raw_direction)
    if direction in {"INCOME", "EXPENSE"}:
        return direction
    _add_interest_invariant_error(
        error_reporter,
        transaction,
        "interest_direction must be INCOME or EXPENSE when provided.",
    )
    return None


def _normalize_transaction_currencies(transaction: CostBasisTransaction) -> None:
    transaction.trade_currency = _normalize_currency_code(transaction.trade_currency)
    transaction.portfolio_base_currency = _normalize_currency_code(
        transaction.portfolio_base_currency
    )


def _normalize_existing_transaction_fx_rate(
    transaction: CostBasisTransaction,
    error_reporter: CostCalculationErrorCollector,
) -> bool:
    if transaction.transaction_fx_rate is None:
        return True
    try:
        transaction.transaction_fx_rate = _normalize_decimal_field(
            transaction.transaction_fx_rate, "transaction_fx_rate"
        )
    except ValueError as exc:
        error_reporter.add_error(transaction.transaction_id, str(exc))
        return False
    if transaction.transaction_fx_rate > 0:
        return True
    error_reporter.add_error(
        transaction.transaction_id,
        "Missing/invalid FX rate for transaction.",
    )
    return False


def _validate_normalized_transaction_fx(
    transaction: CostBasisTransaction,
    error_reporter: CostCalculationErrorCollector,
) -> bool:
    if transaction.trade_currency == transaction.portfolio_base_currency:
        if transaction.transaction_fx_rate is None:
            transaction.transaction_fx_rate = Decimal(1)
        return True
    if transaction.transaction_fx_rate is not None and transaction.transaction_fx_rate > 0:
        return True
    error_reporter.add_error(
        transaction.transaction_id,
        "Missing/invalid FX rate for cross-currency transaction from "
        f"{transaction.trade_currency} to {transaction.portfolio_base_currency}.",
    )
    return False


def _validate_transaction_currency_context(
    transaction: CostBasisTransaction,
    error_reporter: CostCalculationErrorCollector,
) -> bool:
    _normalize_transaction_currencies(transaction)
    if not _normalize_existing_transaction_fx_rate(transaction, error_reporter):
        return False
    if _normalize_transaction_type(transaction.transaction_type) in FX_BASELINE_TRANSACTION_TYPES:
        return True
    return _validate_normalized_transaction_fx(transaction, error_reporter)


class BuyStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        _apply_buy_cost_fields(transaction)
        if not _validate_buy_cost_fields(transaction, error_reporter):
            return

        _record_buy_lot(transaction, disposition_engine, error_reporter)


class SellStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        net_sell_proceeds_local = _net_sell_proceeds_local(transaction)
        fx_rate = _transaction_fx_rate_or_one(transaction)
        net_sell_proceeds_base = TRANSACTION_COST_LEDGER_OUTPUT_V1.multiply(
            net_sell_proceeds_local,
            fx_rate,
            field_name="net_sell_proceeds_base",
        )
        if not _validate_sell_quantity_and_proceeds(
            transaction,
            error_reporter,
            net_sell_proceeds_local=net_sell_proceeds_local,
            net_sell_proceeds_base=net_sell_proceeds_base,
        ):
            return
        if not _validate_disposal_availability(
            transaction,
            disposition_engine,
            error_reporter,
            add_invariant_error=_add_sell_invariant_error,
        ):
            return

        consumed_cost_basis = _consume_disposal_cost_basis(
            transaction,
            disposition_engine,
            error_reporter,
            add_invariant_error=_add_sell_invariant_error,
        )
        if consumed_cost_basis is None:
            return
        cogs_base, cogs_local, _consumed_quantity = consumed_cost_basis

        _apply_sell_disposal_fields(
            transaction,
            net_sell_proceeds_local=net_sell_proceeds_local,
            net_sell_proceeds_base=net_sell_proceeds_base,
            cogs_base=cogs_base,
            cogs_local=cogs_local,
        )
        _validate_sell_disposal_fields(transaction, error_reporter)


class RedemptionStrategy:
    """Consume governed lots and calculate principal-only redemption P&L."""

    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        try:
            assert_redemption_command_eligible(
                transaction_type=transaction.transaction_type,
                settlement_date=getattr(transaction, "settlement_date", None),
                product_type=getattr(transaction, "product_type", None),
                asset_class=getattr(transaction, "asset_class", None),
            )
        except ValueError as exc:
            error_reporter.add_error(transaction.transaction_id, str(exc))
            return
        available_quantity = disposition_engine.get_available_quantity(
            transaction.portfolio_id,
            transaction.instrument_id,
        )
        try:
            preview = calculate_redemption_economics(
                _redemption_terms(
                    transaction,
                    position_quantity=available_quantity,
                    allocated_cost_basis_local=Decimal(0),
                    allocated_cost_basis_base=Decimal(0),
                )
            )
        except RedemptionCalculationError as exc:
            error_reporter.add_error(transaction.transaction_id, str(exc))
            return
        transaction.quantity = preview.redeemed_quantity
        consumed = _consume_disposal_cost_basis(
            transaction,
            disposition_engine,
            error_reporter,
            add_invariant_error=_add_redemption_invariant_error,
        )
        if consumed is None:
            return
        cogs_base, cogs_local, _consumed_quantity = consumed
        try:
            economics = calculate_redemption_economics(
                _redemption_terms(
                    transaction,
                    position_quantity=available_quantity,
                    allocated_cost_basis_local=cogs_local,
                    allocated_cost_basis_base=cogs_base,
                )
            )
        except RedemptionCalculationError as exc:
            error_reporter.add_error(transaction.transaction_id, str(exc))
            return
        policy = TRANSACTION_COST_LEDGER_OUTPUT_V1
        transaction.net_cost_local = policy.normalize(-cogs_local, field_name="net_cost_local")
        transaction.net_cost = policy.normalize(-cogs_base, field_name="net_cost")
        transaction.gross_cost = policy.normalize(-cogs_base, field_name="gross_cost")
        transaction.realized_gain_loss_local = economics.realized_capital_pnl_local
        transaction.realized_gain_loss = economics.realized_capital_pnl_base
        for field_name, value in (
            ("allocated_cost_basis_local", cogs_local),
            ("allocated_cost_basis_base", cogs_base),
            ("realized_capital_pnl_local", economics.realized_capital_pnl_local),
            ("realized_fx_pnl_local", Decimal(0)),
            ("realized_total_pnl_local", economics.realized_capital_pnl_local),
            ("realized_capital_pnl_base", economics.realized_capital_pnl_base),
            ("realized_fx_pnl_base", Decimal(0)),
            ("realized_total_pnl_base", economics.realized_capital_pnl_base),
        ):
            transaction.set_calculated_field(field_name, value)


def _redemption_terms(
    transaction: CostBasisTransaction,
    *,
    position_quantity: Decimal,
    allocated_cost_basis_local: Decimal,
    allocated_cost_basis_base: Decimal,
) -> RedemptionTerms:
    redemption_price = decimal_or_none(getattr(transaction, "price", transaction.average_price))
    if redemption_price is None:
        raise RedemptionCalculationError(
            RedemptionCalculationReasonCode.INVALID_MONETARY_INPUT,
            field="redemption_price",
            message="must be a finite decimal",
        )
    old_factor = getattr(transaction, "old_factor", None)
    new_factor = getattr(transaction, "new_factor", None)
    factor_authority_supplied = old_factor is not None or new_factor is not None
    redeemed_quantity = (
        None
        if transaction.quantity.is_zero() and factor_authority_supplied
        else transaction.quantity
    )
    return RedemptionTerms(
        transaction_type=transaction.transaction_type,
        position_quantity=position_quantity,
        redeemed_quantity=redeemed_quantity,
        redemption_price=redemption_price,
        old_factor=old_factor,
        new_factor=new_factor,
        principal_proceeds_local=getattr(transaction, "principal_proceeds_local", None),
        accrued_interest_proceeds_local=(
            getattr(transaction, "accrued_interest_proceeds_local", None) or Decimal(0)
        ),
        embedded_fee_amount_local=(
            getattr(transaction, "embedded_fee_amount_local", None) or Decimal(0)
        ),
        embedded_tax_amount_local=(
            getattr(transaction, "embedded_tax_amount_local", None) or Decimal(0)
        ),
        allocated_cost_basis_local=allocated_cost_basis_local,
        allocated_cost_basis_base=allocated_cost_basis_base,
        fx_rate_to_base=_transaction_fx_rate_or_one(transaction),
    )


class CashInflowStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        cash_amount_local = _cash_movement_amount(transaction)
        transaction.gross_cost = cash_amount_local
        transaction.net_cost_local = cash_amount_local
        fx_rate = _transaction_fx_rate_or_one(transaction)
        transaction.net_cost = TRANSACTION_COST_LEDGER_OUTPUT_V1.multiply(
            transaction.net_cost_local,
            fx_rate,
            field_name="net_cost",
        )
        cash_buy_equivalent = transaction.model_copy()
        cash_buy_equivalent.quantity = cash_amount_local

        disposition_engine.add_buy_lot(cash_buy_equivalent)


class CashOutflowStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        cash_amount_local = _cash_outflow_book_cost(transaction)
        fx_rate = _transaction_fx_rate_or_one(transaction)
        transaction.net_cost_local = -cash_amount_local
        transaction.net_cost = TRANSACTION_COST_LEDGER_OUTPUT_V1.multiply(
            transaction.net_cost_local,
            fx_rate,
            field_name="net_cost",
        )
        transaction.gross_cost = transaction.net_cost
        _apply_no_realized_pnl(transaction)


class AdjustmentStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        del disposition_engine
        direction = _normalize_code(getattr(transaction, "movement_direction", None) or "INFLOW")
        if direction not in {"INFLOW", "OUTFLOW"}:
            _add_adjustment_invariant_error(
                error_reporter,
                transaction,
                "movement_direction must be INFLOW or OUTFLOW.",
            )
            return
        signed_amount_local = _cash_movement_amount(transaction)
        if direction == "OUTFLOW":
            signed_amount_local = -signed_amount_local
        transaction.net_cost_local = signed_amount_local
        transaction.net_cost = TRANSACTION_COST_LEDGER_OUTPUT_V1.multiply(
            signed_amount_local,
            _transaction_fx_rate_or_one(transaction),
            field_name="net_cost",
        )
        transaction.gross_cost = transaction.net_cost
        _apply_no_realized_pnl(transaction)


class SecurityInflowStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount

        fx_rate = _transaction_fx_rate_or_one(transaction)
        transaction.net_cost = TRANSACTION_COST_LEDGER_OUTPUT_V1.multiply(
            transaction.net_cost_local,
            fx_rate,
            field_name="net_cost",
        )

        if transaction.quantity > Decimal(0):
            _record_buy_lot(transaction, disposition_engine, error_reporter)


class SecurityOutflowStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        """Consumes a cost lot for a security transfer out, but does not realize a P&L."""
        cogs_base, cogs_local, consumed_quantity, error_reason = (
            disposition_engine.consume_sell_quantity(transaction)
        )

        if error_reason:
            error_reporter.add_error(transaction.transaction_id, error_reason)
            return

        if consumed_quantity > Decimal(0):
            transaction.net_cost = TRANSACTION_COST_LEDGER_OUTPUT_V1.normalize(
                -cogs_base,
                field_name="net_cost",
            )
            transaction.net_cost_local = TRANSACTION_COST_LEDGER_OUTPUT_V1.normalize(
                -cogs_local,
                field_name="net_cost_local",
            )
            transaction.gross_cost = transaction.net_cost
            _apply_no_realized_pnl(transaction)


class PartialTransferOutStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        """
        Handles source-retained CA basis transfer-out legs.

        Quantity may be zero for basis-only reallocation flows. In that case we
        apply explicit basis reduction without consuming lots through SELL logic.
        """
        if transaction.quantity > Decimal(0):
            SecurityOutflowStrategy().calculate_costs(
                transaction, disposition_engine, error_reporter
            )
            return

        fx_rate = _transaction_fx_rate_or_one(transaction)
        basis_out_local = transaction.gross_transaction_amount
        basis_out_base = TRANSACTION_COST_LEDGER_OUTPUT_V1.multiply(
            basis_out_local,
            fx_rate,
            field_name="net_cost",
        )
        basis_transfer = disposition_engine.transfer_basis_out(
            transaction,
            cost_base=basis_out_base,
            cost_local=basis_out_local,
        )
        if basis_transfer.error_reason is not None:
            error_reporter.add_error(transaction.transaction_id, basis_transfer.error_reason)
            return
        transaction.net_cost_local = -basis_out_local
        transaction.net_cost = -basis_out_base
        transaction.gross_cost = -basis_out_base
        _apply_no_realized_pnl(transaction)


class IncomeStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        _apply_zero_cost_fields(transaction)
        _apply_no_realized_pnl(transaction)


class CashConsiderationStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        del disposition_engine
        if not _validate_zero_quantity_and_price(
            transaction,
            error_reporter,
            transaction_label="CASH_CONSIDERATION",
            add_invariant_error=_add_cash_consideration_invariant_error,
        ):
            return
        if transaction.gross_transaction_amount <= Decimal(0):
            _add_cash_consideration_invariant_error(
                error_reporter,
                transaction,
                "gross cash proceeds must be greater than 0.",
            )
            return
        try:
            economics = _calculate_transaction_cash_economics(transaction)
        except (CorporateActionCashEconomicsError, ValueError) as exc:
            _add_cash_consideration_invariant_error(error_reporter, transaction, str(exc))
            return
        _apply_corporate_action_cash_economics(transaction, economics)


class CashInLieuStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        if transaction.quantity <= Decimal(0):
            _add_cash_in_lieu_invariant_error(
                error_reporter,
                transaction,
                "quantity_delta must be greater than 0.",
            )
            return
        if transaction.gross_transaction_amount <= Decimal(0):
            _add_cash_in_lieu_invariant_error(
                error_reporter,
                transaction,
                "gross cash proceeds must be greater than 0.",
            )
            return
        try:
            economics = _calculate_transaction_cash_economics(transaction)
        except (CorporateActionCashEconomicsError, ValueError) as exc:
            _add_cash_in_lieu_invariant_error(error_reporter, transaction, str(exc))
            return
        if not _validate_disposal_availability(
            transaction,
            disposition_engine,
            error_reporter,
            add_invariant_error=_add_cash_in_lieu_invariant_error,
        ):
            return
        consumed = _consume_disposal_cost_basis(
            transaction,
            disposition_engine,
            error_reporter,
            add_invariant_error=_add_cash_in_lieu_invariant_error,
        )
        if consumed is None:
            return
        consumed_base, consumed_local, consumed_quantity = consumed
        if consumed_quantity != transaction.quantity:
            _add_cash_in_lieu_invariant_error(
                error_reporter,
                transaction,
                "consumed quantity must equal fractional quantity.",
            )
            return
        if (
            consumed_local != economics.allocated_cost_basis_local
            or consumed_base != economics.allocated_cost_basis_base
        ):
            _add_cash_in_lieu_invariant_error(
                error_reporter,
                transaction,
                "consumed local/base basis must equal allocated fractional basis.",
            )
            return
        _apply_corporate_action_cash_economics(transaction, economics)


def _apply_corporate_action_cash_economics(
    transaction: CostBasisTransaction,
    economics: CorporateActionCashEconomics,
) -> None:
    transaction.set_calculated_field(
        "allocated_cost_basis_local", economics.allocated_cost_basis_local
    )
    transaction.set_calculated_field(
        "allocated_cost_basis_base", economics.allocated_cost_basis_base
    )
    transaction.net_cost_local = -economics.allocated_cost_basis_local
    transaction.net_cost = -economics.allocated_cost_basis_base
    transaction.gross_cost = -economics.allocated_cost_basis_base
    transaction.realized_gain_loss_local = economics.realized_total_pnl_local
    transaction.realized_gain_loss = economics.realized_total_pnl_base
    transaction.set_calculated_field(
        "realized_capital_pnl_local", economics.realized_capital_pnl_local
    )
    transaction.set_calculated_field("realized_fx_pnl_local", economics.realized_fx_pnl_local)
    transaction.set_calculated_field("realized_total_pnl_local", economics.realized_total_pnl_local)
    transaction.set_calculated_field(
        "realized_capital_pnl_base", economics.realized_capital_pnl_base
    )
    transaction.set_calculated_field("realized_fx_pnl_base", economics.realized_fx_pnl_base)
    transaction.set_calculated_field("realized_total_pnl_base", economics.realized_total_pnl_base)


class QuantityRestatementStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        """
        Handles same-instrument corporate-action quantity restatements where
        quantity changes but total basis must remain unchanged.
        """
        _apply_zero_cost_fields(transaction)
        _apply_zero_realized_pnl(transaction)
        definition = get_transaction_type_definition(transaction.transaction_type)
        if definition is None or definition.position_effect not in {"increase", "decrease"}:
            error_reporter.add_error(
                transaction.transaction_id,
                "Quantity restatement invariant violation: transaction type has no direction.",
            )
            return
        signed_quantity_delta = (
            -transaction.quantity
            if definition.position_effect == "decrease"
            else transaction.quantity
        )
        try:
            restatement = disposition_engine.restate_lot_quantities(
                transaction,
                signed_quantity_delta=signed_quantity_delta,
            )
        except LotRestatementError as exc:
            error_reporter.add_error(
                transaction.transaction_id,
                f"Quantity restatement invariant violation: {exc}",
            )
            return
        transaction.set_calculated_field("lot_restatement", restatement.lineage_payload())


class DividendStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        _apply_zero_cost_fields(transaction)
        _apply_zero_realized_pnl(transaction)

        if not _validate_zero_quantity_and_price(
            transaction,
            error_reporter,
            transaction_label="DIVIDEND",
            add_invariant_error=_add_dividend_invariant_error,
        ):
            return

        if transaction.gross_transaction_amount <= Decimal(0):
            _add_dividend_invariant_error(
                error_reporter,
                transaction,
                "gross_dividend_local must be > 0 for DIVIDEND.",
            )
            return

        _validate_zero_cost_and_realized_pnl(
            transaction,
            error_reporter,
            realized_label="DIVIDEND",
            add_invariant_error=_add_dividend_invariant_error,
        )


class InterestStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        _apply_zero_cost_fields(transaction)
        _apply_zero_realized_pnl(transaction)

        if _resolve_interest_direction(transaction, error_reporter) is None:
            return

        if not _validate_zero_quantity_and_price(
            transaction,
            error_reporter,
            transaction_label="INTEREST",
            add_invariant_error=_add_interest_invariant_error,
        ):
            return

        if transaction.gross_transaction_amount <= Decimal(0):
            _add_interest_invariant_error(
                error_reporter,
                transaction,
                "gross_interest_local must be > 0 for INTEREST baseline.",
            )
            return

        _validate_zero_cost_and_realized_pnl(
            transaction,
            error_reporter,
            realized_label="INTEREST",
            add_invariant_error=_add_interest_invariant_error,
        )


class DefaultStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount
        fx_rate = _transaction_fx_rate_or_one(transaction)
        transaction.net_cost = TRANSACTION_COST_LEDGER_OUTPUT_V1.multiply(
            transaction.net_cost_local,
            fx_rate,
            field_name="net_cost",
        )


class UnsupportedTaxStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        error_reporter.add_error(
            transaction.transaction_id,
            "TAX must be represented as a cash instrument outflow.",
        )


class FxBaselineStrategy:
    def calculate_costs(
        self,
        transaction: CostBasisTransaction,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ) -> None:
        if not _validate_canonical_fx_transaction(transaction, error_reporter):
            return
        try:
            update = build_fx_baseline_processing_update(transaction)
        except UnsupportedFxRealizedPnlModeError as exc:
            error_reporter.add_error(transaction.transaction_id, str(exc))
            return
        for field_name, field_value in update.items():
            transaction.set_calculated_field(field_name, field_value)


def _validate_canonical_fx_transaction(
    transaction: CostBasisTransaction,
    error_reporter: CostCalculationErrorCollector,
) -> bool:
    if not isinstance(transaction, FxTransactionSource):
        error_reporter.add_error(
            transaction.transaction_id,
            "FX validation failed: required canonical FX fields are incomplete.",
        )
        return False
    try:
        canonical = FxCanonicalTransaction.from_transaction(transaction)
    except ValueError as exc:
        error_reporter.add_error(
            transaction.transaction_id,
            (
                "FX validation failed: canonical FX fields are incomplete or invalid "
                f"({exc.__class__.__name__})."
            ),
        )
        return False
    issues = validate_fx_transaction(canonical, strict_metadata=False)
    if issues:
        issue_summary = "; ".join(f"{issue.code}:{issue.field}" for issue in issues)
        error_reporter.add_error(
            transaction.transaction_id,
            f"FX validation failed: {issue_summary}.",
        )
        return False
    return True


class CostBasisCalculator:
    def __init__(
        self,
        disposition_engine: LotDispositionEngine,
        error_reporter: CostCalculationErrorCollector,
    ):
        self._disposition_engine = disposition_engine
        self._error_reporter = error_reporter
        self._strategies: dict[str, TransactionCostStrategy] = {
            "BUY": BuyStrategy(),
            "SELL": SellStrategy(),
            "FX_SPOT": FxBaselineStrategy(),
            "FX_FORWARD": FxBaselineStrategy(),
            "FX_SWAP": FxBaselineStrategy(),
            "INTEREST": InterestStrategy(),
            "DIVIDEND": DividendStrategy(),
            "DEPOSIT": CashInflowStrategy(),
            "TRANSFER_IN": SecurityInflowStrategy(),
            "TRANSFER_OUT": SecurityOutflowStrategy(),
            "MERGER_IN": SecurityInflowStrategy(),
            "EXCHANGE_IN": SecurityInflowStrategy(),
            "REPLACEMENT_IN": SecurityInflowStrategy(),
            "MERGER_OUT": SecurityOutflowStrategy(),
            "EXCHANGE_OUT": SecurityOutflowStrategy(),
            "REPLACEMENT_OUT": SecurityOutflowStrategy(),
            "SPIN_IN": SecurityInflowStrategy(),
            "DEMERGER_IN": SecurityInflowStrategy(),
            "SPIN_OFF": PartialTransferOutStrategy(),
            "DEMERGER_OUT": PartialTransferOutStrategy(),
            "CASH_CONSIDERATION": CashConsiderationStrategy(),
            "CASH_IN_LIEU": CashInLieuStrategy(),
            "MATURITY_REDEMPTION": RedemptionStrategy(),
            "CALL_REDEMPTION": RedemptionStrategy(),
            "PARTIAL_REDEMPTION": RedemptionStrategy(),
            "SPLIT": QuantityRestatementStrategy(),
            "REVERSE_SPLIT": QuantityRestatementStrategy(),
            "CONSOLIDATION": QuantityRestatementStrategy(),
            "BONUS_ISSUE": QuantityRestatementStrategy(),
            "STOCK_DIVIDEND": QuantityRestatementStrategy(),
            "RIGHTS_ANNOUNCE": DefaultStrategy(),
            "RIGHTS_ALLOCATE": SecurityInflowStrategy(),
            "RIGHTS_EXPIRE": SecurityOutflowStrategy(),
            "RIGHTS_ADJUSTMENT": DefaultStrategy(),
            "RIGHTS_SELL": SecurityOutflowStrategy(),
            "RIGHTS_SUBSCRIBE": SecurityOutflowStrategy(),
            "RIGHTS_OVERSUBSCRIBE": SecurityOutflowStrategy(),
            "RIGHTS_REFUND": IncomeStrategy(),
            "RIGHTS_SHARE_DELIVERY": SecurityInflowStrategy(),
            "WITHDRAWAL": SecurityOutflowStrategy(),
            "ADJUSTMENT": AdjustmentStrategy(),
            "FEE": DefaultStrategy(),
            "TAX": UnsupportedTaxStrategy(),
        }

    def _validate_fx(self, t: CostBasisTransaction) -> bool:
        return _validate_transaction_currency_context(t, self._error_reporter)

    def calculate_transaction_costs(self, transaction: CostBasisTransaction) -> None:
        if not self._validate_fx(transaction):
            return
        try:
            transaction.transaction_type = _normalize_transaction_type(transaction.transaction_type)
            if get_transaction_type_definition(transaction.transaction_type) is None:
                self._error_reporter.add_error(
                    transaction.transaction_id,
                    f"Unknown transaction type '{transaction.transaction_type}'.",
                )
                return
        except ValueError:
            self._error_reporter.add_error(
                transaction.transaction_id,
                f"Unknown transaction type '{transaction.transaction_type}'.",
            )
            return
        if _is_cash_instrument(transaction):
            _normalize_cash_movement_inputs(transaction)
        lineage_input = _transaction_cost_input(transaction)
        strategy = self._resolve_strategy(transaction.transaction_type, transaction)
        if strategy is None:
            return
        transaction_id = transaction.transaction_id
        self._disposition_engine.discard_pending_disposal(transaction_id)
        try:
            strategy.calculate_costs(transaction, self._disposition_engine, self._error_reporter)
            if self._error_reporter.has_errors_for(transaction_id):
                return
            transaction.set_calculated_field(
                "calculation_lineage",
                build_calculation_lineage(
                    algorithm_id=TRANSACTION_COST_CALCULATION_ALGORITHM_ID,
                    algorithm_version=TRANSACTION_COST_CALCULATION_ALGORITHM_VERSION,
                    intermediate_precision=TRANSACTION_COST_LEDGER_OUTPUT_V1.working_precision,
                    input_payload=canonical_cost_basis_output_payload(lineage_input),
                    output_payload=canonical_cost_basis_output_payload(
                        transaction_cost_output_payload(transaction)
                    ),
                    numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
                ),
            )
            self._disposition_engine.commit_disposal_record(transaction_id)
        finally:
            self._disposition_engine.discard_pending_disposal(transaction_id)

    def _resolve_strategy(
        self, transaction_type: str, transaction: CostBasisTransaction
    ) -> TransactionCostStrategy | None:
        if not is_production_booking_transaction_type(transaction_type):
            definition = get_transaction_type_definition(transaction_type)
            support_status = (
                definition.calculation_support_status if definition is not None else "unknown"
            )
            self._error_reporter.add_error(
                transaction.transaction_id,
                "CostBasisTransaction type "
                f"'{transaction_type}' is not allowed for production booking "
                f"(registry_status={support_status}).",
            )
            return None

        if _is_cash_instrument(transaction):
            if transaction_type in {
                "SELL",
                "WITHDRAWAL",
                "FEE",
                "TAX",
                "TRANSFER_OUT",
                "MERGER_OUT",
                "EXCHANGE_OUT",
                "REPLACEMENT_OUT",
            }:
                return CashOutflowStrategy()

        strategy = self._strategies.get(transaction_type)
        if strategy is None:
            self._error_reporter.add_error(
                transaction.transaction_id,
                f"No cost calculation strategy is registered for '{transaction_type}'.",
            )
        return strategy


def transaction_cost_output_payload(transaction: CostBasisTransaction) -> dict[str, object]:
    """Return the complete calculated transaction-cost output persisted atomically."""

    return {
        "allocated_cost_basis_base": _optional_transaction_decimal(
            transaction, "allocated_cost_basis_base"
        ),
        "allocated_cost_basis_local": _optional_transaction_decimal(
            transaction, "allocated_cost_basis_local"
        ),
        "fee_components": (transaction.fees.model_dump() if transaction.fees is not None else {}),
        "gross_cost": transaction.gross_cost,
        "lot_restatement": transaction.lot_restatement,
        "net_cost": transaction.net_cost,
        "net_cost_local": transaction.net_cost_local,
        "realized_capital_pnl_base": _optional_transaction_decimal(
            transaction, "realized_capital_pnl_base"
        ),
        "realized_capital_pnl_local": _optional_transaction_decimal(
            transaction, "realized_capital_pnl_local"
        ),
        "realized_fx_pnl_base": _optional_transaction_decimal(transaction, "realized_fx_pnl_base"),
        "realized_fx_pnl_local": _optional_transaction_decimal(
            transaction, "realized_fx_pnl_local"
        ),
        "realized_gain_loss": transaction.realized_gain_loss,
        "realized_gain_loss_local": transaction.realized_gain_loss_local,
        "realized_total_pnl_base": _optional_transaction_decimal(
            transaction, "realized_total_pnl_base"
        ),
        "realized_total_pnl_local": _optional_transaction_decimal(
            transaction, "realized_total_pnl_local"
        ),
        "transaction_fx_rate": transaction.transaction_fx_rate,
        "transaction_id": transaction.transaction_id,
    }


def has_governed_transaction_cost_authority(transaction: Mapping[str, Any]) -> bool:
    """Return whether persisted economics bind current inputs and outputs to Core authority."""

    if transaction.get("net_cost") is None or transaction.get("net_cost_local") is None:
        return False
    lineage = transaction.get("calculation_lineage")
    if not isinstance(lineage, CalculationLineage):
        return False
    if (
        lineage.algorithm_id != TRANSACTION_COST_CALCULATION_ALGORITHM_ID
        or lineage.algorithm_version != TRANSACTION_COST_CALCULATION_ALGORITHM_VERSION
        or lineage.numeric_output_policy != TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity()
    ):
        return False
    try:
        persisted_transaction = CostBasisTransaction(**dict(transaction))
    except (TypeError, ValueError):
        return False
    if lineage.input_content_hash != canonical_content_hash(
        canonical_cost_basis_output_payload(_transaction_cost_input(persisted_transaction))
    ):
        return False
    return bool(
        calculation_lineage_binds_output(
            lineage,
            output_payload=canonical_cost_basis_output_payload(
                transaction_cost_output_payload(persisted_transaction)
            ),
        )
    )


def _transaction_cost_input(transaction: CostBasisTransaction) -> dict[str, object]:
    """Return normalized effective inputs without prior or newly calculated outputs."""

    return cast(
        dict[str, object],
        transaction.model_dump(
            exclude={
                "calculation_lineage",
                "allocated_cost_basis_base",
                "allocated_cost_basis_local",
                # Persistence assigns these operational fields after calculation.
                "created_at",
                "epoch",
                # Settlement owns these generated linkage outputs. They may be persisted only
                # after cost calculation and therefore cannot be cost-basis lineage inputs.
                "economic_event_id",
                "error_reason",
                "external_cash_transaction_id",
                "gross_cost",
                "linked_transaction_group_id",
                "net_cost",
                "net_cost_local",
                # ``fees`` is the normalized component authority. The mapper also carries its
                # aggregate as a string for calculation compatibility, but database scale can
                # change that redundant representation (for example 2.00 -> 2.0000000000).
                # Excluding the duplicate keeps identical financial inputs replay-stable while
                # component or amount changes remain bound through ``fees``.
                "trade_fee",
                "realized_gain_loss",
                "realized_gain_loss_local",
                "realized_capital_pnl_base",
                "realized_capital_pnl_local",
                "realized_fx_pnl_base",
                "realized_fx_pnl_local",
                "realized_total_pnl_base",
                "realized_total_pnl_local",
            }
        ),
    )
