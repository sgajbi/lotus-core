from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .control_code_normalization import normalize_transaction_control_code
from .fx_models import (
    FX_BUSINESS_TRANSACTION_TYPES,
    FX_CASH_LEG_ROLES,
    FX_COMPONENT_TYPES,
    FX_RATE_QUOTE_CONVENTIONS,
    FX_REALIZED_PNL_MODES,
    FX_SPOT_EXPOSURE_MODELS,
    FxCanonicalTransaction,
)
from .fx_reason_codes import FxValidationReasonCode


@dataclass(frozen=True)
class FxValidationIssue:
    code: FxValidationReasonCode
    field: str
    message: str


class FxValidationError(ValueError):
    def __init__(self, issues: Iterable[FxValidationIssue]) -> None:
        self.issues = list(issues)
        message = "; ".join(f"{i.code}: {i.field}" for i in self.issues)
        super().__init__(message or "FX validation failed")


@dataclass(frozen=True)
class _NormalizedFxCodes:
    transaction_type: str
    component_type: str
    quote_convention: str
    cash_leg_role: str
    spot_exposure_model: str
    realized_pnl_mode: str


def _validate_zero(
    *,
    issues: list[FxValidationIssue],
    value: Decimal,
    field: str,
    code: FxValidationReasonCode,
    message: str,
) -> None:
    if value != Decimal(0):
        issues.append(FxValidationIssue(code=code, field=field, message=message))


def _validate_realized_total_identity(
    *,
    issues: list[FxValidationIssue],
    capital: Decimal | None,
    fx: Decimal | None,
    total: Decimal | None,
    total_field: str,
) -> None:
    if total is None or fx is None:
        return
    expected_total = (capital or Decimal(0)) + fx
    if total != expected_total:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.REALIZED_TOTAL_PNL_MISMATCH,
                field=total_field,
                message=f"{total_field} must equal realized_capital_pnl + realized_fx_pnl.",
            )
        )


def validate_fx_transaction(
    txn: FxCanonicalTransaction, *, strict_metadata: bool = False
) -> list[FxValidationIssue]:
    issues: list[FxValidationIssue] = []
    normalized = _normalized_fx_codes(txn)
    _validate_control_codes(issues, normalized)
    _validate_component_identity(issues, txn)
    _validate_zero_quantity_and_price(issues, txn)
    _validate_settlement_dates(issues, txn)
    _validate_currency_pair(issues, txn)
    _validate_quote_convention(issues, normalized)
    _validate_positive_amounts_and_rate(issues, txn)
    _validate_strict_metadata(issues, txn, strict_metadata=strict_metadata)
    _validate_cash_settlement_component(issues, txn, normalized)
    _validate_contract_identifier(issues, txn, normalized)
    _validate_swap_structure(issues, txn, normalized)
    _validate_optional_policy_modes(issues, txn, normalized)
    _validate_realized_pnl_fields(issues, txn)
    return issues


def _normalized_fx_codes(txn: FxCanonicalTransaction) -> _NormalizedFxCodes:
    return _NormalizedFxCodes(
        transaction_type=normalize_transaction_control_code(txn.transaction_type),
        component_type=normalize_transaction_control_code(txn.component_type),
        quote_convention=normalize_transaction_control_code(txn.fx_rate_quote_convention),
        cash_leg_role=normalize_transaction_control_code(txn.fx_cash_leg_role),
        spot_exposure_model=normalize_transaction_control_code(txn.spot_exposure_model),
        realized_pnl_mode=normalize_transaction_control_code(txn.fx_realized_pnl_mode),
    )


def _validate_control_codes(
    issues: list[FxValidationIssue],
    normalized: _NormalizedFxCodes,
) -> None:
    if normalized.transaction_type not in FX_BUSINESS_TRANSACTION_TYPES:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.INVALID_TRANSACTION_TYPE,
                field="transaction_type",
                message="transaction_type must be FX_SPOT, FX_FORWARD, or FX_SWAP.",
            )
        )
    if normalized.component_type not in FX_COMPONENT_TYPES:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.INVALID_COMPONENT_TYPE,
                field="component_type",
                message=(
                    "component_type must be FX_CONTRACT_OPEN, FX_CONTRACT_CLOSE, "
                    "FX_CASH_SETTLEMENT_BUY, or FX_CASH_SETTLEMENT_SELL."
                ),
            )
        )


