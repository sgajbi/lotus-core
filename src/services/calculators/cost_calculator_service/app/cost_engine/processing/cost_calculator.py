from decimal import Decimal
from typing import Protocol, cast

from portfolio_common.decimal_amounts import decimal_or_none
from portfolio_common.transaction_domain import (
    FxCanonicalTransaction,
    UnsupportedFxRealizedPnlModeError,
    build_fx_baseline_processing_update,
    validate_fx_transaction,
)
from portfolio_common.transaction_type_registry import (
    get_transaction_type_definition,
    is_production_booking_transaction_type,
)

from ..domain.enums.transaction_type import TransactionType
from ..domain.models.transaction import Transaction
from .disposition_engine import DispositionEngine
from .error_reporter import ErrorReporter


class TransactionCostStrategy(Protocol):
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None: ...


ACCRUED_INTEREST_EXCLUDED_FROM_BOOK_COST_POLICIES = {
    "BUY_EXCLUDE_ACCRUED_INTEREST_FROM_BOOK_COST",
}
SELL_ALLOW_OVERSOLD_POLICIES = {
    "SELL_ALLOW_OVERSOLD_POLICY",
}
FX_BASELINE_TRANSACTION_TYPES = {
    TransactionType.FX_SPOT.value,
    TransactionType.FX_FORWARD.value,
    TransactionType.FX_SWAP.value,
}


def _is_accrued_interest_excluded_from_book_cost(transaction: Transaction) -> bool:
    policy_id = _normalize_code(getattr(transaction, "calculation_policy_id", None))
    return policy_id in ACCRUED_INTEREST_EXCLUDED_FROM_BOOK_COST_POLICIES


def _add_buy_invariant_error(
    error_reporter: ErrorReporter, transaction: Transaction, message: str
) -> None:
    error_reporter.add_error(transaction.transaction_id, f"BUY invariant violation: {message}")


def _add_sell_invariant_error(
    error_reporter: ErrorReporter, transaction: Transaction, message: str
) -> None:
    error_reporter.add_error(transaction.transaction_id, f"SELL invariant violation: {message}")


def _add_dividend_invariant_error(
    error_reporter: ErrorReporter, transaction: Transaction, message: str
) -> None:
    error_reporter.add_error(transaction.transaction_id, f"DIVIDEND invariant violation: {message}")


def _add_interest_invariant_error(
    error_reporter: ErrorReporter, transaction: Transaction, message: str
) -> None:
    error_reporter.add_error(transaction.transaction_id, f"INTEREST invariant violation: {message}")


def _normalize_decimal_field(value: object, field_name: str) -> Decimal:
    resolved_value = decimal_or_none(value)
    if resolved_value is None:
        raise ValueError(f"invalid decimal for {field_name}: {value!r}")
    return cast(Decimal, resolved_value)


def _is_cash_instrument(transaction: Transaction) -> bool:
    product_type = _normalize_code(getattr(transaction, "product_type", ""))
    asset_class = _normalize_code(getattr(transaction, "asset_class", ""))
    instrument_id = _normalize_code(getattr(transaction, "instrument_id", ""))
    security_id = _normalize_code(getattr(transaction, "security_id", ""))
    return (
        product_type == "CASH"
        or asset_class == "CASH"
        or instrument_id.startswith("CASH")
        or security_id.startswith("CASH")
    )


def _cash_movement_amount(transaction: Transaction) -> Decimal:
    gross_amount = _decimal_or_zero(
        transaction.gross_transaction_amount,
        field_name="gross_transaction_amount",
    )
    quantity_amount = _decimal_or_zero(transaction.quantity, field_name="quantity")
    movement_amount = gross_amount if not gross_amount.is_zero() else quantity_amount
    return abs(movement_amount)


def _cash_outflow_book_cost(transaction: Transaction) -> Decimal:
    cash_amount = _cash_movement_amount(transaction)
    if _normalize_code(transaction.transaction_type) != TransactionType.FEE.value:
        return cash_amount
    total_fees = transaction.fees.total_fees if transaction.fees else Decimal(0)
    return cash_amount + total_fees


def _decimal_or_zero(value: object, *, field_name: str) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal(0)
    return _normalize_decimal_field(value, field_name)


