"""Validate strict position valuation worker settings."""

import pytest
from portfolio_common.runtime_settings import RuntimeConfigurationError

from src.services.calculators.position_valuation_calculator.app.settings import (
    get_position_valuation_runtime_settings,
)


def test_position_valuation_settings_use_one_worker_by_default(monkeypatch):
    monkeypatch.delenv("POSITION_VALUATION_WORKER_COUNT", raising=False)

    settings = get_position_valuation_runtime_settings()

    assert settings.worker_count == 1


def test_position_valuation_settings_clamp_invalid_local_worker_count(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("POSITION_VALUATION_WORKER_COUNT", "0")

    settings = get_position_valuation_runtime_settings()

    assert settings.worker_count == 1


def test_position_valuation_settings_reject_invalid_strict_worker_count(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("POSITION_VALUATION_WORKER_COUNT", "0")

    with pytest.raises(RuntimeConfigurationError, match="POSITION_VALUATION_WORKER_COUNT"):
        get_position_valuation_runtime_settings()
