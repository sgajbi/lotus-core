"""API contracts for fail-closed external treasury and OMS source posture."""

from datetime import date
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class ExternalCurrencyExposureRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description=(
            "Business date used to evaluate external treasury currency exposure availability."
        ),
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    reporting_currency: str | None = Field(
        None,
        description="Optional reporting currency supplied by the portfolio-management request.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description=(
            "Optional currency universe requested for hedge policy evaluation. The current "
            "source-owner posture remains unavailable until external treasury ingestion is "
            "certified."
        ),
        examples=[["EUR", "JPY"]],
    )

    model_config = ConfigDict()


class ExternalCurrencyExposureSupportability(BaseModel):
    state: Literal["UNAVAILABLE"] = Field(
        "UNAVAILABLE",
        description=(
            "Supportability state for external treasury currency exposure. The current Lotus "
            "Core runtime exposes only fail-closed unavailable posture."
        ),
        examples=["UNAVAILABLE"],
    )
    reason: Literal["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"] = Field(
        "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED",
        description="Machine-readable fail-closed reason.",
        examples=["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"],
    )
    exposure_count: int = Field(
        0,
        ge=0,
        description="Number of external currency exposure rows returned.",
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description="External treasury source-data families required before exposures can be used.",
    )
    blocked_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities explicitly blocked by unavailable exposure posture.",
    )

    model_config = ConfigDict()


class ExternalCurrencyExposureResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["ExternalCurrencyExposure"] = product_name_field(
        "ExternalCurrencyExposure"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the exposure posture.")
    client_id: str = Field(..., description="Client identifier bound to the portfolio mandate.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    reporting_currency: str | None = Field(
        None,
        description="Requested reporting currency echoed for source-data audit.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description="Requested currency universe echoed for source-data audit.",
    )
    exposures: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "External treasury exposure rows. Empty while external treasury ingestion is not "
            "certified."
        ),
    )
    supportability: ExternalCurrencyExposureSupportability = Field(
        ..., description="Fail-closed supportability posture for external currency exposure."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage and non-claim posture for external currency exposure.",
    )

    model_config = ConfigDict()


class ExternalHedgePolicyRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Business date used to evaluate external treasury hedge-policy availability.",
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    reporting_currency: str | None = Field(
        None,
        description="Optional reporting currency supplied by the portfolio-management request.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description=(
            "Optional exposure currencies whose hedge-policy posture is requested. The current "
            "source-owner posture remains unavailable until external treasury policy ingestion "
            "is certified."
        ),
        examples=[["EUR", "JPY"]],
    )

    model_config = ConfigDict()


class ExternalHedgePolicySupportability(BaseModel):
    state: Literal["UNAVAILABLE"] = Field(
        "UNAVAILABLE",
        description=(
            "Supportability state for external treasury hedge policy. The current Lotus Core "
            "runtime exposes only fail-closed unavailable posture."
        ),
        examples=["UNAVAILABLE"],
    )
    reason: Literal["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"] = Field(
        "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED",
        description="Machine-readable fail-closed reason.",
        examples=["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"],
    )
    policy_rule_count: int = Field(
        0,
        ge=0,
        description="Number of external hedge policy rules returned.",
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description="External treasury source-data families required before policy can be used.",
    )
    blocked_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities explicitly blocked by unavailable hedge-policy posture.",
    )

    model_config = ConfigDict()


class ExternalHedgePolicyResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["ExternalHedgePolicy"] = product_name_field("ExternalHedgePolicy")
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the policy posture.")
    client_id: str = Field(..., description="Client identifier bound to the portfolio mandate.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    reporting_currency: str | None = Field(
        None,
        description="Requested reporting currency echoed for source-data audit.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description="Requested exposure currencies echoed for source-data audit.",
    )
    policy_rules: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "External treasury hedge-policy rules. Empty while external treasury policy "
            "ingestion is not certified."
        ),
    )
    supportability: ExternalHedgePolicySupportability = Field(
        ..., description="Fail-closed supportability posture for external hedge policy."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage and non-claim posture for external hedge policy.",
    )

    model_config = ConfigDict()


class ExternalEligibleHedgeInstrumentRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description=(
            "Business date used to evaluate external treasury eligible hedge instrument "
            "availability."
        ),
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    reporting_currency: str | None = Field(
        None,
        description="Optional reporting currency supplied by the portfolio-management request.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description=(
            "Optional exposure currencies whose eligible hedge instrument posture is "
            "requested. The current source-owner posture remains unavailable until "
            "external treasury instrument eligibility ingestion is certified."
        ),
        examples=[["EUR", "JPY"]],
    )
    instrument_types: list[str] = Field(
        default_factory=list,
        description=(
            "Optional external treasury instrument types requested for audit symmetry. "
            "Core does not infer product shelf eligibility or suitability locally."
        ),
        examples=[["FX_FORWARD", "FX_SWAP"]],
    )

    model_config = ConfigDict()


