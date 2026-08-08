"""Foreign-key-safe SQL plans for deleting portfolio-owned lot evidence.

The lot ledger deliberately uses restrictive foreign keys because receipts, allocations, and
amortized-cost evidence are immutable in production. Local validation reseeds are the exception:
they must remove the complete portfolio-owned evidence graph before deleting its lot roots.
"""

from __future__ import annotations

from typing import Literal


def build_lot_evidence_cleanup_statements(
    *,
    portfolio_selector: str,
    match: Literal["exact", "prefix"],
) -> tuple[str, ...]:
    """Return the portfolio-scoped lot-evidence cleanup plan in dependency order."""

    if match not in {"exact", "prefix"}:
        raise ValueError(f"unsupported portfolio selector match: {match}")
    operator = "=" if match == "exact" else "like"
    value = portfolio_selector if match == "exact" else f"{portfolio_selector}%"
    predicate = f"portfolio_id {operator} {_sql_literal(value)}"
    profile_scope = (
        f"select profile_id, profile_version from lot_amortized_cost_profiles where {predicate}"
    )

    return (
        # Lots optionally point back to their amortized-cost profile. Clear the complete nullable
        # binding first to break that cycle without weakening either foreign key.
        "update position_lot_state set "
        "amortized_cost_profile_id = null, "
        "amortized_cost_profile_version = null, "
        "amortized_cost_profile_content_hash = null, "
        "amortized_cost_recognized_through = null, "
        "amortized_cost_scheduled_local = null, "
        "amortized_book_carrying_local = null, "
        "amortized_book_carrying_base = null, "
        "amortized_cost_book_fx_rate_to_base = null "
        f"where {predicate};",
        f"delete from lot_disposal_allocations where {predicate};",
        f"delete from lot_basis_transfer_allocations where {predicate};",
        "delete from lot_amortized_cost_periods where (profile_id, profile_version) in "
        f"({profile_scope});",
        f"delete from lot_disposal_receipts where {predicate};",
        f"delete from lot_basis_transfer_receipts where {predicate};",
        f"delete from lot_amortized_cost_authority where {predicate};",
        f"delete from lot_amortized_cost_profiles where {predicate};",
    )


def _sql_literal(value: str) -> str:
    """Render a PostgreSQL string literal for the controlled local validation plan."""

    return "'" + value.replace("'", "''") + "'"
