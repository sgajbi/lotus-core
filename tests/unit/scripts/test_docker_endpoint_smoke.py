from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.docker_endpoint_smoke import (
    SMOKE_CSV_TRANSACTION_ID,
    SMOKE_INSTRUMENT_ID,
    SMOKE_ISIN,
    SMOKE_PORTFOLIO_ID,
    SMOKE_SECURITY_ID,
    SMOKE_TRANSACTION_ID,
    SMOKE_TRANSACTION_ID_2,
    _wait_expected_status,
    build_smoke_cleanup_sql,
)


def test_docker_endpoint_smoke_uses_deterministic_identifiers():
    assert SMOKE_PORTFOLIO_ID == "PORT_SMOKE_CANONICAL"
    assert SMOKE_SECURITY_ID == "SEC_SMOKE_CANONICAL"
    assert SMOKE_INSTRUMENT_ID == "INST_SMOKE_CANONICAL"
    assert SMOKE_TRANSACTION_ID == "TX_SMOKE_CANONICAL"
    assert SMOKE_TRANSACTION_ID_2 == "TX2_SMOKE_CANONICAL"
    assert SMOKE_CSV_TRANSACTION_ID == "TXUP_SMOKE_CANONICAL"
    assert SMOKE_ISIN == "US000SMOKE01"


def test_docker_endpoint_smoke_cleanup_sql_purges_legacy_smoke_rows():
    sql = build_smoke_cleanup_sql()

    assert "delete from transactions where portfolio_id like 'PORT_SMOKE_%';" in sql
    assert "delete from portfolios where portfolio_id like 'PORT_SMOKE_%';" in sql
    assert "delete from market_prices where security_id like 'SEC_SMOKE_%';" in sql
    assert "delete from transaction_costs where transaction_id like 'TX%_SMOKE_%';" in sql


def test_wait_expected_status_retries_until_endpoint_is_ready(monkeypatch: pytest.MonkeyPatch):
    responses = iter(
        [
            SimpleNamespace(status_code=404),
            SimpleNamespace(status_code=404),
            SimpleNamespace(status_code=200),
        ]
    )
    get_mock = Mock(side_effect=lambda *args, **kwargs: next(responses))
    now = iter([0, 1, 2, 3])

    monkeypatch.setattr("scripts.docker_endpoint_smoke.requests.get", get_mock)
    monkeypatch.setattr("scripts.docker_endpoint_smoke.time.sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.docker_endpoint_smoke.time.time", lambda: next(now))

    _wait_expected_status("http://query/ready-endpoint", {200}, timeout_seconds=5)

    assert get_mock.call_count == 3


def test_wait_expected_status_raises_with_last_status_context(
    monkeypatch: pytest.MonkeyPatch,
):
    get_mock = Mock(return_value=SimpleNamespace(status_code=404))
    now = iter([0, 1, 2, 3])

    monkeypatch.setattr("scripts.docker_endpoint_smoke.requests.get", get_mock)
    monkeypatch.setattr("scripts.docker_endpoint_smoke.time.sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.docker_endpoint_smoke.time.time", lambda: next(now))

    with pytest.raises(TimeoutError, match="last_status=404"):
        _wait_expected_status("http://query/missing-endpoint", {200}, timeout_seconds=2)
