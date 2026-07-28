from datetime import date, datetime
from decimal import Decimal
from typing import List

from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.financial.precision import BOUNDED_18_10_EXACT
from portfolio_common.domain.valuation import (
    FinancialSourceReference,
    MarketPriceQuoteBasis,
    MarketPriceSourceFact,
    MarketPriceSourceFactStatus,
    ValuationAuthorityScope,
)
from portfolio_common.openapi_enrichment import exact_numeric_openapi_description
from pydantic import BaseModel, ConfigDict, Field, condecimal, field_validator, model_validator


class MarketPrice(BaseModel):
    security_id: str = Field(
        ...,
        description="Canonical security identifier receiving the market-price observation.",
        examples=["SEC_AAPL"],
    )
    price_date: date = Field(
        ...,
        description="Business date for which the market price is valid.",
        examples=["2026-03-10"],
    )
    price: condecimal(gt=Decimal(0)) = Field(
        ...,
        description=exact_numeric_openapi_description(
            "Canonical closing or approved valuation price.",
            precision=18,
            scale=10,
        ),
        examples=["175.5000000000"],
    )
    currency: str = Field(
        ...,
        description="Currency in which the market price is quoted.",
        examples=["USD"],
    )

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency_code(cls, value: object) -> str:
        return normalize_currency_code(value)

    @field_validator("price")
    @classmethod
    def _validate_exact_storage_shape(cls, value: Decimal) -> Decimal:
        return BOUNDED_18_10_EXACT.require_exact(value, field_name="price")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "security_id": "SEC_AAPL",
                "price_date": "2026-03-10",
                "price": 175.50,
                "currency": "USD",
            }
        }
    )


class MarketPriceIngestionRequest(BaseModel):
    market_prices: List[MarketPrice] = Field(
        ...,
        description="Market price observations to publish into the valuation reference-data flow.",
        min_length=1,
        examples=[
            [
                {
                    "security_id": "SEC_AAPL",
                    "price_date": "2026-03-10",
                    "price": "175.5000000000",
                    "currency": "USD",
                }
            ]
        ],
    )


class AuthoritativeMarketPriceSourceFact(BaseModel):
    """Exact-scope, source-versioned market-price authority."""

    tenant_id: str = Field(
        ...,
        min_length=1,
        description="Tenant boundary that owns the valuation fact.",
        examples=["LOTUS_PB_SG"],
    )
    legal_book_id: str = Field(
        ...,
        min_length=1,
        description="Exact legal book; booking-centre inference is prohibited.",
        examples=["SG_PRIVATE_BANK_BOOK"],
    )
    security_id: str = Field(
        ...,
        min_length=1,
        description="Canonical instrument identifier.",
        examples=["BOND_US_CORP_2031"],
    )
    price_date: date = Field(
        ...,
        description="Business date for which this source fact is authoritative.",
        examples=["2026-07-28"],
    )
    price: Decimal = Field(
        ...,
        gt=Decimal(0),
        allow_inf_nan=False,
        description=(
            "Positive finite source value supplied as an exact JSON decimal string and preserved "
            "without an implicit decimal scale or quote-convention inference."
        ),
        examples=["99.250000000000000000"],
    )
    currency: str = Field(
        ...,
        description="ISO 4217 currency of the supplied value.",
        examples=["USD"],
    )
    quote_basis: MarketPriceQuoteBasis = Field(
        ...,
        description="Explicit representation used by the assigned valuation policy.",
    )
    fact_status: MarketPriceSourceFactStatus = Field(
        ...,
        description="Lifecycle state of this exact source assertion.",
    )
    fact_version: int = Field(
        ...,
        ge=1,
        strict=True,
        description="Monotonically increasing correction version for the stable source record.",
        examples=[1],
    )
    source_system: str = Field(
        ...,
        min_length=1,
        description="Authoritative upstream market-data source.",
        examples=["approved_market_data"],
    )
    source_record_id: str = Field(
        ...,
        min_length=1,
        description="Stable upstream record identity across corrections.",
        examples=["PX-BOND_US_CORP_2031-20260728"],
    )
    source_revision: str = Field(
        ...,
        min_length=1,
        description="Source-native revision retained for replay and lineage.",
        examples=["rev-1"],
    )
    source_content_hash: str = Field(
        ...,
        pattern=r"^[0-9a-f]{64}$",
        description="Lowercase SHA-256 digest of the authoritative source content.",
        examples=["a" * 64],
    )
    observed_at: datetime = Field(
        ...,
        description="Timezone-aware instant at which the source observed this revision.",
        examples=["2026-07-28T09:30:00+08:00"],
    )

    @field_validator(
        "tenant_id",
        "legal_book_id",
        "security_id",
        "source_system",
        "source_record_id",
        "source_revision",
    )
    @classmethod
    def normalize_nonblank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("authority and source identity fields must be nonblank")
        return normalized

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    @field_validator("price", mode="before", json_schema_input_type=str)
    @classmethod
    def require_exact_decimal_string(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("price must be supplied as an exact decimal string")
        return value

    @field_validator("observed_at")
    @classmethod
    def require_aware_observation(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_domain_contract(self) -> "AuthoritativeMarketPriceSourceFact":
        self.to_domain()
        return self

    def to_domain(self) -> MarketPriceSourceFact:
        return MarketPriceSourceFact(
            scope=ValuationAuthorityScope(
                tenant_id=self.tenant_id,
                legal_book_id=self.legal_book_id,
                security_id=self.security_id,
            ),
            price_date=self.price_date,
            price=self.price,
            currency=self.currency,
            quote_basis=self.quote_basis,
            source_reference=FinancialSourceReference(
                source_system=self.source_system,
                source_record_id=self.source_record_id,
                source_revision=self.source_revision,
                source_content_hash=self.source_content_hash,
                observed_at=self.observed_at,
            ),
            fact_status=self.fact_status,
            fact_version=self.fact_version,
        )

    model_config = ConfigDict()


class AuthoritativeMarketPriceSourceFactIngestionRequest(BaseModel):
    market_price_source_facts: list[AuthoritativeMarketPriceSourceFact] = Field(
        ...,
        min_length=1,
        max_length=500,
        description=(
            "Exact-scope source facts persisted atomically after correction and overlap checks."
        ),
    )

    @model_validator(mode="after")
    def reject_duplicate_source_versions(
        self,
    ) -> "AuthoritativeMarketPriceSourceFactIngestionRequest":
        identities = [
            (
                fact.source_system,
                fact.source_record_id,
                fact.fact_version,
            )
            for fact in self.market_price_source_facts
        ]
        if len(identities) != len(set(identities)):
            raise ValueError(
                "market_price_source_facts contains duplicate source-version identities"
            )
        return self

    model_config = ConfigDict()
