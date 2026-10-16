"""Retained neutral read commitments, independent of transport segmentation and pagination."""

import base64
import hashlib
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass

from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import (
    InputRole,
    OrderedContentRoot,
    ordered_content_root,
)
from portfolio_common.page_tokens import PageTokenCodec

from ..contracts.portfolio_financial_source_cuts import (
    CaptureSegmentEvidence,
    FinancialCutEvidence,
    FinancialInputEvidence,
    RegistryCutEvidence,
    RegistryMemberEvidence,
    SourceCutAddress,
    SourceCutPagination,
    SourceCutReadResponse,
)
from ..ports.portfolio_financial_source_cuts import RetainedCaptureVerifier, RetainedSourceCutReader

READ_ROOT_CONTRACTS = {
    "CUT_HEADERS": "NeutralSourceCutHeaders:v1",
    "REGISTRY_MEMBERS": "PortfolioHistoricalRegistryMembers:v1",
    "SELECTED_FINANCIAL_INPUTS": "PortfolioFinancialSourceCutInputs:v1",
    "CAPTURE_ARTIFACTS": "PortfolioNeutralSourceCaptureArtifacts:v1",
}


def capture_artifact_projection(segment: CaptureSegmentEvidence) -> dict:
    """One logical role/page artifact; segment bytes and segment indices are separate proof."""
    return {
        "contract": "PortfolioNeutralSourceCaptureArtifact:v1",
        **segment.model_dump(
            mode="json",
            exclude={"row_kind", "segment_index", "segment_hash", "bytes_base64"},
        ),
    }


def source_read_item_hash(root_kind: str, item) -> str:
    """Return the precise bare SHA256 item appended to a view's ordered chain."""
    if root_kind == "CUT_HEADERS" and isinstance(item, (RegistryCutEvidence, FinancialCutEvidence)):
        return item.manifest.content_hash
    if root_kind == "REGISTRY_MEMBERS" and isinstance(item, RegistryMemberEvidence):
        return item.member_content_hash
    if root_kind == "SELECTED_FINANCIAL_INPUTS" and isinstance(item, FinancialInputEvidence):
        return item.input_content_hash
    if root_kind == "CAPTURE_ARTIFACTS" and isinstance(item, CaptureSegmentEvidence):
        return canonical_content_hash(capture_artifact_projection(item))
    raise ValueError("source root kind and commitment item mismatch")


def source_read_root(root_kind: str, ordered_items: Iterable) -> tuple[int, str]:
    """Caller provides canonical logical items exactly once, never every byte segment."""
    if root_kind not in READ_ROOT_CONTRACTS:
        raise ValueError("unsupported source read root")
    return ordered_content_root(
        READ_ROOT_CONTRACTS[root_kind],
        (source_read_item_hash(root_kind, item) for item in ordered_items),
    )


def retained_row_key(row) -> tuple:
    if isinstance(row, RegistryMemberEvidence):
        return (row.member.provider_namespace, row.member.source_member_id)
    if isinstance(row, FinancialInputEvidence):
        return (row.graph.portfolio_id,)
    if isinstance(row, CaptureSegmentEvidence):
        role = -1 if row.role is None else tuple(InputRole).index(row.role)
        return (role, row.source_page_index, row.capture_id, row.segment_index)
    return (0,)


@dataclass(frozen=True, slots=True)
class RetainedReadPage:
    rows: list
    total_count: int
    root_item_count: int
    ordered_set_hash: str
    root_kind: str
    ordering: str
    final_key: tuple | None


