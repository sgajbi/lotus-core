"""Application policy for bulk instrument eligibility evidence."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from ...contracts.instrument_eligibility import (
    InstrumentEligibilityBulkRequest,
    InstrumentEligibilityBulkResponse,
    InstrumentEligibilityRecord,
    InstrumentEligibilitySupportability,
)
from ...domain.dpm_source_readiness import InstrumentEligibilityEvidence
from ...ports.dpm_source_readiness import DpmReferenceDataReader
from .metadata import dpm_source_runtime_metadata

EligibilityStatus = Literal["APPROVED", "RESTRICTED", "SELL_ONLY", "BANNED", "UNKNOWN"]


@dataclass(slots=True)
class InstrumentEligibilityService:
    """Resolve effective eligibility while preserving canonical request order."""

    reader: DpmReferenceDataReader
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def resolve(
        self,
        request: InstrumentEligibilityBulkRequest,
    ) -> InstrumentEligibilityBulkResponse:
        evidence = await self.reader.list_instrument_eligibility_profiles(
            security_ids=request.security_ids,
            as_of_date=request.as_of_date,
        )
        return build_instrument_eligibility_response(
            request=request,
            evidence=evidence,
            generated_at=self.clock(),
        )


def build_instrument_eligibility_response(
    *,
    request: InstrumentEligibilityBulkRequest,
    evidence: list[InstrumentEligibilityEvidence],
    generated_at: datetime,
) -> InstrumentEligibilityBulkResponse:
    """Map eligibility evidence and represent every requested identifier explicitly."""

    evidence_by_id = {row.security_id.strip(): row for row in evidence}
    records: list[InstrumentEligibilityRecord] = []
    missing_security_ids: list[str] = []
    for security_id in request.security_ids:
        row = evidence_by_id.get(security_id)
        if row is None:
            missing_security_ids.append(security_id)
            records.append(_missing_record(security_id))
        else:
            records.append(_eligibility_record(row))
    supportability = InstrumentEligibilitySupportability(
        state="INCOMPLETE" if missing_security_ids else "READY",
        reason=(
            "INSTRUMENT_ELIGIBILITY_MISSING"
            if missing_security_ids
            else "INSTRUMENT_ELIGIBILITY_READY"
        ),
        requested_count=len(request.security_ids),
        resolved_count=len(request.security_ids) - len(missing_security_ids),
        missing_security_ids=missing_security_ids,
    )
    lineage = {
        "source_system": "instrument_eligibility",
        "contract_version": "rfc_087_v1",
    }
    content_payload = {
        "records": [record.model_dump(mode="json") for record in records],
        "supportability": supportability.model_dump(mode="json"),
        "lineage": lineage,
    }
    return InstrumentEligibilityBulkResponse(
        **content_payload,
        **dpm_source_runtime_metadata(
            product_name="InstrumentEligibilityProfile",
            source_key="bulk",
            as_of_date=request.as_of_date,
            generated_at=generated_at,
            tenant_id=request.tenant_id,
            data_quality_status=_data_quality_status(
                evidence=evidence,
                missing_security_ids=missing_security_ids,
            ),
            latest_evidence_timestamp=_latest_evidence_timestamp(evidence),
            content_payload={
                "as_of_date": request.as_of_date,
                "requested_security_ids": request.security_ids,
                **content_payload,
            },
            lineage=lineage,
        ),
    )


def _eligibility_record(evidence: InstrumentEligibilityEvidence) -> InstrumentEligibilityRecord:
    return InstrumentEligibilityRecord(
        security_id=evidence.security_id.strip(),
        found=True,
        eligibility_status=_eligibility_status(evidence.eligibility_status),
        product_shelf_status=_control_code(evidence.product_shelf_status),
        buy_allowed=evidence.buy_allowed,
        sell_allowed=evidence.sell_allowed,
        restriction_reason_codes=list(evidence.restriction_reason_codes),
        settlement_days=evidence.settlement_days,
        settlement_calendar_id=evidence.settlement_calendar_id,
        liquidity_tier=evidence.liquidity_tier,
        issuer_id=evidence.issuer_id,
        issuer_name=evidence.issuer_name,
        ultimate_parent_issuer_id=evidence.ultimate_parent_issuer_id,
        ultimate_parent_issuer_name=evidence.ultimate_parent_issuer_name,
        asset_class=evidence.asset_class,
        country_of_risk=evidence.country_of_risk,
        effective_from=evidence.effective_from,
        effective_to=evidence.effective_to,
        quality_status=_control_code(evidence.quality_status),
        source_record_id=evidence.source_record_id,
    )


def _missing_record(security_id: str) -> InstrumentEligibilityRecord:
    return InstrumentEligibilityRecord(
        security_id=security_id,
        found=False,
        eligibility_status="UNKNOWN",
        product_shelf_status="UNKNOWN",
        buy_allowed=False,
        sell_allowed=False,
        restriction_reason_codes=["ELIGIBILITY_PROFILE_MISSING"],
        settlement_days=None,
        settlement_calendar_id=None,
        liquidity_tier=None,
        issuer_id=None,
        issuer_name=None,
        ultimate_parent_issuer_id=None,
        ultimate_parent_issuer_name=None,
        asset_class=None,
        country_of_risk=None,
        effective_from=None,
        effective_to=None,
        quality_status="MISSING",
        source_record_id=None,
    )


def _control_code(value: str) -> str:
    return value.strip().upper() or "UNKNOWN"


def _eligibility_status(value: str) -> EligibilityStatus:
    normalized = _control_code(value)
    if normalized in {"APPROVED", "RESTRICTED", "SELL_ONLY", "BANNED"}:
        return cast(EligibilityStatus, normalized)
    return "UNKNOWN"


def _data_quality_status(
    *,
    evidence: list[InstrumentEligibilityEvidence],
    missing_security_ids: list[str],
) -> str:
    if missing_security_ids:
        return "PARTIAL" if evidence else "UNKNOWN"
    accepted = {"ACCEPTED", "COMPLETE", "READY"}
    return (
        "COMPLETE"
        if evidence and all(_control_code(row.quality_status) in accepted for row in evidence)
        else "PARTIAL"
    )


def _latest_evidence_timestamp(
    evidence: list[InstrumentEligibilityEvidence],
) -> datetime | None:
    timestamps = [
        timestamp
        for row in evidence
        for timestamp in (row.observed_at, row.updated_at, row.created_at)
        if timestamp is not None
    ]
    return max(timestamps) if timestamps else None
