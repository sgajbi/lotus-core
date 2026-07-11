"""Behavior tests for QCP-owned sustainability preference resolution."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application import (
    sustainability_preference_profile as preference_application,
)
from src.services.query_control_plane_service.app.contracts import (
    sustainability_preference_profile as preference_contracts,
)
from src.services.query_control_plane_service.app.domain.effective_mandate import (
    EffectiveMandateBinding,
)
from src.services.query_control_plane_service.app.domain.sustainability_preference_profile import (
    SustainabilityPreferenceSourceRecord,
)

SustainabilityPreferenceProfileService = (
    preference_application.SustainabilityPreferenceProfileService
)
SustainabilityPreferenceProfileRequest = preference_contracts.SustainabilityPreferenceProfileRequest


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 5, 3, 10, tzinfo=UTC)


class _Reader:
    def __init__(self, binding, preferences):
        self.binding = binding
        self.preferences = preferences
        self.calls: list[str] = []

    async def resolve_mandate_binding(self, **_):
        self.calls.append("binding")
        return self.binding

    async def list_preferences(self, **_):
        self.calls.append("preferences")
        return self.preferences


def _binding() -> EffectiveMandateBinding:
    return EffectiveMandateBinding(
        client_id="CIF_SG_000184",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 7, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def _preference() -> SustainabilityPreferenceSourceRecord:
    return SustainabilityPreferenceSourceRecord(
        preference_framework="LOTUS_SUSTAINABILITY_V1",
        preference_code="MIN_SUSTAINABLE_ALLOCATION",
        preference_status="active",
        preference_source="client_mandate",
        minimum_allocation=Decimal("0.2000000000"),
        maximum_allocation=None,
        applies_to_asset_classes=("equity", "fixed_income"),
        exclusion_codes=("THERMAL_COAL",),
        positive_tilt_codes=("LOW_CARBON_TRANSITION",),
        effective_from=date(2026, 1, 1),
        effective_to=None,
        preference_version=1,
        source_record_id="sustainability:1",
        observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


def _request() -> SustainabilityPreferenceProfileRequest:
    return SustainabilityPreferenceProfileRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
    )


@pytest.mark.asyncio
async def test_resolves_ready_preference_profile() -> None:
    reader = _Reader(_binding(), [_preference()])
    service = SustainabilityPreferenceProfileService(reader=reader, clock=_Clock())

    response = await service.get_sustainability_preference_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )

    assert response is not None
    assert response.generated_at == datetime(2026, 5, 3, 10, tzinfo=UTC)
    assert response.supportability.state == "READY"
    assert response.preferences[0].minimum_allocation == Decimal("0.2000000000")
    assert response.preferences[0].exclusion_codes == ["THERMAL_COAL"]
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert response.snapshot_id is not None
    assert reader.calls == ["binding", "preferences"]


@pytest.mark.asyncio
async def test_marks_empty_profile_incomplete() -> None:
    service = SustainabilityPreferenceProfileService(reader=_Reader(_binding(), []), clock=_Clock())

    response = await service.get_sustainability_preference_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )

    assert response is not None
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.missing_data_families == ["sustainability_preferences"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)


@pytest.mark.asyncio
async def test_missing_binding_skips_preference_read() -> None:
    reader = _Reader(None, [_preference()])
    service = SustainabilityPreferenceProfileService(reader=reader, clock=_Clock())

    response = await service.get_sustainability_preference_profile(
        portfolio_id="PB_MISSING", request=_request()
    )

    assert response is None
    assert reader.calls == ["binding"]


@pytest.mark.asyncio
async def test_snapshot_identity_is_stable_for_same_scope() -> None:
    service = SustainabilityPreferenceProfileService(
        reader=_Reader(_binding(), [_preference()]), clock=_Clock()
    )
    first = await service.get_sustainability_preference_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )
    second = await service.get_sustainability_preference_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )
    assert first is not None and second is not None
    assert first.snapshot_id == second.snapshot_id
