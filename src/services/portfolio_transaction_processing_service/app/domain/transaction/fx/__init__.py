"""Expose canonical foreign-exchange transaction economics policies."""

from .baseline_processing import (
    UnsupportedFxRealizedPnlModeError,
    assert_fx_processed_event_valid,
    build_fx_baseline_processing_update,
    build_fx_processed_event,
)
from .contract_instrument import (
    FX_CONTRACT_ASSET_CLASS,
    FX_CONTRACT_PRODUCT_TYPE,
    build_fx_contract_instrument_event,
    is_fx_contract_component_event,
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
from .validation import FxValidationError, FxValidationIssue, validate_fx_transaction

__all__ = [
    "FX_BUSINESS_TRANSACTION_TYPES",
    "FX_COMPONENT_TYPES",
    "FX_CASH_LEG_ROLES",
    "FX_RATE_QUOTE_CONVENTIONS",
    "FX_SPOT_EXPOSURE_MODELS",
    "FX_REALIZED_PNL_MODES",
    "FxCanonicalTransaction",
    "FX_DEFAULT_POLICY_ID",
    "FX_DEFAULT_POLICY_VERSION",
    "enrich_fx_transaction_metadata",
    "FX_CONTRACT_ASSET_CLASS",
    "FX_CONTRACT_PRODUCT_TYPE",
    "is_fx_contract_component_event",
    "build_fx_contract_instrument_event",
    "build_fx_processed_event",
    "build_fx_baseline_processing_update",
    "assert_fx_processed_event_valid",
    "UnsupportedFxRealizedPnlModeError",
    "FxValidationError",
    "FxValidationIssue",
    "FxValidationReasonCode",
    "validate_fx_transaction",
]
