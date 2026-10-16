"""Pinned neutral custody reads; batch manifests and selected portfolio graphs are distinct."""

import base64
import hashlib
from datetime import datetime
from typing import Annotated, Literal, Self

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import (
    FinancialSourceCut,
    FinancialSourceCutManifest,
    HistoricalRegistryCut,
    HistoricalRegistryMember,
    InputRole,
)
from portfolio_common.domain.portfolio_source_observations import require_observation_identity
from portfolio_common.portfolio_financial_source_cut_admission import (
    Count,
    Digest,
    FinancialInput,
    Identity,
    Revision,
    financial_input_from_payload,
)
from portfolio_common.portfolio_financial_source_cut_decoding import ClosedSourceDeclaration
from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class ClosedSourceRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceCutPageRequest(ClosedSourceRead):
    page_size: StrictInt = Field(ge=1, le=500)
    page_token: str | None = Field(None, min_length=1, max_length=8192)


class SourceCutAddress(ClosedSourceRead):
    source_system: Identity
    registry_scope_id: Identity
    source_cut_id: Identity
    revision: Revision

    @field_validator("source_system", "registry_scope_id", "source_cut_id")
    @classmethod
    def exact_identity(cls, value):
        require_observation_identity(value, "exact source query identity")
        return value


class ExactSourceCutQuery(SourceCutAddress):
    content_hash: Digest = Field(
        description=(
            "Exact BATCH manifest/CAS root, bare64; never the selected portfolio graph root."
        )
    )
    page: SourceCutPageRequest


class HistoricalRegistryQuery(ExactSourceCutQuery):
    view: Literal["CUT", "MEMBERS", "CAPTURES"]


class FinancialSourceCutQuery(ExactSourceCutQuery):
    portfolio_id: Identity
    view: Literal["CUT", "INPUTS", "CAPTURES"]

    @field_validator("portfolio_id")
    @classmethod
    def exact_portfolio(cls, value):
        require_observation_identity(value, "selected portfolio")
        return value


class RegistryCutEvidence(ClosedSourceRead):
    row_kind: Literal["REGISTRY_CUT"] = "REGISTRY_CUT"
    manifest: Annotated[HistoricalRegistryCut, ClosedSourceDeclaration]
    receipt_job_id: Identity
    received_at: datetime
    completed_at: datetime


class FinancialCutEvidence(ClosedSourceRead):
    row_kind: Literal["FINANCIAL_CUT"] = "FINANCIAL_CUT"
    manifest: Annotated[FinancialSourceCutManifest, ClosedSourceDeclaration]
    receipt_job_id: Identity
    received_at: datetime
    completed_at: datetime


class RegistryMemberEvidence(ClosedSourceRead):
    row_kind: Literal["REGISTRY_MEMBER"] = "REGISTRY_MEMBER"
    member: Annotated[HistoricalRegistryMember, ClosedSourceDeclaration]
    member_content_hash: Digest

    @model_validator(mode="after")
    def exact_member(self) -> Self:
        if type(self.member) is not HistoricalRegistryMember:
            raise ValueError("governed retained registry member required")
        HistoricalRegistryMember.__post_init__(self.member)
        if self.member_content_hash != self.member.content_hash:
            raise ValueError("retained registry member hash mismatch")
        return self


class FinancialInputEvidence(ClosedSourceRead):
    row_kind: Literal["FINANCIAL_INPUT"] = "FINANCIAL_INPUT"
    declaration: FinancialInput
    input_content_hash: Digest
    graph: Annotated[FinancialSourceCut, ClosedSourceDeclaration]
    graph_content_hash: Digest

    @model_validator(mode="after")
    def independently_recomputable_graph(self) -> Self:
        if type(self.graph) is not FinancialSourceCut:
            raise ValueError("governed selected financial graph required")
        FinancialSourceCut.__post_init__(self.graph)
        payload = self.declaration.model_dump(mode="json")
        expected_input = canonical_content_hash(
            {"contract": "PortfolioFinancialSourceCutInput:v1", "selection": payload}
        )
        reconstructed = financial_input_from_payload(self.graph.identity, payload)
        if (expected_input, reconstructed.content_hash, self.graph.content_hash) != (
            self.input_content_hash,
            self.graph_content_hash,
            self.graph_content_hash,
        ):
            raise ValueError("selected declaration/graph hashes did not reconstruct")
        return self


