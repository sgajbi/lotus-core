import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    LiquidityReserveRequirementRequest,
)
from src.services.query_service.app.services.liquidity_reserve_requirement import (
    build_liquidity_reserve_requirement_response,
    resolve_liquidity_reserve_requirement_response,
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


def _reserve_row() -> SimpleNamespace:
    return SimpleNamespace(
        reserve_requirement_id="RESERVE_MIN_CASH_001",
        reserve_type="MIN_CASH_BUFFER",
        reserve_status="active",
        required_amount=Decimal("150000.0000"),
        currency="SGD",
        horizon_days=90,
        priority=1,
        policy_source="POLICY_DPM_SG_BALANCED_V1",
        effective_from=date(2026, 4, 1),
        effective_to=None,
        requirement_version=2,
        source_record_id="reserve:1",
        observed_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


def _request() -> LiquidityReserveRequirementRequest:
    return LiquidityReserveRequirementRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="default",
        mandate_id="MANDATE_PB_SG_GLOBAL_BAL_001",
    )


def test_build_liquidity_reserve_requirement_response_marks_ready() -> None:
    response = build_liquidity_reserve_requirement_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[_reserve_row()],
    )

    assert response.product_name == "LiquidityReserveRequirement"
    assert response.client_id == "CIF_SG_000184"
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "LIQUIDITY_RESERVE_REQUIREMENT_READY"
    assert response.supportability.requirement_count == 1
    assert response.supportability.missing_data_families == []
    assert response.requirements[0].required_amount == Decimal("150000.0000")
    assert response.requirements[0].currency == "SGD"
    assert response.requirements[0].horizon_days == 90
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert response.source_batch_fingerprint is not None
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("liquidity_reserve_requirement:")
    assert response.lineage == {
        "source_system": "lotus-core-query-service",
        "source_table": "liquidity_reserve_requirements,portfolio_mandate_bindings",
        "contract_version": "rfc_042_liquidity_reserve_requirement_v1",
    }


def test_resolve_liquidity_reserve_requirement_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[object, list[tuple[str, dict[str, object]]]]:
        calls: list[tuple[str, dict[str, object]]] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(
                self, **kwargs: object
            ) -> SimpleNamespace:
                calls.append(("binding", kwargs))
                return _binding()

            async def list_liquidity_reserve_requirements(
                self, **kwargs: object
            ) -> list[SimpleNamespace]:
                calls.append(("requirements", kwargs))
                return [_reserve_row()]

        response = await resolve_liquidity_reserve_requirement_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is not None
    assert response.client_id == "CIF_SG_000184"
    assert response.supportability.state == "READY"
    assert calls == [
        (
            "binding",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
            },
        ),
        (
            "requirements",
            {
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "client_id": "CIF_SG_000184",
                "as_of_date": date(2026, 5, 3),
                "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                "include_inactive_requirements": False,
            },
        ),
    ]


def test_resolve_liquidity_reserve_requirement_response_skips_rows_without_binding() -> None:
    async def run_case() -> tuple[object | None, list[str]]:
        calls: list[str] = []

        class Repository:
            async def resolve_discretionary_mandate_binding(self, **_: object) -> None:
                calls.append("binding")
                return None

            async def list_liquidity_reserve_requirements(self, **_: object) -> list[object]:
                calls.append("requirements")
                raise AssertionError("Unexpected reserve read without mandate binding")

        response = await resolve_liquidity_reserve_requirement_response(
            repository=Repository(),
            portfolio_id="PB_SG_GLOBAL_BAL_001",
            request=_request(),
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response is None
    assert calls == ["binding"]


def test_build_liquidity_reserve_requirement_response_marks_empty_missing() -> None:
    response = build_liquidity_reserve_requirement_response(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        binding=_binding(),
        request=_request(),
        rows=[],
    )

    assert response.requirements == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "LIQUIDITY_RESERVE_REQUIREMENT_EMPTY"
    assert response.supportability.requirement_count == 0
    assert response.supportability.missing_data_families == ["liquidity_reserve_requirement"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 8, tzinfo=UTC)
