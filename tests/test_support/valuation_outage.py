"""Scoped SQL observations and assertions for the existing database-outage E2E test."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from sqlalchemy import text


def valuation_outage_snapshot(engine, scope: Mapping[str, str]) -> dict[str, Any]:
    """Read only the synthetic portfolio/security/date owned by the fault test."""
    with engine.connect() as connection:
        jobs = (
            connection.execute(
                text("""
                SELECT id, portfolio_id, security_id, valuation_date, epoch, status,
                       attempt_count, failure_reason, requeue_requested,
                       valuation_lease_owner, valuation_claim_token,
                       valuation_lease_expires_at, updated_at, clock_timestamp() AS observed_at
                FROM portfolio_valuation_jobs
                WHERE portfolio_id = :pid AND security_id = :sid AND valuation_date = :date
                ORDER BY epoch, id
            """),
                dict(scope),
            )
            .mappings()
            .all()
        )
        snapshots = (
            connection.execute(
                text("""
                SELECT portfolio_id, security_id, date, epoch, valuation_status,
                       quantity, cost_basis, market_price, market_value, unrealized_gain_loss
                FROM daily_position_snapshots
                WHERE portfolio_id = :pid AND security_id = :sid AND date = :date
                ORDER BY epoch, id
            """),
                dict(scope),
            )
            .mappings()
            .all()
        )
    return {"jobs": [dict(row) for row in jobs], "snapshots": [dict(row) for row in snapshots]}


def assert_live_default_claim(observation: dict[str, Any]) -> dict[str, Any]:
    """Refuse completed, missing, shortened or already-expired admission evidence."""
    assert len(observation["jobs"]) == 1, observation
    claim: dict[str, Any] = observation["jobs"][0]
    assert claim["status"] == "PROCESSING", observation
    assert claim["attempt_count"] == 1, observation
    assert claim["valuation_lease_owner"], observation
    token = claim["valuation_claim_token"]
    assert (
        isinstance(token, str) and len(token) == 32 and all(c in "0123456789abcdef" for c in token)
    )
    expires = claim["valuation_lease_expires_at"]
    # updated_at is the claim transaction's start; expiry uses clock_timestamp().
    # The difference can exceed 900 slightly, but cannot represent a shorter lease.
    assert (expires - claim["updated_at"]).total_seconds() >= 900, observation
    assert 780 < (expires - claim["observed_at"]).total_seconds() <= 900, observation
    assert not observation["snapshots"], observation
    return claim


def assert_same_claim_financial_settlement(before: dict[str, Any], after: dict[str, Any]) -> None:
    """Completion must be the admitted row/epoch, not a reset/reclaimed replacement."""
    assert len(after["jobs"]) == len(after["snapshots"]) == 1, after
    job, snapshot = after["jobs"][0], after["snapshots"][0]
    for field in ("id", "portfolio_id", "security_id", "valuation_date", "epoch", "attempt_count"):
        assert job[field] == before[field], (field, before, after)
    assert job["status"] == "COMPLETE", after
    assert all(
        job[field] is None
        for field in (
            "valuation_lease_owner",
            "valuation_claim_token",
            "valuation_lease_expires_at",
        )
    ), after
    assert snapshot["portfolio_id"] == before["portfolio_id"], after
    assert snapshot["security_id"] == before["security_id"], after
    assert snapshot["date"] == before["valuation_date"], after
    assert snapshot["epoch"] == before["epoch"], after
    assert snapshot["valuation_status"] == "VALUED_CURRENT", after
    expected = {
        "quantity": "1",
        "cost_basis": "1",
        "market_price": "2",
        "market_value": "2",
        "unrealized_gain_loss": "1",
    }
    for field, value in expected.items():
        assert snapshot[field] == Decimal(value), (field, after)
