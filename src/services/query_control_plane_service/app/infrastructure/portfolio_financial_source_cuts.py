"""Compatible retained custody infrastructure imports and admitted catalog dispatch."""

from .source_custody.ingress import IngressRetainedCaptureVerifier as IngressRetainedCaptureVerifier
from .source_custody.native import NativeRetainedCaptureVerifier as NativeRetainedCaptureVerifier
from .source_custody.reconstruction import (
    manifest_from_payload as manifest_from_payload,
)
from .source_custody.reconstruction import (
    native_capture_identity as native_capture_identity,
)
from .source_custody.reconstruction import (
    require_capture_fields as require_capture_fields,
)
from .source_custody.reconstruction import (
    require_capture_receipt as require_capture_receipt,
)
from .source_custody.reconstruction import (
    require_raw as require_raw,
)
from .source_custody.reconstruction import (
    retained_stamp as retained_stamp,
)
from .source_custody.sql_reader import (
    SqlAlchemyPortfolioFinancialSourceCutReader as SqlAlchemyPortfolioFinancialSourceCutReader,
)
from .source_custody.sql_reader import (
    exact_scope as exact_scope,
)
from .source_custody.valuation import (
    RetainedValuationCaptureVerifier as RetainedValuationCaptureVerifier,
)


class RetainedSourceCaptureVerifier:
    """Dispatch only the admitted ingress and native catalogs; original bytes remain unchanged."""

    def verify(self, artifact, raw, *, identity, financial_input=None):
        verifier = (
            IngressRetainedCaptureVerifier()
            if artifact.source_context.capture_origin == "INGRESS_JSON"
            else NativeRetainedCaptureVerifier()
        )
        try:
            verifier.verify(artifact, raw, identity=identity, financial_input=financial_input)
        except (KeyError, TypeError, AttributeError, StopIteration) as error:
            raise ValueError("retained capture contract could not be reconstructed") from error