def _normalize_code(value: object) -> str:
    return str(value or "").strip().upper()


def _normalize_currency_code(currency_code: str) -> str:
    return _normalize_code(currency_code)


def _normalize_transaction_type(transaction_type: str | TransactionType) -> str:
    if isinstance(transaction_type, TransactionType):
        return cast(str, transaction_type.value)
    return str(transaction_type).strip().upper()


def _transaction_fx_rate_or_one(transaction: Transaction) -> Decimal:
    return transaction.transaction_fx_rate or Decimal(1)


def _transaction_total_fees(transaction: Transaction) -> Decimal:
    return transaction.fees.total_fees if transaction.fees else Decimal(0)


def _apply_zero_cost_fields(transaction: Transaction) -> None:
    transaction.net_cost = Decimal(0)
    transaction.net_cost_local = Decimal(0)
    transaction.gross_cost = Decimal(0)


def _apply_zero_realized_pnl(transaction: Transaction) -> None:
    transaction.realized_gain_loss = Decimal(0)
    transaction.realized_gain_loss_local = Decimal(0)


def _apply_no_realized_pnl(transaction: Transaction) -> None:
    transaction.realized_gain_loss = None
    transaction.realized_gain_loss_local = None


def _has_non_zero_cost_fields(transaction: Transaction) -> bool:
    return bool(transaction.net_cost != Decimal(0) or transaction.net_cost_local != Decimal(0))


def _has_non_zero_realized_pnl(transaction: Transaction) -> bool:
    return bool(
        transaction.realized_gain_loss != Decimal(0)
        or transaction.realized_gain_loss_local != Decimal(0)
    )


def _normalized_price_or_error(
    transaction: Transaction,
    error_reporter: ErrorReporter,
    add_invariant_error,
) -> Decimal | None:
    try:
        return _normalize_decimal_field(getattr(transaction, "price", Decimal(0)), "price")
    except ValueError as exc:
        add_invariant_error(error_reporter, transaction, str(exc))
        return None


def _validate_zero_quantity_and_price(
    transaction: Transaction,
    error_reporter: ErrorReporter,
    *,
    transaction_label: str,
    add_invariant_error,
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
    transaction: Transaction,
    error_reporter: ErrorReporter,
    *,
    realized_label: str,
    add_invariant_error,
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


def _apply_buy_cost_fields(transaction: Transaction) -> None:
    total_fees_local = _transaction_total_fees(transaction)
    accrued_interest_local = transaction.accrued_interest or Decimal(0)
    fx_rate = _transaction_fx_rate_or_one(transaction)
    transaction.gross_cost = transaction.gross_transaction_amount * fx_rate

    transaction.net_cost_local = transaction.gross_transaction_amount + total_fees_local
    if not _is_accrued_interest_excluded_from_book_cost(transaction):
        transaction.net_cost_local += accrued_interest_local

    transaction.net_cost = transaction.net_cost_local * fx_rate
    _apply_zero_realized_pnl(transaction)


def _validate_buy_cost_fields(transaction: Transaction, error_reporter: ErrorReporter) -> bool:
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
    transaction: Transaction, error_reporter: ErrorReporter
) -> bool:
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
    transaction: Transaction,
    disposition_engine: DispositionEngine,
    error_reporter: ErrorReporter,
) -> None:
    try:
        disposition_engine.add_buy_lot(transaction)
    except ValueError as e:
        error_reporter.add_error(transaction.transaction_id, str(e))


def _net_sell_proceeds_local(transaction: Transaction) -> Decimal:
    return cast(Decimal, transaction.gross_transaction_amount) - _transaction_total_fees(
        transaction
    )