class SourceCaptureContext(ClosedSourceRead):
    capture_origin: Literal["ACQUIRED_NATIVE_DTO", "INGRESS_JSON"]
    captured_at: datetime
    snapshot_epoch: str | None
    request_scope: str | None
    receipt_job_id: Identity
    source_revision: str | None
    selector_json: str | None
    export_job_id: str | None
    refresh_of_job_id: str | None
    returned_count: Count | None
    total_count: Count | None
    next_page_token: str | None

    @model_validator(mode="after")
    def retained_context(self) -> Self:
        if self.captured_at.utcoffset() is None:
            raise ValueError("aware retained capture time required")
        if self.capture_origin == "ACQUIRED_NATIVE_DTO" and (
            self.returned_count is None
            or self.total_count is None
            or self.returned_count > self.total_count
        ):
            raise ValueError("actual native capture cardinality required")
        return self


class CaptureSegmentEvidence(ClosedSourceRead):
    row_kind: Literal["CAPTURE_SEGMENT"] = "CAPTURE_SEGMENT"
    capture_id: Digest
    role: InputRole | None
    source_page_index: Count
    source_product: Identity
    product_version: Identity
    selector_hash: Digest | None
    typed_content_hash: Digest
    raw_hash: Digest
    byte_count: Count
    segment_index: Count
    segment_count: Revision
    segment_hash: Digest
    bytes_base64: str = Field(max_length=699052)
    serializer_id: Identity
    schema_version: Identity
    mime_type: Literal["application/json", "application/x-ndjson"]
    source_context: SourceCaptureContext
    original_supplier_digest: Digest | None = None
    original_supplier_reference: str | None = None

    @model_validator(mode="after")
    def exact_segment(self) -> Self:
        raw = base64.b64decode(self.bytes_base64, validate=True)
        if not 0 < len(raw) <= 524288 or self.segment_index >= self.segment_count:
            raise ValueError("bounded ordered capture segment required")
        if hashlib.sha256(raw).hexdigest() != self.segment_hash:
            raise ValueError("capture segment hash mismatch")
        if self.segment_count != (self.byte_count + 524287) // 524288 or len(raw) != min(
            524288, self.byte_count - self.segment_index * 524288
        ):
            raise ValueError("capture segment does not match retained byte cardinality")
        if self.source_context.capture_origin == "ACQUIRED_NATIVE_DTO" and self.role is None:
            raise ValueError("native financial capture requires an explicit role")
        if (
            self.source_product == "PortfolioTimeseriesInput"
            and self.source_context.snapshot_epoch is None
        ):
            raise ValueError("valuation capture requires its actual snapshot epoch")
        if (self.original_supplier_digest is None) != (self.original_supplier_reference is None):
            raise ValueError("independent original supplier digest/reference must be paired")
        return self


SourceReadRow = Annotated[
    RegistryCutEvidence
    | FinancialCutEvidence
    | RegistryMemberEvidence
    | FinancialInputEvidence
    | CaptureSegmentEvidence,
    Field(discriminator="row_kind"),
]


class SourceCutPagination(ClosedSourceRead):
    total_count: Count
    returned_count: Count
    next_page_token: str | None
    ordered_set_hash: Digest
    root_item_count: Count
    root_kind: Literal[
        "CUT_HEADERS", "REGISTRY_MEMBERS", "SELECTED_FINANCIAL_INPUTS", "CAPTURE_ARTIFACTS"
    ]
    ordering: Literal[
        "single_cut",
        "provider_namespace,source_member_id",
        "selected_portfolio",
        "role,source_page_index,capture_id,segment_index",
    ]


