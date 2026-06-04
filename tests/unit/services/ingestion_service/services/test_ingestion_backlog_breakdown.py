from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.services.ingestion_service.app.services.ingestion_backlog_breakdown import (
    build_backlog_breakdown_response,
    empty_backlog_breakdown_response,
)


def test_build_backlog_breakdown_response_orders_groups_and_concentration():
    now = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    rows = [
        ("/ingest/instruments", "instrument", 40, 1, 0, 2, now - timedelta(minutes=2)),
        ("/ingest/transactions", "transaction", 100, 4, 2, 3, now - timedelta(minutes=10)),
        ("/ingest/market-prices", "market_price", 70, 3, 1, 1, now - timedelta(minutes=5)),
    ]

    response = build_backlog_breakdown_response(
        lookback_minutes=60,
        total_backlog_jobs=11,
        grouped_rows=rows,
        now=now,
        limit=10,
    )

    assert response.largest_group_backlog_jobs == 6
    assert response.largest_group_backlog_share == Decimal("0.5454545454545454545454545455")
    assert response.top_3_backlog_share == Decimal("1")
    assert [group.endpoint for group in response.groups] == [
        "/ingest/transactions",
        "/ingest/market-prices",
        "/ingest/instruments",
    ]
    assert response.groups[0].failure_rate == Decimal("0.03")
    assert response.groups[0].oldest_backlog_age_seconds == 600.0


def test_build_backlog_breakdown_response_applies_limit_before_top3_share():
    now = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    rows = [
        ("/a", "a", 10, 4, 1, 0, now - timedelta(minutes=5)),
        ("/b", "b", 10, 3, 1, 0, now - timedelta(minutes=4)),
        ("/c", "c", 10, 2, 1, 0, now - timedelta(minutes=3)),
    ]

    response = build_backlog_breakdown_response(
        lookback_minutes=60,
        total_backlog_jobs=12,
        grouped_rows=rows,
        now=now,
        limit=2,
    )

    assert len(response.groups) == 2
    assert response.top_3_backlog_share == Decimal("0.75")


def test_empty_backlog_breakdown_response_has_zero_concentration():
    response = empty_backlog_breakdown_response(lookback_minutes=15)

    assert response.lookback_minutes == 15
    assert response.total_backlog_jobs == 0
    assert response.largest_group_backlog_jobs == 0
    assert response.largest_group_backlog_share == Decimal("0")
    assert response.top_3_backlog_share == Decimal("0")
    assert response.groups == []
