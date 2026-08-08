import pytest

from tools.lot_evidence_cleanup import build_lot_evidence_cleanup_statements


def test_lot_evidence_cleanup_escapes_exact_portfolio_identity() -> None:
    statements = build_lot_evidence_cleanup_statements(
        portfolio_selector="PB_'PRIVATE'",
        match="exact",
    )

    assert statements
    assert all("portfolio_id = 'PB_''PRIVATE'''" in statement for statement in statements)
    assert all(" like " not in statement for statement in statements)


def test_lot_evidence_cleanup_rejects_unknown_match_policy() -> None:
    with pytest.raises(ValueError, match="unsupported portfolio selector match"):
        build_lot_evidence_cleanup_statements(
            portfolio_selector="PB_",
            match="contains",  # type: ignore[arg-type]
        )
