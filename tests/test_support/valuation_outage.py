"""Scoped SQL observations and assertions for the existing database-outage E2E test."""

from collections.abc import Mapping
from decimal import Decimal
from ipaddress import ip_address
from typing import Any

from portfolio_common.config import DEFAULT_BUSINESS_CALENDAR_CODE
from sqlalchemy import text


def valuation_source_prerequisites(engine, scope: Mapping[str, str]) -> dict[str, Any]:
    """Observe price-consumer completion before introducing the synthetic position."""
    with engine.connect() as connection:
        row = (
            connection.execute(
                text("""
                SELECT
                    EXISTS(SELECT 1 FROM business_dates
                           WHERE date = CAST(:date AS date) AND calendar_code = :calendar)
                        AS calendar_present,
                    (SELECT count(*) FROM market_prices WHERE security_id = :sid
                     AND price_date = CAST(:date AS date) AND price = 2 AND currency = 'USD')
                        AS prices,
                    (SELECT count(*) FROM instrument_reprocessing_state WHERE security_id = :sid)
                        AS replay_pending,
                    (SELECT count(*) FROM position_history WHERE portfolio_id = :pid
                     AND security_id = :sid) AS positions,
                    (SELECT count(*) FROM portfolio_valuation_jobs WHERE portfolio_id = :pid
                     AND security_id = :sid) AS jobs
            """),
                dict(scope, calendar=DEFAULT_BUSINESS_CALENDAR_CODE),
            )
            .mappings()
            .one()
        )
        receipts = (
            connection.execute(
                text("""
                SELECT o.id AS outbox_id, o.correlation_id, p.event_id, p.processed_at
                FROM outbox_events o JOIN processed_events p
                  ON p.correlation_id = o.correlation_id
                 AND p.service_name = 'price-event-reprocessing-trigger'
                 AND p.processed_at >= o.created_at
                WHERE o.event_type = 'MarketPricePersisted' AND o.aggregate_id = :sid
                  AND o.payload ->> 'security_id' = :sid
                  AND o.payload ->> 'price_date' = :date
                  AND CAST(o.payload ->> 'price' AS numeric) = 2
                  AND o.payload ->> 'currency' = 'USD'
                  AND o.status = 'PROCESSED'
            """),
                dict(scope),
            )
            .mappings()
            .all()
        )
    return dict(row, receipts=[dict(receipt) for receipt in receipts])


def assert_stable_valuation_sources(observation: dict[str, Any]) -> None:
    """Neither persistence alone nor an unconsumed/replaying price admits the fault."""
    assert observation["calendar_present"] is True, observation
    assert observation["prices"] == 1, observation
    assert observation["replay_pending"] == observation["positions"] == observation["jobs"] == 0, (
        observation
    )
    assert len(observation["receipts"]) == 1, observation
    receipt = observation["receipts"][0]
    assert receipt["outbox_id"] > 0 and receipt["correlation_id"], observation
    assert receipt["event_id"] and receipt["processed_at"], observation


def valuation_outage_snapshot(engine, scope: Mapping[str, str]) -> dict[str, Any]:
    """Read only the synthetic portfolio/security/date owned by the fault test."""
    with engine.connect() as connection:
        jobs = (
            connection.execute(
                text("""
                SELECT id, portfolio_id, security_id, valuation_date, epoch, status,
                       attempt_count, failure_reason, requeue_requested,
                       valuation_lease_owner, valuation_claim_token,
                       valuation_lease_expires_at, source_correction_id, correlation_id,
                       claimed_readiness_outbox_id,
                       COALESCE((SELECT max(o.id) FROM outbox_events o
                           WHERE o.aggregate_type = 'ValuationReadiness'
                             AND o.event_type = 'PortfolioDayReadyForValuation'
                             AND o.payload ->> 'portfolio_id' = :pid
                             AND o.payload ->> 'security_id' = :sid
                             AND o.payload ->> 'valuation_date' = :date
                             AND CAST(o.payload ->> 'epoch' AS integer) = j.epoch), 0)
                           AS latest_readiness_outbox_id,
                       updated_at, clock_timestamp() AS observed_at
                FROM portfolio_valuation_jobs j
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
    assert claim["requeue_requested"] is False, observation
    assert 0 < claim["latest_readiness_outbox_id"] == claim["claimed_readiness_outbox_id"], (
        observation
    )
    assert claim["correlation_id"], observation
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
    for field in (
        "id",
        "portfolio_id",
        "security_id",
        "valuation_date",
        "epoch",
        "source_correction_id",
        "correlation_id",
        "claimed_readiness_outbox_id",
        "latest_readiness_outbox_id",
        "requeue_requested",
    ):
        assert job[field] == before[field], (field, before, after)
    # The existing terminal transition increments once as it clears the live lease.
    # A zero increment or an extra claim/reclaim cannot qualify completion.
    assert job["attempt_count"] == before["attempt_count"] + 1, (before, after)
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


def assert_same_live_claim(before: dict[str, Any], observation: dict[str, Any]) -> None:
    """Keep the exact admitted owner/token/expiry while the worker is blocked."""
    current = assert_live_default_claim(observation)
    for field in (
        "id",
        "portfolio_id",
        "security_id",
        "valuation_date",
        "epoch",
        "attempt_count",
        "valuation_lease_owner",
        "valuation_claim_token",
        "valuation_lease_expires_at",
        "requeue_requested",
        "source_correction_id",
        "correlation_id",
        "claimed_readiness_outbox_id",
        "latest_readiness_outbox_id",
    ):
        assert current[field] == before[field], (field, before, observation)


def assert_worker_row_lock(
    rows: list[dict[str, Any]], *, holder_pid: int, worker_ips: list[str]
) -> None:
    """Qualify measured blocking on the sole test-held claim, not SQL text spelling."""
    assert rows and worker_ips, (rows, worker_ips)
    expected_ips = {ip_address(value) for value in worker_ips}
    for row in rows:
        assert row["pid"] > 0 and row["pid"] != holder_pid, row
        assert ip_address(row["client_host"]) in expected_ips, row
        assert holder_pid in row["blocking_pids"], row
        assert row["state"] == "active" and row["wait_event_type"] == "Lock", row
        assert row["wait_event"] in {"transactionid", "tuple"}, row
        assert row["backend_start"] and row["query_start"] and row["query"].strip(), row
