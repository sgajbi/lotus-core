from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.query_service.app.dtos.reference_integration_dto import (
    MarketDataCoverageRequest,
    MarketDataCurrencyPair,
)
from src.services.query_service.app.services.market_data_coverage import (
    build_market_data_coverage_response,
    market_data_coverage_read_scope,
    resolve_market_data_coverage_response,
)


def test_market_data_coverage_read_scope_normalizes_and_deduplicates_lookup_scope() -> None:
    request = SimpleNamespace(
        instrument_ids=[" EQ_US_AAPL ", "EQ_US_AAPL", "FI_US_GOV_10Y"],
        currency_pairs=[
            SimpleNamespace(from_currency="USD", to_currency="SGD"),
            SimpleNamespace(from_currency="USD", to_currency="SGD"),
            SimpleNamespace(from_currency="EUR", to_currency="SGD"),
        ],
        valuation_currency=" sgd ",
    )

    read_scope = market_data_coverage_read_scope(request)

    assert read_scope.instrument_ids == ["EQ_US_AAPL", "EQ_US_AAPL", "FI_US_GOV_10Y"]
    assert read_scope.unique_instrument_ids == ["EQ_US_AAPL", "FI_US_GOV_10Y"]
    assert read_scope.fx_pairs == [("USD", "SGD"), ("USD", "SGD"), ("EUR", "SGD")]
    assert read_scope.unique_fx_pairs == [("USD", "SGD"), ("EUR", "SGD")]
    assert read_scope.valuation_currency == "SGD"


def test_market_data_coverage_response_preserves_ready_evidence_and_runtime_lineage() -> None:
    request = MarketDataCoverageRequest(
        as_of_date=date(2026, 4, 10),
        instrument_ids=["EQ_US_AAPL"],
        currency_pairs=[MarketDataCurrencyPair(from_currency="USD", to_currency="SGD")],
        valuation_currency="SGD",
        max_staleness_days=5,
    )
    read_scope = market_data_coverage_read_scope(request)
    price_rows = [
        SimpleNamespace(
            security_id=" EQ_US_AAPL ",
            price_date=date(2026, 4, 10),
            price=Decimal("187.1200000000"),
            currency="USD",
            updated_at=datetime(2026, 4, 10, 8, tzinfo=UTC),
        )
    ]
    fx_rows = [
        SimpleNamespace(
            from_currency="USD",
            to_currency="SGD",
            rate_date=date(2026, 4, 10),
            rate=Decimal("1.3521000000"),
            updated_at=datetime(2026, 4, 10, 9, tzinfo=UTC),
        )
    ]

    response = build_market_data_coverage_response(
        request=request,
        read_scope=read_scope,
        price_rows=price_rows,
        fx_rows=fx_rows,
    )

    assert response.supportability.state == "READY"
    assert response.supportability.reason == "MARKET_DATA_READY"
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == datetime(2026, 4, 10, 9, tzinfo=UTC)
    assert response.lineage == {
        "source_system": "market_prices+fx_rates",
        "contract_version": "rfc_087_v1",
    }


def test_resolve_market_data_coverage_response_orchestrates_repository_reads() -> None:
    async def run_case() -> tuple[object, list[tuple[str, object]]]:
        call_log: list[tuple[str, object]] = []

        class Repository:
            async def list_latest_market_prices(
                self,
                *,
                security_ids: list[str],
                as_of_date: date,
            ) -> list[SimpleNamespace]:
                call_log.append(
                    ("prices", {"security_ids": security_ids, "as_of_date": as_of_date})
                )
                return [
                    SimpleNamespace(
                        security_id="EQ_US_AAPL",
                        price_date=date(2026, 4, 10),
                        price=Decimal("187.1200000000"),
                        currency="USD",
                    )
                ]

            async def list_latest_fx_rates(
                self,
                *,
                currency_pairs: list[tuple[str, str]],
                as_of_date: date,
            ) -> list[SimpleNamespace]:
                call_log.append(
                    ("fx", {"currency_pairs": currency_pairs, "as_of_date": as_of_date})
                )
                return [
                    SimpleNamespace(
                        from_currency="USD",
                        to_currency="SGD",
                        rate_date=date(2026, 4, 10),
                        rate=Decimal("1.3521000000"),
                    )
                ]

        response = await resolve_market_data_coverage_response(
            repository=Repository(),
            request=SimpleNamespace(
                as_of_date=date(2026, 4, 10),
                instrument_ids=[" EQ_US_AAPL ", "EQ_US_AAPL"],
                currency_pairs=[
                    SimpleNamespace(from_currency="USD", to_currency="SGD"),
                    SimpleNamespace(from_currency="USD", to_currency="SGD"),
                ],
                valuation_currency=None,
                max_staleness_days=5,
            ),
        )
        return response, call_log

    response, call_log = asyncio.run(run_case())

    assert response.supportability.state == "READY"
    assert response.supportability.requested_price_count == 2
    assert response.supportability.requested_fx_count == 2
    assert call_log == [
        ("prices", {"security_ids": ["EQ_US_AAPL"], "as_of_date": date(2026, 4, 10)}),
        ("fx", {"currency_pairs": [("USD", "SGD")], "as_of_date": date(2026, 4, 10)}),
    ]


@pytest.mark.parametrize(
    ("price_date", "fx_rate_date", "expected_state", "expected_reason"),
    [
        (date(2026, 4, 1), date(2026, 4, 10), "DEGRADED", "MARKET_DATA_STALE"),
        (None, date(2026, 4, 10), "INCOMPLETE", "MARKET_DATA_MISSING"),
    ],
)
def test_market_data_coverage_response_classifies_stale_and_missing_evidence(
    price_date: date | None,
    fx_rate_date: date,
    expected_state: str,
    expected_reason: str,
) -> None:
    request = MarketDataCoverageRequest(
        as_of_date=date(2026, 4, 10),
        instrument_ids=["EQ_US_AAPL"],
        currency_pairs=[MarketDataCurrencyPair(from_currency="USD", to_currency="SGD")],
        max_staleness_days=5,
    )
    read_scope = market_data_coverage_read_scope(request)
    price_rows = (
        [
            SimpleNamespace(
                security_id="EQ_US_AAPL",
                price_date=price_date,
                price=Decimal("187.1200000000"),
                currency="USD",
            )
        ]
        if price_date is not None
        else []
    )
    fx_rows = [
        SimpleNamespace(
            from_currency="USD",
            to_currency="SGD",
            rate_date=fx_rate_date,
            rate=Decimal("1.3521000000"),
        )
    ]

    response = build_market_data_coverage_response(
        request=request,
        read_scope=read_scope,
        price_rows=price_rows,
        fx_rows=fx_rows,
    )

    assert response.supportability.state == expected_state
    assert response.supportability.reason == expected_reason
    assert response.data_quality_status == "PARTIAL"