def _validate_component_identity(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
) -> None:
    if not (txn.component_id or "").strip():
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.MISSING_COMPONENT_ID,
                field="component_id",
                message="component_id is required for canonical FX validation.",
            )
        )


def _validate_zero_quantity_and_price(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
) -> None:
    _validate_zero(
        issues=issues,
        value=txn.quantity,
        field="quantity",
        code=FxValidationReasonCode.NON_ZERO_QUANTITY,
        message="quantity must be zero for canonical FX transactions.",
    )
    _validate_zero(
        issues=issues,
        value=txn.price,
        field="price",
        code=FxValidationReasonCode.NON_ZERO_PRICE,
        message="price must be zero for canonical FX transactions.",
    )


def _validate_settlement_dates(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
) -> None:
    if txn.settlement_date is None:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.MISSING_SETTLEMENT_DATE,
                field="settlement_date",
                message="settlement_date is required for canonical FX validation.",
            )
        )
    elif txn.transaction_date > txn.settlement_date:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.INVALID_DATE_ORDER,
                field="transaction_date",
                message="transaction_date must be on or before settlement_date.",
            )
        )


def _validate_currency_pair(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
) -> None:
    if not txn.pair_base_currency or not txn.pair_quote_currency:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.MISSING_PAIR_CURRENCY,
                field="pair_base_currency",
                message="pair_base_currency and pair_quote_currency are required.",
            )
        )
    if txn.buy_currency == txn.sell_currency:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.SAME_CURRENCY_NOT_ALLOWED,
                field="buy_currency",
                message="buy_currency and sell_currency must differ for FX transactions.",
            )
        )


def _validate_quote_convention(
    issues: list[FxValidationIssue],
    normalized: _NormalizedFxCodes,
) -> None:
    if normalized.quote_convention not in FX_RATE_QUOTE_CONVENTIONS:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.INVALID_QUOTE_CONVENTION,
                field="fx_rate_quote_convention",
                message="fx_rate_quote_convention must be QUOTE_PER_BASE or BASE_PER_QUOTE.",
            )
        )


def _validate_positive_amounts_and_rate(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
) -> None:
    _validate_positive_decimal(
        issues,
        value=txn.buy_amount,
        field="buy_amount",
        code=FxValidationReasonCode.NON_POSITIVE_BUY_AMOUNT,
        message="buy_amount must be greater than zero.",
    )
    _validate_positive_decimal(
        issues,
        value=txn.sell_amount,
        field="sell_amount",
        code=FxValidationReasonCode.NON_POSITIVE_SELL_AMOUNT,
        message="sell_amount must be greater than zero.",
    )
    _validate_positive_decimal(
        issues,
        value=txn.contract_rate,
        field="contract_rate",
        code=FxValidationReasonCode.NON_POSITIVE_CONTRACT_RATE,
        message="contract_rate must be greater than zero.",
    )


def _validate_positive_decimal(
    issues: list[FxValidationIssue],
    *,
    value: Decimal,
    field: str,
    code: FxValidationReasonCode,
    message: str,
) -> None:
    if value <= 0:
        issues.append(FxValidationIssue(code=code, field=field, message=message))


def _validate_strict_metadata(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
    *,
    strict_metadata: bool,
) -> None:
    if not strict_metadata:
        return
    _validate_strict_linkage_metadata(issues, txn)
    _validate_strict_policy_metadata(issues, txn)


def _validate_strict_linkage_metadata(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
) -> None:
    if not txn.economic_event_id or not txn.linked_transaction_group_id:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.MISSING_LINKAGE_IDENTIFIER,
                field="economic_event_id",
                message=(
                    "economic_event_id and linked_transaction_group_id are required "
                    "under strict metadata validation."
                ),
            )
        )


def _validate_strict_policy_metadata(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
) -> None:
    if not txn.calculation_policy_id or not txn.calculation_policy_version:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.MISSING_POLICY_METADATA,
                field="calculation_policy_id",
                message=(
                    "calculation_policy_id and calculation_policy_version are required "
                    "under strict metadata validation."
                ),
            )
        )


