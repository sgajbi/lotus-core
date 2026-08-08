# services/ingestion_service/app/DTOs/transaction_model_dto.py
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional, cast

from portfolio_common.domain.currency import normalize_optional_currency_code
from portfolio_common.domain.transaction.fee_components import (
    TRANSACTION_FEE_COMPONENT_FIELDS,
    resolve_transaction_trade_fee,
)
from portfolio_common.domain.transaction.numeric_policy import (
    TRANSACTION_COMMAND_DECIMAL_FIELDS,
    require_transaction_persistence_precision,
)
from portfolio_common.domain.transaction.type_registry import (
    get_transaction_type_definition,
    production_transaction_types_for_lifecycle_families,
)
from portfolio_common.domain.transaction_control_codes import (
    normalize_optional_transaction_control_code,
    normalize_transaction_control_code,
)
from portfolio_common.openapi_enrichment import document_exact_numeric_properties
from portfolio_common.temporal import standardize_governed_datetime
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from .ingestion_validation_errors import BLANK_IDENTIFIER, raise_ingestion_validation_error

NonNegativeDecimal = Annotated[Decimal, Field(ge=Decimal(0))]
PositiveDecimal = Annotated[Decimal, Field(gt=Decimal(0))]
RedemptionPriceType = Literal["PAR", "CALL_PRICE", "MARKET_PRICE"]
REDEMPTION_TRANSACTION_TYPES = production_transaction_types_for_lifecycle_families("redemption")


def _normalized_control_code_schema(*codes: str) -> dict[str, Any]:
    """Describe control codes using the same case/whitespace tolerance as ingestion."""

    alternatives = [
        {
            "type": "string",
            "pattern": (
                r"^\s*"
                + "".join(
                    f"[{character.lower()}{character.upper()}]"
                    if character.isalpha()
                    else re.escape(character)
                    for character in code
                )
                + r"\s*$"
            ),
        }
        for code in codes
    ]
    if len(alternatives) == 1:
        return alternatives[0]
    return {"anyOf": alternatives}


def _required_linkage_schema() -> dict[str, Any]:
    nonblank_identifier = {"type": "string", "pattern": r".*\S.*"}
    return {
        "required": ["economic_event_id", "linked_transaction_group_id"],
        "properties": {
            "economic_event_id": nonblank_identifier,
            "linked_transaction_group_id": nonblank_identifier,
        },
    }


def _document_transaction_numeric_contract(schema: dict[str, Any]) -> None:
    document_exact_numeric_properties(
        schema,
        field_names=TRANSACTION_COMMAND_DECIMAL_FIELDS,
        precision=18,
        scale=10,
    )
    schema.setdefault("allOf", []).append(
        {
            "if": {
                "properties": {
                    "transaction_type": _normalized_control_code_schema(
                        *sorted(REDEMPTION_TRANSACTION_TYPES)
                    ),
                    "price": {"const": 0},
                },
                "required": ["transaction_type", "price"],
            },
            "then": {"properties": {"gross_transaction_amount": {"minimum": 0}}},
            "else": {"properties": {"gross_transaction_amount": {"exclusiveMinimum": 0}}},
        }
    )
    schema["allOf"].extend(
        [
            {
                "if": {
                    "properties": {
                        "transaction_type": _normalized_control_code_schema(
                            *sorted(REDEMPTION_TRANSACTION_TYPES)
                        )
                    },
                    "required": ["transaction_type"],
                },
                "then": _required_linkage_schema(),
            },
            {
                "if": {
                    "anyOf": [
                        {
                            "properties": {
                                "cash_entry_mode": _normalized_control_code_schema(
                                    "UPSTREAM_PROVIDED"
                                )
                            },
                            "required": ["cash_entry_mode"],
                        },
                        {
                            "properties": {
                                "originating_transaction_id": {
                                    "type": "string",
                                    "pattern": r".*\S.*",
                                }
                            },
                            "required": ["originating_transaction_id"],
                        },
                    ]
                },
                "then": _required_linkage_schema(),
            },
        ]
    )


