import argparse

from tools import db_retention_maintenance


def test_valuation_retention_rule_includes_all_terminal_statuses() -> None:
    rules = db_retention_maintenance._rules(argparse.Namespace())
    valuation_rule = next(
        rule for rule in rules if rule.name == "portfolio_valuation_jobs_terminal"
    )

    for status in db_retention_maintenance.TERMINAL_VALUATION_JOB_STATUSES:
        assert status in valuation_rule.count_sql
        assert status in valuation_rule.delete_sql

    assert "SKIPPED_SUPERSEDED" in valuation_rule.count_sql
    assert "SKIPPED_SUPERSEDED" in valuation_rule.delete_sql
