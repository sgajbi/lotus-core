# libs/financial-calculator-engine/src/logic/cost_calculator.py
from decimal import Decimal
from typing import Protocol

from core.enums.transaction_type import TransactionType
from core.models.transaction import Transaction
from logic.disposition_engine import DispositionEngine
from logic.error_reporter import ErrorReporter


class TransactionCostStrategy(Protocol):
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None: ...

ACCRUED_INTEREST_EXCLUDED_FROM_BOOK_COST_POLICIES = {
    "BUY_EXCLUDE_ACCRUED_INTEREST_FROM_BOOK_COST",
}
SELL_ALLOW_OVERSOLD_POLICIES = {
    "SELL_ALLOW_OVERSOLD_POLICY",
}


def _is_accrued_interest_excluded_from_book_cost(transaction: Transaction) -> bool:
    policy_id = getattr(transaction, "calculation_policy_id", None)
    return isinstance(policy_id, str) and policy_id in ACCRUED_INTEREST_EXCLUDED_FROM_BOOK_COST_POLICIES


def _add_buy_invariant_error(error_reporter: ErrorReporter, transaction: Transaction, message: str) -> None:
    error_reporter.add_error(transaction.transaction_id, f"BUY invariant violation: {message}")


def _add_sell_invariant_error(
    error_reporter: ErrorReporter, transaction: Transaction, message: str
) -> None:
    error_reporter.add_error(transaction.transaction_id, f"SELL invariant violation: {message}")


def _add_dividend_invariant_error(
    error_reporter: ErrorReporter, transaction: Transaction, message: str
) -> None:
    error_reporter.add_error(
        transaction.transaction_id, f"DIVIDEND invariant violation: {message}"
    )


