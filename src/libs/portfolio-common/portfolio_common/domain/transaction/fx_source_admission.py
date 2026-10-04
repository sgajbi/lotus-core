"""Fresh FX source admission; never a historical receipt-rebuild policy."""

from decimal import Decimal

from portfolio_common.domain.transaction.type_registry import (
    production_transaction_types_for_lifecycle_families,
)
from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

FX_UPSTREAM_SOURCE_INCOMPLETE = "FX_UPSTREAM_SOURCE_INCOMPLETE"
FX_SOURCE_ADMISSION_TYPES = production_transaction_types_for_lifecycle_families("fx")
FX_NON_REALIZING_SOURCE_COMPONENTS = frozenset({"FX_CONTRACT_OPEN"})
FX_REALIZED_SOURCE_FIELDS = ("realized_fx_pnl_local", "realized_fx_pnl_base")


class IncompleteFxSourceError(ValueError):
    """Bounded server-owned refusal, without transaction identifiers or input values."""

    code = FX_UPSTREAM_SOURCE_INCOMPLETE

    def __init__(self, missing_fields: tuple[str, ...]) -> None:
        self.missing_fields = missing_fields
        super().__init__(self.code)


def missing_fx_upstream_source_fields(
    *,
    transaction_type: str,
    component_type: str | None,
    fx_realized_pnl_mode: str | None,
    realized_fx_pnl_local: Decimal | None,
    realized_fx_pnl_base: Decimal | None,
) -> tuple[str, ...]:
    """Require both currency bases for an applicable explicit upstream source claim.

    Only canonical contract-open components are non-realizing. An absent or
    unrecognized component cannot downgrade an explicit realized source claim.
    Totals, defaulted capital, caller receipts and truthiness are not FX source
    authority. Separate business validation still governs modes and arithmetic.
    """
    if (
        normalize_transaction_control_code(transaction_type) not in FX_SOURCE_ADMISSION_TYPES
        or normalize_transaction_control_code(fx_realized_pnl_mode) != "UPSTREAM_PROVIDED"
        or normalize_transaction_control_code(component_type) in FX_NON_REALIZING_SOURCE_COMPONENTS
    ):
        return ()
    return tuple(
        field
        for field, amount in zip(
            FX_REALIZED_SOURCE_FIELDS, (realized_fx_pnl_local, realized_fx_pnl_base), strict=True
        )
        if amount is None
    )
