"""Isolate older migration rollbacks from newer portfolio-tenant foreign keys.

Alembic normally downgrades c171 before c168/c118. Historical migration tests
invoke the older revisions directly against the current schema, so they must
temporarily remove the verified newer foreign keys that depend on c168's
portfolio tenant uniqueness constraint, then restore and verify them. This now
includes selected-history and financial-reconciliation authority introduced by
later revisions.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_DEPENDENCIES = (
    (
        "portfolio_selected_history_observations",
        "fk_portfolio_selected_history_observations_tenant_portfolio",
    ),
    (
        "portfolio_selected_history_valuation_states",
        "fk_portfolio_selected_history_valuation_states_tenant_portfolio",
    ),
    (
        "financial_reconciliation_runs",
        "fk_fin_recon_runs_tenant_portfolio",
    ),
    (
        "financial_reconciliation_findings",
        "fk_fin_recon_findings_tenant_portfolio",
    ),
)


def _assert_portfolio_tenant_foreign_keys(connection: Connection) -> None:
    for table_name, constraint_name in _DEPENDENCIES:
        matches = [
            foreign_key
            for foreign_key in inspect(connection).get_foreign_keys(table_name)
            if foreign_key["name"] == constraint_name
        ]
        if len(matches) != 1:
            raise AssertionError(f"expected exactly one {constraint_name} on {table_name}")
        foreign_key = matches[0]
        if (
            foreign_key["constrained_columns"] != ["tenant_id", "portfolio_id"]
            or foreign_key["referred_table"] != "portfolios"
            or foreign_key["referred_columns"] != ["tenant_id", "portfolio_id"]
        ):
            raise AssertionError(f"unexpected tenant authority for {constraint_name}")


def suspend_selected_history_portfolio_foreign_keys(connection: Connection) -> None:
    """Drop verified newer tenant dependencies before an older direct rollback."""

    _assert_portfolio_tenant_foreign_keys(connection)
    for table_name, _constraint_name in _DEPENDENCIES:
        if connection.scalar(text(f'SELECT EXISTS (SELECT 1 FROM "{table_name}" LIMIT 1)')):
            raise AssertionError(f"cannot suspend tenant authority with rows in {table_name}")
    for table_name, constraint_name in _DEPENDENCIES:
        connection.execute(text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT "{constraint_name}"'))


def restore_selected_history_portfolio_foreign_keys(connection: Connection) -> None:
    """Reestablish current-schema tenant authority after the older upgrade."""

    for table_name, constraint_name in _DEPENDENCIES:
        connection.execute(
            text(
                f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
                "FOREIGN KEY (tenant_id, portfolio_id) "
                "REFERENCES portfolios (tenant_id, portfolio_id)"
            )
        )
    _assert_portfolio_tenant_foreign_keys(connection)
