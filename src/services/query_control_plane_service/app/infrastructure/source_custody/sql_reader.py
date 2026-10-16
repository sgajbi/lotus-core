"""Tenant-fenced SQL custody reads and row hydration; no source clients or writes."""

import base64
import hashlib

from portfolio_common.database_models import IngestionJob
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import InputRole, OrderedContentRoot
from portfolio_common.portfolio_financial_source_cut_admission import (
    FinancialInput,
    RegistryMemberInput,
    closed_source_json,
    financial_input_from_payload,
    registry_member_from_payload,
)
from portfolio_common.portfolio_financial_source_cut_models import (
    SCOPE,
    FinancialSourceCaptureLinkRow,
    FinancialSourceCaptureRow,
    FinancialSourceCaptureSegmentRow,
    FinancialSourceChunkRow,
    FinancialSourceCutRow,
    FinancialSourceCutWorkRow,
    FinancialSourceInputRow,
    HistoricalRegistryMemberRow,
    ingress_capture_projection,
)
from sqlalchemy import case, select

from ...contracts.portfolio_financial_source_cuts import (
    CaptureSegmentEvidence,
    FinancialCutEvidence,
    FinancialInputEvidence,
    RegistryCutEvidence,
    RegistryMemberEvidence,
)
from ...ports.portfolio_financial_source_cuts import RetainedCut
from .reconstruction import manifest_from_payload, native_capture_identity, require_raw


def exact_scope(model, tenant, product, query):
    values = dict(
        tenant_id=tenant,
        product_name=product,
        **query.model_dump(
            include={"source_system", "registry_scope_id", "source_cut_id", "revision"}
        ),
    )
    return [getattr(model, name) == values[name] for name in SCOPE]


