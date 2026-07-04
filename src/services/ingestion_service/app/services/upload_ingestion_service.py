from __future__ import annotations

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
            sample_rows=validation.valid_rows[: command.sample_size],
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
