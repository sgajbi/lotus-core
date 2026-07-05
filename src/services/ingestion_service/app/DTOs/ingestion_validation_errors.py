from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping
from typing import Any, Literal

from pydantic_core import PydanticCustomError

ValidationSeverity = Literal["error", "warning"]

SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
INVALID_EFFECTIVE_WINDOW = "INVALID_EFFECTIVE_WINDOW"
DUPLICATE_SOURCE_KEY = "DUPLICATE_SOURCE_KEY"
MISSING_REQUIRED_LINEAGE = "MISSING_REQUIRED_LINEAGE"
INVALID_TRANSACTION_LIFECYCLE_LINK = "INVALID_TRANSACTION_LIFECYCLE_LINK"
INVALID_QUALITY_STATUS = "INVALID_QUALITY_STATUS"
INVALID_THRESHOLD_PAIR = "INVALID_THRESHOLD_PAIR"
MISSING_RULE_EVIDENCE = "MISSING_RULE_EVIDENCE"
INVALID_ALLOCATION_BOUNDS = "INVALID_ALLOCATION_BOUNDS"
MISSING_PROFILE_SUBSTANCE = "MISSING_PROFILE_SUBSTANCE"
INVALID_TAX_STATUS_DETAIL = "INVALID_TAX_STATUS_DETAIL"
BLANK_IDENTIFIER = "BLANK_IDENTIFIER"

INGESTION_VALIDATION_TAXONOMY: dict[str, dict[str, str]] = {
    SCHEMA_VALIDATION_FAILED: {
        "message": "Payload failed schema validation.",
        "remediation": "Correct the field value according to the published ingestion schema.",
    },
    INVALID_EFFECTIVE_WINDOW: {
        "message": "effective_to must be on or after effective_from.",
        "remediation": "Use an effective_to date that is not earlier than effective_from.",
    },
    DUPLICATE_SOURCE_KEY: {
        "message": "Payload contains duplicate source-owned effective records.",
        "remediation": "Submit one record for each source key, effective date, and version.",
    },
    MISSING_REQUIRED_LINEAGE: {
        "message": "Required source lineage is missing.",
        "remediation": "Provide source_system plus source_record_id or observed_at.",
    },
    INVALID_TRANSACTION_LIFECYCLE_LINK: {
        "message": "Transaction lifecycle link fields are inconsistent.",
        "remediation": (
            "Provide the required linked transaction identifiers for the lifecycle mode."
        ),
    },
    INVALID_QUALITY_STATUS: {
        "message": "quality_status is invalid.",
        "remediation": "Provide a non-blank governed quality status.",
    },
    INVALID_THRESHOLD_PAIR: {
        "message": "Threshold amount and currency must be supplied together.",
        "remediation": "Provide both threshold_amount and threshold_currency or omit both.",
    },
    MISSING_RULE_EVIDENCE: {
        "message": "Tax rule set record lacks bounded rule evidence.",
        "remediation": (
            "Provide a rate, threshold, applicable asset class, security, or income type."
        ),
    },
    INVALID_ALLOCATION_BOUNDS: {
        "message": "minimum_allocation must be less than or equal to maximum_allocation.",
        "remediation": (
            "Correct the allocation bounds so the lower bound does not exceed the upper."
        ),
    },
    MISSING_PROFILE_SUBSTANCE: {
        "message": "Profile record lacks required business substance.",
        "remediation": "Provide at least one governed exclusion, tilt, or allocation bound.",
    },
    INVALID_TAX_STATUS_DETAIL: {
        "message": "UNKNOWN tax_status cannot carry applicable tax detail.",
        "remediation": "Use a concrete tax_status or remove the applicable tax details.",
    },
    BLANK_IDENTIFIER: {
        "message": "Identifier must not be blank.",
        "remediation": "Provide a non-blank source-owned identifier.",
    },
}

