"""Application use case for the effective client restriction source product."""

from typing import Literal

from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import source_data_product_runtime_metadata

from ..contracts.client_restriction_profile import (
    ClientRestrictionProfileEntry,
    ClientRestrictionProfileRequest,
    ClientRestrictionProfileResponse,
    ClientRestrictionProfileSupportability,
)
from ..domain.client_restriction_profile import (
    ClientRestrictionSourceRecord,
)
from ..domain.effective_mandate import EffectiveMandateBinding
from ..ports.client_restriction_profile import ClientRestrictionProfileSourceReader
from .source_evidence import latest_evidence_timestamp


class ClientRestrictionProfileService:
    """Resolve one deterministic restriction profile through an explicit source port."""

    def __init__(self, *, reader: ClientRestrictionProfileSourceReader, clock: Clock) -> None:
        self._reader = reader
        self._clock = clock

    async def get_client_restriction_profile(
        self,
        *,
        portfolio_id: str,
        request: ClientRestrictionProfileRequest,
    ) -> ClientRestrictionProfileResponse | None:
        binding = await self._reader.resolve_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        restrictions = await self._reader.list_restrictions(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_restrictions=request.include_inactive_restrictions,
        )
        return self._build_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
            restrictions=restrictions,
        )

    def _build_response(
        self,
        *,
        portfolio_id: str,
        binding: EffectiveMandateBinding,
        request: ClientRestrictionProfileRequest,
        restrictions: list[ClientRestrictionSourceRecord],
    ) -> ClientRestrictionProfileResponse:
        entries = [_restriction_entry(record) for record in restrictions]
        supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "CLIENT_RESTRICTION_PROFILE_READY"
        missing_data_families: list[str] = []
        if not restrictions:
            supportability_state = "INCOMPLETE"
            supportability_reason = "CLIENT_RESTRICTION_PROFILE_EMPTY"
            missing_data_families.append("client_restrictions")

        return ClientRestrictionProfileResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            restrictions=entries,
            supportability=ClientRestrictionProfileSupportability(
                state=supportability_state,
                reason=supportability_reason,
                restriction_count=len(entries),
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "client_restriction_profiles,portfolio_mandate_bindings",
                "contract_version": "rfc_040_client_restriction_profile_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=self._clock.utc_now(),
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if restrictions else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp([binding], restrictions),
                source_batch_fingerprint=None,
                snapshot_id=(
                    "client_restriction_profile:"
                    + request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                        }
                    )
                ),
            ),
        )


def _restriction_entry(record: ClientRestrictionSourceRecord) -> ClientRestrictionProfileEntry:
    return ClientRestrictionProfileEntry(
        restriction_scope=record.restriction_scope,
        restriction_code=record.restriction_code,
        restriction_status=record.restriction_status,
        restriction_source=record.restriction_source,
        applies_to_buy=record.applies_to_buy,
        applies_to_sell=record.applies_to_sell,
        instrument_ids=list(record.instrument_ids),
        asset_classes=list(record.asset_classes),
        issuer_ids=list(record.issuer_ids),
        country_codes=list(record.country_codes),
        effective_from=record.effective_from,
        effective_to=record.effective_to,
        restriction_version=record.restriction_version,
        source_record_id=record.source_record_id,
    )
