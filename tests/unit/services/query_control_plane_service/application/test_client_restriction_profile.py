"""Behavior tests for QCP-owned client restriction profile resolution."""

from datetime import UTC, date, datetime

import pytest

from src.services.query_control_plane_service.app.application.client_restriction_profile import (
    ClientRestrictionProfileService,
)
from src.services.query_control_plane_service.app.contracts.client_restriction_profile import (
    ClientRestrictionProfileRequest,
)
from src.services.query_control_plane_service.app.domain.client_restriction_profile import (
    ClientRestrictionSourceRecord,
)
from src.services.query_control_plane_service.app.domain.effective_mandate import (
    EffectiveMandateBinding,
)


class _FixedClock:
    def utc_now(self) -> datetime:
        return datetime(2026, 5, 3, 10, tzinfo=UTC)


class _Reader:
    def __init__(
        self,
        *,
        binding: EffectiveMandateBinding | None,
        restrictions: list[ClientRestrictionSourceRecord],
    ) -> None:
        self.binding = binding
        self.restrictions = restrictions
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def resolve_mandate_binding(self, **kwargs: object):
        self.calls.append(("binding", kwargs))
        return self.binding

    async def list_restrictions(self, **kwargs: object):
        self.calls.append(("restrictions", kwargs))
        return self.restrictions


def _binding() -> EffectiveMandateBinding:
    return EffectiveMandateBinding(
        client_id="CIF_SG_000184",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 7, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def _restriction() -> ClientRestrictionSourceRecord:
    return ClientRestrictionSourceRecord(
        restriction_scope="asset_class",
        restriction_code="NO_PRIVATE_CREDIT_BUY",
        restriction_status="active",
        restriction_source="client_mandate",
        applies_to_buy=True,
        applies_to_sell=False,
        instrument_ids=(),
        asset_classes=("private_credit",),
        issuer_ids=(),
        country_codes=(),
        effective_from=date(2026, 1, 1),
        effective_to=None,
        restriction_version=1,
        source_record_id="client-restriction:1",
        observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


def _request() -> ClientRestrictionProfileRequest:
    return ClientRestrictionProfileRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
    )


@pytest.mark.asyncio
async def test_resolves_ready_profile_through_typed_source_port() -> None:
    reader = _Reader(binding=_binding(), restrictions=[_restriction()])
    service = ClientRestrictionProfileService(reader=reader, clock=_FixedClock())

    response = await service.get_client_restriction_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=_request(),
    )

    assert response is not None
    assert response.generated_at == datetime(2026, 5, 3, 10, tzinfo=UTC)
    assert response.client_id == "CIF_SG_000184"
    assert response.supportability.state == "READY"
    assert response.restrictions[0].asset_classes == ["private_credit"]
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert response.data_quality_status == "ACCEPTED"
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("client_restriction_profile:")
    assert reader.calls == [
        (
            "binding",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
            },
        ),
        (
            "restrictions",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "client_id": "CIF_SG_000184",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                "include_inactive_restrictions": False,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_marks_empty_profile_incomplete_without_hiding_binding_evidence() -> None:
    service = ClientRestrictionProfileService(
        reader=_Reader(binding=_binding(), restrictions=[]),
        clock=_FixedClock(),
    )

    response = await service.get_client_restriction_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=_request(),
    )

    assert response is not None
    assert response.restrictions == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "CLIENT_RESTRICTION_PROFILE_EMPTY"
    assert response.supportability.missing_data_families == ["client_restrictions"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)


@pytest.mark.asyncio
async def test_returns_none_without_reading_restrictions_when_binding_is_missing() -> None:
    reader = _Reader(binding=None, restrictions=[_restriction()])
    service = ClientRestrictionProfileService(reader=reader, clock=_FixedClock())

    response = await service.get_client_restriction_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=_request(),
    )

    assert response is None
    assert [name for name, _ in reader.calls] == ["binding"]


@pytest.mark.asyncio
async def test_snapshot_identity_is_deterministic_for_same_business_scope() -> None:
    service = ClientRestrictionProfileService(
        reader=_Reader(binding=_binding(), restrictions=[_restriction()]),
        clock=_FixedClock(),
    )

    first = await service.get_client_restriction_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )
    second = await service.get_client_restriction_profile(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request()
    )

    assert first is not None and second is not None
    assert first.snapshot_id == second.snapshot_id