class SqlAlchemyPortfolioFinancialSourceCutReader:
    def __init__(self, session):
        self.session = session

    async def cut(self, tenant_id, product, query):
        row = await self.session.scalar(
            select(FinancialSourceCutRow).where(
                *exact_scope(FinancialSourceCutRow, tenant_id, product, query)
            )
        )
        if row is None:
            raise LookupError("exact retained cut absent")
        manifest = manifest_from_payload(row.declaration, tenant_id, product)
        raw_manifest = manifest_from_payload(require_raw(row), tenant_id, product)
        if (
            manifest != raw_manifest
            or manifest.content_hash != row.content_hash
            or row.content_hash != query.content_hash
        ):
            raise ValueError("retained raw and typed manifest mismatch")
        job = await self.session.scalar(
            select(IngestionJob).where(
                IngestionJob.tenant_id == tenant_id, IngestionJob.job_id == row.receipt_job_id
            )
        )
        work = await self.session.scalar(
            select(FinancialSourceCutWorkRow).where(
                *exact_scope(FinancialSourceCutWorkRow, tenant_id, product, query),
                FinancialSourceCutWorkRow.partition_index == 0,
            )
        )
        registry = product == "PortfolioHistoricalRegistry"
        endpoint, entity = (
            ("/ingest/portfolio-historical-registry-cuts", "portfolio_historical_registry")
            if registry
            else ("/ingest/portfolio-financial-source-cuts", "portfolio_financial_source_cut")
        )
        if (
            job is None
            or job.status != "completed"
            or job.completed_at is None
            or (job.endpoint, job.entity_type, job.accepted_count) != (endpoint, entity, 1)
            or work is None
            or work.status != "COMPLETED"
            or (work.receipt_job_id, work.content_hash) != (row.receipt_job_id, row.content_hash)
            or job.completed_at < row.received_at
        ):
            raise ValueError("native retained terminal custody receipt unavailable")
        model = RegistryCutEvidence if registry else FinancialCutEvidence
        header = model(
            manifest=manifest,
            receipt_job_id=row.receipt_job_id,
            received_at=row.received_at,
            completed_at=job.completed_at,
        )
        posture = (
            "DECLARED_UNVERIFIED"
            if work.checkpoint.get("compatibility_declaration_count", 0) > 0
            else "UNAVAILABLE"
        )
        return RetainedCut(header, posture)

    async def members(self, tenant_id, query):
        statement = (
            select(HistoricalRegistryMemberRow)
            .where(
                *exact_scope(
                    HistoricalRegistryMemberRow, tenant_id, "PortfolioHistoricalRegistry", query
                )
            )
            .order_by(
                HistoricalRegistryMemberRow.provider_namespace,
                HistoricalRegistryMemberRow.source_member_id,
            )
        )
        stream = await self.session.stream_scalars(statement.execution_options(yield_per=100))
        try:
            async for row in stream:
                member = registry_member_from_payload(row.declaration)
                if (
                    member.provider_namespace,
                    member.source_member_id,
                    member.core_portfolio_id,
                    member.member_revision,
                ) != (
                    row.provider_namespace,
                    row.source_member_id,
                    row.core_portfolio_id,
                    row.member_revision,
                ):
                    raise ValueError("retained member index mismatch")
                yield RegistryMemberEvidence(member=member, member_content_hash=row.content_hash)
        finally:
            await stream.close()

    async def selected_input(self, tenant_id, query, cut):
        row = await self.session.scalar(
            select(FinancialSourceInputRow).where(
                *exact_scope(
                    FinancialSourceInputRow, tenant_id, "PortfolioFinancialSourceCut", query
                ),
                FinancialSourceInputRow.portfolio_id == query.portfolio_id,
            )
        )
        if row is None:
            raise LookupError("selected retained financial input absent")
        declaration = FinancialInput.model_validate(row.declaration)
        if declaration.portfolio_id != query.portfolio_id:
            raise ValueError("retained selected portfolio index mismatch")
        graph = financial_input_from_payload(
            cut.header.manifest.identity, declaration.model_dump(mode="json")
        )
        return FinancialInputEvidence(
            declaration=declaration,
            input_content_hash=row.content_hash,
            graph=graph,
            graph_content_hash=graph.content_hash,
        )

    async def _ingress(self, tenant_id, query):
        row = await self.session.scalar(
            select(FinancialSourceCutRow).where(
                *exact_scope(FinancialSourceCutRow, tenant_id, "PortfolioHistoricalRegistry", query)
            )
        )
        if row is None:
            raise ValueError("retained ingress header unavailable")
        yield row, False
        statement = (
            select(FinancialSourceChunkRow)
            .where(
                *exact_scope(
                    FinancialSourceChunkRow, tenant_id, "PortfolioHistoricalRegistry", query
                )
            )
            .order_by(FinancialSourceChunkRow.chunk_index)
        )
        stream = await self.session.stream_scalars(statement.execution_options(yield_per=1))
        root = OrderedContentRoot("NeutralSourceChunks:v1")
        try:
            async for chunk in stream:
                if chunk.chunk_index != root.count:
                    raise ValueError("retained ingress chunk gap")
                body = require_raw(chunk)
                members = [
                    RegistryMemberInput.model_validate(value).to_domain()
                    for value in body["members"]
                ]
                typed = canonical_content_hash(
                    {
                        "contract": "PortfolioHistoricalRegistryChunk:v1",
                        "members": [member.content_hash for member in members],
                    }
                )
                if typed != chunk.typed_hash or len(members) != chunk.row_count:
                    raise ValueError("retained chunk typed root mismatch")
                receipt = await self.session.scalar(
                    select(IngestionJob).where(
                        IngestionJob.tenant_id == tenant_id,
                        IngestionJob.job_id == chunk.receipt_job_id,
                    )
                )
                if (
                    receipt is None
                    or receipt.status != "completed"
                    or receipt.completed_at is None
                    or receipt.completed_at < chunk.received_at
                    or (receipt.endpoint, receipt.entity_type, receipt.accepted_count)
                    != (
                        "/ingest/portfolio-historical-registry-chunks",
                        "portfolio_historical_registry_chunk",
                        chunk.row_count,
                    )
                ):
                    raise ValueError("native retained chunk receipt unavailable")
                root.append(chunk.typed_hash)
                yield chunk, True
        finally:
            await stream.close()
        manifest = manifest_from_payload(row.declaration, tenant_id, row.product_name)
        if root.finish() != (manifest.chunk_count, manifest.chunks_root):
            raise ValueError("retained ingress chunks root mismatch")

    def _native_capture_metadata(self, tenant_id, query, selected, link, capture, pages):
        role = InputRole(link.role)
        selection = next(s for s in selected.declaration.selections if s.role == role)
        context = capture.source_context
        expected_capture_id = native_capture_identity(
            tenant_id, query.portfolio_id, selection, link.page_index
        )
        if capture.capture_id != expected_capture_id:
            raise ValueError("retained native capture identity mismatch")
        previous = pages.get(role)
        stable_context = (
            context["total_count"],
            context["snapshot_epoch"],
            context["request_scope"],
            context["export_job_id"],
            context["refresh_of_job_id"],
        )
        if (
            link.page_index != (0 if previous is None else previous[0] + 1)
            or previous is not None
            and (previous[1] is None or previous[3] != stable_context)
        ):
            raise ValueError("retained native page closure mismatch")
        cumulative = context["returned_count"] + (0 if previous is None else previous[2])
        if cumulative > context["total_count"]:
            raise ValueError("retained native source cardinality mismatch")
        pages[role] = (
            link.page_index,
            context["next_page_token"],
            cumulative,
            stable_context,
        )
        if (
            capture.source_product,
            capture.product_version,
            capture.selector_hash,
            capture.typed_content_hash,
            context["completed_receipt_id"],
            context["source_revision"],
            closed_source_json(context["selector_json"]),
        ) != (
            selection.product_name,
            selection.product_version,
            selection.selector_hash,
            selection.content_hash,
            selection.receipt_job_id,
            selection.source_revision,
            selection.selector.model_dump(mode="json"),
        ):
            raise ValueError("retained role selector, receipt or typed root mismatch")
        source_context = dict(
            capture_origin="ACQUIRED_NATIVE_DTO",
            captured_at=context["captured_at"],
            receipt_job_id=context["completed_receipt_id"],
            **{
                name: context[name]
                for name in (
                    "snapshot_epoch",
                    "request_scope",
                    "source_revision",
                    "selector_json",
                    "export_job_id",
                    "refresh_of_job_id",
                    "returned_count",
                    "total_count",
                    "next_page_token",
                )
            },
        )
        return role, context, source_context

    async def _capture_segments(self, tenant_id, link, capture, role, context, source_context):
        segments = await self.session.stream_scalars(
            select(FinancialSourceCaptureSegmentRow)
            .where(
                FinancialSourceCaptureSegmentRow.tenant_id == tenant_id,
                FinancialSourceCaptureSegmentRow.capture_id == capture.capture_id,
            )
            .order_by(FinancialSourceCaptureSegmentRow.segment_index)
            .execution_options(yield_per=1)
        )
        try:
            segment_count = 0
            async for segment in segments:
                segment_count += 1
                yield CaptureSegmentEvidence(
                    **{
                        name: getattr(capture, name)
                        for name in (
                            "capture_id",
                            "source_product",
                            "product_version",
                            "selector_hash",
                            "typed_content_hash",
                            "raw_hash",
                            "byte_count",
                            "segment_count",
                            "serializer_id",
                            "mime_type",
                            "original_supplier_digest",
                            "original_supplier_reference",
                        )
                    },
                    role=role,
                    source_page_index=link.page_index,
                    source_context=source_context,
                    schema_version=context["schema_version"],
                    segment_index=segment.segment_index,
                    segment_hash=hashlib.sha256(segment.raw_bytes).hexdigest(),
                    bytes_base64=base64.b64encode(segment.raw_bytes).decode(),
                )
            if segment_count != capture.segment_count:
                raise ValueError("retained native capture segment cardinality mismatch")
        finally:
            await segments.close()

    async def captures(self, tenant_id, query, cut, selected=None):
        if isinstance(cut.header, RegistryCutEvidence):
            async for row, chunk in self._ingress(tenant_id, query):
                metadata = ingress_capture_projection(row, chunk=chunk)
                for index in range(metadata["segment_count"]):
                    raw = row.raw_bytes[index * 524288 : (index + 1) * 524288]
                    yield CaptureSegmentEvidence(
                        **metadata,
                        segment_index=index,
                        segment_hash=hashlib.sha256(raw).hexdigest(),
                        bytes_base64=base64.b64encode(raw).decode(),
                    )
            return
        if selected is None:
            selected = await self.selected_input(tenant_id, query, cut)
        links = FinancialSourceCaptureLinkRow
        captures = FinancialSourceCaptureRow
        rank = case({role.value: index for index, role in enumerate(InputRole)}, value=links.role)
        statement = (
            select(links, captures)
            .join(
                captures,
                (captures.tenant_id == links.tenant_id) & (captures.capture_id == links.capture_id),
            )
            .where(
                *exact_scope(links, tenant_id, "PortfolioFinancialSourceCut", query),
                links.portfolio_id == query.portfolio_id,
            )
            .order_by(rank, links.page_index, links.capture_id)
        )
        stream = await self.session.stream(statement.execution_options(yield_per=1))
        seen = set()
        pages = {}
        try:
            async for link, capture in stream:
                role, context, source_context = self._native_capture_metadata(
                    tenant_id, query, selected, link, capture, pages
                )
                seen.add(role)
                async for segment in self._capture_segments(
                    tenant_id, link, capture, role, context, source_context
                ):
                    yield segment
        finally:
            await stream.close()
        if seen != set(InputRole):
            raise ValueError("complete selected five-role captures unavailable")
        if any(
            next_token is not None or count != stable[0]
            for _, next_token, count, stable in pages.values()
        ):
            raise ValueError("retained native source page population incomplete")