SAFE_LINEAGE_FIELDS = ("source_system", "source_record_id", "observed_at", "source_batch_id")
RECORD_KEY_FIELDS = (
    "source_record_id",
    "transaction_id",
    "business_date",
    "security_id",
    "instrument_id",
    "portfolio_id",
)


def raise_ingestion_validation_error(
    code: str,
    *,
    field_path: str,
    message: str | None = None,
    remediation: str | None = None,
    record_key: str | None = None,
    severity: ValidationSeverity = "error",
) -> None:
    definition = INGESTION_VALIDATION_TAXONOMY.get(code, {})
    error_message = message or definition.get("message") or "Ingestion validation failed."
    raise PydanticCustomError(
        code,
        error_message,
        {
            "code": code,
            "field_path": field_path,
            "severity": severity,
            "remediation": remediation or definition.get("remediation"),
            "record_key": record_key,
        },
    )


def validate_effective_window(
    *,
    effective_from: Any,
    effective_to: Any | None,
    field_path: str = "effective_to",
) -> None:
    if effective_to is not None and effective_to < effective_from:
        raise_ingestion_validation_error(
            INVALID_EFFECTIVE_WINDOW,
            field_path=field_path,
        )


def validate_unique_records(
    keys: Iterable[Hashable],
    *,
    field_path: str,
    message: str | None = None,
) -> None:
    materialized_keys = list(keys)
    if len(materialized_keys) != len(set(materialized_keys)):
        raise_ingestion_validation_error(
            DUPLICATE_SOURCE_KEY,
            field_path=field_path,
            message=message,
        )


def validate_required_lineage(
    *,
    source_system: str | None,
    source_record_id: str | None,
    observed_at: Any | None,
    field_path: str = "source_record_id",
) -> None:
    if source_system and (source_record_id or observed_at):
        return
    raise_ingestion_validation_error(MISSING_REQUIRED_LINEAGE, field_path=field_path)


def code_from_pydantic_error(error: Mapping[str, Any]) -> str:
    raw_code = str(error.get("type") or "")
    if raw_code in INGESTION_VALIDATION_TAXONOMY:
        return raw_code
    if _is_blank_identifier_error(raw_code, field_path_from_pydantic_error(error)):
        return BLANK_IDENTIFIER
    return SCHEMA_VALIDATION_FAILED


def _is_blank_identifier_error(raw_code: str, field_path: str | None) -> bool:
    if raw_code not in {"missing", "string_type"} or field_path is None:
        return False
    normalized_field = field_path.rsplit(".", 1)[-1]
    return normalized_field.endswith("_id") or normalized_field in {"identifier", "security_id"}


def field_path_from_pydantic_error(error: Mapping[str, Any]) -> str | None:
    ctx = error.get("ctx")
    if isinstance(ctx, Mapping) and ctx.get("field_path"):
        return str(ctx["field_path"])
    loc = error.get("loc")
    if isinstance(loc, tuple) and loc:
        return ".".join(str(part) for part in loc)
    return None


def remediation_from_pydantic_error(error: Mapping[str, Any]) -> str | None:
    ctx = error.get("ctx")
    if isinstance(ctx, Mapping) and ctx.get("remediation"):
        return str(ctx["remediation"])
    code = code_from_pydantic_error(error)
    return INGESTION_VALIDATION_TAXONOMY.get(code, {}).get("remediation")


def severity_from_pydantic_error(error: Mapping[str, Any]) -> ValidationSeverity:
    ctx = error.get("ctx")
    if isinstance(ctx, Mapping) and ctx.get("severity") == "warning":
        return "warning"
    return "error"


def safe_source_lineage_from_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    lineage: dict[str, str] = {}
    for field_name in SAFE_LINEAGE_FIELDS:
        value = payload.get(field_name)
        if value is not None and str(value).strip():
            lineage[field_name] = str(value)
    return lineage


def record_key_from_payload(payload: Mapping[str, Any]) -> str | None:
    for field_name in RECORD_KEY_FIELDS:
        value = payload.get(field_name)
        if value is not None and str(value).strip():
            return f"{field_name}:{value}"
    return None