class ExternalEligibleHedgeInstrumentSupportability(BaseModel):
    state: Literal["UNAVAILABLE"] = Field(
        "UNAVAILABLE",
        description=(
            "Supportability state for external treasury eligible hedge instruments. The "
            "current Lotus Core runtime exposes only fail-closed unavailable posture."
        ),
        examples=["UNAVAILABLE"],
    )
    reason: Literal["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"] = Field(
        "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED",
        description="Machine-readable fail-closed reason.",
        examples=["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"],
    )
    instrument_count: int = Field(
        0,
        ge=0,
        description="Number of eligible hedge instrument rows returned.",
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description=(
            "External treasury source-data families required before eligible hedge "
            "instrument evidence can be used."
        ),
    )
    blocked_capabilities: list[str] = Field(
        default_factory=list,
        description=("Capabilities explicitly blocked by unavailable eligible-instrument posture."),
    )

    model_config = ConfigDict()


class ExternalEligibleHedgeInstrumentResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["ExternalEligibleHedgeInstrument"] = product_name_field(
        "ExternalEligibleHedgeInstrument"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ..., description="Portfolio identifier for the eligible-instrument posture."
    )
    client_id: str = Field(..., description="Client identifier bound to the portfolio mandate.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    reporting_currency: str | None = Field(
        None,
        description="Requested reporting currency echoed for source-data audit.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description="Requested exposure currencies echoed for source-data audit.",
    )
    instrument_types: list[str] = Field(
        default_factory=list,
        description="Requested external treasury instrument types echoed for source-data audit.",
    )
    eligible_instruments: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "External treasury eligible hedge instrument rows. Empty while external treasury "
            "instrument eligibility ingestion is not certified."
        ),
    )
    supportability: ExternalEligibleHedgeInstrumentSupportability = Field(
        ...,
        description=("Fail-closed supportability posture for external eligible hedge instruments."),
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Source lineage and non-claim posture for external eligible hedge instruments."
        ),
    )

    model_config = ConfigDict()


class ExternalFXForwardCurveRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description=(
            "Business date used to evaluate external treasury FX forward curve availability."
        ),
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    reporting_currency: str | None = Field(
        None,
        description="Optional reporting currency supplied by the portfolio-management request.",
        examples=["USD"],
    )
    currency_pairs: list[str] = Field(
        default_factory=list,
        description=(
            "Optional ISO currency pairs requested for FX forward readiness. The current "
            "source-owner posture remains unavailable until external treasury curve ingestion "
            "is certified."
        ),
        examples=[["EUR/USD", "USD/JPY"]],
    )
    tenors: list[str] = Field(
        default_factory=list,
        description=(
            "Optional forward tenors requested for audit symmetry. Core does not price "
            "forwards or infer missing tenor points locally."
        ),
        examples=[["1M", "3M", "6M"]],
    )

    model_config = ConfigDict()


class ExternalFXForwardCurveSupportability(BaseModel):
    state: Literal["UNAVAILABLE"] = Field(
        "UNAVAILABLE",
        description=(
            "Supportability state for external treasury FX forward curves. The current Lotus "
            "Core runtime exposes only fail-closed unavailable posture."
        ),
        examples=["UNAVAILABLE"],
    )
    reason: Literal["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"] = Field(
        "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED",
        description="Machine-readable fail-closed reason.",
        examples=["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"],
    )
    curve_point_count: int = Field(
        0,
        ge=0,
        description="Number of external FX forward curve points returned.",
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description="External treasury source-data families required before curves can be used.",
    )
    blocked_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities explicitly blocked by unavailable forward-curve posture.",
    )

    model_config = ConfigDict()


class ExternalFXForwardCurveResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["ExternalFXForwardCurve"] = product_name_field("ExternalFXForwardCurve")
    product_version: Literal["v1"] = product_version_field()
    reporting_currency: str | None = Field(
        None,
        description="Requested reporting currency echoed for source-data audit.",
        examples=["USD"],
    )
    currency_pairs: list[str] = Field(
        default_factory=list,
        description="Requested currency pairs echoed for source-data audit.",
    )
    tenors: list[str] = Field(
        default_factory=list,
        description="Requested forward tenors echoed for source-data audit.",
    )
    curve_points: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "External treasury FX forward curve points. Empty while external treasury curve "
            "ingestion is not certified."
        ),
    )
    supportability: ExternalFXForwardCurveSupportability = Field(
        ..., description="Fail-closed supportability posture for external FX forward curves."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage and non-claim posture for external FX forward curves.",
    )

    model_config = ConfigDict()


class ExternalHedgeExecutionReadinessRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description=(
            "Business date used to evaluate external treasury source availability for hedge "
            "execution readiness."
        ),
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    reporting_currency: str | None = Field(
        None,
        description="Optional reporting currency supplied by the portfolio-management request.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description=(
            "Optional exposure currencies to check for treasury readiness. The current "
            "source-owner posture remains unavailable until external treasury ingestion is "
            "certified."
        ),
        examples=[["EUR", "JPY"]],
    )

    model_config = ConfigDict()


