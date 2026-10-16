"""Static native acquisition port; no caller URL or credentials cross this boundary."""

import hashlib
import tempfile
from collections.abc import AsyncIterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from portfolio_common.domain.calculation_lineage import (
    canonical_content_hash,
    require_sha256_digest,
)
from portfolio_common.domain.portfolio_financial_source_cuts import InputRole


class SourceCaptureUnavailable(ValueError):
    """A source cannot satisfy its exact retained contract; no completeness is earned."""


class SourceCaptureBytes:
    """Owned streaming spool; bounded memory/segments without a total-history byte cap."""

    def __init__(self) -> None:
        self._stream = tempfile.SpooledTemporaryFile(max_size=1_048_576, mode="w+b")
        self.byte_count = 0
        self.raw_hash: str = ""

    @classmethod
    async def acquire(cls, chunks: AsyncIterable[bytes]) -> "SourceCaptureBytes":
        owned = cls()
        digest = hashlib.sha256()
        try:
            async for chunk in chunks:
                if type(chunk) is not bytes or len(chunk) > 524_288:
                    raise SourceCaptureUnavailable("SOURCE_CAPTURE_SEGMENT_INVALID")
                owned._stream.write(chunk)
                owned.byte_count += len(chunk)
                digest.update(chunk)
            owned.raw_hash = digest.hexdigest()
            return owned
        except BaseException:
            owned.close()
            raise

    def segments(self) -> Iterator[bytes]:
        self._stream.seek(0)
        digest = hashlib.sha256()
        total = 0
        while chunk := self._stream.read(524_288):
            total += len(chunk)
            digest.update(chunk)
            yield chunk
        if total != self.byte_count or digest.hexdigest() != self.raw_hash:
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_RAW_DRIFT")

    def close(self) -> None:
        self._stream.close()

    def segment_window(self, first: int, limit: int = 2):
        """At most 1MiB per fenced write; final cache acquisition verifies whole bytes."""
        if type(first) is not int or first < 0 or type(limit) is not int or not 1 <= limit <= 2:
            raise ValueError("bounded capture segment window required")
        self._stream.seek(first * 524288)
        for index in range(first, first + limit):
            raw = self._stream.read(524288)
            if not raw:
                return
            yield index, raw


@dataclass(frozen=True, slots=True)
class SourceCaptureRequest:
    tenant_id: str
    portfolio_id: str
    role: InputRole
    product_name: str
    product_version: str
    selector_json: bytes
    selector_hash: str
    expected_content_hash: str
    receipt_job_id: str
    source_revision: str
    page_token: str | None
    page_index: int = 0
    currency: str = field(kw_only=True)

    @property
    def capture_id(self) -> str:
        return canonical_content_hash(
            {
                "contract": "NativeSourceCaptureRequest:v1",
                "tenant": self.tenant_id,
                "portfolio": self.portfolio_id,
                "product": self.product_name,
                "version": self.product_version,
                "selector": self.selector_hash,
                "content": self.expected_content_hash,
                "receipt": self.receipt_job_id,
                "revision": self.source_revision,
                "page_index": self.page_index,
            }
        )


@dataclass(frozen=True, slots=True)
class CapturedSourcePage:
    request: SourceCaptureRequest
    capture_bytes: SourceCaptureBytes
    serializer_id: str
    mime_type: str
    typed_content_hash: str
    snapshot_epoch: str | None
    request_scope: str | None
    returned_count: int
    total_count: int
    next_page_token: str | None
    completed_receipt_id: str
    captured_at: datetime
    schema_version: str
    export_job_id: str | None = None
    refresh_of_job_id: str | None = None
    retained_bytes_verified: bool = False

    def __post_init__(self) -> None:
        require_sha256_digest(self.typed_content_hash, "captured typed source")
        if (
            not isinstance(self.capture_bytes, SourceCaptureBytes)
            or self.capture_bytes.byte_count == 0
        ):
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_BYTES_MISSING")
        if not self.serializer_id or not self.mime_type or not self.schema_version:
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_CONTEXT_MISSING")
        if self.captured_at.utcoffset() is None:
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_TIME_INVALID")
        if self.request_scope is not None and (
            type(self.request_scope) is not str or not self.request_scope.strip()
        ):
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_SCOPE_INVALID")
        if self.snapshot_epoch is not None and (
            type(self.snapshot_epoch) is not str or not self.snapshot_epoch.strip()
        ):
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_EPOCH_INVALID")
        if self.request.product_name == "PortfolioTimeseriesInput" and self.snapshot_epoch is None:
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_VALUATION_EPOCH_MISSING")
        if (
            any(type(n) is not int or n < 0 for n in (self.returned_count, self.total_count))
            or self.returned_count > self.total_count
        ):
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_COUNT_INVALID")
        if (
            self.completed_receipt_id != self.request.receipt_job_id
            or self.typed_content_hash != self.request.expected_content_hash
        ):
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_RECEIPT_OR_ROOT_MISMATCH")
        if self.next_page_token is not None and (
            not self.next_page_token
            or self.returned_count == 0
            or self.next_page_token == self.request.page_token
        ):
            raise SourceCaptureUnavailable("SOURCE_CAPTURE_CURSOR_NO_PROGRESS")

    @property
    def raw_hash(self) -> str:
        return self.capture_bytes.raw_hash


class FinancialSourceCaptureClient(Protocol):
    async def fetch(self, request: SourceCaptureRequest) -> CapturedSourcePage: ...

    async def close(self) -> None: ...
