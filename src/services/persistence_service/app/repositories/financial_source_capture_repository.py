"""Immutable acquired artifacts, bounded segments and verified source-off cache reads."""

from datetime import datetime

from portfolio_common.domain.portfolio_financial_source_cuts import (
    InputRole,
)
from portfolio_common.portfolio_financial_source_cut_models import (
    FinancialSourceCaptureLinkRow,
    FinancialSourceCaptureRow,
    FinancialSourceCaptureSegmentRow,
)
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from ..ports.financial_source_captures import (
    CapturedSourcePage,
    SourceCaptureBytes,
    SourceCaptureUnavailable,
)
from .financial_source_cut_claims import scope


class FinancialSourceCaptureRepository:
    def __init__(self, session_factory):
        self.sessions = session_factory

    async def cached_capture(self, request):
        # No write transaction and no source call; first acquired bytes/context remain original.
        async with self.sessions() as session:
            row = await session.scalar(
                select(FinancialSourceCaptureRow).where(
                    FinancialSourceCaptureRow.tenant_id == request.tenant_id,
                    FinancialSourceCaptureRow.capture_id == request.capture_id,
                )
            )
            if row is None:
                return None
            count = await session.scalar(
                select(func.count())
                .select_from(FinancialSourceCaptureSegmentRow)
                .where(
                    FinancialSourceCaptureSegmentRow.tenant_id == request.tenant_id,
                    FinancialSourceCaptureSegmentRow.capture_id == request.capture_id,
                )
            )
            if count != row.segment_count:
                return None
            context = dict(row.source_context)
            if (
                request.role in {InputRole.CASH, InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS}
                and context.get("currency") != request.currency
            ):
                raise SourceCaptureUnavailable("SOURCE_CAPTURE_CACHED_CURRENCY_MISMATCH")
            statement = (
                select(FinancialSourceCaptureSegmentRow)
                .where(
                    FinancialSourceCaptureSegmentRow.tenant_id == request.tenant_id,
                    FinancialSourceCaptureSegmentRow.capture_id == request.capture_id,
                )
                .order_by(FinancialSourceCaptureSegmentRow.segment_index)
            )

            async def chunks():
                expected = 0
                async for segment in await session.stream_scalars(statement):
                    if segment.segment_index != expected:
                        raise SourceCaptureUnavailable("SOURCE_CAPTURE_SEGMENT_GAP")
                    expected += 1
                    yield segment.raw_bytes
                if expected != row.segment_count:
                    raise SourceCaptureUnavailable("SOURCE_CAPTURE_SEGMENT_COUNT")

            owned = await SourceCaptureBytes.acquire(chunks())
            try:
                if owned.raw_hash != row.raw_hash or owned.byte_count != row.byte_count:
                    raise SourceCaptureUnavailable("SOURCE_CAPTURE_RAW_DRIFT")
                return CapturedSourcePage(
                    request,
                    owned,
                    row.serializer_id,
                    row.mime_type,
                    row.typed_content_hash,
                    context["snapshot_epoch"],
                    context["request_scope"],
                    context["returned_count"],
                    context["total_count"],
                    context["next_page_token"],
                    context["completed_receipt_id"],
                    datetime.fromisoformat(context["captured_at"]),
                    context["schema_version"],
                    context["export_job_id"],
                    context["refresh_of_job_id"],
                    retained_bytes_verified=True,
                )
            except BaseException:
                owned.close()
                raise

    async def append(self, session, row, page):
        request = page.request
        existing = await session.scalar(
            select(FinancialSourceCaptureRow).where(
                FinancialSourceCaptureRow.tenant_id == row.tenant_id,
                FinancialSourceCaptureRow.capture_id == request.capture_id,
            )
        )
        if existing is None:
            context = {
                "snapshot_epoch": page.snapshot_epoch,
                "request_scope": page.request_scope,
                "returned_count": page.returned_count,
                "total_count": page.total_count,
                "next_page_token": page.next_page_token,
                "completed_receipt_id": page.completed_receipt_id,
                "source_revision": request.source_revision,
                "currency": request.currency,
                "selector_json": request.selector_json.decode(),
                "captured_at": page.captured_at.isoformat(),
                "schema_version": page.schema_version,
                "export_job_id": page.export_job_id,
                "refresh_of_job_id": page.refresh_of_job_id,
            }
            segment_count = max(1, (page.capture_bytes.byte_count + 524_287) // 524_288)
            session.add(
                FinancialSourceCaptureRow(
                    tenant_id=row.tenant_id,
                    capture_id=request.capture_id,
                    source_product=request.product_name,
                    product_version=request.product_version,
                    selector_hash=request.selector_hash,
                    typed_content_hash=page.typed_content_hash,
                    raw_hash=page.raw_hash,
                    byte_count=page.capture_bytes.byte_count,
                    segment_count=segment_count,
                    serializer_id=page.serializer_id,
                    mime_type=page.mime_type,
                    source_context=context,
                )
            )
            await session.flush()
        elif (
            existing.typed_content_hash,
            existing.raw_hash,
            existing.source_context["snapshot_epoch"],
            existing.source_context["request_scope"],
        ) != (page.typed_content_hash, page.raw_hash, page.snapshot_epoch, page.request_scope):
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_DIVERGENT_REPLAY")
        if (
            existing is not None
            and request.role in {InputRole.CASH, InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS}
            and existing.source_context.get("currency") != request.currency
        ):
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_CACHED_CURRENCY_MISMATCH")
        count, low, high = (
            await session.execute(
                select(
                    func.count(),
                    func.min(FinancialSourceCaptureSegmentRow.segment_index),
                    func.max(FinancialSourceCaptureSegmentRow.segment_index),
                ).where(
                    FinancialSourceCaptureSegmentRow.tenant_id == row.tenant_id,
                    FinancialSourceCaptureSegmentRow.capture_id == request.capture_id,
                )
            )
        ).one()
        segment_count = (page.capture_bytes.byte_count + 524287) // 524288
        if count > segment_count or (count and (low != 0 or high != count - 1)):
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_SEGMENT_GAP")
        if count != segment_count:
            for index, raw in page.capture_bytes.segment_window(count):
                await session.execute(
                    insert(FinancialSourceCaptureSegmentRow)
                    .values(
                        tenant_id=row.tenant_id,
                        capture_id=request.capture_id,
                        segment_index=index,
                        raw_bytes=raw,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["tenant_id", "capture_id", "segment_index"]
                    )
                )
            return False
        if not page.retained_bytes_verified:
            # Next step re-reads the complete immutable segments outside this
            # write transaction and verifies raw hash/cardinality before linking.
            return False
        session.add(
            FinancialSourceCaptureLinkRow(
                **scope(row),
                portfolio_id=request.portfolio_id,
                role=request.role.value,
                page_index=request.page_index,
                capture_id=request.capture_id,
            )
        )
        return True
