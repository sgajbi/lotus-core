import logging

from portfolio_common import logging_utils


def test_setup_logging_uses_error_level_for_tooling_quiet(monkeypatch):
    monkeypatch.setenv("LOTUS_TOOLING_QUIET", "1")

    logging_utils.setup_logging()

    assert logging.getLogger().level == logging.ERROR


def test_setup_logging_defaults_to_info_level(monkeypatch):
    monkeypatch.delenv("LOTUS_TOOLING_QUIET", raising=False)

    logging_utils.setup_logging()

    assert logging.getLogger().level == logging.INFO
