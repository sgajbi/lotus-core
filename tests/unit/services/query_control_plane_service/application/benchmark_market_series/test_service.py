"""Tests for benchmark market-series use-case orchestration."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from portfolio_common.reference_data_paging import ReferencePageRequest

from services.query_control_plane_service.app.application.benchmark_market_series.service import (
    BenchmarkMarketSeriesService,
)
from services.query_control_plane_service.app.contracts.benchmark_market_series import (
    BenchmarkMarketSeriesRequest,
)
from services.query_control_plane_service.app.contracts.common import IntegrationWindow
from services.query_control_plane_service.app.domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)
from services.query_control_plane_service.app.domain.benchmark_return_series import (
    BenchmarkReturnEvidence,
)
from services.query_control_plane_service.app.domain.index_series import (
    IndexPriceEvidence,
    IndexReturnEvidence,
)
from services.query_control_plane_service.app.domain.market_fx import FxRateEvidence
from services.query_control_plane_service.app.ports.benchmark_definition import (
    BenchmarkDefinitionReader,
)
from services.query_control_plane_service.app.ports.benchmark_return_series import (
    BenchmarkReturnSeriesReader,
)
from services.query_control_plane_service.app.ports.index_series import IndexSeriesReader
from services.query_control_plane_service.app.ports.market_fx import MarketFxRateReader

EVIDENCE_TIME = datetime(2026, 1, 31, 8, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 1, 31, 9, 0, tzinfo=UTC)


class RecordingPageTokens:
    """Deterministic test token codec with observable calls."""

    def __init__(self, *, cursor: dict[str, Any] | None = None, error: Exception | None = None):
        self.cursor = cursor or {}
        self.error = error
        self.encoded_payloads: list[dict[str, str]] = []

    def decode(self, token: str | None) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.cursor

    def encode(self, payload: dict[str, Any]) -> str:
        self.encoded_payloads.append(cast(dict[str, str], payload))
        return "encoded-next-page"


class RecordingBenchmarkReader:
    """Test benchmark reader recording source-read order."""

    def __init__(self, *, candidate_ids: list[str], calls: list[str]):
        self.candidate_ids = candidate_ids
        self.calls = calls

    async def resolve_definition(self, **_: object) -> BenchmarkDefinitionEvidence:
        self.calls.append("definition")
        return _definition()

    async def list_component_index_ids_page(self, **_: object) -> list[str]:
        self.calls.append("index_ids")
        return self.candidate_ids

    async def list_components_for_indices_overlapping_window(
        self, **_: object
    ) -> list[BenchmarkComponentEvidence]:
        self.calls.append("components")
        return [_component()]


class RecordingIndexSeriesReader:
    """Test index reader recording conditional source reads."""

    def __init__(self, calls: list[str]):
        self.calls = calls

    async def list_prices_for_indices(self, **_: object) -> list[IndexPriceEvidence]:
        self.calls.append("index_prices")
        return [_price()]

    async def list_returns_for_indices(self, **_: object) -> list[IndexReturnEvidence]:
        self.calls.append("index_returns")
        return [_index_return()]


class RecordingBenchmarkReturnReader:
    """Test benchmark-return reader recording conditional reads."""

    def __init__(self, calls: list[str]):
        self.calls = calls

    async def list_returns(self, **_: object) -> list[BenchmarkReturnEvidence]:
        self.calls.append("benchmark_returns")
        return [_benchmark_return()]


class RecordingFxReader:
    """Test FX reader recording conditional reads."""

    def __init__(self, calls: list[str]):
        self.calls = calls

    async def list_rates(self, **_: object) -> list[FxRateEvidence]:
        self.calls.append("fx_rates")
        return [_fx_rate()]


def _request(*, page_size: int = 1, page_token: str | None = None) -> BenchmarkMarketSeriesRequest:
    return BenchmarkMarketSeriesRequest(
        as_of_date=date(2026, 1, 31),
        window=IntegrationWindow(start_date=date(2026, 1, 30), end_date=date(2026, 1, 31)),
        frequency="daily",
        target_currency="SGD",
        series_fields=[
            "index_price",
            "index_return",
            "benchmark_return",
            "component_weight",
            "fx_rate",
        ],
        page=ReferencePageRequest(page_size=page_size, page_token=page_token),
    )


def _service(
    *,
    benchmark_reader: RecordingBenchmarkReader,
    calls: list[str],
    page_tokens: RecordingPageTokens,
) -> BenchmarkMarketSeriesService:
    return BenchmarkMarketSeriesService(
        benchmark_reader=cast(BenchmarkDefinitionReader, benchmark_reader),
        index_series_reader=cast(IndexSeriesReader, RecordingIndexSeriesReader(calls)),
        benchmark_return_reader=cast(
            BenchmarkReturnSeriesReader, RecordingBenchmarkReturnReader(calls)
        ),
        fx_rate_reader=cast(MarketFxRateReader, RecordingFxReader(calls)),
        page_tokens=page_tokens,
        clock=lambda: GENERATED_AT,
    )


@pytest.mark.asyncio
async def test_service_validates_page_token_before_source_reads() -> None:
    calls: list[str] = []
    service = _service(
        benchmark_reader=RecordingBenchmarkReader(candidate_ids=[], calls=calls),
        calls=calls,
        page_tokens=RecordingPageTokens(error=ValueError("invalid token")),
    )

    with pytest.raises(ValueError, match="invalid token"):
        await service.get(benchmark_id="BMK_1", request=_request(page_token="bad"))

    assert calls == []


@pytest.mark.asyncio
async def test_service_reads_requested_evidence_sequentially_and_encodes_cursor() -> None:
    calls: list[str] = []
    tokens = RecordingPageTokens()
    service = _service(
        benchmark_reader=RecordingBenchmarkReader(candidate_ids=["IDX_1", "IDX_2"], calls=calls),
        calls=calls,
        page_tokens=tokens,
    )

    response = await service.get(benchmark_id="BMK_1", request=_request())

    assert calls == [
        "definition",
        "index_ids",
        "components",
        "index_prices",
        "index_returns",
        "benchmark_returns",
        "fx_rates",
    ]
    assert response.page.next_page_token == "encoded-next-page"
    assert response.page.returned_component_count == 1
    assert response.data_quality_status == "PARTIAL"
    assert tokens.encoded_payloads == [
        {
            "scope_fingerprint": response.request_fingerprint,
            "last_index_id": "IDX_1",
        }
    ]


@pytest.mark.asyncio
async def test_service_skips_page_evidence_reads_when_no_component_ids() -> None:
    calls: list[str] = []
    service = _service(
        benchmark_reader=RecordingBenchmarkReader(candidate_ids=[], calls=calls),
        calls=calls,
        page_tokens=RecordingPageTokens(),
    )

    response = await service.get(benchmark_id="BMK_1", request=_request())

    assert calls == ["definition", "index_ids"]
    assert response.data_quality_status == "EMPTY"
    assert response.component_series == []


def _definition() -> BenchmarkDefinitionEvidence:
    return BenchmarkDefinitionEvidence(
        benchmark_id="BMK_1",
        benchmark_name="Global Balanced",
        benchmark_type="COMPOSITE",
        benchmark_currency="USD",
        return_convention="TOTAL_RETURN",
        benchmark_status="ACTIVE",
        benchmark_family=None,
        benchmark_provider="PROVIDER",
        rebalance_frequency="MONTHLY",
        classification_set_id=None,
        classification_labels={},
        effective_from=date(2020, 1, 1),
        effective_to=None,
        source_timestamp=EVIDENCE_TIME,
        source_vendor="PROVIDER",
        source_record_id="BMK_1",
        quality_status="ACCEPTED",
        created_at=EVIDENCE_TIME,
        updated_at=EVIDENCE_TIME,
    )


def _component() -> BenchmarkComponentEvidence:
    return BenchmarkComponentEvidence(
        benchmark_id="BMK_1",
        index_id="IDX_1",
        composition_effective_from=date(2026, 1, 1),
        composition_effective_to=None,
        composition_weight=Decimal("1.0000000000"),
        rebalance_event_id="REB_1",
        source_timestamp=EVIDENCE_TIME,
        source_vendor="PROVIDER",
        source_record_id="BMK_1:IDX_1",
        quality_status="ACCEPTED",
        created_at=EVIDENCE_TIME,
        updated_at=EVIDENCE_TIME,
    )


def _price() -> IndexPriceEvidence:
    return IndexPriceEvidence(
        series_id="PRICE:IDX_1",
        index_id="IDX_1",
        series_date=date(2026, 1, 30),
        index_price=Decimal("100.0000000000"),
        series_currency="USD",
        value_convention="CLOSE",
        quality_status="ACCEPTED",
        observed_at=EVIDENCE_TIME,
        source_vendor="PROVIDER",
        source_record_id="PRICE:IDX_1",
        created_at=EVIDENCE_TIME,
        updated_at=EVIDENCE_TIME,
    )


def _index_return() -> IndexReturnEvidence:
    return IndexReturnEvidence(
        series_id="RETURN:IDX_1",
        index_id="IDX_1",
        series_date=date(2026, 1, 30),
        index_return=Decimal("0.0010000000"),
        return_period="DAILY",
        return_convention="TOTAL_RETURN",
        series_currency="USD",
        quality_status="ACCEPTED",
        observed_at=EVIDENCE_TIME,
        source_vendor="PROVIDER",
        source_record_id="RETURN:IDX_1",
        created_at=EVIDENCE_TIME,
        updated_at=EVIDENCE_TIME,
    )


def _benchmark_return() -> BenchmarkReturnEvidence:
    return BenchmarkReturnEvidence(
        series_id="BMK_RETURN:BMK_1",
        benchmark_id="BMK_1",
        series_date=date(2026, 1, 30),
        benchmark_return=Decimal("0.0008000000"),
        return_period="DAILY",
        return_convention="TOTAL_RETURN",
        series_currency="USD",
        quality_status="ACCEPTED",
        observed_at=EVIDENCE_TIME,
        source_vendor="PROVIDER",
        source_record_id="BMK_RETURN:BMK_1",
        created_at=EVIDENCE_TIME,
        updated_at=EVIDENCE_TIME,
    )


def _fx_rate() -> FxRateEvidence:
    return FxRateEvidence(
        from_currency="USD",
        to_currency="SGD",
        rate_date=date(2026, 1, 30),
        rate=Decimal("1.3500000000"),
        created_at=EVIDENCE_TIME,
        updated_at=EVIDENCE_TIME,
    )
