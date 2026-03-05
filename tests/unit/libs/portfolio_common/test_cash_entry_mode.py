from portfolio_common.transaction_domain import (
    AUTO_CASH_ENTRY_MODE,
    EXTERNAL_CASH_ENTRY_MODE,
    is_external_cash_entry_mode,
    normalize_cash_entry_mode,
)


def test_normalize_cash_entry_mode_defaults_to_auto() -> None:
    assert normalize_cash_entry_mode(None) == AUTO_CASH_ENTRY_MODE


def test_normalize_cash_entry_mode_accepts_known_mode_case_insensitively() -> None:
    assert normalize_cash_entry_mode("external") == EXTERNAL_CASH_ENTRY_MODE


def test_normalize_cash_entry_mode_falls_back_to_auto_for_unknown_mode() -> None:
    assert normalize_cash_entry_mode("MANUAL") == AUTO_CASH_ENTRY_MODE


def test_is_external_cash_entry_mode_true_only_for_external() -> None:
    assert is_external_cash_entry_mode("EXTERNAL")
    assert not is_external_cash_entry_mode("AUTO")
