"""Keep existing consumer imports bound to the extracted implementation objects."""

from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_financial_source_cuts as retained,
)
from src.services.query_control_plane_service.app.infrastructure.source_custody import (
    ingress,
    native,
    reconstruction,
    sql_reader,
    valuation,
)


def test_original_infrastructure_symbols_keep_single_implementation_identity():
    exports = {
        ingress: ("IngressRetainedCaptureVerifier",),
        native: ("NativeRetainedCaptureVerifier",),
        valuation: ("RetainedValuationCaptureVerifier",),
        reconstruction: (
            "manifest_from_payload",
            "require_raw",
            "native_capture_identity",
            "require_capture_fields",
            "retained_stamp",
            "require_capture_receipt",
        ),
        sql_reader: ("exact_scope", "SqlAlchemyPortfolioFinancialSourceCutReader"),
    }
    for module, names in exports.items():
        for name in names:
            assert getattr(retained, name) is getattr(module, name)
    assert retained.RetainedSourceCaptureVerifier.__module__ == retained.__name__