class ExternalHedgeExecutionReadinessSupportability(BaseModel):
    state: Literal["UNAVAILABLE"] = Field(
        "UNAVAILABLE",
        description=(
            "Supportability state for external treasury hedge execution readiness. The current "
            "Lotus Core runtime exposes only fail-closed unavailable posture."
        ),
        examples=["UNAVAILABLE"],
    )
    reason: Literal["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"] = Field(
        "EXTERNAL_TREASURY_SOURCE_NOT_INGESTED",
        description="Machine-readable fail-closed reason.",
        examples=["EXTERNAL_TREASURY_SOURCE_NOT_INGESTED"],
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description="External treasury source-data families required before readiness can be used.",
    )
    blocked_capabilities: list[str] = Field(
        default_factory=list,
        description=(
            "Capabilities explicitly blocked by the unavailable posture. These are non-claims, "
            "not pending recommendations."
        ),
    )

    model_config = ConfigDict()


class ExternalHedgeExecutionReadinessResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["ExternalHedgeExecutionReadiness"] = product_name_field(
        "ExternalHedgeExecutionReadiness"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(..., description="Portfolio identifier for the readiness posture.")
    client_id: str = Field(..., description="Client identifier bound to the portfolio mandate.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    reporting_currency: str | None = Field(
        None,
        description="Requested reporting currency echoed for source-data audit.",
        examples=["USD"],
    )
    exposure_currencies: list[str] = Field(
        default_factory=list,
        description="Requested exposure currencies echoed for source-data audit.",
    )
    readiness_checks: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "External treasury readiness checks. Empty while external treasury ingestion is not "
            "certified."
        ),
    )
    supportability: ExternalHedgeExecutionReadinessSupportability = Field(
        ..., description="Fail-closed supportability posture for external treasury readiness."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage and non-claim posture for external treasury readiness.",
    )

    model_config = ConfigDict()


class ExternalOrderExecutionAcknowledgementRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description=(
            "Business date used to evaluate external OMS acknowledgement availability for "
            "portfolio execution evidence."
        ),
        examples=["2026-05-03"],
    )
    tenant_id: str | None = Field(None, description="Optional tenant identifier.")
    mandate_id: str | None = Field(None, description="Optional mandate disambiguator.")
    execution_intent_id: str | None = Field(
        None,
        description=(
            "Optional downstream execution-intent identifier echoed for audit. Core does not "
            "create, route, or amend orders from this value."
        ),
        examples=["rebalance-run-2026-05-03-001"],
    )
    order_reference_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Optional external order references requested for acknowledgement lookup. The "
            "current source-owner posture remains unavailable until bank-owned OMS "
            "acknowledgement ingestion is certified."
        ),
        examples=[["OMS-ORDER-001", "OMS-ORDER-002"]],
    )

    model_config = ConfigDict()


class ExternalOrderExecutionAcknowledgementSupportability(BaseModel):
    state: Literal["UNAVAILABLE"] = Field(
        "UNAVAILABLE",
        description=(
            "Supportability state for external OMS order-execution acknowledgement. The "
            "current Lotus Core runtime exposes only fail-closed unavailable posture."
        ),
        examples=["UNAVAILABLE"],
    )
    reason: Literal["EXTERNAL_OMS_SOURCE_NOT_INGESTED"] = Field(
        "EXTERNAL_OMS_SOURCE_NOT_INGESTED",
        description="Machine-readable fail-closed reason.",
        examples=["EXTERNAL_OMS_SOURCE_NOT_INGESTED"],
    )
    acknowledgement_count: int = Field(
        0,
        ge=0,
        description="Number of external OMS acknowledgement rows returned.",
    )
    missing_data_families: list[str] = Field(
        default_factory=list,
        description=(
            "External OMS source-data families required before acknowledgement evidence can "
            "be used."
        ),
    )
    blocked_capabilities: list[str] = Field(
        default_factory=list,
        description=("Capabilities explicitly blocked by unavailable OMS acknowledgement posture."),
    )

    model_config = ConfigDict()


class ExternalOrderExecutionAcknowledgementResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["ExternalOrderExecutionAcknowledgement"] = product_name_field(
        "ExternalOrderExecutionAcknowledgement"
    )
    product_version: Literal["v1"] = product_version_field()
    portfolio_id: str = Field(
        ..., description="Portfolio identifier for the OMS acknowledgement posture."
    )
    client_id: str = Field(..., description="Client identifier bound to the portfolio mandate.")
    mandate_id: str | None = Field(None, description="Mandate identifier, when available.")
    execution_intent_id: str | None = Field(
        None,
        description="Requested execution-intent identifier echoed for downstream audit.",
    )
    order_reference_ids: list[str] = Field(
        default_factory=list,
        description="Requested external order references echoed for downstream audit.",
    )
    acknowledgements: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "External OMS acknowledgement rows. Empty while external OMS acknowledgement "
            "ingestion is not certified."
        ),
    )
    supportability: ExternalOrderExecutionAcknowledgementSupportability = Field(
        ...,
        description="Fail-closed supportability posture for external OMS acknowledgement.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Source lineage and non-claim posture for external OMS acknowledgement.",
    )

    model_config = ConfigDict()
