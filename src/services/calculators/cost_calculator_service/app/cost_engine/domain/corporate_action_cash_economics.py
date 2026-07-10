from dataclasses import dataclass
from decimal import Decimal


class CorporateActionCashEconomicsError(ValueError):
    """Raised when source-provided corporate-action cash economics do not reconcile."""


@dataclass(frozen=True, slots=True)
class CorporateActionCashEconomics:
    net_proceeds_local: Decimal
    net_proceeds_base: Decimal
    allocated_cost_basis_local: Decimal
    allocated_cost_basis_base: Decimal
    realized_capital_pnl_local: Decimal
    realized_fx_pnl_local: Decimal
    realized_total_pnl_local: Decimal
    realized_capital_pnl_base: Decimal
    realized_fx_pnl_base: Decimal
    realized_total_pnl_base: Decimal


def calculate_corporate_action_cash_economics(
    *,
    gross_proceeds_local: Decimal,
    fees_local: Decimal,
    allocated_cost_basis_local: Decimal | None,
    allocated_cost_basis_base: Decimal | None,
    local_currency: str,
    base_currency: str,
    transaction_fx_rate: Decimal,
    realized_capital_pnl_local: Decimal | None = None,
    realized_fx_pnl_local: Decimal | None = None,
    realized_total_pnl_local: Decimal | None = None,
    realized_capital_pnl_base: Decimal | None = None,
    realized_fx_pnl_base: Decimal | None = None,
    realized_total_pnl_base: Decimal | None = None,
) -> CorporateActionCashEconomics:
    """Calculate auditable cash-consideration basis disposal and realized P&L."""
    _validate_non_negative(gross_proceeds_local, "gross_proceeds_local")
    _validate_non_negative(fees_local, "fees_local")
    if transaction_fx_rate <= 0:
        raise CorporateActionCashEconomicsError("transaction_fx_rate must be greater than 0")

    basis_local = _required_non_negative_basis(
        allocated_cost_basis_local, "allocated_cost_basis_local"
    )
    basis_base = _required_non_negative_basis(
        allocated_cost_basis_base, "allocated_cost_basis_base"
    )
    net_proceeds_local = gross_proceeds_local - fees_local
    if net_proceeds_local < 0:
        raise CorporateActionCashEconomicsError("fees_local must not exceed gross_proceeds_local")
    net_proceeds_base = net_proceeds_local * transaction_fx_rate
    expected_total_local = net_proceeds_local - basis_local
    expected_total_base = net_proceeds_base - basis_base

    same_currency = _currency(local_currency) == _currency(base_currency)
    if same_currency:
        expected_basis_base = basis_local * transaction_fx_rate
        if basis_base != expected_basis_base:
            raise CorporateActionCashEconomicsError(
                "allocated_cost_basis_base must equal allocated_cost_basis_local converted "
                "at transaction_fx_rate for same-currency consideration"
            )
        capital_local, fx_local = _same_currency_components(
            expected_total=expected_total_local,
            provided_capital=realized_capital_pnl_local,
            provided_fx=realized_fx_pnl_local,
            currency_basis="local",
        )
        capital_base, fx_base = _same_currency_components(
            expected_total=expected_total_base,
            provided_capital=realized_capital_pnl_base,
            provided_fx=realized_fx_pnl_base,
            currency_basis="base",
        )
    else:
        capital_local, fx_local = _required_cross_currency_components(
            provided_capital=realized_capital_pnl_local,
            provided_fx=realized_fx_pnl_local,
            expected_total=expected_total_local,
            currency_basis="local",
        )
        capital_base, fx_base = _required_cross_currency_components(
            provided_capital=realized_capital_pnl_base,
            provided_fx=realized_fx_pnl_base,
            expected_total=expected_total_base,
            currency_basis="base",
        )

    _validate_optional_total(
        provided=realized_total_pnl_local,
        expected=expected_total_local,
        field_name="realized_total_pnl_local",
    )
    _validate_optional_total(
        provided=realized_total_pnl_base,
        expected=expected_total_base,
        field_name="realized_total_pnl_base",
    )
    return CorporateActionCashEconomics(
        net_proceeds_local=net_proceeds_local,
        net_proceeds_base=net_proceeds_base,
        allocated_cost_basis_local=basis_local,
        allocated_cost_basis_base=basis_base,
        realized_capital_pnl_local=capital_local,
        realized_fx_pnl_local=fx_local,
        realized_total_pnl_local=expected_total_local,
        realized_capital_pnl_base=capital_base,
        realized_fx_pnl_base=fx_base,
        realized_total_pnl_base=expected_total_base,
    )


def _currency(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        raise CorporateActionCashEconomicsError("currency must not be empty")
    return normalized


def _validate_non_negative(value: Decimal, field_name: str) -> None:
    if value < 0:
        raise CorporateActionCashEconomicsError(f"{field_name} must be greater than or equal to 0")


def _required_non_negative_basis(value: Decimal | None, field_name: str) -> Decimal:
    if value is None:
        raise CorporateActionCashEconomicsError(f"{field_name} is required")
    _validate_non_negative(value, field_name)
    return value


def _same_currency_components(
    *,
    expected_total: Decimal,
    provided_capital: Decimal | None,
    provided_fx: Decimal | None,
    currency_basis: str,
) -> tuple[Decimal, Decimal]:
    capital = expected_total if provided_capital is None else provided_capital
    fx = Decimal(0) if provided_fx is None else provided_fx
    if capital != expected_total or fx != 0:
        raise CorporateActionCashEconomicsError(
            f"same-currency realized P&L {currency_basis} components must assign total P&L "
            "to capital and zero to FX"
        )
    return capital, fx


def _required_cross_currency_components(
    *,
    provided_capital: Decimal | None,
    provided_fx: Decimal | None,
    expected_total: Decimal,
    currency_basis: str,
) -> tuple[Decimal, Decimal]:
    if provided_capital is None or provided_fx is None:
        raise CorporateActionCashEconomicsError(
            f"cross-currency realized capital and FX P&L {currency_basis} components are required"
        )
    if provided_capital + provided_fx != expected_total:
        raise CorporateActionCashEconomicsError(
            f"cross-currency realized capital and FX P&L {currency_basis} components must "
            "reconcile to proceeds less allocated basis"
        )
    return provided_capital, provided_fx


def _validate_optional_total(
    *, provided: Decimal | None, expected: Decimal, field_name: str
) -> None:
    if provided is not None and provided != expected:
        raise CorporateActionCashEconomicsError(
            f"{field_name} must reconcile to proceeds less allocated basis"
        )
