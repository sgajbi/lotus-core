"""Application use case for effective sustainability preference evidence."""

from typing import Literal

from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import source_data_product_runtime_metadata

from ..contracts.sustainability_preference_profile import (
    SustainabilityPreferenceProfileEntry,
    SustainabilityPreferenceProfileRequest,
    SustainabilityPreferenceProfileResponse,
    SustainabilityPreferenceProfileSupportability,
)
from ..domain.effective_mandate import EffectiveMandateBinding
from ..domain.sustainability_preference_profile import SustainabilityPreferenceSourceRecord
from ..ports.sustainability_preference_profile import SustainabilityPreferenceProfileSourceReader
from .source_evidence import latest_evidence_timestamp


class SustainabilityPreferenceProfileService:
    """Resolve one deterministic sustainability preference profile."""

    def __init__(
        self, *, reader: SustainabilityPreferenceProfileSourceReader, clock: Clock
    ) -> None:
        self._reader = reader
        self._clock = clock

    async def get_sustainability_preference_profile(
        self, *, portfolio_id: str, request: SustainabilityPreferenceProfileRequest
    ) -> SustainabilityPreferenceProfileResponse | None:
        binding = await self._reader.resolve_mandate_binding(
            portfolio_id=portfolio_id, as_of_date=request.as_of_date, mandate_id=request.mandate_id
        )
        if binding is None:
            return None
        preferences = await self._reader.list_preferences(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_preferences=request.include_inactive_preferences,
        )
        return self._build_response(
            portfolio_id=portfolio_id, binding=binding, request=request, preferences=preferences
        )

    def _build_response(
        self,
        *,
        portfolio_id: str,
        binding: EffectiveMandateBinding,
        request: SustainabilityPreferenceProfileRequest,
        preferences: list[SustainabilityPreferenceSourceRecord],
    ) -> SustainabilityPreferenceProfileResponse:
        entries = [_entry(record) for record in preferences]
        state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        reason = "SUSTAINABILITY_PREFERENCE_PROFILE_READY"
        missing: list[str] = []
        if not preferences:
            state = "INCOMPLETE"
            reason = "SUSTAINABILITY_PREFERENCE_PROFILE_EMPTY"
            missing.append("sustainability_preferences")
        return SustainabilityPreferenceProfileResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            preferences=entries,
            supportability=SustainabilityPreferenceProfileSupportability(
                state=state,
                reason=reason,
                preference_count=len(entries),
                missing_data_families=missing,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "sustainability_preference_profiles,portfolio_mandate_bindings",
                "contract_version": "rfc_040_sustainability_preference_profile_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=self._clock.utc_now(),
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if preferences else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp([binding], preferences),
                source_batch_fingerprint=None,
                snapshot_id="sustainability_preference_profile:"
                + request_fingerprint(
                    {
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "as_of_date": request.as_of_date.isoformat(),
                    }
                ),
            ),
        )


def _entry(record: SustainabilityPreferenceSourceRecord) -> SustainabilityPreferenceProfileEntry:
    return SustainabilityPreferenceProfileEntry(
        preference_framework=record.preference_framework,
        preference_code=record.preference_code,
        preference_status=record.preference_status,
        preference_source=record.preference_source,
        minimum_allocation=record.minimum_allocation,
        maximum_allocation=record.maximum_allocation,
        applies_to_asset_classes=list(record.applies_to_asset_classes),
        exclusion_codes=list(record.exclusion_codes),
        positive_tilt_codes=list(record.positive_tilt_codes),
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        preference_version=record.preference_version,
        source_record_id=record.source_record_id,
    )