def _normalize_decimal_field(value: object, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:  # pragma: no cover - defensive normalization path
        raise ValueError(f"invalid decimal for {field_name}: {value!r}") from exc


class BuyStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        total_fees_local = transaction.fees.total_fees if transaction.fees else Decimal(0)
        accrued_interest_local = transaction.accrued_interest or Decimal(0)

        # Principal in base currency for consistent accounting output.
        fx_rate = transaction.transaction_fx_rate or Decimal(1)
        transaction.gross_cost = transaction.gross_transaction_amount * fx_rate

        if _is_accrued_interest_excluded_from_book_cost(transaction):
            transaction.net_cost_local = transaction.gross_transaction_amount + total_fees_local
        else:
            transaction.net_cost_local = transaction.gross_transaction_amount + total_fees_local + accrued_interest_local

        transaction.net_cost = transaction.net_cost_local * fx_rate
        transaction.realized_gain_loss = Decimal(0)
        transaction.realized_gain_loss_local = Decimal(0)

        if transaction.quantity <= Decimal(0):
            _add_buy_invariant_error(error_reporter, transaction, "quantity_delta must be > 0.")
            return
        if transaction.gross_cost < Decimal(0):
            _add_buy_invariant_error(error_reporter, transaction, "gross_cost must be >= 0.")
            return
        if transaction.net_cost_local < Decimal(0):
            _add_buy_invariant_error(error_reporter, transaction, "book_cost_local must be >= 0.")
            return
        if transaction.net_cost < Decimal(0):
            _add_buy_invariant_error(error_reporter, transaction, "book_cost_base must be >= 0.")
            return
        if transaction.realized_gain_loss != Decimal(0) or transaction.realized_gain_loss_local != Decimal(0):
            _add_buy_invariant_error(error_reporter, transaction, "realized P&L must be explicit zero for BUY.")
            return
        
        if transaction.quantity > Decimal(0):
            try:
                disposition_engine.add_buy_lot(transaction)
            except ValueError as e:
                error_reporter.add_error(transaction.transaction_id, str(e))

class SellStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        sell_fees_local = transaction.fees.total_fees if transaction.fees else Decimal(0)
        net_sell_proceeds_local = transaction.gross_transaction_amount - sell_fees_local
        if net_sell_proceeds_local < Decimal(0):
            _add_sell_invariant_error(
                error_reporter,
                transaction,
                "net_sell_proceeds_local must be >= 0.",
            )
            return

        fx_rate = transaction.transaction_fx_rate or Decimal(1)
        net_sell_proceeds_base = net_sell_proceeds_local * fx_rate
        if net_sell_proceeds_base < Decimal(0):
            _add_sell_invariant_error(
                error_reporter,
                transaction,
                "net_sell_proceeds_base must be >= 0.",
            )
            return
        
        available_quantity = disposition_engine.get_available_quantity(
            transaction.portfolio_id, transaction.instrument_id
        )
        policy_id = getattr(transaction, "calculation_policy_id", None)
        allows_oversold = (
            isinstance(policy_id, str)
            and policy_id in SELL_ALLOW_OVERSOLD_POLICIES
        )
        if transaction.quantity > available_quantity:
            if allows_oversold:
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
            return

        cogs_base, cogs_local, consumed_quantity, error_reason = disposition_engine.consume_sell_quantity(transaction)
        
        if error_reason:
            error_reporter.add_error(transaction.transaction_id, error_reason)
            return

        if consumed_quantity <= Decimal(0):
            _add_sell_invariant_error(
                error_reporter, transaction, "consumed_quantity must be > 0."
            )
            return

        if cogs_base < Decimal(0) or cogs_local < Decimal(0):
            _add_sell_invariant_error(
                error_reporter,
                transaction,
                "disposed cost basis must be non-negative.",
            )
            return

        transaction.realized_gain_loss_local = net_sell_proceeds_local - cogs_local
        transaction.realized_gain_loss = net_sell_proceeds_base - cogs_base
        transaction.net_cost = -cogs_base
        transaction.net_cost_local = -cogs_local
        transaction.gross_cost = -cogs_base

        if transaction.net_cost > Decimal(0) or transaction.net_cost_local > Decimal(0):
            _add_sell_invariant_error(
                error_reporter,
                transaction,
                "net_cost and net_cost_local must be <= 0 for SELL disposal.",
            )
            return

class CashInflowStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount
        fx_rate = transaction.transaction_fx_rate or Decimal(1)
        transaction.net_cost = transaction.net_cost_local * fx_rate
        cash_buy_equivalent = transaction.model_copy()
        cash_buy_equivalent.quantity = transaction.gross_transaction_amount
        
        
        disposition_engine.add_buy_lot(cash_buy_equivalent)

class SecurityInflowStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount
        
        fx_rate = transaction.transaction_fx_rate or Decimal(1)
        transaction.net_cost = transaction.net_cost_local * fx_rate
        
        if transaction.quantity > Decimal(0):
            try:
                disposition_engine.add_buy_lot(transaction)
            except ValueError as e:
                error_reporter.add_error(transaction.transaction_id, str(e))

class SecurityOutflowStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        """Consumes a cost lot for a security transfer out, but does not realize a P&L."""
        cogs_base, cogs_local, consumed_quantity, error_reason = disposition_engine.consume_sell_quantity(transaction)
        
        if error_reason:
            error_reporter.add_error(transaction.transaction_id, error_reason)
            return

        if consumed_quantity > Decimal(0):
            transaction.net_cost = -cogs_base
            transaction.net_cost_local = -cogs_local
            transaction.gross_cost = -cogs_base
            transaction.realized_gain_loss = None
            transaction.realized_gain_loss_local = None

class IncomeStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.net_cost = Decimal(0)
        transaction.net_cost_local = Decimal(0)
        transaction.gross_cost = Decimal(0)
        transaction.realized_gain_loss = None
        transaction.realized_gain_loss_local = None


class DividendStrategy:
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter,
    ) -> None:
        transaction.net_cost = Decimal(0)
        transaction.net_cost_local = Decimal(0)
        transaction.gross_cost = Decimal(0)
        transaction.realized_gain_loss = Decimal(0)
        transaction.realized_gain_loss_local = Decimal(0)

        if transaction.quantity != Decimal(0):
            _add_dividend_invariant_error(
                error_reporter, transaction, "quantity_delta must be 0 for DIVIDEND."
            )
            return

        try:
            price = _normalize_decimal_field(getattr(transaction, "price", Decimal(0)), "price")
        except ValueError as exc:
            _add_dividend_invariant_error(error_reporter, transaction, str(exc))
            return

        if price != Decimal(0):
            _add_dividend_invariant_error(
                error_reporter, transaction, "price must be 0 for DIVIDEND."
            )
            return

        if transaction.gross_transaction_amount <= Decimal(0):
            _add_dividend_invariant_error(
                error_reporter,
                transaction,
                "gross_dividend_local must be > 0 for DIVIDEND.",
            )
            return

        if transaction.net_cost != Decimal(0) or transaction.net_cost_local != Decimal(0):
            _add_dividend_invariant_error(
                error_reporter, transaction, "net_cost and net_cost_local must be 0."
            )
            return

        if (
            transaction.realized_gain_loss != Decimal(0)
            or transaction.realized_gain_loss_local != Decimal(0)
        ):
            _add_dividend_invariant_error(
                error_reporter,
                transaction,
                "realized capital/FX P&L must be explicit zero for DIVIDEND.",
            )
            return

class DefaultStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount
        fx_rate = transaction.transaction_fx_rate or Decimal(1)
        transaction.net_cost = transaction.net_cost_local * fx_rate

class CostCalculator:
    def __init__(self, disposition_engine: DispositionEngine, error_reporter: ErrorReporter):
        self._disposition_engine = disposition_engine
        self._error_reporter = error_reporter
        self._strategies: dict[TransactionType, TransactionCostStrategy] = {
            TransactionType.BUY: BuyStrategy(),
            TransactionType.SELL: SellStrategy(),
            TransactionType.INTEREST: IncomeStrategy(),
            TransactionType.DIVIDEND: DividendStrategy(),
            TransactionType.DEPOSIT: CashInflowStrategy(),
            TransactionType.TRANSFER_IN: SecurityInflowStrategy(),
            TransactionType.TRANSFER_OUT: SecurityOutflowStrategy(),
            TransactionType.WITHDRAWAL: SecurityOutflowStrategy(),
            TransactionType.FEE: DefaultStrategy(),
            TransactionType.OTHER: DefaultStrategy(),
        }
        self._default_strategy = DefaultStrategy()

    def _validate_fx(self, t: Transaction) -> bool:
        if t.trade_currency == t.portfolio_base_currency:
            if not t.transaction_fx_rate:
                t.transaction_fx_rate = Decimal(1)
            return True
        if t.transaction_fx_rate is None or t.transaction_fx_rate <= 0:
            self._error_reporter.add_error(
                t.transaction_id,
                f"Missing/invalid FX rate for cross-currency transaction from {t.trade_currency} to {t.portfolio_base_currency}."
            )
            return False
        return True

    def calculate_transaction_costs(self, transaction: Transaction):
        if not self._validate_fx(transaction):
            return
        try:
            if transaction.transaction_type not in TransactionType.list():
                self._error_reporter.add_error(transaction.transaction_id, f"Unknown transaction type '{transaction.transaction_type}'.")
                return
            transaction_type_enum = TransactionType(transaction.transaction_type)
        except ValueError:
            self._error_reporter.add_error(transaction.transaction_id, f"Unknown transaction type '{transaction.transaction_type}'.")
            return
        strategy = self._strategies.get(transaction_type_enum, self._default_strategy)
        strategy.calculate_costs(transaction, self._disposition_engine, self._error_reporter)