def _validate_sell_quantity_and_proceeds(
    transaction: Transaction,
    error_reporter: ErrorReporter,
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


def _validate_sell_availability(
    transaction: Transaction,
    disposition_engine: DispositionEngine,
    error_reporter: ErrorReporter,
) -> bool:
    available_quantity = disposition_engine.get_available_quantity(
        transaction.portfolio_id, transaction.instrument_id
    )
    policy_id = _normalize_code(getattr(transaction, "calculation_policy_id", None))
    if transaction.quantity <= available_quantity:
        return True
    if policy_id in SELL_ALLOW_OVERSOLD_POLICIES:
        _add_sell_invariant_error(
            error_reporter,
            transaction,
            "oversold policy is configured but not supported in current engine.",
        )
    else:
        _add_sell_invariant_error(
            error_reporter,
            transaction,
            "sell quantity exceeds available holdings under strict oversell policy.",
        )
    return False


def _consume_sell_cost_basis(
    transaction: Transaction,
    disposition_engine: DispositionEngine,
    error_reporter: ErrorReporter,
) -> tuple[Decimal, Decimal, Decimal] | None:
    cogs_base, cogs_local, consumed_quantity, error_reason = (
        disposition_engine.consume_sell_quantity(transaction)
    )

    if error_reason:
        error_reporter.add_error(transaction.transaction_id, error_reason)
        return None
    if consumed_quantity <= Decimal(0):
        _add_sell_invariant_error(error_reporter, transaction, "consumed_quantity must be > 0.")
        return None
    if cogs_base < Decimal(0) or cogs_local < Decimal(0):
        _add_sell_invariant_error(
            error_reporter,
            transaction,
            "disposed cost basis must be non-negative.",
        )
        return None
    return cogs_base, cogs_local, consumed_quantity


def _apply_sell_disposal_fields(
    transaction: Transaction,
    *,
    net_sell_proceeds_local: Decimal,
    net_sell_proceeds_base: Decimal,
    cogs_base: Decimal,
    cogs_local: Decimal,
) -> None:
    transaction.realized_gain_loss_local = net_sell_proceeds_local - cogs_local
    transaction.realized_gain_loss = net_sell_proceeds_base - cogs_base
    transaction.net_cost = -cogs_base
    transaction.net_cost_local = -cogs_local
    transaction.gross_cost = -cogs_base


def _validate_sell_disposal_fields(transaction: Transaction, error_reporter: ErrorReporter) -> bool:
    if transaction.net_cost <= Decimal(0) and transaction.net_cost_local <= Decimal(0):
        return True
    _add_sell_invariant_error(
        error_reporter,
        transaction,
        "net_cost and net_cost_local must be <= 0 for SELL disposal.",
    )
    return False


def _resolve_interest_direction(
    transaction: Transaction,
    error_reporter: ErrorReporter,
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


def _normalize_transaction_currencies(transaction: Transaction) -> None:
    transaction.trade_currency = _normalize_currency_code(transaction.trade_currency)
    transaction.portfolio_base_currency = _normalize_currency_code(
        transaction.portfolio_base_currency
    )


def _normalize_existing_transaction_fx_rate(
    transaction: Transaction,
    error_reporter: ErrorReporter,
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
    transaction: Transaction,
    error_reporter: ErrorReporter,
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
    transaction: Transaction,
    error_reporter: ErrorReporter,
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
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        _apply_buy_cost_fields(transaction)
        if not _validate_buy_cost_fields(transaction, error_reporter):
            return

        _record_buy_lot(transaction, disposition_engine, error_reporter)


class SellStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        net_sell_proceeds_local = _net_sell_proceeds_local(transaction)
        fx_rate = _transaction_fx_rate_or_one(transaction)
        net_sell_proceeds_base = net_sell_proceeds_local * fx_rate
        if not _validate_sell_quantity_and_proceeds(
            transaction,
            error_reporter,
            net_sell_proceeds_local=net_sell_proceeds_local,
            net_sell_proceeds_base=net_sell_proceeds_base,
        ):
            return
        if not _validate_sell_availability(transaction, disposition_engine, error_reporter):
            return

        consumed_cost_basis = _consume_sell_cost_basis(
            transaction, disposition_engine, error_reporter
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


class CashInflowStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        cash_amount_local = _cash_movement_amount(transaction)
        transaction.gross_cost = cash_amount_local
        transaction.net_cost_local = cash_amount_local
        fx_rate = _transaction_fx_rate_or_one(transaction)
        transaction.net_cost = transaction.net_cost_local * fx_rate
        cash_buy_equivalent = transaction.model_copy()
        cash_buy_equivalent.quantity = cash_amount_local

        disposition_engine.add_buy_lot(cash_buy_equivalent)


class CashOutflowStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        cash_amount_local = _cash_outflow_book_cost(transaction)
        fx_rate = _transaction_fx_rate_or_one(transaction)
        transaction.net_cost_local = -cash_amount_local
        transaction.net_cost = transaction.net_cost_local * fx_rate
        transaction.gross_cost = transaction.net_cost
        _apply_no_realized_pnl(transaction)


class SecurityInflowStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount

        fx_rate = _transaction_fx_rate_or_one(transaction)
        transaction.net_cost = transaction.net_cost_local * fx_rate

        if transaction.quantity > Decimal(0):
            _record_buy_lot(transaction, disposition_engine, error_reporter)


class SecurityOutflowStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        """Consumes a cost lot for a security transfer out, but does not realize a P&L."""
        cogs_base, cogs_local, consumed_quantity, error_reason = (
            disposition_engine.consume_sell_quantity(transaction)
        )

        if error_reason:
            error_reporter.add_error(transaction.transaction_id, error_reason)
            return

        if consumed_quantity > Decimal(0):
            transaction.net_cost = -cogs_base
            transaction.net_cost_local = -cogs_local
            transaction.gross_cost = -cogs_base
            _apply_no_realized_pnl(transaction)


class PartialTransferOutStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
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
        basis_out_base = basis_out_local * fx_rate
        transaction.net_cost_local = -basis_out_local
        transaction.net_cost = -basis_out_base
        transaction.gross_cost = -basis_out_base
        _apply_no_realized_pnl(transaction)


class IncomeStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        _apply_zero_cost_fields(transaction)
        _apply_no_realized_pnl(transaction)


class QuantityRestatementStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        """
        Handles same-instrument corporate-action quantity restatements where
        quantity changes but total basis must remain unchanged.
        """
        _apply_zero_cost_fields(transaction)
        _apply_zero_realized_pnl(transaction)


class DividendStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
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
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
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
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount
        fx_rate = _transaction_fx_rate_or_one(transaction)
        transaction.net_cost = transaction.net_cost_local * fx_rate


class UnsupportedTaxStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        error_reporter.add_error(
            transaction.transaction_id,
            "TAX must be represented as a cash instrument outflow.",
        )


class FxBaselineStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        if not _validate_canonical_fx_transaction(transaction, error_reporter):
            return
        try:
            update = build_fx_baseline_processing_update(transaction)
        except UnsupportedFxRealizedPnlModeError as exc:
            error_reporter.add_error(transaction.transaction_id, str(exc))
            return
        for field_name, field_value in update.items():
            setattr(transaction, field_name, field_value)


def _validate_canonical_fx_transaction(
    transaction: Transaction,
    error_reporter: ErrorReporter,
) -> bool:
    try:
        canonical = FxCanonicalTransaction.model_validate(transaction.model_dump(mode="python"))
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


class CostCalculator:
    def __init__(self, disposition_engine: DispositionEngine, error_reporter: ErrorReporter):
        self._disposition_engine = disposition_engine
        self._error_reporter = error_reporter
        self._strategies: dict[TransactionType, TransactionCostStrategy] = {
            TransactionType.BUY: BuyStrategy(),
            TransactionType.SELL: SellStrategy(),
            TransactionType.FX_SPOT: FxBaselineStrategy(),
            TransactionType.FX_FORWARD: FxBaselineStrategy(),
            TransactionType.FX_SWAP: FxBaselineStrategy(),
            TransactionType.INTEREST: InterestStrategy(),
            TransactionType.DIVIDEND: DividendStrategy(),
            TransactionType.DEPOSIT: CashInflowStrategy(),
            TransactionType.TRANSFER_IN: SecurityInflowStrategy(),
            TransactionType.TRANSFER_OUT: SecurityOutflowStrategy(),
            TransactionType.MERGER_IN: SecurityInflowStrategy(),
            TransactionType.EXCHANGE_IN: SecurityInflowStrategy(),
            TransactionType.REPLACEMENT_IN: SecurityInflowStrategy(),
            TransactionType.MERGER_OUT: SecurityOutflowStrategy(),
            TransactionType.EXCHANGE_OUT: SecurityOutflowStrategy(),
            TransactionType.REPLACEMENT_OUT: SecurityOutflowStrategy(),
            TransactionType.SPIN_IN: SecurityInflowStrategy(),
            TransactionType.DEMERGER_IN: SecurityInflowStrategy(),
            TransactionType.SPIN_OFF: PartialTransferOutStrategy(),
            TransactionType.DEMERGER_OUT: PartialTransferOutStrategy(),
            TransactionType.CASH_CONSIDERATION: IncomeStrategy(),
            TransactionType.CASH_IN_LIEU: SellStrategy(),
            TransactionType.SPLIT: QuantityRestatementStrategy(),
            TransactionType.REVERSE_SPLIT: QuantityRestatementStrategy(),
            TransactionType.CONSOLIDATION: QuantityRestatementStrategy(),
            TransactionType.BONUS_ISSUE: QuantityRestatementStrategy(),
            TransactionType.STOCK_DIVIDEND: QuantityRestatementStrategy(),
            TransactionType.RIGHTS_ANNOUNCE: DefaultStrategy(),
            TransactionType.RIGHTS_ALLOCATE: SecurityInflowStrategy(),
            TransactionType.RIGHTS_EXPIRE: SecurityOutflowStrategy(),
            TransactionType.RIGHTS_ADJUSTMENT: DefaultStrategy(),
            TransactionType.RIGHTS_SELL: SecurityOutflowStrategy(),
            TransactionType.RIGHTS_SUBSCRIBE: SecurityOutflowStrategy(),
            TransactionType.RIGHTS_OVERSUBSCRIBE: SecurityOutflowStrategy(),
            TransactionType.RIGHTS_REFUND: IncomeStrategy(),
            TransactionType.RIGHTS_SHARE_DELIVERY: SecurityInflowStrategy(),
            TransactionType.WITHDRAWAL: SecurityOutflowStrategy(),
            TransactionType.ADJUSTMENT: DefaultStrategy(),
            TransactionType.FEE: DefaultStrategy(),
            TransactionType.TAX: UnsupportedTaxStrategy(),
        }

    def _validate_fx(self, t: Transaction) -> bool:
        return _validate_transaction_currency_context(t, self._error_reporter)

    def calculate_transaction_costs(self, transaction: Transaction):
        if not self._validate_fx(transaction):
            return
        try:
            transaction.transaction_type = _normalize_transaction_type(transaction.transaction_type)
            if transaction.transaction_type not in TransactionType.list():
                self._error_reporter.add_error(
                    transaction.transaction_id,
                    f"Unknown transaction type '{transaction.transaction_type}'.",
                )
                return
            transaction_type_enum = TransactionType(transaction.transaction_type)
        except ValueError:
            self._error_reporter.add_error(
                transaction.transaction_id,
                f"Unknown transaction type '{transaction.transaction_type}'.",
            )
            return
        strategy = self._resolve_strategy(transaction_type_enum, transaction)
        if strategy is None:
            return
        strategy.calculate_costs(transaction, self._disposition_engine, self._error_reporter)

    def _resolve_strategy(
        self, transaction_type: TransactionType, transaction: Transaction
    ) -> TransactionCostStrategy | None:
        if not is_production_booking_transaction_type(transaction_type.value):
            definition = get_transaction_type_definition(transaction_type.value)
            support_status = (
                definition.calculation_support_status if definition is not None else "unknown"
            )
            self._error_reporter.add_error(
                transaction.transaction_id,
                "Transaction type "
                f"'{transaction_type.value}' is not allowed for production booking "
                f"(registry_status={support_status}).",
            )
            return None

        if _is_cash_instrument(transaction):
            if transaction_type in {
                TransactionType.SELL,
                TransactionType.WITHDRAWAL,
                TransactionType.FEE,
                TransactionType.TAX,
                TransactionType.TRANSFER_OUT,
                TransactionType.MERGER_OUT,
                TransactionType.EXCHANGE_OUT,
                TransactionType.REPLACEMENT_OUT,
            }:
                return CashOutflowStrategy()

        strategy = self._strategies.get(transaction_type)
        if strategy is None:
            self._error_reporter.add_error(
                transaction.transaction_id,
                f"No cost calculation strategy is registered for '{transaction_type.value}'.",
            )
        return strategy