class SourceCutReadResponse(SourceDataProductRuntimeMetadata):
    model_config = ConfigDict(extra="forbid", frozen=True)
    product_name: Literal["PortfolioHistoricalRegistry", "PortfolioFinancialSourceCut"]
    product_version: Literal["v1"] = "v1"
    tenant_id: Identity
    source_address: SourceCutAddress
    batch_manifest_hash: Digest
    portfolio_id: Identity | None
    view: Literal["CUT", "MEMBERS", "INPUTS", "CAPTURES"]
    receipt_job_id: Identity
    received_at: datetime
    completed_at: datetime
    qualification: Literal["UNQUALIFIED"] = "UNQUALIFIED"
    population_verification: Literal["UNVERIFIED"] = "UNVERIFIED"
    compatibility_posture: Literal["DECLARED_UNVERIFIED", "UNAVAILABLE"]
    authoritative_use_available: Literal[False] = False
    pagination: SourceCutPagination
    rows: tuple[SourceReadRow, ...] = Field(max_length=500)

    @model_validator(mode="after")
    def exact_envelope(self) -> Self:
        if (
            self.content_hash != "sha256:" + self.batch_manifest_hash
            or self.source_digest != self.content_hash
        ):
            raise ValueError("standard metadata must bind batch root exactly once")
        if (
            self.pagination.returned_count != len(self.rows)
            or self.pagination.returned_count > self.pagination.total_count
        ):
            raise ValueError("exact source page cardinality required")
        allowed = {
            ("PortfolioHistoricalRegistry", "CUT"): "REGISTRY_CUT",
            ("PortfolioFinancialSourceCut", "CUT"): "FINANCIAL_CUT",
            ("PortfolioHistoricalRegistry", "MEMBERS"): "REGISTRY_MEMBER",
            ("PortfolioFinancialSourceCut", "INPUTS"): "FINANCIAL_INPUT",
            ("PortfolioHistoricalRegistry", "CAPTURES"): "CAPTURE_SEGMENT",
            ("PortfolioFinancialSourceCut", "CAPTURES"): "CAPTURE_SEGMENT",
        }
        expected_kind = allowed.get((self.product_name, self.view))
        if expected_kind is None or any(row.row_kind != expected_kind for row in self.rows):
            raise ValueError("product/view/row discriminator mismatch")
        if (self.product_name == "PortfolioHistoricalRegistry") != (self.portfolio_id is None):
            raise ValueError("registry/selected portfolio context mismatch")
        root_kind = {
            "CUT": "CUT_HEADERS",
            "MEMBERS": "REGISTRY_MEMBERS",
            "INPUTS": "SELECTED_FINANCIAL_INPUTS",
            "CAPTURES": "CAPTURE_ARTIFACTS",
        }[self.view]
        if self.pagination.root_kind != root_kind:
            raise ValueError("source page root kind mismatch")
        if self.pagination.total_count > 0 and self.pagination.returned_count == 0:
            raise ValueError("nonempty pinned page cannot return absent rows")
        if self.view == "CUT" and (
            len(self.rows) != 1
            or self.pagination.total_count != 1
            or self.pagination.next_page_token is not None
        ):
            raise ValueError("absent headers cannot masquerade as complete empty cuts")
        for row in self.rows:
            identity = (
                row.manifest.identity
                if isinstance(row, (RegistryCutEvidence, FinancialCutEvidence))
                else row.graph.identity
                if isinstance(row, FinancialInputEvidence)
                else None
            )
            if identity is not None and (
                identity.tenant_id,
                identity.source_system,
                identity.scope_id,
                identity.source_cut_id,
                identity.revision,
            ) != (
                self.tenant_id,
                self.source_address.source_system,
                self.source_address.registry_scope_id,
                self.source_address.source_cut_id,
                self.source_address.revision,
            ):
                raise ValueError("retained row tenant/source address mismatch")
            if (
                isinstance(row, (RegistryCutEvidence, FinancialCutEvidence))
                and row.manifest.content_hash != self.batch_manifest_hash
            ):
                raise ValueError("retained batch manifest hash mismatch")
            if isinstance(row, (RegistryCutEvidence, FinancialCutEvidence)) and (
                row.receipt_job_id,
                row.received_at,
                row.completed_at,
            ) != (self.receipt_job_id, self.received_at, self.completed_at):
                raise ValueError("retained terminal receipt envelope mismatch")
            if (
                isinstance(row, FinancialInputEvidence)
                and row.graph.portfolio_id != self.portfolio_id
            ):
                raise ValueError("selected portfolio graph mismatch")
        for stamp in (self.received_at, self.completed_at, self.generated_at):
            if stamp.utcoffset() is None:
                raise ValueError("aware retained source timestamps required")
        return self


class HistoricalRegistryReadResponse(SourceCutReadResponse):
    """Exact route product identity; all original neutral envelope rules remain inherited."""

    product_name: Literal["PortfolioHistoricalRegistry"] = product_name_field(
        "PortfolioHistoricalRegistry"
    )
    product_version: Literal["v1"] = product_version_field()


class FinancialSourceCutReadResponse(SourceCutReadResponse):
    """Exact route product identity; all original neutral envelope rules remain inherited."""

    product_name: Literal["PortfolioFinancialSourceCut"] = product_name_field(
        "PortfolioFinancialSourceCut"
    )
    product_version: Literal["v1"] = product_version_field()