class Transaction(BaseModel):
    model_config = ConfigDict(json_schema_extra=_document_transaction_numeric_contract)

    transaction_id: str = Field(
        description="Canonical transaction identifier for ingestion, replay, and audit workflows.",
        json_schema_extra={"example": "TRN001"},
    )
    portfolio_id: str = Field(
        description="Canonical portfolio identifier that owns the transaction.",
        json_schema_extra={"example": "PORT001"},
    )
    instrument_id: str = Field(
        description="Canonical instrument identifier associated with the transaction.",
        json_schema_extra={"example": "AAPL"},
    )
    security_id: str = Field(
        description="Canonical security identifier associated with the transaction record.",
        json_schema_extra={"example": "SEC_AAPL"},
    )
    transaction_date: datetime = Field(
        description="Trade or economic timestamp used to order the transaction in the ledger.",
        json_schema_extra={"example": "2023-01-15T10:00:00Z"},
    )
    transaction_type: str = Field(
        description="Canonical transaction type that drives downstream calculator behavior.",
        json_schema_extra={"example": "BUY"},
    )

    @field_validator("transaction_type", mode="before")
    @classmethod
    def _normalize_transaction_control_code(cls, value: str | None) -> str:
        return cast(str, normalize_transaction_control_code(value))

    @field_validator(
        "transaction_id",
        "portfolio_id",
        "instrument_id",
        "security_id",
        mode="before",
    )
    @classmethod
    def _normalize_required_identifier(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        identifier = value.strip()
        if not identifier:
            raise_ingestion_validation_error(
                BLANK_IDENTIFIER,
                field_path="identifier",
                message="Identifier must not be blank.",
            )
        return identifier

    @field_validator(
        "economic_event_id",
        "linked_transaction_group_id",
        "originating_transaction_id",
        mode="before",
    )
    @classmethod
    def _normalize_optional_linkage_identifier(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip() or None

    quantity: NonNegativeDecimal = Field(
        description="Absolute traded quantity or units moved by the transaction.",
        json_schema_extra={"example": "10.0"},
    )
    price: NonNegativeDecimal = Field(
        description="Per-unit transaction price in the trade currency.",
        json_schema_extra={"example": "150.0"},
    )
    gross_transaction_amount: NonNegativeDecimal = Field(
        description=(
            "Gross economic amount before fees, taxes, or deductions. Must be greater than zero "
            "except for a governed zero-price redemption."
        ),
        json_schema_extra={"example": "1500.0"},
    )
    trade_currency: str = Field(
        description="Trade currency in which price and gross amount are quoted.",
        json_schema_extra={"example": "USD"},
    )
    currency: str = Field(
        description=(
            "Canonical transaction currency retained for compatibility with downstream ledgers."
        ),
        json_schema_extra={"example": "USD"},
    )
    transaction_fx_rate: Optional[PositiveDecimal] = Field(
        default=None,
        description=(
            "Historical FX rate used to translate the transaction from trade currency into "
            "portfolio base currency when the transaction is cross-currency."
        ),
        json_schema_extra={"example": "1.074352"},
    )
    trade_fee: Optional[NonNegativeDecimal] = Field(
        default=Decimal(0),
        description=(
            "Aggregate trade fee applied to the transaction when fee breakdown is not split out."
        ),
        json_schema_extra={"example": "5.0"},
    )
    brokerage: Optional[NonNegativeDecimal] = Field(
        default=None,
        description=(
            "Brokerage fee component. If provided with other fee components, trade_fee "
            "is recomputed from breakdown."
        ),
        json_schema_extra={"example": "2.50"},
    )
    stamp_duty: Optional[NonNegativeDecimal] = Field(
        default=None,
        description="Stamp duty fee component.",
        json_schema_extra={"example": "1.20"},
    )
    exchange_fee: Optional[NonNegativeDecimal] = Field(
        default=None,
        description="Exchange fee component.",
        json_schema_extra={"example": "0.70"},
    )
    gst: Optional[NonNegativeDecimal] = Field(
        default=None,
        description="Goods and services tax fee component.",
        json_schema_extra={"example": "0.45"},
    )
    other_fees: Optional[NonNegativeDecimal] = Field(
        default=None,
        description="Other fee components not covered by standard fields.",
        json_schema_extra={"example": "0.15"},
    )
    settlement_date: Optional[datetime] = Field(
        default=None,
        description=(
            "Settlement timestamp used for cash-leg timing and operations monitoring; required "
            "for maturity, call, and partial redemption commands."
        ),
        json_schema_extra={"example": "2023-01-17T10:00:00Z"},
    )
    economic_event_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "EVT-2026-00987"},
        description=(
            "Canonical economic event identifier that groups all legs or "
            "components of the same economic workflow."
        ),
    )
    linked_transaction_group_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "LTG-2026-00456"},
        description=(
            "Canonical linkage group identifier shared by related product and cash-leg entries."
        ),
    )
    calculation_policy_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY_DEFAULT_POLICY"},
        description="Resolved calculation-policy identifier used to process the transaction.",
    )
    calculation_policy_version: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "1.0.0"},
        description="Resolved calculation-policy version used to process the transaction.",
    )
    source_system: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "OMS_PRIMARY"},
        description="Upstream source-system identifier for lineage.",
    )
    cash_entry_mode: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "AUTO_GENERATE"},
        description=(
            "Cash-leg handling mode. Use AUTO_GENERATE for service-generated "
            "cash legs or UPSTREAM_PROVIDED when the upstream cash entry is authoritative."
        ),
    )
    external_cash_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CASH-ENTRY-2026-0001"},
        description=(
            "Upstream cash transaction identifier when cash_entry_mode is UPSTREAM_PROVIDED."
        ),
    )
    settlement_cash_account_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CASH-ACC-USD-001"},
        description=(
            "Settlement cash account identifier used to resolve or build the "
            "cash-leg posting destination."
        ),
    )
    settlement_cash_instrument_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CASH-USD"},
        description=(
            "Optional direct cash instrument identifier for generated or "
            "linked cash legs. If omitted, the engine resolves from the account mapping."
        ),
    )
    movement_direction: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "INFLOW"},
        description=(
            "Cash movement direction for cash-leg style transactions. "
            "Supported canonical values are INFLOW and OUTFLOW."
        ),
    )
    originating_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "TRN001"},
        description="Product-leg transaction identifier linked to the related cash-leg entry.",
    )
    originating_transaction_type: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY"},
        description="Product-leg transaction type linked to the related cash-leg entry.",
    )
    adjustment_reason: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY_SETTLEMENT"},
        description="Canonical reason code describing why the cash-leg entry exists.",
    )
    link_type: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY_TO_CASH"},
        description="Canonical relationship label between product and cash-leg entries.",
    )
    reconciliation_key: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "REC-2026-0001"},
        description=(
            "Optional reconciliation key shared by paired or grouped dual-leg transactions."
        ),
    )
    interest_direction: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "INCOME"},
        description=(
            "Semantic direction for INTEREST transactions. Supported values are INCOME and EXPENSE."
        ),
    )
    withholding_tax_amount: Optional[NonNegativeDecimal] = Field(
        default=None,
        json_schema_extra={"example": "15.25"},
        description=(
            "Source-recorded withholding tax amount applied to a DIVIDEND or INTEREST "
            "transaction. Core preserves this evidence without deriving jurisdiction-specific "
            "tax policy."
        ),
    )
    other_interest_deductions_amount: Optional[NonNegativeDecimal] = Field(
        default=None,
        json_schema_extra={"example": "1.00"},
        description="Other non-tax deductions applied to the interest transaction.",
    )
    net_interest_amount: Optional[NonNegativeDecimal] = Field(
        default=None,
        json_schema_extra={"example": "108.20"},
        description=(
            "Interest amount after withholding tax and other interest deductions, "
            "but before separately reported transaction fees; when supplied upstream, "
            "it is reconciled against the gross and deduction fields."
        ),
    )
    component_type: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX_CASH_SETTLEMENT_BUY"},
        description=(
            "Canonical FX component role within the economic event, such as "
            "cash settlement or contract open/close."
        ),
    )
    component_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX-COMP-0001"},
        description="Unique FX component identifier within the linked transaction group.",
    )
    linked_component_ids: Optional[list[str]] = Field(
        default=None,
        json_schema_extra={"example": ["FX-COMP-0002", "FX-COMP-0003"]},
        description="Other FX component identifiers linked to this transaction component.",
    )
    fx_cash_leg_role: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "BUY"},
        description=(
            "Canonical FX settlement-leg direction for the cash component. "
            "Supported values are BUY and SELL."
        ),
    )
    linked_fx_cash_leg_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX-SETTLE-SELL-0001"},
        description="Opposite FX cash settlement transaction identifier.",
    )
    settlement_status: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "PENDING"},
        description=(
            "Settlement lifecycle status for FX cash-settlement components, "
            "for example PENDING or SETTLED."
        ),
    )
    pair_base_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "EUR"},
        description="Base currency of the quoted FX pair.",
    )
    pair_quote_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "USD"},
        description="Quote currency of the quoted FX pair.",
    )
    fx_rate_quote_convention: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "QUOTE_PER_BASE"},
        description=(
            "Explicit quote convention used to interpret contract_rate, for example QUOTE_PER_BASE."
        ),
    )
    buy_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "USD"},
        description="Currency bought/received by the FX transaction.",
    )
    sell_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "EUR"},
        description="Currency sold/delivered by the FX transaction.",
    )
    buy_amount: Optional[PositiveDecimal] = Field(
        default=None,
        json_schema_extra={"example": "1095000"},
        description="Positive magnitude of currency bought.",
    )
    sell_amount: Optional[PositiveDecimal] = Field(
        default=None,
        json_schema_extra={"example": "1000000"},
        description="Positive magnitude of currency sold.",
    )
    contract_rate: Optional[PositiveDecimal] = Field(
        default=None,
        json_schema_extra={"example": "1.095"},
        description=(
            "Contractual FX rate agreed for the deal, interpreted using fx_rate_quote_convention."
        ),
    )
    fx_contract_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXC-2026-0001"},
        description=(
            "Stable FX contract identifier used to group open, close, and "
            "settlement components for the same forward or swap contract."
        ),
    )
    fx_contract_open_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX-OPEN-0001"},
        description="Linked FX contract-open transaction identifier.",
    )
    fx_contract_close_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX-CLOSE-0001"},
        description="Linked FX contract-close transaction identifier.",
    )
    settlement_of_fx_contract_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXC-2026-0001"},
        description=(
            "FX contract identifier whose settlement obligation is being "
            "discharged by this cash component."
        ),
    )
    swap_event_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXSWAP-2026-0001"},
        description=(
            "Stable economic event identifier shared by all legs and "
            "settlement components of the same FX swap."
        ),
    )
    near_leg_group_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXSWAP-2026-0001-NEAR"},
        description=(
            "Linkage group identifier for the near leg of an FX swap, used to "
            "tie together its product and settlement components."
        ),
    )
    far_leg_group_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FXSWAP-2026-0001-FAR"},
        description=(
            "Linkage group identifier for the far leg of an FX swap, used to "
            "tie together its product and settlement components."
        ),
    )
    spot_exposure_model: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "NONE"},
        description=(
            "Policy-driven spot exposure model. Supported values are NONE and FX_CONTRACT."
        ),
    )
    fx_realized_pnl_mode: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM_PROVIDED"},
        description=(
            "Policy-driven mode for realized FX P&L population, for example "
            "NONE or UPSTREAM_PROVIDED."
        ),
    )
    allocated_cost_basis_local: Optional[NonNegativeDecimal] = Field(
        default=None,
        json_schema_extra={"example": "50.00"},
        description=(
            "Source-provided cost basis allocated to a cash consideration or cash-in-lieu "
            "product leg in local currency. This is not cash proceeds."
        ),
    )
    allocated_cost_basis_base: Optional[NonNegativeDecimal] = Field(
        default=None,
        json_schema_extra={"example": "50.00"},
        description=(
            "Source-provided cost basis allocated to a cash consideration or cash-in-lieu "
            "product leg in portfolio base currency."
        ),
    )
    realized_capital_pnl_local: Optional[Decimal] = Field(
        default=None,
        json_schema_extra={"example": "0.00"},
        description=(
            "Realized capital P&L in local currency. Under the canonical FX "
            "model this is expected to remain explicit zero."
        ),
    )
    realized_fx_pnl_local: Optional[Decimal] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description=(
            "Realized FX P&L in local currency for the transaction or settlement component."
        ),
    )
    realized_total_pnl_local: Optional[Decimal] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description=(
            "Total realized P&L in local currency after combining capital and FX components."
        ),
    )
    realized_capital_pnl_base: Optional[Decimal] = Field(
        default=None,
        json_schema_extra={"example": "0.00"},
        description=(
            "Realized capital P&L translated into portfolio base currency. "
            "Under the canonical FX model this is expected to remain explicit zero."
        ),
    )
    realized_fx_pnl_base: Optional[Decimal] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description=("Realized FX P&L translated into portfolio base currency."),
    )
    realized_total_pnl_base: Optional[Decimal] = Field(
        default=None,
        json_schema_extra={"example": "1250.00"},
        description=("Total realized P&L translated into portfolio base currency."),
    )
    parent_transaction_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA_PARENT_TXN_001"},
        description=(
            "Corporate-action parent transaction reference used to link child "
            "transactions back to the upstream parent instruction."
        ),
    )
    linked_parent_event_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-EVT-2026-0001"},
        description=(
            "Canonical parent corporate-action event identifier shared by all "
            "child transactions created from the same event."
        ),
    )
    parent_event_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM-CA-REF-2026-0001"},
        description=(
            "Upstream parent-event reference shared by all related "
            "corporate-action child transactions."
        ),
    )
    child_role: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "SOURCE_POSITION_CLOSE"},
        description=(
            "Canonical corporate-action child role used to drive dependency-aware "
            "processing and downstream calculator interpretation."
        ),
    )
    child_sequence_hint: Optional[int] = Field(
        default=None,
        json_schema_extra={"example": 10},
        description=(
            "Optional upstream sequencing hint used to preserve deterministic "
            "ordering between related corporate-action child transactions."
        ),
    )
    dependency_reference_ids: Optional[list[str]] = Field(
        default=None,
        json_schema_extra={"example": ["CA-CHILD-OUT-001"]},
        description=(
            "Optional upstream dependency reference identifiers that must be "
            "resolved before this child transaction is processed."
        ),
    )
    source_instrument_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "OLD_SEC_001"},
        description=(
            "Source instrument identifier for transfer, replacement, or "
            "exchange-style corporate actions."
        ),
    )
    target_instrument_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "NEW_SEC_001"},
        description=(
            "Target instrument identifier for transfer, replacement, or "
            "exchange-style corporate actions."
        ),
    )
    source_transaction_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-CHILD-OUT-001"},
        description=(
            "Reference to the source-side corporate-action child transaction "
            "within the same parent event."
        ),
    )
    target_transaction_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-CHILD-IN-001"},
        description=(
            "Reference to the target-side corporate-action child transaction "
            "within the same parent event."
        ),
    )
    external_destination_reference: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CUSTODIAN-ACCOUNT-7788"},
        description=(
            "Opaque governed destination reference for a securities transfer out of the "
            "current Lotus book. It must not be interpreted as an internal transaction or lot."
        ),
    )
    linked_cash_transaction_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "CA-CIL-CASH-001"},
        description=(
            "Linked cash transaction identifier used for cash-in-lieu or "
            "other corporate-action settlement entries."
        ),
    )
    redemption_price_type: Optional[RedemptionPriceType] = Field(
        default=None,
        json_schema_extra={"example": "PAR"},
        description="Authority classification for the fixed-income redemption price.",
    )
    old_factor: Optional[PositiveDecimal] = Field(
        default=None,
        json_schema_extra={"example": "1.0"},
        description="Factor immediately before a governed partial-redemption transition.",
    )
    new_factor: Optional[NonNegativeDecimal] = Field(
        default=None,
        json_schema_extra={"example": "0.75"},
        description="Factor immediately after a governed partial-redemption transition.",
    )
    principal_proceeds_local: Optional[NonNegativeDecimal] = Field(
        default=None,
        description="Explicit principal proceeds, excluding accrued interest, fees, and taxes.",
    )
    accrued_interest_proceeds_local: Optional[NonNegativeDecimal] = Field(
        default=None,
        description="Accrued-interest proceeds embedded in the redemption cash settlement.",
    )
    embedded_fee_amount_local: Optional[NonNegativeDecimal] = Field(
        default=None,
        description="Fees embedded in the redemption cash settlement.",
    )
    embedded_tax_amount_local: Optional[NonNegativeDecimal] = Field(
        default=None,
        description="Taxes embedded in the redemption cash settlement.",
    )
    has_synthetic_flow: Optional[bool] = Field(
        default=None,
        json_schema_extra={"example": True},
        description=(
            "Whether this transaction carries a position-level synthetic flow "
            "payload for analytics and performance treatment."
        ),
    )
    synthetic_flow_effective_date: Optional[date] = Field(
        default=None,
        json_schema_extra={"example": "2026-03-15"},
        description=(
            "Effective business date of the synthetic flow used in corporate-action analytics."
        ),
    )
    synthetic_flow_amount_local: Optional[Decimal] = Field(
        default=None,
        json_schema_extra={"example": "-10000.00"},
        description=(
            "Synthetic flow amount in the local flow currency before base currency translation."
        ),
    )
    synthetic_flow_currency: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "USD"},
        description="Currency in which synthetic_flow_amount_local is expressed.",
    )
    synthetic_flow_amount_base: Optional[Decimal] = Field(
        default=None,
        json_schema_extra={"example": "-10000.00"},
        description=("Synthetic flow amount translated into the portfolio base currency."),
    )
    synthetic_flow_fx_rate_to_base: Optional[PositiveDecimal] = Field(
        default=None,
        json_schema_extra={"example": "1.000000"},
        description=(
            "FX rate used to derive synthetic_flow_amount_base from the local "
            "synthetic flow amount."
        ),
    )
    synthetic_flow_price_used: Optional[NonNegativeDecimal] = Field(
        default=None,
        json_schema_extra={"example": "200.00"},
        description=(
            "Price input used when the synthetic flow valuation method depends "
            "on market-value transfer pricing."
        ),
    )
    synthetic_flow_quantity_used: Optional[NonNegativeDecimal] = Field(
        default=None,
        json_schema_extra={"example": "50.00"},
        description=(
            "Quantity input used when the synthetic flow valuation method "
            "depends on market-value transfer quantity."
        ),
    )
    synthetic_flow_valuation_method: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "MVT_PRICE_X_QTY"},
        description=(
            "Synthetic flow valuation method classification used to explain "
            "how the synthetic amount was derived."
        ),
    )
    synthetic_flow_classification: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "POSITION_TRANSFER_OUT"},
        description=(
            "Synthetic flow classification used by position-level analytics "
            "and performance engines."
        ),
    )
    synthetic_flow_price_source: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM"},
        description=("Source classification for the price input used in synthetic flow valuation."),
    )
    synthetic_flow_fx_source: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "FX_SERVICE"},
        description=("Source classification for the FX input used in synthetic flow translation."),
    )
    synthetic_flow_source: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "UPSTREAM_PROVIDED"},
        description=(
            "Origin descriptor that explains whether the synthetic flow was "
            "supplied upstream or derived internally."
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Ingestion-side creation timestamp for lineage and troubleshooting.",
        json_schema_extra={"example": "2026-03-10T11:32:15Z"},
    )

    @field_validator("transaction_date", "settlement_date", "created_at", mode="before")
    @classmethod
    def _standardize_governed_timestamps(cls, value: object) -> object:
        return standardize_governed_datetime(value)

    @field_validator(
        "trade_currency",
        "currency",
        "pair_base_currency",
        "pair_quote_currency",
        "buy_currency",
        "sell_currency",
        "synthetic_flow_currency",
        mode="before",
    )
    @classmethod
    def _normalize_currency_code(cls, value: object) -> str | None:
        return cast(str | None, normalize_optional_currency_code(value))

    @field_validator(
        "cash_entry_mode",
        "movement_direction",
        "originating_transaction_type",
        "adjustment_reason",
        "link_type",
        "interest_direction",
        "component_type",
        "fx_cash_leg_role",
        "settlement_status",
        "fx_rate_quote_convention",
        "spot_exposure_model",
        "fx_realized_pnl_mode",
        "child_role",
        "redemption_price_type",
        "synthetic_flow_valuation_method",
        "synthetic_flow_classification",
        "synthetic_flow_price_source",
        "synthetic_flow_fx_source",
        "synthetic_flow_source",
        mode="before",
    )
    @classmethod
    def _normalize_optional_transaction_control_code(cls, value: str | None) -> str | None:
        return cast(str | None, normalize_optional_transaction_control_code(value))

    @field_validator(*TRANSACTION_COMMAND_DECIMAL_FIELDS)
    @classmethod
    def _validate_persistence_precision(
        cls,
        value: Decimal | None,
        info: ValidationInfo,
    ) -> Decimal | None:
        return cast(
            Decimal | None,
            require_transaction_persistence_precision(
                value,
                field_name=info.field_name,
            ),
        )

    @field_validator("gross_transaction_amount")
    @classmethod
    def _validate_gross_transaction_amount_for_family(
        cls,
        value: Decimal,
        info: ValidationInfo,
    ) -> Decimal:
        transaction_type = info.data.get("transaction_type")
        price = info.data.get("price")
        if value == 0 and (transaction_type not in REDEMPTION_TRANSACTION_TYPES or price != 0):
            raise ValueError(
                "gross_transaction_amount must be greater than 0 except for a governed "
                "zero-price redemption"
            )
        return value

    @model_validator(mode="after")
    def _aggregate_fee_components(self) -> "Transaction":
        self.trade_fee = require_transaction_persistence_precision(
            resolve_transaction_trade_fee(
                self.trade_fee,
                {field: getattr(self, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS},
            ),
            field_name="trade_fee",
        )
        return self

    @model_validator(mode="after")
    def _validate_redemption_factor_transition(self) -> "Transaction":
        if (self.old_factor is None) != (self.new_factor is None):
            raise ValueError("old_factor and new_factor must be supplied together")
        if (
            self.old_factor is not None
            and self.new_factor is not None
            and self.new_factor >= self.old_factor
        ):
            raise ValueError("new_factor must be less than old_factor")
        return self

    @model_validator(mode="after")
    def _validate_redemption_settlement_date(self) -> "Transaction":
        if self.transaction_type in REDEMPTION_TRANSACTION_TYPES and self.settlement_date is None:
            raise ValueError(f"settlement_date is required for {self.transaction_type}")
        return self

    @model_validator(mode="after")
    def _validate_linked_economic_authority(self) -> "Transaction":
        requires_linkage = (
            self.transaction_type in REDEMPTION_TRANSACTION_TYPES
            or self.cash_entry_mode == "UPSTREAM_PROVIDED"
            or self.originating_transaction_id is not None
        )
        if requires_linkage and (
            self.economic_event_id is None or self.linked_transaction_group_id is None
        ):
            raise ValueError(
                "economic_event_id and linked_transaction_group_id are required for governed "
                "redemptions and upstream-provided cash legs"
            )
        return self

    @model_validator(mode="after")
    def _validate_disposal_destination(self) -> "Transaction":
        target_transaction = _normalized_destination_text(self.target_transaction_reference)
        target_instrument = _normalized_destination_text(self.target_instrument_id)
        external_destination = _normalized_destination_text(self.external_destination_reference)
        has_any_internal = target_transaction is not None or target_instrument is not None
        has_complete_internal = target_transaction is not None and target_instrument is not None
        has_external = external_destination is not None

        if self.transaction_type == "TRANSFER_OUT":
            if has_complete_internal == has_external or (
                has_any_internal and not has_complete_internal
            ):
                raise ValueError(
                    "TRANSFER_OUT requires exactly one complete destination: either "
                    "target_transaction_reference with target_instrument_id, or "
                    "external_destination_reference"
                )
        else:
            if has_external:
                raise ValueError("external_destination_reference is valid only for TRANSFER_OUT")
            definition = get_transaction_type_definition(self.transaction_type)
            supports_internal_destination = bool(
                definition
                and definition.position_effect == "decrease"
                and definition.lot_behavior in {"transfer_basis_out", "partial_basis_transfer"}
            )
            uses_target_instrument_identity = bool(
                definition
                and definition.position_effect == "increase"
                and definition.lot_behavior == "basis_allocation_in"
            )
            requires_internal_destination = bool(
                definition
                and definition.position_effect == "decrease"
                and definition.lot_behavior == "transfer_basis_out"
            )
            if requires_internal_destination and not has_complete_internal:
                raise ValueError(
                    f"{self.transaction_type} requires target_transaction_reference and "
                    "target_instrument_id"
                )
            has_unsupported_target_metadata = (
                target_transaction is not None and not supports_internal_destination
            ) or (
                target_instrument is not None
                and not (supports_internal_destination or uses_target_instrument_identity)
            )
            if has_unsupported_target_metadata:
                raise ValueError(
                    "target transaction and instrument destination metadata is not valid for "
                    f"{self.transaction_type}"
                )

        self.target_transaction_reference = target_transaction
        self.target_instrument_id = target_instrument
        self.external_destination_reference = external_destination
        return self


def _normalized_destination_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
