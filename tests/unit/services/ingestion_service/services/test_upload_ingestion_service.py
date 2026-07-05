from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook

from src.services.ingestion_service.app.application.errors import ValidationRejected
from src.services.ingestion_service.app.application.upload_commands import (
    UploadCommitCommand,
    UploadPreviewCommand,
)
from src.services.ingestion_service.app.services.upload_ingestion_service import (
    UploadIngestionService,
)
from src.services.ingestion_service.app.services.upload_validation import BulkUploadValidator


def _csv_bytes(content: str) -> bytes:
    return content.encode("utf-8")


def _xlsx_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


@pytest.fixture
def upload_service() -> UploadIngestionService:
    publisher = AsyncMock()
    publisher.publish_records = AsyncMock()
    return UploadIngestionService(
        validator=BulkUploadValidator(),
        publisher=publisher,
    )


def test_preview_upload_csv_with_mixed_rows(upload_service: UploadIngestionService) -> None:
    content = _csv_bytes(
        "\n".join(
            [
                "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency",
                "T1,P1,I1,S1,2026-01-02T10:00:00Z,BUY,10,100,1000,USD,USD",
                "T2,P1,I1,S1,INVALID_DATE,BUY,10,100,1000,USD,USD",
            ]
        )
    )

    response = upload_service.preview_upload(
        UploadPreviewCommand(
            entity_type="transactions",
            filename="transactions.csv",
            content=content,
            sample_size=10,
        )
    )

    assert response.file_format == "csv"
    assert response.total_rows == 2
    assert response.valid_rows == 1
    assert response.invalid_rows == 1
    assert response.sample_rows == []
    assert response.errors[0].row_number == 3


def test_preview_upload_privileged_sample_rows_are_redacted(
    upload_service: UploadIngestionService,
) -> None:
    content = _csv_bytes(
        "\n".join(
            [
                "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency",
                "T1,P1,I1,S1,2026-01-02T10:00:00Z,BUY,10,100,1000,USD,USD",
            ]
        )
    )

    response = upload_service.preview_upload(
        UploadPreviewCommand(
            entity_type="transactions",
            filename="transactions.csv",
            content=content,
            sample_size=10,
            include_sample_rows=True,
        )
    )

    row = response.sample_rows[0]
    assert row["transaction_id"] == "T1"
    assert row["transaction_type"] == "BUY"
    assert row["portfolio_id"] == "***REDACTED***"
    assert row["instrument_id"] == "***REDACTED***"
    assert row["security_id"] == "***REDACTED***"
    assert row["quantity"] == "***REDACTED***"
    assert row["price"] == "***REDACTED***"
    assert row["gross_transaction_amount"] == "***REDACTED***"
    assert row["trade_fee"] == "***REDACTED***"


def test_preview_upload_xlsx_canonical_headers(upload_service: UploadIngestionService) -> None:
    content = _xlsx_bytes(
        headers=["security_id", "name", "isin", "currency", "product_type"],
        rows=[["SEC1", "Bond A", "ISIN1", "USD", "Bond"]],
    )

    response = upload_service.preview_upload(
        UploadPreviewCommand(
            entity_type="instruments",
            filename="instruments.xlsx",
            content=content,
            sample_size=5,
        )
    )

    assert response.file_format == "xlsx"
    assert response.total_rows == 1
    assert response.valid_rows == 1
    assert response.invalid_rows == 0
    assert response.sample_rows == []


@pytest.mark.asyncio
async def test_commit_upload_rejects_partial_by_default(
    upload_service: UploadIngestionService,
) -> None:
    content = _csv_bytes(
        "\n".join(
            [
                "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency",
                "T1,P1,I1,S1,2026-01-02T10:00:00Z,BUY,10,100,1000,USD,USD",
                "T2,P1,I1,S1,INVALID_DATE,BUY,10,100,1000,USD,USD",
            ]
        )
    )

    with pytest.raises(ValidationRejected) as exc:
        await upload_service.commit_upload(
            UploadCommitCommand(
                entity_type="transactions",
                filename="transactions.csv",
                content=content,
                allow_partial=False,
            )
        )

    assert exc.value.reason_code == "upload_invalid_rows"
    assert exc.value.detail["message"] == (
        "Upload contains invalid rows. Fix errors or use allow_partial=true."
    )
    assert exc.value.detail["errors"][0]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert exc.value.detail["errors"][0]["record_key"] == "transaction_id:T2"
    upload_service._publisher.publish_records.assert_not_awaited()


@pytest.mark.asyncio
async def test_commit_upload_allows_partial(upload_service: UploadIngestionService) -> None:
    content = _csv_bytes(
        "\n".join(
            [
                "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency",
                "T1,P1,I1,S1,2026-01-02T10:00:00Z,BUY,10,100,1000,USD,USD",
                "T2,P1,I1,S1,INVALID_DATE,BUY,10,100,1000,USD,USD",
            ]
        )
    )

    response = await upload_service.commit_upload(
        UploadCommitCommand(
            entity_type="transactions",
            filename="transactions.csv",
            content=content,
            allow_partial=True,
        )
    )

    assert response.published_rows == 1
    assert response.skipped_rows == 1
    upload_service._publisher.publish_records.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_upload_empty_data_rows(upload_service: UploadIngestionService) -> None:
    content = _csv_bytes(
        "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency\n"
    )

    with pytest.raises(ValidationRejected) as exc:
        await upload_service.commit_upload(
            UploadCommitCommand(
                entity_type="transactions",
                filename="transactions.csv",
                content=content,
                allow_partial=True,
            )
        )

    assert exc.value.reason_code == "empty_upload"
    assert exc.value.detail == "Upload file contains no data rows."
