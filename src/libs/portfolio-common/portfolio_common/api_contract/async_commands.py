"""Closed source-confirmation input; persisted owners and grants are not caller fields."""

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceEvidenceConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_head_id: str = Field(min_length=1, max_length=128)
    expected_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=512)
    realized_pnl_local: Decimal | None = Field(default=None, max_digits=18, decimal_places=10)
    realized_pnl_base: Decimal | None = Field(default=None, max_digits=18, decimal_places=10)

    @field_validator("expected_head_id", "reason")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Source confirmation text must be nonblank")
        return value

    @field_validator("realized_pnl_local", "realized_pnl_base", mode="before")
    @classmethod
    def require_exact_decimal(cls, value: object) -> Decimal:
        if not isinstance(value, (str, Decimal)):
            raise ValueError("Source confirmation requires exact decimal text")
        if isinstance(value, str) and (not value.strip() or len(value) > 128):
            raise ValueError("Source confirmation decimal text is invalid")
        try:
            amount = Decimal(value)
        except InvalidOperation:
            raise ValueError("Source confirmation decimal text is invalid") from None
        if not amount.is_finite():
            raise ValueError("Source confirmation requires a finite amount")
        return amount

    @model_validator(mode="after")
    def require_confirmation(self) -> Self:
        if not self.supplied_bases:
            raise ValueError("At least one source basis must be supplied")
        return self

    @property
    def supplied_bases(self) -> tuple[Literal["local", "base"], ...]:
        bases: list[Literal["local", "base"]] = []
        if "realized_pnl_local" in self.model_fields_set:
            bases.append("local")
        if "realized_pnl_base" in self.model_fields_set:
            bases.append("base")
        return tuple(bases)

    def canonical_request_sha256(self, *, target_transaction_id: str) -> str:
        """Bind target, CAS, reason and supplied presence without Decimal rounding."""
        # A model_copy/model_construct is not a validated request at a trust boundary.
        request = type(self).model_validate(self.model_dump(exclude_unset=True))
        if not target_transaction_id.strip() or len(target_transaction_id) > 256:
            raise ValueError("Source confirmation target is invalid")
        values = request.model_dump(exclude_unset=True)
        for field in ("realized_pnl_local", "realized_pnl_base"):
            if field in values:
                amount = values[field]
                text = format(amount, "f")
                values[field] = (
                    "0" if amount == 0 else (text.rstrip("0").rstrip(".") if "." in text else text)
                )
        canonical = {
            "contract_version": "lotus.transaction-source-confirmation.v1",
            "target_transaction_id": target_transaction_id,
            "supplied_bases": request.supplied_bases,
            "request": values,
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class AsyncCommandIdempotency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    key: str = Field(min_length=1, max_length=256)
    scope: str = Field(min_length=1, max_length=256)


class AsyncCommandAccepted(BaseModel):
    """#531 accepted means queued, never durable successful completion."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    correlation_id: str = Field(min_length=1, max_length=128)
    operation_id: str = Field(min_length=1, max_length=128)
    status: Literal["QUEUED"] = "QUEUED"
    status_url: str = Field(min_length=1, max_length=512)
    retry_after_seconds: int = Field(default=2, ge=1, le=60)
    idempotency: AsyncCommandIdempotency


class AsyncCommandStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    # Internal status projection has no HTTP request. The owning router supplies this field.
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    operation_id: str = Field(min_length=1, max_length=128)
    status: Literal["QUEUED", "SUCCEEDED", "FAILED", "UNAVAILABLE"]
    revision_id: str | None = Field(default=None, min_length=1, max_length=128)
    revision_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,127}$")

    @model_validator(mode="after")
    def require_complete_outcome(self) -> Self:
        has_revision = self.revision_id is not None and self.revision_sha256 is not None
        if self.status == "SUCCEEDED":
            if not has_revision or self.reason_code is not None:
                raise ValueError("Successful command requires complete revision identity")
        elif self.revision_id is not None or self.revision_sha256 is not None:
            raise ValueError("Uncompleted command cannot expose revision authority")
        if self.status in {"FAILED", "UNAVAILABLE"} and self.reason_code is None:
            raise ValueError("Unavailable command requires a bounded reason")
        if self.status == "QUEUED" and self.reason_code is not None:
            raise ValueError("Queued command cannot expose a terminal reason")
        return self
