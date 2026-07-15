"""Prove portfolio aggregation lease identity and expiry invariants."""

from datetime import datetime, timezone

import pytest

from src.services.portfolio_aggregation_service.app.domain.aggregation_records import (
    AggregationJobLease,
)


def test_aggregation_job_lease_preserves_fenced_ownership() -> None:
    expires_at = datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc)

    lease = AggregationJobLease(
        owner="portfolio-aggregation-worker-1",
        token="lease-token-1",
        expires_at=expires_at,
    )

    assert lease.owner == "portfolio-aggregation-worker-1"
    assert lease.token == "lease-token-1"
    assert lease.expires_at == expires_at


@pytest.mark.parametrize(
    ("owner", "token", "expires_at", "message"),
    [
        (" ", "lease-token", datetime.now(timezone.utc), "owner"),
        ("worker", " ", datetime.now(timezone.utc), "token"),
        ("worker", "lease-token", datetime(2026, 7, 15, 8, 30), "timezone-aware"),
        ("w" * 129, "lease-token", datetime.now(timezone.utc), "128"),
        ("worker", "t" * 65, datetime.now(timezone.utc), "64"),
    ],
)
def test_aggregation_job_lease_rejects_invalid_persistence_identity(
    owner: str,
    token: str,
    expires_at: datetime,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        AggregationJobLease(owner=owner, token=token, expires_at=expires_at)
