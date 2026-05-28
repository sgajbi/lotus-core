from datetime import date
from types import SimpleNamespace

from src.services.query_service.app.services.request_fingerprint import (
    request_fingerprint,
    series_request_fingerprint,
)


def test_request_fingerprint_is_stable_for_key_order() -> None:
    assert request_fingerprint({"portfolio_id": "PB_001", "as_of_date": "2026-05-03"}) == (
        request_fingerprint({"as_of_date": "2026-05-03", "portfolio_id": "PB_001"})
    )


def test_request_fingerprint_changes_with_payload_value() -> None:
    assert request_fingerprint({"portfolio_id": "PB_001"}) != request_fingerprint(
        {"portfolio_id": "PB_002"}
    )


def test_series_request_fingerprint_includes_window_and_extras() -> None:
    request = SimpleNamespace(
        as_of_date=date(2026, 5, 3),
        window=SimpleNamespace(
            start_date=date(2026, 4, 1),
            end_date=date(2026, 5, 3),
        ),
        frequency="DAILY",
    )

    base_fingerprint = series_request_fingerprint(
        series_key="benchmark_return_series",
        identifier_key="benchmark_id",
        identifier_value="BMK_GLOBAL_60_40",
        request=request,
    )
    scoped_fingerprint = series_request_fingerprint(
        series_key="benchmark_return_series",
        identifier_key="benchmark_id",
        identifier_value="BMK_GLOBAL_60_40",
        request=request,
        extras={"currency": "USD"},
    )

    assert scoped_fingerprint != base_fingerprint
