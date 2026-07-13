"""Protect canonical INTEREST net and settlement-cash methodology wording."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INTEREST_RFC = (
    REPO_ROOT
    / "docs"
    / "rfc-transaction-specs"
    / "transactions"
    / "INTEREST"
    / "RFC-INTEREST-01.md"
)
PERFORMANCE_METHODOLOGY = (
    REPO_ROOT
    / "docs"
    / "methodologies"
    / "source-data-products"
    / "performance-component-economics.md"
)


def test_interest_rfc_distinguishes_pre_fee_net_from_settlement_cash() -> None:
    methodology = INTEREST_RFC.read_text(encoding="utf-8")

    assert (
        "net_interest_local = gross_interest_local - withholding_tax_local - "
        "other_interest_deductions_local"
    ) in methodology
    assert (
        "settlement_cash_amount_local = net_interest_local - transaction_fee_local"
    ) in methodology
    assert (
        "settlement_cash_amount_local = net_interest_local + transaction_fee_local"
    ) in methodology
    assert "Equivalent explicit and derived net-interest inputs" in methodology


def test_performance_methodology_keeps_interest_and_fee_evidence_separate() -> None:
    methodology = PERFORMANCE_METHODOLOGY.read_text(encoding="utf-8")

    assert (
        "`net_interest_amount` and fee evidence are intentionally separate components"
        in methodology
    )
    assert "linked latest-epoch\ncashflow remains the source-owned settled amount" in methodology
