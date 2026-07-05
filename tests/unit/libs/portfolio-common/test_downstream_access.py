import pytest
from portfolio_common.downstream_access import load_downstream_access_policy
from portfolio_common.runtime_settings import RuntimeConfigurationError


def test_downstream_access_policy_defaults(monkeypatch):
    for env_name in (
        "LOTUS_CORE_DOWNSTREAM_CONNECT_TIMEOUT_MS",
        "LOTUS_CORE_DOWNSTREAM_REQUEST_TIMEOUT_MS",
        "LOTUS_CORE_DOWNSTREAM_RETRY_MAX_ATTEMPTS",
        "LOTUS_CORE_DOWNSTREAM_RETRY_BACKOFF_MS",
        "LOTUS_CORE_DOWNSTREAM_RETRY_MAX_ELAPSED_MS",
        "LOTUS_CORE_DOWNSTREAM_CIRCUIT_BREAKER_ENABLED",
        "LOTUS_CORE_DOWNSTREAM_MAX_PAGE_SIZE",
        "LOTUS_CORE_DOWNSTREAM_MAX_BATCH_SIZE",
        "LOTUS_CORE_DOWNSTREAM_CACHE_ALLOWED",
    ):
        monkeypatch.delenv(env_name, raising=False)

    policy = load_downstream_access_policy()

    assert policy.connect_timeout_seconds == 0.5
    assert policy.request_timeout_seconds == 5.0
    assert policy.retry_max_attempts == 15
    assert policy.retry_backoff_seconds == 4.0
    assert policy.retry_max_elapsed_seconds == 60.0
    assert policy.circuit_breaker_enabled is False
    assert policy.max_page_size == 500
    assert policy.max_batch_size == 500
    assert policy.cache_allowed is True


def test_downstream_access_policy_reads_overrides(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_CONNECT_TIMEOUT_MS", "250")
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_REQUEST_TIMEOUT_MS", "1250")
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_RETRY_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_RETRY_BACKOFF_MS", "100")
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_RETRY_MAX_ELAPSED_MS", "2000")
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_CIRCUIT_BREAKER_ENABLED", "true")
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_MAX_PAGE_SIZE", "50")
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_MAX_BATCH_SIZE", "25")
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_CACHE_ALLOWED", "false")

    policy = load_downstream_access_policy()

    assert policy.connect_timeout_seconds == 0.25
    assert policy.request_timeout_seconds == 1.25
    assert policy.retry_max_attempts == 3
    assert policy.retry_backoff_seconds == 0.1
    assert policy.retry_max_elapsed_seconds == 2.0
    assert policy.circuit_breaker_enabled is True
    assert policy.max_page_size == 50
    assert policy.max_batch_size == 25
    assert policy.cache_allowed is False


def test_downstream_access_policy_strict_validation_rejects_invalid_timeout(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_REQUEST_TIMEOUT_MS", "0")

    with pytest.raises(RuntimeConfigurationError, match="LOTUS_CORE_DOWNSTREAM_REQUEST_TIMEOUT_MS"):
        load_downstream_access_policy()
