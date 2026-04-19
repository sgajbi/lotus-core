from portfolio_common.valuation_runtime_settings import get_valuation_runtime_settings


def test_get_valuation_runtime_settings_uses_defaults_when_env_missing(monkeypatch):
    for name in (
        "VALUATION_SCHEDULER_POLL_INTERVAL",
        "VALUATION_SCHEDULER_BATCH_SIZE",
        "VALUATION_SCHEDULER_DISPATCH_ROUNDS",
        "VALUATION_SCHEDULER_STALE_TIMEOUT_MINUTES",
        "VALUATION_SCHEDULER_MAX_ATTEMPTS",
        "REPROCESSING_WORKER_POLL_INTERVAL_SECONDS",
        "REPROCESSING_WORKER_BATCH_SIZE",
        "REPROCESSING_WORKER_STALE_TIMEOUT_MINUTES",
        "REPROCESSING_WORKER_MAX_ATTEMPTS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = get_valuation_runtime_settings()

    assert settings.valuation_scheduler_poll_interval_seconds == 30
    assert settings.valuation_scheduler_batch_size == 100
    assert settings.valuation_scheduler_dispatch_rounds == 10
    assert settings.valuation_scheduler_stale_timeout_minutes == 15
    assert settings.valuation_scheduler_max_attempts == 3
    assert settings.reprocessing_worker_poll_interval_seconds == 10
    assert settings.reprocessing_worker_batch_size == 10
    assert settings.reprocessing_worker_stale_timeout_minutes == 15
    assert settings.reprocessing_worker_max_attempts == 3


def test_get_valuation_runtime_settings_clamps_invalid_env_values(monkeypatch):
    monkeypatch.setenv("VALUATION_SCHEDULER_POLL_INTERVAL", "0")
    monkeypatch.setenv("VALUATION_SCHEDULER_BATCH_SIZE", "-5")
    monkeypatch.setenv("VALUATION_SCHEDULER_DISPATCH_ROUNDS", "abc")
    monkeypatch.setenv("REPROCESSING_WORKER_BATCH_SIZE", "2")

    settings = get_valuation_runtime_settings(scheduler_dispatch_rounds_default=7)

    assert settings.valuation_scheduler_poll_interval_seconds == 1
    assert settings.valuation_scheduler_batch_size == 1
    assert settings.valuation_scheduler_dispatch_rounds == 7
    assert settings.reprocessing_worker_batch_size == 2
