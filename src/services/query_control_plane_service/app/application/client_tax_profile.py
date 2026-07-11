"""Application use case for effective client tax-reference evidence."""

from typing import Literal

from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import source_data_product_runtime_metadata

from ..contracts.client_tax_profile import (
    ClientTaxProfileEntry,
    ClientTaxProfileRequest,
    ClientTaxProfileResponse,
    ClientTaxProfileSupportability,
)
from ..domain.client_tax_profile import ClientTaxProfileSourceRecord
from ..domain.effective_mandate import EffectiveMandateBinding
from ..ports.client_tax_profile import ClientTaxProfileSourceReader
from ..ports.effective_mandate import EffectiveMandateReader
from .source_evidence import latest_evidence_timestamp


class ClientTaxProfileService:
    """Resolve one deterministic tax-reference profile source product."""

    def __init__(
        self,
        *,
        mandate_reader: EffectiveMandateReader,
        reader: ClientTaxProfileSourceReader,
        clock: Clock,
    ) -> None:
        self._mandate_reader = mandate_reader
        self._reader = reader
        self._clock = clock

    async def get_client_tax_profile(
        self, *, portfolio_id: str, request: ClientTaxProfileRequest
    ) -> ClientTaxProfileResponse | None:
        binding = await self._mandate_reader.resolve(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None
        profiles = await self._reader.list_profiles(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_profiles=request.include_inactive_profiles,
        )
        return self._build_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
            profiles=profiles,
        )

    def _build_response(
        self,
        *,
        portfolio_id: str,
        binding: EffectiveMandateBinding,
        request: ClientTaxProfileRequest,
        profiles: list[ClientTaxProfileSourceRecord],
    ) -> ClientTaxProfileResponse:
        entries = [_entry(record) for record in profiles]
        state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        reason = "CLIENT_TAX_PROFILE_READY"
        missing: list[str] = []
        if not profiles:
            state = "INCOMPLETE"
            reason = "CLIENT_TAX_PROFILE_EMPTY"
            missing.append("client_tax_profile")
        return ClientTaxProfileResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            profiles=entries,
            supportability=ClientTaxProfileSupportability(
                state=state,
                reason=reason,
                profile_count=len(entries),
                missing_data_families=missing,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "client_tax_profiles,portfolio_mandate_bindings",
                "contract_version": "rfc_042_client_tax_profile_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=self._clock.utc_now(),
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if profiles else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp([binding], profiles),
                source_batch_fingerprint=None,
                snapshot_id="client_tax_profile:"
                + request_fingerprint(
                    {
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "as_of_date": request.as_of_date.isoformat(),
                    }
                ),
            ),
        )


def _entry(record: ClientTaxProfileSourceRecord) -> ClientTaxProfileEntry:
    return ClientTaxProfileEntry(
        tax_profile_id=record.tax_profile_id,
        tax_residency_country=record.tax_residency_country,
        booking_tax_jurisdiction=record.booking_tax_jurisdiction,
        tax_status=record.tax_status,
        profile_status=record.profile_status,
        withholding_tax_rate=record.withholding_tax_rate,
        capital_gains_tax_applicable=record.capital_gains_tax_applicable,
        income_tax_applicable=record.income_tax_applicable,
        treaty_codes=list(record.treaty_codes),
        eligible_account_types=list(record.eligible_account_types),
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        profile_version=record.profile_version,
        source_record_id=record.source_record_id,
    )
