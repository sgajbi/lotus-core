import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    ExternalOrderExecutionAcknowledgementRequest,
)
from src.services.query_service.app.services.external_order_execution_acknowledgement import (
    EXTERNAL_ORDER_ACK_BLOCKED_CAPABILITIES,
    EXTERNAL_ORDER_ACK_MISSING_FAMILIES,
    build_external_order_execution_acknowledgement_response,
    resolve_external_order_execution_acknowledgement_response,
)


def _binding(as_of_date: date = date(2026, 5, 3)) -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_000184",
        effective_from=as_of_date,
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
    )


def _request() -> ExternalOrderExecutionAcknowledgementRequest:
    return ExternalOrderExecutionAcknowledgementRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
        execution_intent_id="rebalance-run-2026-05-03-001",
        order_reference_ids=["OMS-ORDER-002", "OMS-ORDER-001"],
    )


def test_build_external_order_execution_acknowledgement_response_fails_closed() -> None:
    response = build_external_order_execution_acknowledgement_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
    )

    assert response.product_name == "ExternalOrderExecutionAcknowledgement"
    assert response.client_id == "CIF_SG_000184"
    assert response.execution_intent_id == "rebalance-run-2026-05-03-001"
    assert response.order_reference_ids == ["OMS-ORDER-002", "OMS-ORDER-001"]
    assert response.acknowledgements == []
    assert response.supportability.state == "UNAVAILABLE"
    assert response.supportability.reason == "EXTERNAL_OMS_SOURCE_NOT_INGESTED"
    assert response.supportability.acknowledgement_count == 0
    assert response.supportability.missing_data_families == (EXTERNAL_ORDER_ACK_MISSING_FAMILIES)
    assert response.supportability.blocked_capabilities == (EXTERNAL_ORDER_ACK_BLOCKED_CAPABILITIES)
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp is None
    assert response.source_batch_fingerprint is None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("external_order_execution_acknowledgement:")
    assert response.lineage == {
        "source_system": "external-bank-oms",
        "source_table": "not_ingested",
        "contract_version": "rfc_042_external_order_execution_acknowledgement_v1",
        "integration_status": "not_ingested",
        "runtime_posture": "fail_closed",
        "non_claims": ",".join(EXTERNAL_ORDER_ACK_BLOCKED_CAPABILITIES),
    }


def test_resolve_external_order_ack_response_orchestrates_binding_read() -> None:
    async def run_case() -> tuple[object, list[dict[str, object]]]:
        calls: list[dict[str, object]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self,
                **kwargs: object,
            ) -> SimpleNamespace:
                calls.append(kwargs)
                return _binding()

        response = await resolve_external_order_execution_acknowledgement_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is not None
    assert response.product_name == "ExternalOrderExecutionAcknowledgement"
    assert response.supportability.state == "UNAVAILABLE"
    assert calls == [
        {
            "portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "as_of_date": date(2026, 5, 3),
            "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
        }
    ]


def test_resolve_external_order_ack_response_returns_none_without_binding() -> None:
    async def run_case() -> tuple[object, list[dict[str, object]]]:
        calls: list[dict[str, object]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self,
                **kwargs: object,
            ) -> None:
                calls.append(kwargs)
                return None

        response = await resolve_external_order_execution_acknowledgement_response(
            repository=Repository(),
            portfolio_id="PB_MISSING",
            request=ExternalOrderExecutionAcknowledgementRequest(as_of_date=date(2026, 5, 3)),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == [
        {
            "portfolio_id": "PB_MISSING",
            "as_of_date": date(2026, 5, 3),
            "mandate_id": None,
        }
    ]
