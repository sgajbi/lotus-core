from scripts.quality.warning_budget_gate import parse_warning_count


def test_parse_warning_count_from_pytest_summary() -> None:
    output = "470 passed, 6 deselected, 8 warnings in 18.39s"
    assert parse_warning_count(output) == 8


def test_parse_warning_count_when_no_summary_present() -> None:
    output = "12 passed in 0.20s"
    assert parse_warning_count(output) == 0
