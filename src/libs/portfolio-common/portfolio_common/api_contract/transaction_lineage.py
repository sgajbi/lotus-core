"""Additive supplier lineage; independent of transaction economic identity."""

from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError


class TransactionSourceLineage(BaseModel):
    source_record_id: str | None = Field(
        None,
        min_length=1,
        max_length=256,
        description="Supplier record identity, independent of corporate-action child references.",
        examples=["CUST-TRADE-20261009-1842"],
    )
    source_batch_id: str | None = Field(
        None,
        min_length=1,
        max_length=256,
        description="Supplier-declared batch identity; never a Lotus job or content hash.",
        examples=["CUST-20261009-PM"],
    )
    observed_at: AwareDatetime | None = Field(
        None,
        description="Upstream observation time, independent of receipt, trade and settlement time.",
        examples=["2026-10-09T09:30:00Z"],
    )

    @model_validator(mode="before")
    @classmethod
    def validate_supplier_lineage(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        unknown = sorted(
            key
            for key in value
            if isinstance(key, str)
            and (key.startswith("source_") or key.startswith("observed_"))
            and key not in cls.model_fields
        )
        if unknown:
            raise PydanticCustomError(
                "transaction_lineage_unknown_field",
                "Unknown transaction lineage fields: {fields}",
                {"fields": ", ".join(unknown)},
            )
        supplied = any(
            value.get(key) is not None
            for key in ("source_record_id", "source_batch_id", "observed_at")
        )
        if supplied and not str(value.get("source_system") or "").strip():
            raise PydanticCustomError(
                "transaction_lineage_source_system_required",
                "Supplier lineage requires source_system",
            )
        for key in (
            ("source_system", "source_record_id", "source_batch_id")
            if supplied
            else ("source_record_id", "source_batch_id")
        ):
            identifier = value.get(key)
            if isinstance(identifier, str) and (
                not identifier.strip() or identifier != identifier.strip()
            ):
                raise PydanticCustomError(
                    "transaction_lineage_identifier_invalid",
                    "Supplier lineage identifiers must be nonblank and have no boundary whitespace",
                )
        return value
