"""Fast refusal controls for SQL-backed outage admission and financial observations."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from tests.test_support.valuation_outage import (
    assert_live_default_claim,
    assert_same_claim_financial_settlement,
    assert_same_live_claim,
    assert_worker_row_lock,
)


def admitted():
    now = datetime(2026, 10, 10, tzinfo=UTC)
    return {
        "jobs": [
            {
                "id": 17,
                "portfolio_id": "OWNED",
                "security_id": "OWNED_SEC",
                "valuation_date": now.date(),
                "epoch": 3,
                "status": "PROCESSING",
                "attempt_count": 1,
                "valuation_lease_owner": "native-scheduler",
                "valuation_claim_token": "a" * 32,
                "updated_at": now,
                "observed_at": now + timedelta(seconds=2),
                "valuation_lease_expires_at": now + timedelta(seconds=900),
            }
        ],
        "snapshots": [],
    }


def settled(before):
    job = dict(
        before["jobs"][0],
        status="COMPLETE",
        attempt_count=before["jobs"][0]["attempt_count"] + 1,
        valuation_lease_owner=None,
        valuation_claim_token=None,
        valuation_lease_expires_at=None,
    )
    snapshot = {
        "portfolio_id": job["portfolio_id"],
        "security_id": job["security_id"],
        "date": job["valuation_date"],
        "epoch": job["epoch"],
        "valuation_status": "VALUED_CURRENT",
        "quantity": Decimal("1"),
        "cost_basis": Decimal("1"),
        "market_price": Decimal("2"),
        "market_value": Decimal("2"),
        "unrealized_gain_loss": Decimal("1"),
    }
    return {"jobs": [job], "snapshots": [snapshot]}


def test_default_live_claim_and_same_row_financial_settlement():
    before = admitted()
    original = deepcopy(before)
    claim = assert_live_default_claim(before)
    assert_same_claim_financial_settlement(claim, settled(before))
    assert before == original  # Observation qualification cannot repair a claim.


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "COMPLETE"),
        ("status", "FAILED"),
        ("attempt_count", 2),
        ("valuation_lease_owner", None),
        ("valuation_claim_token", None),
        ("valuation_claim_token", "z" * 32),
        ("valuation_claim_token", "a" * 31),
    ],
)
def test_invalid_admission_is_refused(field, value):
    before = admitted()
    before["jobs"][0][field] = value
    with pytest.raises(AssertionError):
        assert_live_default_claim(before)


@pytest.mark.parametrize("lease_seconds", [30, 120, 899])
def test_shortened_lease_cannot_qualify(lease_seconds):
    before = admitted()
    job = before["jobs"][0]
    job["valuation_lease_expires_at"] = job["updated_at"] + timedelta(seconds=lease_seconds)
    with pytest.raises(AssertionError):
        assert_live_default_claim(before)


def test_expired_default_lease_cannot_qualify():
    before = admitted()
    job = before["jobs"][0]
    job["observed_at"] = job["valuation_lease_expires_at"]
    with pytest.raises(AssertionError):
        assert_live_default_claim(before)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 18),
        ("portfolio_id", "FOREIGN"),
        ("security_id", "FOREIGN"),
        ("epoch", 4),
        ("attempt_count", 1),
        ("attempt_count", 3),
        ("status", "PROCESSING"),
        ("valuation_claim_token", "b" * 32),
    ],
)
def test_replacement_reclaim_foreign_or_unfinished_job_cannot_qualify(field, value):
    before = admitted()
    after = settled(before)
    after["jobs"][0][field] = value
    with pytest.raises(AssertionError):
        assert_same_claim_financial_settlement(before["jobs"][0], after)


@pytest.mark.parametrize(
    "field,value",
    [
        ("portfolio_id", "FOREIGN"),
        ("security_id", "FOREIGN"),
        ("epoch", 4),
        ("valuation_status", "UNVALUED"),
        ("quantity", Decimal("0")),
        ("cost_basis", Decimal("0")),
        ("market_price", Decimal("1")),
        ("market_value", None),
        ("unrealized_gain_loss", Decimal("0")),
    ],
)
def test_wrong_scope_or_financial_result_cannot_qualify(field, value):
    before = admitted()
    after = settled(before)
    after["snapshots"][0][field] = value
    with pytest.raises(AssertionError):
        assert_same_claim_financial_settlement(before["jobs"][0], after)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 18),
        ("epoch", 4),
        ("attempt_count", 2),
        ("valuation_lease_owner", "stale-owner"),
        ("valuation_claim_token", "b" * 32),
        ("valuation_lease_expires_at", datetime(2026, 10, 10, 0, 15, 1, tzinfo=UTC)),
    ],
)
def test_blocked_observation_refuses_replacement_or_changed_live_claim(field, value):
    before = admitted()
    assert_same_live_claim(before["jobs"][0], deepcopy(before))
    changed = deepcopy(before)
    changed["jobs"][0][field] = value
    with pytest.raises(AssertionError):
        assert_same_live_claim(before["jobs"][0], changed)


def blocked_backend():
    now = datetime(2026, 10, 10, tzinfo=UTC)
    return {
        "pid": 201,
        "client_host": "172.20.0.8",
        "blocking_pids": [101],
        "state": "active",
        "wait_event_type": "Lock",
        "wait_event": "transactionid",
        "backend_start": now,
        "query_start": now,
        "query": "WITH owned_claim AS (...) SELECT complete_owned_claim(...)",
    }


@pytest.mark.parametrize("wait_event", ["transactionid", "tuple"])
def test_actual_worker_block_does_not_depend_on_sql_spelling(wait_event):
    row = blocked_backend()
    row["wait_event"] = wait_event
    assert_worker_row_lock([row], holder_pid=101, worker_ips=["172.20.0.8"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("pid", 101),
        ("pid", 0),
        ("client_host", "172.20.0.9"),
        ("blocking_pids", [102]),
        ("state", "idle"),
        ("wait_event_type", "Client"),
        ("wait_event", "relation"),
        ("backend_start", None),
        ("query_start", None),
        ("query", "  "),
    ],
)
def test_worker_block_refuses_foreign_unblocked_or_missing_backend_evidence(field, value):
    row = blocked_backend()
    row[field] = value
    with pytest.raises(AssertionError):
        assert_worker_row_lock([row], holder_pid=101, worker_ips=["172.20.0.8"])


@pytest.mark.parametrize("rows,ips", [([], ["172.20.0.8"]), ([blocked_backend()], [])])
def test_worker_block_requires_actual_rows_and_container_identity(rows, ips):
    with pytest.raises(AssertionError):
        assert_worker_row_lock(rows, holder_pid=101, worker_ips=ips)


@pytest.mark.parametrize("family", ["jobs", "snapshots"])
@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_duplicate_terminal_rows_cannot_qualify(family, count):
    before = admitted()
    after = settled(before)
    after[family] *= count
    with pytest.raises(AssertionError):
        assert_same_claim_financial_settlement(before["jobs"][0], after)


@pytest.mark.parametrize("restoration_fails", [False, True])
def test_setup_failure_preserves_primary_and_restores_stopped_worker(
    monkeypatch, restoration_fails
):
    from tests.e2e import test_failure_scenarios as scenario

    commands = []
    primary = ValueError("native admission failed")

    def compose(*args):
        commands.append(args)
        if args[0] == "start" and restoration_fails:
            raise RuntimeError("worker unavailable")

    def trigger():
        raise primary

    monkeypatch.setattr(scenario, "_native_compose", compose)
    monkeypatch.setattr(scenario, "valuation_outage_snapshot", lambda *_: admitted())
    monkeypatch.setattr(scenario, "emit_test_output", lambda *_: None)
    with pytest.raises(ValueError) as caught:
        scenario._recover_admitted_valuation(object(), {"pid": "OWNED"}, trigger)
    assert caught.value is primary
    assert commands == [
        ("stop", "position_valuation_calculator"),
        ("start", "position_valuation_calculator"),
    ]
    assert any("Valuation outage evidence:" in note for note in primary.__notes__)
    assert any("restoration failed" in note for note in primary.__notes__) == restoration_fails


def test_failure_observation_unavailable_does_not_replace_primary(monkeypatch):
    from tests.e2e import test_failure_scenarios as scenario

    primary = ValueError("admission failed")

    def trigger():
        raise primary

    def unavailable(*_):
        raise ConnectionRefusedError("database remains unavailable")

    monkeypatch.setattr(scenario, "_native_compose", lambda *_: "")
    monkeypatch.setattr(scenario, "valuation_outage_snapshot", unavailable)
    monkeypatch.setattr(scenario, "emit_test_output", lambda *_: None)
    with pytest.raises(ValueError) as caught:
        scenario._recover_admitted_valuation(object(), {"pid": "OWNED"}, trigger)
    assert caught.value is primary
    assert '"missing"' in primary.__notes__[0]
    assert "ConnectionRefusedError" in primary.__notes__[0]


def test_blocker_timeout_retains_raw_backend_and_identity_without_starting_outage(monkeypatch):
    from tests.e2e import test_failure_scenarios as scenario

    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.side_effect = [17, 101]
    raw = dict(blocked_backend(), query="actual worker statement", wait_event_type="Client")
    connection.execute.return_value.mappings.return_value = [raw]
    primary = TimeoutError("worker did not qualify")
    commands = []
    calls = 0

    def compose(*args):
        commands.append(args)
        return "172.20.0.8" if args[0] == "exec" else ""

    def wait(observe, accept):
        nonlocal calls
        calls += 1
        if calls == 1:
            return admitted()
        rows = observe()
        assert rows == [raw] and not accept(rows)
        raise primary

    monkeypatch.setattr(scenario, "_native_compose", compose)
    monkeypatch.setattr(scenario, "wait_for_value", wait)
    monkeypatch.setattr(scenario, "valuation_outage_snapshot", lambda *_: admitted())
    monkeypatch.setattr(scenario, "emit_test_output", lambda *_: None)
    with pytest.raises(TimeoutError) as caught:
        scenario._recover_admitted_valuation(engine, {"pid": "OWNED"}, lambda: None)
    assert caught.value is primary
    note = primary.__notes__[0]
    assert '"holder_pid": 101' in note and '"worker_ips": ["172.20.0.8"]' in note
    assert '"blocker_observation"' in note and "actual worker statement" in note
    assert all("postgres" not in command for command in commands)