class PortfolioFinancialSourceCutsService:
    """Stream immutable commitments; buffer only one bounded response and one artifact spool."""

    def __init__(
        self,
        reader: RetainedSourceCutReader,
        page_tokens: PageTokenCodec,
        *,
        capture_verifier: RetainedCaptureVerifier | None = None,
        response_byte_budget: int = 2_097_152,
    ):
        if type(response_byte_budget) is not int or not 1024 <= response_byte_budget <= 8_388_608:
            raise ValueError("bounded serialized response budget required")
        self.reader = reader
        self.page_tokens = page_tokens
        self.capture_verifier = capture_verifier
        self.response_byte_budget = response_byte_budget

    async def _rows(self, tenant, product, query, cut, selected=None):
        if query.view == "CUT":
            yield cut.header
        elif query.view == "MEMBERS":
            async for row in self.reader.members(tenant, query):
                yield row
        elif query.view == "INPUTS":
            yield await self.reader.selected_input(tenant, query, cut)
        else:
            async for row in self.reader.captures(tenant, query, cut, selected):
                yield row

    async def _validated_rows(self, tenant, product, query, cut):
        previous = None
        representative = None
        digest = hashlib.sha256()
        size = 0
        selected = (
            await self.reader.selected_input(tenant, query, cut)
            if product == "PortfolioFinancialSourceCut" and query.view == "CAPTURES"
            else None
        )
        with tempfile.SpooledTemporaryFile(max_size=1_048_576, mode="w+b") as raw:
            async for row in self._rows(tenant, product, query, cut, selected):
                key = retained_row_key(row)
                if previous is not None and key <= previous:
                    raise ValueError("retained order or duplicate mismatch")
                if isinstance(row, CaptureSegmentEvidence):
                    if representative is None or key[:-1] != retained_row_key(representative)[:-1]:
                        if representative is not None:
                            self._verify_artifact(
                                representative,
                                digest,
                                size,
                                raw,
                                cut.header.manifest.identity,
                                selected,
                            )
                        if row.segment_index != 0:
                            raise ValueError("first retained segment missing")
                        representative, digest, size = row, hashlib.sha256(), 0
                        raw.seek(0)
                        raw.truncate()
                    elif (
                        capture_artifact_projection(row)
                        != capture_artifact_projection(representative)
                        or row.segment_index != previous[-1] + 1
                    ):
                        raise ValueError("retained artifact context or segment gap")
                    chunk = base64.b64decode(row.bytes_base64, validate=True)
                    digest.update(chunk)
                    raw.write(chunk)
                    size += len(chunk)
                previous = key
                yield row
            if representative is not None:
                self._verify_artifact(
                    representative,
                    digest,
                    size,
                    raw,
                    cut.header.manifest.identity,
                    selected,
                )

    def _verify_artifact(self, artifact, digest, size, raw, identity, selected):
        if (digest.hexdigest(), size) != (artifact.raw_hash, artifact.byte_count):
            raise ValueError("whole retained artifact hash or cardinality mismatch")
        if self.capture_verifier is None:
            raise ValueError("native retained serializer catalog unavailable")
        raw.seek(0)
        self.capture_verifier.verify(artifact, raw, identity=identity, financial_input=selected)

    @staticmethod
    def _require_header(tenant_id, request, cut):
        header = cut.header
        identity = header.manifest.identity
        if (
            identity.tenant_id,
            identity.source_system,
            identity.scope_id,
            identity.source_cut_id,
            identity.revision,
            header.manifest.content_hash,
        ) != (
            tenant_id,
            request.source_system,
            request.registry_scope_id,
            request.source_cut_id,
            request.revision,
            request.content_hash,
        ):
            raise ValueError("retained source header scope or root mismatch")

    async def _read_page(self, tenant_id, product, request, cut, last_key):
        root_kind, ordering = {
            "CUT": ("CUT_HEADERS", "single_cut"),
            "MEMBERS": ("REGISTRY_MEMBERS", "provider_namespace,source_member_id"),
            "INPUTS": ("SELECTED_FINANCIAL_INPUTS", "selected_portfolio"),
            "CAPTURES": ("CAPTURE_ARTIFACTS", "role,source_page_index,capture_id,segment_index"),
        }[request.view]
        accumulator = OrderedContentRoot(READ_ROOT_CONTRACTS[root_kind])
        rows, total, buffered_bytes = [], 0, 0
        found_last, collecting = last_key is None, True
        key = None
        async for row in self._validated_rows(tenant_id, product, request, cut):
            key = retained_row_key(row)
            total += 1
            if not isinstance(row, CaptureSegmentEvidence) or row.segment_index == 0:
                accumulator.append(source_read_item_hash(root_kind, row))
            if key == last_key:
                found_last = True
            if last_key is not None and key <= last_key:
                continue
            if collecting and len(rows) < request.page.page_size:
                row_bytes = len(row.model_dump_json().encode("utf-8"))
                if rows and buffered_bytes + row_bytes > self.response_byte_budget:
                    collecting = False
                else:
                    rows.append(row)
                    buffered_bytes += row_bytes
        root_count, root_hash = accumulator.finish()
        if not found_last:
            raise ValueError("retained cursor key absent")
        if request.view == "MEMBERS" and (root_count, root_hash) != (
            cut.header.manifest.supplied_count,
            cut.header.manifest.members_root,
        ):
            raise ValueError("retained member set does not reconcile")
        return RetainedReadPage(rows, total, root_count, root_hash, root_kind, ordering, key)

    async def query(self, *, tenant_id, service_identity, product, request):
        route = {
            "PortfolioHistoricalRegistry": "/integration/portfolio-historical-registries/query",
            "PortfolioFinancialSourceCut": "/integration/financial-source-cuts/query",
        }[product]
        scope = {
            "product": product,
            "version": "v1",
            "service_identity": service_identity,
            "selectors": request.model_dump(mode="json", exclude={"page"}),
            "page_size": request.page.page_size,
        }
        token = self.page_tokens.decode(request.page.page_token, route=route, tenant_id=tenant_id)
        if token and (set(token) != {"scope", "last_key", "commitment"} or token["scope"] != scope):
            raise ValueError("retained page token scope mismatch")
        if token and (type(token["last_key"]) is not list or not token["last_key"]):
            raise ValueError("retained immutable cursor key required")
        last_key = tuple(token["last_key"]) if token else None
        cut = await self.reader.cut(tenant_id, product, request)
        self._require_header(tenant_id, request, cut)
        page = await self._read_page(tenant_id, product, request, cut, last_key)
        commitment = canonical_content_hash(
            {
                "root": page.ordered_set_hash,
                "root_count": page.root_item_count,
                "total": page.total_count,
                "header": cut.header.model_dump(mode="json"),
                "ordering": page.ordering,
                "compatibility_posture": cut.compatibility_posture,
            }
        )
        if token and token["commitment"] != commitment:
            raise ValueError("retained continuation commitment changed")
        return self._response(tenant_id, product, request, cut, page, route, scope, commitment)

    def _response(self, tenant_id, product, request, cut, page, route, scope, commitment):
        header = cut.header
        base = dict(
            product_name=product,
            tenant_id=tenant_id,
            source_address=SourceCutAddress.model_validate(
                request.model_dump(include=set(SourceCutAddress.model_fields))
            ),
            batch_manifest_hash=request.content_hash,
            portfolio_id=getattr(request, "portfolio_id", None),
            view=request.view,
            receipt_job_id=header.receipt_job_id,
            received_at=header.received_at,
            completed_at=header.completed_at,
            generated_at=header.completed_at,
            as_of_date=header.manifest.identity.coverage_to,
            compatibility_posture=cut.compatibility_posture,
            content_hash="sha256:" + request.content_hash,
            source_digest="sha256:" + request.content_hash,
        )
        rows = page.rows
        while True:
            has_more = bool(rows) and retained_row_key(rows[-1]) != page.final_key
            next_token = (
                self.page_tokens.encode(
                    {
                        "scope": scope,
                        "last_key": retained_row_key(rows[-1]),
                        "commitment": commitment,
                    },
                    route=route,
                    tenant_id=tenant_id,
                )
                if has_more
                else None
            )
            response = SourceCutReadResponse(
                **base,
                rows=tuple(rows),
                pagination=SourceCutPagination(
                    total_count=page.total_count,
                    returned_count=len(rows),
                    next_page_token=next_token,
                    root_item_count=page.root_item_count,
                    ordered_set_hash=page.ordered_set_hash,
                    root_kind=page.root_kind,
                    ordering=page.ordering,
                ),
            )
            if len(response.model_dump_json().encode("utf-8")) <= self.response_byte_budget:
                return response
            if len(rows) <= 1:
                raise ValueError("retained row exceeds serialized response budget")
            rows.pop()
