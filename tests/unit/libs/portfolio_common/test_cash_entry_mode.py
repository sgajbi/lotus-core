from portfolio_common.transaction_domain import (
    AUTO_GENERATE_CASH_ENTRY_MODE,
    UPSTREAM_PROVIDED_CASH_ENTRY_MODE,
    is_upstream_provided_cash_entry_mode,
    normalize_cash_entry_mode,
)


def test_normalize_cash_entry_mode_defaults_to_auto() -> None:
    assert normalize_cash_entry_mode(None) == AUTO_GENERATE_CASH_ENTRY_MODE


def test_normalize_cash_entry_mode_accepts_known_mode_case_insensitively() -> None:
    assert (
        normalize_cash_entry_mode("upstream_provided")
        == UPSTREAM_PROVIDED_CASH_ENTRY_MODE
    )


def test_normalize_cash_entry_mode_rejects_unknown_mode() -> None:
    try:
        normalize_cash_entry_mode("MANUAL")
    except ValueError as exc:
        assert "Unsupported cash_entry_mode" in str(exc)
    else:
        raise AssertionError("Expected normalize_cash_entry_mode to reject unknown mode.")


def test_is_upstream_provided_cash_entry_mode_true_only_for_upstream_mode() -> None:
    assert is_upstream_provided_cash_entry_mode("UPSTREAM_PROVIDED")
    assert not is_upstream_provided_cash_entry_mode("AUTO_GENERATE")
