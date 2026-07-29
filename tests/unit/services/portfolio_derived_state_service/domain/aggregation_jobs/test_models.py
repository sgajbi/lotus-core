"""Prove portfolio aggregation lease identity and expiry invariants."""

from datetime import datetime, timezone

import pytest

from src.services.portfolio_derived_state_service.app.domain.aggregation_jobs.models import (
    AggregationJobLease,
    ClaimedAggregationJob,
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


@pytest.mark.parametrize(
    ("target_epoch", "source_revision", "message"),
    [
        (-1, 1, "target epoch"),
        (0, 0, "source revision"),
    ],
)
def test_claimed_aggregation_job_rejects_invalid_source_identity(
    target_epoch: int,
    source_revision: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ClaimedAggregationJob(
            id=1,
            portfolio_id="P1",
            aggregation_date=datetime.now(timezone.utc).date(),
            aggregation_revision=1,
            target_epoch=target_epoch,
            source_revision=source_revision,
            correlation_id=None,
            lease=AggregationJobLease(
                owner="worker",
                token="lease",
                expires_at=datetime.now(timezone.utc),
            ),
        )
