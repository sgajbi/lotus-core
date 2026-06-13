from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClientRestrictionProfileRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the restriction profile.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the restriction profile.")
    mandate_id: str | None = Field(
        None, description="Mandate identifier when the restriction is mandate-specific."
    )
    restriction_scope: Literal[
        "client", "mandate", "instrument", "issuer", "country", "asset_class"
    ] = Field(..., description="Bounded restriction scope.")
    restriction_code: str = Field(
        ..., description="Machine-readable restriction code.", examples=["NO_PRIVATE_CREDIT_BUY"]
    )
    restriction_status: Literal["active", "inactive", "suspended"] = Field(
        "active", description="Restriction lifecycle status."
    )
    restriction_source: str = Field(
        ..., description="Source channel that captured the restriction."
    )
    applies_to_buy: bool = Field(True, description="Whether the restriction applies to buys.")
    applies_to_sell: bool = Field(False, description="Whether the restriction applies to sells.")
    instrument_ids: list[str] = Field(default_factory=list)
    asset_classes: list[str] = Field(default_factory=list)
    issuer_ids: list[str] = Field(default_factory=list)
    country_codes: list[str] = Field(default_factory=list)
    effective_from: date = Field(..., description="Restriction effective start date.")
    effective_to: date | None = Field(None, description="Restriction effective end date.")
    restriction_version: int = Field(1, ge=1)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @model_validator(mode="after")
    def validate_profile(self) -> "ClientRestrictionProfileRecord":
        _validate_effective_window(self.effective_from, self.effective_to)
        _validate_scoped_restriction_values(
            restriction_scope=self.restriction_scope,
            instrument_ids=self.instrument_ids,
            asset_classes=self.asset_classes,
            issuer_ids=self.issuer_ids,
            country_codes=self.country_codes,
        )
        return self

    model_config = ConfigDict()


class ClientRestrictionProfileIngestionRequest(BaseModel):
    restriction_profiles: list[ClientRestrictionProfileRecord] = Field(
        ...,
        description="Effective-dated client restriction profile records to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_profile_uniqueness(self) -> "ClientRestrictionProfileIngestionRequest":
        keys = [
            (
                profile.client_id,
                profile.portfolio_id,
                profile.restriction_code,
                profile.effective_from,
                profile.restriction_version,
            )
            for profile in self.restriction_profiles
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("restriction_profiles contains duplicate effective records")
        return self

    model_config = ConfigDict()


def _validate_effective_window(effective_from: date, effective_to: date | None) -> None:
    if effective_to is not None and effective_to < effective_from:
        raise ValueError("effective_to must be on or after effective_from")


def _validate_scoped_restriction_values(
    *,
    restriction_scope: str,
    instrument_ids: list[str],
    asset_classes: list[str],
    issuer_ids: list[str],
    country_codes: list[str],
) -> None:
    if _restriction_scope_requires_values(restriction_scope) and not _has_scoped_values(
        instrument_ids=instrument_ids,
        asset_classes=asset_classes,
        issuer_ids=issuer_ids,
        country_codes=country_codes,
    ):
        raise ValueError("scoped restrictions must include at least one scoped identifier")


def _restriction_scope_requires_values(restriction_scope: str) -> bool:
    return restriction_scope not in {"client", "mandate"}


def _has_scoped_values(
    *,
    instrument_ids: list[str],
    asset_classes: list[str],
    issuer_ids: list[str],
    country_codes: list[str],
) -> bool:
    return any((instrument_ids, asset_classes, issuer_ids, country_codes))
