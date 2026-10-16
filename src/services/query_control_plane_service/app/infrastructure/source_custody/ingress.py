"""Original ingress JSON capture verification against the admitted serializer catalog."""

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.portfolio_financial_source_cut_admission import (
    RegistryMemberInput,
    closed_source_json,
)
from portfolio_common.portfolio_financial_source_cut_models import INGRESS_CAPTURE_SERIALIZERS

from .reconstruction import manifest_from_payload


class IngressRetainedCaptureVerifier:
    """Pinned ingress recipes only. Native DTO decoding requires the owner's frozen catalog."""

    def verify(self, artifact, raw, *, identity, financial_input=None):
        self._catalog(artifact)
        body = closed_source_json(raw.read())
        self._context(artifact, identity)
        self._source_address(body, identity)
        typed = self._typed_root(body, artifact, identity)
        capture_id = canonical_content_hash(
            {
                "contract": "NeutralIngressSourceCapture:v1",
                "tenant_id": identity.tenant_id,
                "product_name": artifact.source_product,
                "source_system": identity.source_system,
                "registry_scope_id": identity.scope_id,
                "source_cut_id": identity.source_cut_id,
                "revision": identity.revision,
                "source_page_index": artifact.source_page_index,
                "raw_hash": artifact.raw_hash,
            }
        )
        if typed != artifact.typed_content_hash or capture_id != artifact.capture_id:
            raise ValueError("ingress retained typed root or capture identity mismatch")

    def _catalog(self, artifact):
        registry = artifact.source_product == "PortfolioHistoricalRegistry"
        chunk = artifact.source_page_index > 0
        expected_tag = INGRESS_CAPTURE_SERIALIZERS.get((artifact.source_product, chunk))
        if (
            not registry
            or artifact.serializer_id != expected_tag
            or artifact.schema_version != "v1"
            or artifact.mime_type != "application/json"
            or artifact.source_context.capture_origin != "INGRESS_JSON"
        ):
            raise ValueError("retained serializer catalog unavailable")

    def _context(self, artifact, identity):
        context = artifact.source_context
        if (
            artifact.role is not None
            or artifact.selector_hash is not None
            or artifact.original_supplier_digest is not None
            or artifact.original_supplier_reference is not None
            or context.source_revision != str(identity.revision)
            or any(
                getattr(context, field) is not None
                for field in (
                    "snapshot_epoch",
                    "request_scope",
                    "selector_json",
                    "export_job_id",
                    "refresh_of_job_id",
                    "returned_count",
                    "total_count",
                    "next_page_token",
                )
            )
        ):
            raise ValueError("ingress capture context mismatch")

    def _source_address(self, body, identity):
        expected_address = (
            identity.source_system,
            identity.scope_id,
            identity.source_cut_id,
            identity.revision,
        )
        if (
            tuple(
                body[name]
                for name in ("source_system", "registry_scope_id", "source_cut_id", "revision")
            )
            != expected_address
        ):
            raise ValueError("ingress capture source scope mismatch")

    def _typed_root(self, body, artifact, identity):
        chunk = artifact.source_page_index > 0
        if chunk:
            if (
                set(body)
                != {
                    "source_system",
                    "registry_scope_id",
                    "source_cut_id",
                    "revision",
                    "chunk_index",
                    "members",
                    "typed_content_hash",
                }
                or body["chunk_index"] + 1 != artifact.source_page_index
            ):
                raise ValueError("closed ingress chunk shape required")
            members = [
                RegistryMemberInput.model_validate(value).to_domain() for value in body["members"]
            ]
            if len(members) > 500 or type(body["chunk_index"]) is not int:
                raise ValueError("bounded ingress chunk required")
            typed = canonical_content_hash(
                {
                    "contract": "PortfolioHistoricalRegistryChunk:v1",
                    "members": [member.content_hash for member in members],
                }
            )
            if typed != body["typed_content_hash"]:
                raise ValueError("ingress chunk declared typed root mismatch")
        else:
            typed = manifest_from_payload(
                body, identity.tenant_id, artifact.source_product
            ).content_hash
        return typed
