from __future__ import annotations

import csv
from csv import Error as CsvError
from dataclasses import dataclass
from io import BytesIO, StringIO
from typing import Any, Literal
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, ValidationError

from ..application.errors import UnsupportedOperation, ValidationRejected
from ..application.upload_commands import UploadEntity, UploadRowIssue
from ..DTOs.business_date_dto import BusinessDate
from ..DTOs.fx_rate_dto import FxRate
from ..DTOs.instrument_dto import Instrument
from ..DTOs.market_price_dto import MarketPrice
from ..DTOs.portfolio_dto import Portfolio
from ..DTOs.transaction_dto import Transaction

MODEL_BY_ENTITY: dict[UploadEntity, type[BaseModel]] = {
    "portfolios": Portfolio,
    "instruments": Instrument,
    "transactions": Transaction,
    "market_prices": MarketPrice,
    "fx_rates": FxRate,
    "business_dates": BusinessDate,
}


@dataclass(frozen=True, slots=True)
class UploadValidationReport:
    file_format: Literal["csv", "xlsx"]
    valid_models: list[BaseModel]
    valid_rows: list[dict[str, Any]]
    errors: list[UploadRowIssue]
    total_rows: int


class BulkUploadValidator:
    def validate(
        self,
        *,
        entity_type: UploadEntity,
        filename: str,
        content: bytes,
    ) -> UploadValidationReport:
        model_cls = MODEL_BY_ENTITY[entity_type]
        alias_index = _field_alias_index(model_cls)
        file_format, rows = _parse_rows(filename, content)

        valid_models: list[BaseModel] = []
        valid_rows: list[dict[str, Any]] = []
        errors: list[UploadRowIssue] = []

        for index, row in enumerate(rows, start=2):
            normalized_row = _normalize_row(row, alias_index)
            try:
                model = model_cls.model_validate(normalized_row)
            except ValidationError as exc:
                errors.append(_row_issue(row_number=index, exc=exc))
                continue

            valid_models.append(model)
            valid_rows.append(model.model_dump())

        return UploadValidationReport(
            file_format=file_format,
            valid_models=valid_models,
            valid_rows=valid_rows,
            errors=errors,
            total_rows=len(rows),
        )


def _row_issue(*, row_number: int, exc: ValidationError) -> UploadRowIssue:
    issues: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        issues.append(f"{location}: {error.get('msg', 'invalid value')}")
    return UploadRowIssue(row_number=row_number, message="; ".join(issues))


def _normalized_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _field_alias_index(model_cls: type[BaseModel]) -> dict[str, str]:
    index: dict[str, str] = {}
    for field_name, field_info in model_cls.model_fields.items():
        index[_normalized_key(field_name)] = field_name
        alias = field_info.alias
        if alias:
            index[_normalized_key(alias)] = alias
    return index


def _normalize_row(row: dict[str, Any], alias_index: dict[str, str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in row.items():
        canonical_key = _canonical_row_key(raw_key, alias_index)
        if canonical_key is None:
            continue
        normalized[canonical_key] = _normalized_row_value(raw_value)
    return normalized


def _canonical_row_key(raw_key: Any, alias_index: dict[str, str]) -> str | None:
    if raw_key is None:
        return None
    return alias_index.get(_normalized_key(str(raw_key)))


def _normalized_row_value(raw_value: Any) -> Any:
    if not isinstance(raw_value, str):
        return raw_value
    stripped = raw_value.strip()
    return None if stripped == "" else stripped


def _parse_rows(
    filename: str,
    content: bytes,
) -> tuple[Literal["csv", "xlsx"], list[dict[str, Any]]]:
    file_format = _detect_format(filename)
    try:
        if file_format == "csv":
            return file_format, _parse_csv(content)
        return file_format, _parse_xlsx(content)
    except (UnicodeDecodeError, CsvError) as exc:
        raise ValidationRejected(
            reason_code="invalid_csv_content",
            detail=f"Invalid CSV content: {exc}",
        ) from exc
    except (BadZipFile, InvalidFileException, ValueError) as exc:
        raise ValidationRejected(
            reason_code="invalid_xlsx_content",
            detail=f"Invalid XLSX content: {exc}",
        ) from exc


def _parse_csv(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))
    return [dict(row) for row in reader]


def _parse_xlsx(content: bytes) -> list[dict[str, Any]]:
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    worksheet = workbook.active
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return []

    headers = _xlsx_headers(rows[0])
    records: list[dict[str, Any]] = []
    for row_values in rows[1:]:
        row_dict = _xlsx_row_record(headers, row_values)
        if _xlsx_row_has_data(row_dict):
            records.append(row_dict)
    return records


def _xlsx_headers(row: tuple[Any, ...]) -> list[str]:
    return [str(cell).strip() if cell is not None else "" for cell in row]


def _xlsx_row_record(headers: list[str], row_values: tuple[Any, ...] | None) -> dict[str, Any]:
    if row_values is None:
        return {}
    return {
        header: row_values[index] if index < len(row_values) else None
        for index, header in enumerate(headers)
        if header
    }


def _xlsx_row_has_data(row: dict[str, Any]) -> bool:
    return any(value is not None and str(value).strip() != "" for value in row.values())


def _detect_format(filename: str) -> Literal["csv", "xlsx"]:
    lowered = filename.lower()
    if lowered.endswith(".csv"):
        return "csv"
    if lowered.endswith(".xlsx"):
        return "xlsx"
    raise UnsupportedOperation(
        reason_code="unsupported_upload_file_format",
        detail="Unsupported file format. Use .csv or .xlsx.",
    )
