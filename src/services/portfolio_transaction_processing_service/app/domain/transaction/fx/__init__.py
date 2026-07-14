"""Expose canonical foreign-exchange transaction economics policies."""

from .baseline_processing import (
    UnsupportedFxRealizedPnlModeError,
    assert_fx_processed_transaction_valid,
    build_fx_baseline_processing_update,
    build_fx_processed_transaction,
)
from .contract_instrument import (
    FX_CONTRACT_ASSET_CLASS,
    FX_CONTRACT_PRODUCT_TYPE,
    FxContractInstrument,
    build_fx_contract_instrument,
    is_fx_contract_component,
)
from .linkage import (
    FX_DEFAULT_POLICY_ID,
    FX_DEFAULT_POLICY_VERSION,
    enrich_fx_transaction_metadata,
)
from .models import (
    FX_BUSINESS_TRANSACTION_TYPES,
    FX_CASH_LEG_ROLES,
    FX_COMPONENT_TYPES,
    FX_RATE_QUOTE_CONVENTIONS,
    FX_REALIZED_PNL_MODES,
    FX_SPOT_EXPOSURE_MODELS,
    FxCanonicalTransaction,
)
from .reason_codes import FxValidationReasonCode
from .transaction_source import FxTransactionSource
from .validation import FxValidationError, FxValidationIssue, validate_fx_transaction

__all__ = [
    "FX_BUSINESS_TRANSACTION_TYPES",
    "FX_COMPONENT_TYPES",
    "FX_CASH_LEG_ROLES",
    "FX_RATE_QUOTE_CONVENTIONS",
    "FX_SPOT_EXPOSURE_MODELS",
    "FX_REALIZED_PNL_MODES",
    "FxCanonicalTransaction",
    "FxTransactionSource",
    "FX_DEFAULT_POLICY_ID",
    "FX_DEFAULT_POLICY_VERSION",
    "enrich_fx_transaction_metadata",
    "FX_CONTRACT_ASSET_CLASS",
    "FX_CONTRACT_PRODUCT_TYPE",
    "FxContractInstrument",
    "is_fx_contract_component",
    "build_fx_contract_instrument",
    "build_fx_processed_transaction",
    "build_fx_baseline_processing_update",
    "assert_fx_processed_transaction_valid",
    "UnsupportedFxRealizedPnlModeError",
    "FxValidationError",
    "FxValidationIssue",
    "FxValidationReasonCode",
    "validate_fx_transaction",
]
