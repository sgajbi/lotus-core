from __future__ import annotations

from typing import Any

from ..application.errors import ValidationRejected
from ..application.upload_commands import (
    UploadCommitCommand,
    UploadCommitResult,
    UploadEntity,
    UploadPreviewCommand,
    UploadPreviewResult,
    UploadRowIssue,
)
from ..ports.upload_record_publisher import UploadRecordPublisher
from .upload_validation import BulkUploadValidator, UploadValidationReport

SENSITIVE_SAMPLE_FIELDS = frozenset(
    {
        "account_id",
        "account_number",
        "amount",
        "base_market_value",
        "brokerage",
        "client_id",
        "exchange_fee",
        "gross_transaction_amount",
        "gst",
        "instrument_id",
        "isin",
        "market_value",
        "other_fees",
        "portfolio_id",
        "price",
        "quantity",
        "rate",
        "security_id",
        "stamp_duty",
        "tax_amount",
        "trade_fee",
    }
)
SENSITIVE_SAMPLE_SUFFIXES = (
    "_amount",
    "_balance",
    "_fee",
    "_fees",
    "_market_value",
    "_notional",
    "_price",
)
REDACTED_SAMPLE_VALUE = "***REDACTED***"


class UploadIngestionService:
    def __init__(
        self,
        validator: BulkUploadValidator,
        publisher: UploadRecordPublisher,
    ) -> None:
        self._validator = validator
        self._publisher = publisher

    def preview_upload(
        self,
        command: UploadPreviewCommand,
    ) -> UploadPreviewResult:
        validation = self._validator.validate(
            entity_type=command.entity_type,
            filename=command.filename,
            content=command.content,
        )
        return UploadPreviewResult(
            entity_type=command.entity_type,
            file_format=validation.file_format,
            total_rows=validation.total_rows,
            valid_rows=len(validation.valid_models),
            invalid_rows=len(validation.errors),
            sample_rows=(
                _redacted_sample_rows(validation.valid_rows[: command.sample_size])
                if command.include_sample_rows
                else []
            ),
            errors=validation.errors[: command.sample_size],
        )

    async def commit_upload(
        self,
        command: UploadCommitCommand,
    ) -> UploadCommitResult:
        validation = self._validator.validate(
            entity_type=command.entity_type,
            filename=command.filename,
            content=command.content,
        )
        self._validate_commit(validation, command.allow_partial)
        await self._publisher.publish_records(command.entity_type, validation.valid_models)
        return self._commit_response(command.entity_type, validation)

    def _validate_commit(self, validation: UploadValidationReport, allow_partial: bool) -> None:
        if validation.total_rows == 0:
            self._raise_empty_upload()
        if validation.errors and not allow_partial:
            self._raise_partial_upload_rejected(validation.errors)
        if not validation.valid_models:
            self._raise_no_valid_upload_rows()

    def _raise_empty_upload(self) -> None:
        raise ValidationRejected(
            reason_code="empty_upload",
            detail="Upload file contains no data rows.",
        )

    def _raise_partial_upload_rejected(self, errors: list[UploadRowIssue]) -> None:
        raise ValidationRejected(
            reason_code="upload_invalid_rows",
            detail={
                "message": "Upload contains invalid rows. Fix errors or use allow_partial=true.",
                "errors": [error.as_dict() for error in errors[:50]],
            },
        )

    def _raise_no_valid_upload_rows(self) -> None:
        raise ValidationRejected(
            reason_code="upload_no_valid_rows",
            detail="No valid rows found in upload.",
        )

    def _commit_response(
        self, entity_type: UploadEntity, validation: UploadValidationReport
    ) -> UploadCommitResult:
        return UploadCommitResult(
            entity_type=entity_type,
            file_format=validation.file_format,
            total_rows=validation.total_rows,
            valid_rows=len(validation.valid_models),
            invalid_rows=len(validation.errors),
            published_rows=len(validation.valid_models),
            skipped_rows=len(validation.errors),
            message="Upload committed and queued for processing.",
        )


def _redacted_sample_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: _redacted_sample_value(key, value) for key, value in row.items()} for row in rows]


def _redacted_sample_value(field_name: str, value: Any) -> Any:
    normalized = field_name.strip().lower()
    if normalized in SENSITIVE_SAMPLE_FIELDS or normalized.endswith(SENSITIVE_SAMPLE_SUFFIXES):
        return REDACTED_SAMPLE_VALUE
    return value
