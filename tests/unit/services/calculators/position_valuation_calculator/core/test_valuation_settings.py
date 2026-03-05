from src.services.calculators.position_valuation_calculator.app.settings import (
    get_valuation_runtime_settings,
)


def test_runtime_settings_defaults_when_env_missing(monkeypatch):
    monkeypatch.delenv("VALUATION_SCHEDULER_POLL_INTERVAL", raising=False)
    monkeypatch.delenv("VALUATION_SCHEDULER_BATCH_SIZE", raising=False)
    monkeypatch.delenv("VALUATION_SCHEDULER_DISPATCH_ROUNDS", raising=False)
    monkeypatch.delenv("REPROCESSING_WORKER_POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("REPROCESSING_WORKER_BATCH_SIZE", raising=False)

    settings = get_valuation_runtime_settings(
        scheduler_poll_interval_default=17,
        scheduler_batch_size_default=222,
        scheduler_dispatch_rounds_default=5,
        worker_poll_interval_default=9,
        worker_batch_size_default=13,
    )

    assert settings.valuation_scheduler_poll_interval_seconds == 17
    assert settings.valuation_scheduler_batch_size == 222
    assert settings.valuation_scheduler_dispatch_rounds == 5
    assert settings.reprocessing_worker_poll_interval_seconds == 9
    assert settings.reprocessing_worker_batch_size == 13


def test_runtime_settings_env_override_with_positive_int_guard(monkeypatch):
    monkeypatch.setenv("VALUATION_SCHEDULER_POLL_INTERVAL", "20")
    monkeypatch.setenv("VALUATION_SCHEDULER_BATCH_SIZE", "300")
    monkeypatch.setenv("VALUATION_SCHEDULER_DISPATCH_ROUNDS", "6")
    monkeypatch.setenv("REPROCESSING_WORKER_POLL_INTERVAL_SECONDS", "15")
    monkeypatch.setenv("REPROCESSING_WORKER_BATCH_SIZE", "24")

    settings = get_valuation_runtime_settings(
        scheduler_poll_interval_default=17,
        scheduler_batch_size_default=222,
        scheduler_dispatch_rounds_default=5,
        worker_poll_interval_default=9,
        worker_batch_size_default=13,
    )

    assert settings.valuation_scheduler_poll_interval_seconds == 20
    assert settings.valuation_scheduler_batch_size == 300
    assert settings.valuation_scheduler_dispatch_rounds == 6
    assert settings.reprocessing_worker_poll_interval_seconds == 15
    assert settings.reprocessing_worker_batch_size == 24

