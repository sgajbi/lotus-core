"""Cross-cutting corporate-action and FX transaction compatibility contracts."""

from .ca_bundle_a_reason_codes import CaBundleAValidationReasonCode
from .ca_bundle_a_reconciliation import (
    DEFAULT_CA_BUNDLE_A_BASIS_TOLERANCE,
    CaBundleAReconciliationResult,
    evaluate_ca_bundle_a_reconciliation,
    find_missing_ca_bundle_a_dependencies,
)
from .ca_bundle_a_validation import (
    CA_BUNDLE_A_TRANSACTION_TYPES,
    CaBundleAValidationError,
    CaBundleAValidationIssue,
    assert_ca_bundle_a_transaction_valid,
    is_ca_bundle_a_transaction_type,
    validate_ca_bundle_a_transaction,
)
from .effective_processing_type import (
    FX_COMPONENT_PROCESSING_TYPES,
    NON_CASHFLOW_PROCESSING_TYPES,
    requires_cashflow_processing,
    resolve_effective_processing_transaction_type,
)
from .fx_baseline_processing import (
    UnsupportedFxRealizedPnlModeError,
    assert_fx_processed_event_valid,
    build_fx_baseline_processing_update,
    build_fx_processed_event,
)
from .fx_contract_instrument import (
    FX_CONTRACT_ASSET_CLASS,
    FX_CONTRACT_PRODUCT_TYPE,
    build_fx_contract_instrument_event,
    is_fx_contract_component_event,
)
from .fx_linkage import (
    FX_DEFAULT_POLICY_ID,
    FX_DEFAULT_POLICY_VERSION,
    enrich_fx_transaction_metadata,
)
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
from .fx_validation import FxValidationError, FxValidationIssue, validate_fx_transaction

__all__ = [
    "CA_BUNDLE_A_TRANSACTION_TYPES",
    "DEFAULT_CA_BUNDLE_A_BASIS_TOLERANCE",
    "CaBundleAReconciliationResult",
    "evaluate_ca_bundle_a_reconciliation",
    "find_missing_ca_bundle_a_dependencies",
    "CaBundleAValidationError",
    "CaBundleAValidationIssue",
    "CaBundleAValidationReasonCode",
    "is_ca_bundle_a_transaction_type",
    "validate_ca_bundle_a_transaction",
    "assert_ca_bundle_a_transaction_valid",
    "FX_COMPONENT_PROCESSING_TYPES",
    "NON_CASHFLOW_PROCESSING_TYPES",
    "requires_cashflow_processing",
    "resolve_effective_processing_transaction_type",
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
