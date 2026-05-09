from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _single_line(text: str) -> str:
    return " ".join(text.split())


def test_rfc0083_documents_realized_outcome_source_boundaries() -> None:
    catalog = _read("docs/architecture/RFC-0083-source-data-product-catalog.md")
    normalized_catalog = _single_line(catalog)

    assert "## Realized Outcome Source Boundaries" in catalog
    assert "| `TransactionLedgerWindow:v1` |" in catalog
    assert "trade fees, transaction-cost records, withholding tax" in catalog
    assert "realized capital/FX/total P&L fields" in catalog
    assert "linked cashflow records" in catalog
    assert "must not aggregate rows into tax methodology" in catalog
    assert "FX attribution, cash movement methodology, transaction-cost methodology" in catalog
    assert "| `PortfolioCashflowProjection:v1` |" in catalog
    assert "Daily net cashflow points, cumulative cashflow across the returned window" in catalog
    assert "must not treat the projection as a liquidity ladder" in catalog
    assert "| `TransactionCostCurve:v1` |" in catalog
    assert "must not claim predictive market-impact, venue-routing, fill-quality" in catalog
    assert "transaction-cost-curve.md" in catalog
    assert "notional-weighted average cost bps plus min/max" in catalog
    assert "Downstream products must carry source refs and supportability metadata" in (
        normalized_catalog
    )


def test_mesh_wiki_explains_core_source_authority_for_non_engineering_audiences() -> None:
    wiki = _read("wiki/Mesh-Data-Products.md")
    normalized_wiki = _single_line(wiki)

    assert "## Realized Outcome Evidence Boundaries" in wiki
    assert "Developers and architects" in wiki
    assert "Sales and client demos" in wiki
    assert "`TransactionLedgerWindow:v1`" in wiki
    assert "`PortfolioCashflowProjection:v1`" in wiki
    assert "not an execution-quality, tax-advice, liquidity-planning" in normalized_wiki
    assert "Preserve the source measure, source unit, selected field, supportability state" in (
        normalized_wiki
    )
    assert "settlement-dated future external `DEPOSIT` and `WITHDRAWAL` movements" in wiki
    assert "Same-day booked and projected movements are additive" in wiki
    assert "observed booked transaction-fee evidence" in wiki
    assert "explicit `transaction_costs` rows when present" in wiki
    assert "best-execution, OMS acknowledgement" in normalized_wiki
    assert "flowchart LR" in wiki


def test_portfolio_cashflow_projection_methodology_is_implementation_backed() -> None:
    methodology = _read("docs/methodologies/source-data-products/portfolio-cashflow-projection.md")
    normalized_methodology = _single_line(methodology)

    expected_sections = [
        "## Metric",
        "## Endpoint and Mode Coverage",
        "## Inputs",
        "## Upstream Data Sources",
        "## Unit Conventions",
        "## Variable Dictionary",
        "## Methodology and Formulas",
        "## Step-by-Step Computation",
        "## Validation and Failure Behavior",
        "## Configuration Options",
        "## Outputs",
        "## Worked Example",
    ]
    section_positions = [methodology.index(section) for section in expected_sections]

    assert section_positions == sorted(section_positions)
    assert "`PortfolioCashflowProjection:v1`" in methodology
    assert "Projected `DEPOSIT` amounts are `abs(gross_transaction_amount)`" in (
        normalized_methodology
    )
    assert "Projected `WITHDRAWAL` amounts are `-abs(gross_transaction_amount)`" in (
        normalized_methodology
    )
    assert "transaction dates before the projection start date" in methodology
    assert "Only the latest cashflow row per transaction contributes to `B_d`" in methodology
    assert "Same-day booked and projected movements exist" in methodology
    assert "No FX conversion, tax methodology, liquidity bucketing" in normalized_methodology
    assert "| `points[2026-03-04].net_cashflow` | -18000 |" in methodology


def test_transaction_cost_curve_methodology_is_implementation_backed() -> None:
    methodology = _read("docs/methodologies/source-data-products/transaction-cost-curve.md")
    normalized_methodology = _single_line(methodology)

    expected_sections = [
        "## Metric",
        "## Endpoint and Mode Coverage",
        "## Inputs",
        "## Upstream Data Sources",
        "## Unit Conventions",
        "## Variable Dictionary",
        "## Methodology and Formulas",
        "## Step-by-Step Computation",
        "## Validation and Failure Behavior",
        "## Configuration Options",
        "## Outputs",
        "## Worked Example",
    ]
    section_positions = [methodology.index(section) for section in expected_sections]

    assert section_positions == sorted(section_positions)
    assert "`TransactionCostCurve:v1`" in methodology
    assert "grouped by security, transaction type, and fee currency" in methodology
    assert "Cost rows take precedence over `trade_fee`" in methodology
    assert "No FX conversion, market-impact adjustment" in normalized_methodology
    assert "best-execution assessment, OMS acknowledgement" in normalized_methodology
    assert "`AB_G = TC_G / TN_G * 10000`" in methodology
    assert "security_id:asc,transaction_type:asc,currency:asc" in methodology
    assert "| `curve_points[0].average_cost_bps` | 13.3333 |" in methodology


def test_methodology_index_links_source_data_product_methodologies() -> None:
    index = _read("docs/methodologies/README.md")

    assert "source-data-products/portfolio-cashflow-projection.md" in index
    assert "source-data-products/transaction-cost-curve.md" in index
    assert "Observed booked-fee aggregation by security, transaction type, and currency" in index
