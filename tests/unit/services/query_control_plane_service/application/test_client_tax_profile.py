"""Behavior tests for QCP-owned client tax-profile resolution."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.client_tax_profile import (
    ClientTaxProfileService,
)
from src.services.query_control_plane_service.app.contracts.client_tax_profile import (
    ClientTaxProfileRequest,
)
from src.services.query_control_plane_service.app.domain.client_tax_profile import (
    ClientTaxProfileSourceRecord,
)
from src.services.query_control_plane_service.app.domain.effective_mandate import (
    EffectiveMandateBinding,
)


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 5, 3, 10, tzinfo=UTC)


class _Reader:
    def __init__(self, binding, profiles):
        self.binding = binding
        self.profiles = profiles
        self.calls: list[str] = []

    async def resolve(self, **_):
        self.calls.append("binding")
        return self.binding

    async def list_profiles(self, **_):
        self.calls.append("profiles")
        return self.profiles


def _binding() -> EffectiveMandateBinding:
    return EffectiveMandateBinding(
        client_id="CIF_SG_000184",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 7, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def _profile() -> ClientTaxProfileSourceRecord:
    timestamp = datetime(2026, 5, 3, 9, tzinfo=UTC)
    return ClientTaxProfileSourceRecord(
        tax_profile_id="TAX_PROFILE_SG_001",
        tax_residency_country="SG",
        booking_tax_jurisdiction="SG",
        tax_status="TAXABLE",
        profile_status="active",
        withholding_tax_rate=Decimal("0.1500000000"),
        capital_gains_tax_applicable=False,
        income_tax_applicable=True,
        treaty_codes=("US_SG_TREATY",),
        eligible_account_types=("DPM",),
        effective_from=date(2026, 1, 1),
        effective_to=None,
        profile_version=1,
        source_record_id="tax-profile:1",
        observed_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _request() -> ClientTaxProfileRequest:
    return ClientTaxProfileRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
    )


def _service(reader: _Reader) -> ClientTaxProfileService:
    return ClientTaxProfileService(mandate_reader=reader, reader=reader, clock=_Clock())


@pytest.mark.asyncio
async def test_resolves_ready_tax_profile() -> None:
    reader = _Reader(_binding(), [_profile()])
    response = await _service(reader).get_client_tax_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )

    assert response is not None
    assert response.generated_at == datetime(2026, 5, 3, 10, tzinfo=UTC)
    assert response.supportability.state == "READY"
    assert response.profiles[0].withholding_tax_rate == Decimal("0.1500000000")
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert response.snapshot_id is not None
    assert reader.calls == ["binding", "profiles"]


@pytest.mark.asyncio
async def test_marks_empty_tax_profile_incomplete() -> None:
    response = await _service(_Reader(_binding(), [])).get_client_tax_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )

    assert response is not None
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.missing_data_families == ["client_tax_profile"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)


@pytest.mark.asyncio
async def test_missing_binding_skips_tax_profile_read() -> None:
    reader = _Reader(None, [_profile()])
    response = await _service(reader).get_client_tax_profile(
        portfolio_id="PB_MISSING", request=_request()
    )
    assert response is None
    assert reader.calls == ["binding"]


@pytest.mark.asyncio
async def test_snapshot_identity_is_stable_for_same_scope() -> None:
    service = _service(_Reader(_binding(), [_profile()]))
    first = await service.get_client_tax_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )
    second = await service.get_client_tax_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )
    assert first is not None and second is not None
    assert first.snapshot_id == second.snapshot_id
