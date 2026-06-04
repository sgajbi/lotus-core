import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    IndexSeriesRequest,
    IntegrationWindow,
)
from src.services.query_service.app.services.index_return_series import (
    build_index_return_series_response,
    resolve_index_return_series_response,
)


def test_build_index_return_series_response_maps_points_and_runtime_metadata() -> None:
    observed_at = datetime(2026, 1, 31, 9, 30, tzinfo=UTC)
    rows = [
        SimpleNamespace(
            series_date=date(2026, 1, 30),
            index_return=Decimal("0.0023"),
            return_period="1d",
            return_convention="total_return_index",
            series_currency="USD",
            quality_status="accepted",
            observed_at=observed_at,
        )
    ]
    request = IndexSeriesRequest(
        as_of_date=date(2026, 1, 31),
        window=IntegrationWindow(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        ),
        frequency="daily",
    )

    response = build_index_return_series_response(
        index_id="IDX_MSCI_WORLD_TR",
        request=request,
        rows=rows,
    )

    assert response.product_name == "IndexSeriesWindow"
    assert response.index_id == "IDX_MSCI_WORLD_TR"
    assert response.as_of_date == date(2026, 1, 31)
    assert response.resolved_window.start_date == date(2026, 1, 1)
    assert response.resolved_window.end_date == date(2026, 1, 31)
    assert response.frequency == "daily"
    assert response.request_fingerprint
    assert len(response.points) == 1
    assert response.points[0].series_date == date(2026, 1, 30)
    assert response.points[0].index_return == Decimal("0.0023")
    assert response.points[0].return_period == "1d"
    assert response.points[0].return_convention == "total_return_index"
    assert response.points[0].series_currency == "USD"
    assert response.points[0].quality_status == "accepted"
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == observed_at
    assert response.lineage == {
        "contract_version": "rfc_062_v1",
        "source_system": "lotus-core-query-service",
        "generated_by": "integration.index_return_series",
    }


def test_resolve_index_return_series_response_orchestrates_repository_read() -> None:
    observed_at = datetime(2026, 1, 31, 9, 30, tzinfo=UTC)
    request = IndexSeriesRequest(
        as_of_date=date(2026, 1, 31),
        window=IntegrationWindow(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        ),
        frequency="daily",
    )

    async def run_case() -> tuple[object, list[dict[str, object]]]:
        calls: list[dict[str, object]] = []

        class Repository:
            async def list_index_return_series(self, **kwargs: object) -> list[SimpleNamespace]:
                calls.append(kwargs)
                return [
                    SimpleNamespace(
                        series_date=date(2026, 1, 30),
                        index_return=Decimal("0.0023"),
                        return_period="1d",
                        return_convention="total_return_index",
                        series_currency="USD",
                        quality_status="accepted",
                        observed_at=observed_at,
                    )
                ]

        response = await resolve_index_return_series_response(
            repository=Repository(),
            index_id="IDX_MSCI_WORLD_TR",
            request=request,
        )
        return response, calls

    response, calls = asyncio.run(run_case())

    assert response.index_id == "IDX_MSCI_WORLD_TR"
    assert response.points[0].index_return == Decimal("0.0023")
    assert response.data_quality_status == "COMPLETE"
    assert response.request_fingerprint
    assert calls == [
        {
            "index_id": "IDX_MSCI_WORLD_TR",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 1, 31),
        }
    ]
