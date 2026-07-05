from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook

from src.services.ingestion_service.app.application.errors import (
    UnsupportedOperation,
    ValidationRejected,
)
from src.services.ingestion_service.app.DTOs.ingestion_validation_errors import (
    BLANK_IDENTIFIER,
    SCHEMA_VALIDATION_FAILED,
)
from src.services.ingestion_service.app.services.upload_validation import (
    BulkUploadValidator,
    UploadParserBudget,
)


def _csv_bytes(content: str) -> bytes:
    return content.encode("utf-8")


def _xlsx_bytes(headers: list[str], rows: list[list[object | None]]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_upload_validator_normalizes_header_spelling_and_ignores_unknown_columns() -> None:
    content = _csv_bytes(
        "\n".join(
            [
                "Security ID,Name,ISIN,Currency,Product Type,Ignored Column",
                " SEC1 , Bond A , ISIN1 , usd , bond , ignored",
            ]
        )
    )

    report = BulkUploadValidator().validate(
        entity_type="instruments",
        filename="instruments.csv",
        content=content,
    )

    assert report.file_format == "csv"
    assert report.total_rows == 1
    assert len(report.valid_models) == 1
    assert report.errors == []
    assert report.valid_rows[0]["security_id"] == "SEC1"
    assert report.valid_rows[0]["currency"] == "USD"
    assert "Ignored Column" not in report.valid_rows[0]


def test_upload_validator_skips_blank_xlsx_rows() -> None:
    content = _xlsx_bytes(
        headers=["security_id", "name", "isin", "currency", "product_type"],
        rows=[
            [None, None, None, None, None],
            ["SEC1", "Bond A", "ISIN1", "USD", "bond"],
        ],
    )

    report = BulkUploadValidator().validate(
        entity_type="instruments",
        filename="instruments.xlsx",
        content=content,
    )

    assert report.file_format == "xlsx"
    assert report.total_rows == 1
    assert len(report.valid_models) == 1
    assert report.errors == []


def test_upload_validator_reports_invalid_rows_without_publish_dependency() -> None:
    content = _csv_bytes(
        "\n".join(
            [
                "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency",
                "T1,P1,I1,S1,INVALID_DATE,BUY,10,100,1000,USD,USD",
            ]
        )
    )

    report = BulkUploadValidator().validate(
        entity_type="transactions",
        filename="transactions.csv",
        content=content,
    )

    assert report.total_rows == 1
    assert report.valid_models == []
    assert report.errors[0].row_number == 2
    assert report.errors[0].code == SCHEMA_VALIDATION_FAILED
    assert report.errors[0].field_path == "transaction_date"
    assert report.errors[0].record_key == "transaction_id:T1"
    assert "transaction_date" in report.errors[0].message


def test_upload_validator_reports_structured_row_validation_metadata() -> None:
    content = _csv_bytes(
        "\n".join(
            [
                (
                    "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,"
                    "transaction_type,quantity,price,gross_transaction_amount,trade_currency,"
                    "currency,source_system,source_record_id,observed_at"
                ),
                (
                    "  ,P1,I1,S1,2026-01-02T10:00:00Z,BUY,10,100,1000,USD,USD,"
                    "OMS,txn-source-001,2026-01-02T10:05:00Z"
                ),
            ]
        )
    )

    report = BulkUploadValidator().validate(
        entity_type="transactions",
        filename="transactions.csv",
        content=content,
    )

    assert report.valid_models == []
    error = report.errors[0]
    assert error.code == BLANK_IDENTIFIER
    assert error.severity == "error"
    assert error.field_path == "transaction_id"
    assert error.record_key == "source_record_id:txn-source-001"
    assert error.remediation == "Provide a non-blank source-owned identifier."
    assert error.source_lineage == {
        "source_system": "OMS",
        "source_record_id": "txn-source-001",
        "observed_at": "2026-01-02T10:05:00Z",
    }


def test_upload_validator_rejects_unsupported_file_format() -> None:
    with pytest.raises(UnsupportedOperation) as exc_info:
        BulkUploadValidator().validate(
            entity_type="transactions",
            filename="transactions.txt",
            content=b"",
        )

    assert exc_info.value.reason_code == "unsupported_upload_file_format"


def test_upload_validator_rejects_invalid_csv_bytes() -> None:
    with pytest.raises(ValidationRejected) as exc_info:
        BulkUploadValidator().validate(
            entity_type="transactions",
            filename="transactions.csv",
            content=b"\xff",
        )

    assert exc_info.value.reason_code == "invalid_csv_content"


def test_upload_validator_rejects_csv_above_row_budget() -> None:
    content = _csv_bytes(
        "\n".join(
            [
                "security_id,name,isin,currency,product_type",
                "SEC1,Bond A,ISIN1,USD,Bond",
                "SEC2,Bond B,ISIN2,USD,Bond",
            ]
        )
    )

    with pytest.raises(ValidationRejected) as exc_info:
        BulkUploadValidator(budget=UploadParserBudget(max_rows=1)).validate(
            entity_type="instruments",
            filename="instruments.csv",
            content=content,
        )

    assert exc_info.value.reason_code == "upload_parser_budget_exceeded"
    assert exc_info.value.detail["budget"] == "max_rows"


def test_upload_validator_rejects_csv_above_column_budget() -> None:
    content = _csv_bytes(
        "\n".join(
            [
                "security_id,name,isin,currency,product_type,extra",
                "SEC1,Bond A,ISIN1,USD,Bond,ignored",
            ]
        )
    )

    with pytest.raises(ValidationRejected) as exc_info:
        BulkUploadValidator(budget=UploadParserBudget(max_columns=5)).validate(
            entity_type="instruments",
            filename="instruments.csv",
            content=content,
        )

    assert exc_info.value.reason_code == "upload_parser_budget_exceeded"
    assert exc_info.value.detail["budget"] == "max_columns"
    assert exc_info.value.detail["row_number"] == 1


def test_upload_validator_rejects_csv_above_cell_length_budget() -> None:
    content = _csv_bytes(
        "\n".join(
            [
                "security_id,name,isin,currency,product_type",
                "SEC1,VeryLongBondName,ISIN1,USD,Bond",
            ]
        )
    )

    with pytest.raises(ValidationRejected) as exc_info:
        BulkUploadValidator(budget=UploadParserBudget(max_cell_length=12)).validate(
            entity_type="instruments",
            filename="instruments.csv",
            content=content,
        )

    assert exc_info.value.reason_code == "upload_parser_budget_exceeded"
    assert exc_info.value.detail["budget"] == "max_cell_length"
    assert exc_info.value.detail["row_number"] == 2


def test_upload_validator_rejects_xlsx_above_row_budget_without_materializing_workbook() -> None:
    content = _xlsx_bytes(
        headers=["security_id", "name", "isin", "currency", "product_type"],
        rows=[
            ["SEC1", "Bond A", "ISIN1", "USD", "Bond"],
            ["SEC2", "Bond B", "ISIN2", "USD", "Bond"],
        ],
    )

    with pytest.raises(ValidationRejected) as exc_info:
        BulkUploadValidator(budget=UploadParserBudget(max_rows=1)).validate(
            entity_type="instruments",
            filename="instruments.xlsx",
            content=content,
        )

    assert exc_info.value.reason_code == "upload_parser_budget_exceeded"
    assert exc_info.value.detail["budget"] == "max_rows"