def _validate_cash_settlement_component(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
    normalized: _NormalizedFxCodes,
) -> None:
    if not normalized.component_type.startswith("FX_CASH_SETTLEMENT"):
        return
    if normalized.cash_leg_role not in FX_CASH_LEG_ROLES:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.INVALID_FX_CASH_ROLE,
                field="fx_cash_leg_role",
                message="fx_cash_leg_role must be BUY or SELL for cash settlement components.",
            )
        )
    if not txn.linked_fx_cash_leg_id:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.MISSING_LINKED_FX_CASH_LEG,
                field="linked_fx_cash_leg_id",
                message="linked_fx_cash_leg_id is required for FX cash settlement components.",
            )
        )


def _validate_contract_identifier(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
    normalized: _NormalizedFxCodes,
) -> None:
    requires_contract_id = normalized.transaction_type in {
        "FX_FORWARD",
        "FX_SWAP",
    } or normalized.component_type.startswith("FX_CONTRACT")
    if requires_contract_id and not txn.fx_contract_id:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.MISSING_FX_CONTRACT_ID,
                field="fx_contract_id",
                message=(
                    "fx_contract_id is required for forwards, swaps, and contract components."
                ),
            )
        )


def _validate_swap_structure(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
    normalized: _NormalizedFxCodes,
) -> None:
    if normalized.transaction_type != "FX_SWAP":
        return
    if _missing_swap_group_identifiers(txn):
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.MISSING_SWAP_GROUP_IDENTIFIER,
                field="swap_event_id",
                message=(
                    "swap_event_id, near_leg_group_id, and far_leg_group_id are required "
                    "for FX_SWAP."
                ),
            )
        )
    elif txn.near_leg_group_id == txn.far_leg_group_id:
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.INVALID_SWAP_GROUP_STRUCTURE,
                field="near_leg_group_id",
                message="near_leg_group_id and far_leg_group_id must be distinct for FX_SWAP.",
            )
        )


def _missing_swap_group_identifiers(txn: FxCanonicalTransaction) -> bool:
    return not txn.swap_event_id or not txn.near_leg_group_id or not txn.far_leg_group_id


def _validate_optional_policy_modes(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
    normalized: _NormalizedFxCodes,
) -> None:
    if txn.spot_exposure_model is not None and normalized.spot_exposure_model not in (
        FX_SPOT_EXPOSURE_MODELS
    ):
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.INVALID_SPOT_EXPOSURE_MODEL,
                field="spot_exposure_model",
                message="spot_exposure_model must be NONE or FX_CONTRACT when provided.",
            )
        )
    if txn.fx_realized_pnl_mode is not None and normalized.realized_pnl_mode not in (
        FX_REALIZED_PNL_MODES
    ):
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.INVALID_REALIZED_PNL_MODE,
                field="fx_realized_pnl_mode",
                message=(
                    "fx_realized_pnl_mode must be NONE, UPSTREAM_PROVIDED, or "
                    "CASH_LOT_COST_METHOD when provided."
                ),
            )
        )


def _validate_realized_pnl_fields(
    issues: list[FxValidationIssue],
    txn: FxCanonicalTransaction,
) -> None:
    for field_name, field_value in (
        ("realized_capital_pnl_local", txn.realized_capital_pnl_local),
        ("realized_capital_pnl_base", txn.realized_capital_pnl_base),
    ):
        _validate_realized_capital_pnl_zero(
            issues=issues,
            field_name=field_name,
            field_value=field_value,
        )
    _validate_realized_total_identity(
        issues=issues,
        capital=txn.realized_capital_pnl_local,
        fx=txn.realized_fx_pnl_local,
        total=txn.realized_total_pnl_local,
        total_field="realized_total_pnl_local",
    )
    _validate_realized_total_identity(
        issues=issues,
        capital=txn.realized_capital_pnl_base,
        fx=txn.realized_fx_pnl_base,
        total=txn.realized_total_pnl_base,
        total_field="realized_total_pnl_base",
    )


def _validate_realized_capital_pnl_zero(
    *,
    issues: list[FxValidationIssue],
    field_name: str,
    field_value: Decimal | None,
) -> None:
    if field_value is not None and field_value != Decimal(0):
        issues.append(
            FxValidationIssue(
                code=FxValidationReasonCode.NON_ZERO_REALIZED_CAPITAL_PNL,
                field=field_name,
                message=f"{field_name} must be explicit zero for FX.",
            )
        )
