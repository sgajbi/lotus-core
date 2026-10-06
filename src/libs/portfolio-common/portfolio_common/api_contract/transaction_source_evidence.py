"""Closed read contract for independently qualified Core FX source evidence."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceEvidenceConsumer = Literal["core-qcp", "core-ledger"]
SourceEvidenceSelection = Literal["current", "original", "revision"]
SourceEvidenceStatus = Literal["QUALIFIED", "INCOMPLETE", "CONFIRMED", "UNAVAILABLE"]


class TransactionSourceEvidence(BaseModel):
    """Read proof, not raw/auth payload, financial restatement or runtime certification."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    contract_version: Literal["transaction-source-evidence.v1"] = "transaction-source-evidence.v1"
    consumer: SourceEvidenceConsumer
    tenant_id: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    transaction_id: str = Field(min_length=1)
    selection: SourceEvidenceSelection
    status: SourceEvidenceStatus
    root_raw_id: str | None = None
    root_raw_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    revision_id: str | None = None
    revision_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    confirmed_at: datetime | None = None
    original_local_present: bool | None = None
    original_base_present: bool | None = None
    realized_fx_pnl_local: Decimal | None = Field(default=None, allow_inf_nan=False)
    realized_fx_pnl_base: Decimal | None = Field(default=None, allow_inf_nan=False)
    producer_algorithm_version: Literal[1, 2] | None = None
    source_cut_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_qualified_identity(self) -> Self:
        if self.status == "UNAVAILABLE":
            if self.realized_fx_pnl_local is not None or self.realized_fx_pnl_base is not None:
                raise ValueError("Unavailable evidence cannot supply financial source amounts")
            return self
        if self.root_raw_id is None or self.root_raw_sha256 is None:
            raise ValueError("Qualified source requires an original retained root")
        if self.producer_algorithm_version is None:
            raise ValueError("Qualified source requires a verified producer receipt")
        if self.status == "CONFIRMED":
            if (
                self.revision_id is None
                or self.revision_sha256 is None
                or self.confirmed_at is None
            ):
                raise ValueError("Confirmed source requires immutable revision authority")
            if self.confirmed_at.tzinfo is None or self.confirmed_at.utcoffset() is None:
                raise ValueError("Confirmation time must be timezone-aware")
        elif self.revision_id is not None or self.revision_sha256 is not None:
            raise ValueError("Original source cannot claim confirmed revision authority")
        return self
