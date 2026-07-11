"""Behavior tests for QCP-owned external treasury and OMS posture."""

from datetime import UTC, date, datetime

import pytest

from src.services.query_control_plane_service.app.application.external_hedge_posture import (
    CURRENCY_EXPOSURE_BLOCKED,
    CURRENCY_EXPOSURE_MISSING,
    ELIGIBLE_INSTRUMENT_BLOCKED,
    EXECUTION_READINESS_MISSING,
    FX_FORWARD_CURVE_BLOCKED,
    HEDGE_POLICY_BLOCKED,
    ORDER_ACKNOWLEDGEMENT_BLOCKED,
    ExternalHedgePostureService,
)
from src.services.query_control_plane_service.app.contracts.external_hedge_posture import (
    ExternalCurrencyExposureRequest,
    ExternalEligibleHedgeInstrumentRequest,
    ExternalFXForwardCurveRequest,
    ExternalHedgeExecutionReadinessRequest,
    ExternalHedgePolicyRequest,
    ExternalOrderExecutionAcknowledgementRequest,
)
from src.services.query_control_plane_service.app.domain.effective_mandate import (
    EffectiveMandateBinding,
)


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 5, 3, 10, tzinfo=UTC)


class _MandateReader:
    def __init__(self, binding: EffectiveMandateBinding | None) -> None:
        self.binding = binding
        self.calls: list[dict[str, object]] = []

    async def resolve(self, **kwargs):
        self.calls.append(kwargs)
        return self.binding


def _binding() -> EffectiveMandateBinding:
    return EffectiveMandateBinding(
        client_id="CIF_SG_000184",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 7, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def _service(reader: _MandateReader) -> ExternalHedgePostureService:
    return ExternalHedgePostureService(mandate_reader=reader, clock=_Clock())


def _common_request_fields() -> dict[str, object]:
    return {
        "as_of_date": date(2026, 5, 3),
        "tenant_id": "default",
        "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
    }


def _assert_common_posture(response, product_name: str) -> None:
    assert response.product_name == product_name
    assert response.generated_at == datetime(2026, 5, 3, 10, tzinfo=UTC)
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp is None
    assert response.source_batch_fingerprint is None
    assert response.supportability.state == "UNAVAILABLE"
    assert response.lineage["integration_status"] == "not_ingested"
    assert response.lineage["runtime_posture"] == "fail_closed"
    assert response.snapshot_id is not None


@pytest.mark.asyncio
async def test_currency_exposure_is_fail_closed() -> None:
    response = await _service(_MandateReader(_binding())).get_external_currency_exposure(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=ExternalCurrencyExposureRequest(
            **_common_request_fields(),
            reporting_currency="USD",
            exposure_currencies=["JPY", "EUR"],
        ),
    )

    assert response is not None
    _assert_common_posture(response, "ExternalCurrencyExposure")
    assert response.exposures == []
    assert response.supportability.missing_data_families == list(CURRENCY_EXPOSURE_MISSING)
    assert response.supportability.blocked_capabilities == list(CURRENCY_EXPOSURE_BLOCKED)
    assert response.lineage["source_system"] == "external-bank-treasury"


@pytest.mark.asyncio
async def test_hedge_policy_is_fail_closed() -> None:
    response = await _service(_MandateReader(_binding())).get_external_hedge_policy(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=ExternalHedgePolicyRequest(
            **_common_request_fields(), reporting_currency="USD", exposure_currencies=["EUR"]
        ),
    )

    assert response is not None
    _assert_common_posture(response, "ExternalHedgePolicy")
    assert response.policy_rules == []
    assert response.supportability.blocked_capabilities == list(HEDGE_POLICY_BLOCKED)


@pytest.mark.asyncio
async def test_eligible_instruments_are_fail_closed() -> None:
    response = await _service(_MandateReader(_binding())).get_external_eligible_hedge_instruments(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=ExternalEligibleHedgeInstrumentRequest(
            **_common_request_fields(),
            reporting_currency="USD",
            exposure_currencies=["EUR"],
            instrument_types=["FX_FORWARD", "FX_SWAP"],
        ),
    )

    assert response is not None
    _assert_common_posture(response, "ExternalEligibleHedgeInstrument")
    assert response.eligible_instruments == []
    assert response.instrument_types == ["FX_FORWARD", "FX_SWAP"]
    assert response.supportability.blocked_capabilities == list(ELIGIBLE_INSTRUMENT_BLOCKED)


@pytest.mark.asyncio
async def test_execution_readiness_is_fail_closed() -> None:
    response = await _service(_MandateReader(_binding())).get_external_hedge_execution_readiness(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=ExternalHedgeExecutionReadinessRequest(
            **_common_request_fields(), reporting_currency="USD", exposure_currencies=["EUR"]
        ),
    )

    assert response is not None
    _assert_common_posture(response, "ExternalHedgeExecutionReadiness")
    assert response.readiness_checks == []
    assert response.supportability.missing_data_families == list(EXECUTION_READINESS_MISSING)


@pytest.mark.asyncio
async def test_order_acknowledgement_uses_oms_lineage_and_identity() -> None:
    service = _service(_MandateReader(_binding()))
    request = ExternalOrderExecutionAcknowledgementRequest(
        **_common_request_fields(),
        execution_intent_id="REBALANCE_001",
        order_reference_ids=["ORDER_2", "ORDER_1"],
    )
    first = await service.get_external_order_execution_acknowledgement(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=request
    )
    second = await service.get_external_order_execution_acknowledgement(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=request
    )

    assert first is not None and second is not None
    _assert_common_posture(first, "ExternalOrderExecutionAcknowledgement")
    assert first.acknowledgements == []
    assert first.lineage["source_system"] == "external-bank-oms"
    assert first.supportability.blocked_capabilities == list(ORDER_ACKNOWLEDGEMENT_BLOCKED)
    assert first.snapshot_id == second.snapshot_id


def test_fx_forward_curve_is_fail_closed_without_source_reads() -> None:
    reader = _MandateReader(_binding())
    service = _service(reader)
    request = ExternalFXForwardCurveRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        reporting_currency="USD",
        currency_pairs=["USD/JPY", "EUR/USD"],
        tenors=["6M", "1M"],
    )

    first = service.get_external_fx_forward_curve(request=request)
    second = service.get_external_fx_forward_curve(request=request)

    _assert_common_posture(first, "ExternalFXForwardCurve")
    assert first.curve_points == []
    assert first.supportability.blocked_capabilities == list(FX_FORWARD_CURVE_BLOCKED)
    assert first.snapshot_id == second.snapshot_id
    assert reader.calls == []


@pytest.mark.asyncio
async def test_missing_binding_returns_none_with_one_scoped_read() -> None:
    reader = _MandateReader(None)
    response = await _service(reader).get_external_hedge_policy(
        portfolio_id="PB_MISSING",
        request=ExternalHedgePolicyRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None
    assert reader.calls == [
        {
            "portfolio_id": "PB_MISSING",
            "as_of_date": date(2026, 5, 3),
            "mandate_id": None,
        }
    ]
