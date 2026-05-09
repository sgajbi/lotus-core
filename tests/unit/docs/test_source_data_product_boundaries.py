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
    assert "| `HoldingsAsOf:v1` |" in catalog
    assert "holdings-as-of.md" in catalog
    assert "current-epoch snapshot reconciliation" in catalog
    assert "| `MarketDataCoverageWindow:v1` |" in catalog
    assert "market-data-coverage-window.md" in catalog
    assert "missing and stale identifiers" in catalog
    assert "must not infer portfolio valuation, FX attribution" in catalog
    assert "| `DpmSourceReadiness:v1` |" in catalog
    assert "dpm-source-readiness.md" in catalog
    assert "Fail-closed source-family readiness" in catalog
    assert "must not infer mandate approval, suitability, valuation" in catalog
    assert "| `TransactionLedgerWindow:v1` |" in catalog
    assert "trade fees, transaction-cost records, withholding tax" in catalog
    assert "realized capital/FX/total P&L fields" in catalog
    assert "linked cashflow records" in catalog
    assert "transaction-ledger-window.md" in catalog
    assert "must not aggregate rows into tax methodology" in catalog
    assert "FX attribution, cash movement methodology, transaction-cost methodology" in catalog
    assert "| `PortfolioCashflowProjection:v1` |" in catalog
    assert "Daily net cashflow points, cumulative cashflow across the returned window" in catalog
    assert "must not treat the projection as a liquidity ladder" in catalog
    assert "| `PortfolioTaxLotWindow:v1` |" in catalog
    assert "portfolio-tax-lot-window.md" in catalog
    assert "wash-sale treatment" in catalog
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
    assert "`MarketDataCoverageWindow:v1`" in wiki
    assert "`DpmSourceReadiness:v1`" in wiki
    assert "`PortfolioCashflowProjection:v1`" in wiki
    assert "`PortfolioTaxLotWindow:v1`" in wiki
    assert "snapshot-backed positions to latest current-epoch history quantity" in (normalized_wiki)
    assert "cash-account master data" in wiki
    assert "not an execution-quality, tax-advice, liquidity-planning" in normalized_wiki
    assert "Preserve the source measure, source unit, selected field, supportability state" in (
        normalized_wiki
    )
    assert "filters booked transaction rows by portfolio" in normalized_wiki
    assert "optional instrument/security, transaction type, FX/event linkage" in normalized_wiki
    assert "classifies empty, complete, and paged windows" in normalized_wiki
    assert "settlement-dated future external `DEPOSIT` and `WITHDRAWAL` movements" in wiki
    assert "Same-day booked and projected movements are additive" in wiki
    assert "position_lot_state" in wiki
    assert "wash-sale treatment" in wiki
    assert "observed booked transaction-fee evidence" in wiki
    assert "explicit `transaction_costs` rows when present" in wiki
    assert "best-execution, OMS acknowledgement" in normalized_wiki
    assert "latest market prices and FX rates on or before the requested as-of date" in (
        normalized_wiki
    )
    assert "not a valuation engine, FX attribution method, liquidity ladder" in normalized_wiki
    assert "composes mandate binding, model targets, instrument eligibility" in normalized_wiki
    assert "`UNAVAILABLE` source families outrank `INCOMPLETE`" in normalized_wiki
    assert "without reconstructing mandate, eligibility, tax, market-data" in normalized_wiki
    assert "flowchart LR" in wiki


def test_holdings_as_of_methodology_is_implementation_backed() -> None:
    methodology = _read("docs/methodologies/source-data-products/holdings-as-of.md")
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
    assert "`HoldingsAsOf:v1`" in methodology
    assert "`GET /portfolios/{portfolio_id}/positions`" in methodology
    assert "`GET /portfolios/{portfolio_id}/cash-balances`" in methodology
    assert "S_latest.quantity = H_latest.quantity" in methodology
    assert "market_value = cost_basis" in methodology
    assert "W_i = V_i / sum(V_i for all returned positions)" in methodology
    assert "C_r = C_p * X_c" in methodology
    assert "held_since_date" in methodology
    assert "No performance return, risk exposure, liquidity ladder" in normalized_methodology
    assert "| `data_quality_status` | `PARTIAL` |" in methodology


def test_market_data_coverage_window_methodology_is_implementation_backed() -> None:
    methodology = _read("docs/methodologies/source-data-products/market-data-coverage-window.md")
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
        "## Output Contract",
        "## Worked Example",
        "## Downstream Consumption Rules",
    ]
    section_positions = [methodology.index(section) for section in expected_sections]

    assert section_positions == sorted(section_positions)
    assert "`MarketDataCoverageWindow:v1`" in methodology
    assert "`POST /integration/market-data/coverage`" in methodology
    assert "`market_prices`" in methodology
    assert "`fx_rates`" in methodology
    assert "age_days = as_of_date - observation_date" in methodology
    assert "M_s = latest market_prices" in methodology
    assert "F_c = latest fx_rates" in methodology
    assert "INCOMPLETE` / `MARKET_DATA_MISSING`" in methodology
    assert "DEGRADED` / `MARKET_DATA_STALE`" in methodology
    assert "Batch supportability is `INCOMPLETE`" in methodology
    assert "must not: 1. infer FX attribution" in normalized_methodology
    assert "market-impact model, execution-quality assessment" in normalized_methodology


def test_dpm_source_readiness_methodology_is_implementation_backed() -> None:
    methodology = _read("docs/methodologies/source-data-products/dpm-source-readiness.md")
    normalized_methodology = _single_line(methodology)

    expected_sections = [
        "## Purpose",
        "## Supported Modes",
        "## Inputs And Variables",
        "## Source Tables And Products",
        "## Methodology And Formulas",
        "## Deterministic Steps",
        "## Validation And Failure Behavior",
        "## Output Contract Mapping",
        "## Worked Examples",
        "## Downstream Consumption Rule",
    ]
    section_positions = [methodology.index(section) for section in expected_sections]

    assert section_positions == sorted(section_positions)
    assert "`DpmSourceReadiness:v1`" in methodology
    assert "`POST /integration/portfolios/{portfolio_id}/dpm-source-readiness`" in methodology
    assert "`DiscretionaryMandateBinding:v1`" in methodology
    assert "`DpmModelPortfolioTarget:v1`" in methodology
    assert "`InstrumentEligibilityProfile:v1`" in methodology
    assert "`PortfolioTaxLotWindow:v1`" in methodology
    assert "`MarketDataCoverageWindow:v1`" in methodology
    assert "`I_eval = sort(unique(I_req union I_model))`" in methodology
    assert "if any family is `UNAVAILABLE`" in methodology
    assert "DPM_SOURCE_READINESS_READY" in methodology
    assert "data_quality_status` is `COMPLETE` only when" in normalized_methodology
    assert "must not: 1. infer mandate approval" in normalized_methodology


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


def test_transaction_ledger_window_methodology_is_implementation_backed() -> None:
    methodology = _read("docs/methodologies/source-data-products/transaction-ledger-window.md")
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
    assert "`TransactionLedgerWindow:v1`" in methodology
    assert "Default booked ledger" in methodology
    assert "Projected-inclusive ledger" in methodology
    assert "Reporting-currency restated ledger" in methodology
    assert "transaction_date < start_of_next_day(A)" in methodology
    assert "amount_reporting_currency = amount * X_c" in methodology
    assert "row-level `cashflow` and `transaction_costs` evidence" in (normalized_methodology)
    assert "No tax calculation, FX attribution" in normalized_methodology
    assert "| `transactions[1].withholding_tax_amount_reporting_currency` | 13.60 |" in (
        methodology
    )


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


def test_portfolio_tax_lot_window_methodology_is_implementation_backed() -> None:
    methodology = _read("docs/methodologies/source-data-products/portfolio-tax-lot-window.md")
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
    assert "`PortfolioTaxLotWindow:v1`" in methodology
    assert "`position_lot_state`" in methodology
    assert "returns open lots by default" in normalized_methodology
    assert "not recalculated, reallocated, or tax-optimized" in normalized_methodology
    assert "TAX_LOTS_EMPTY" in methodology
    assert "wash-sale treatment" in methodology
    assert "| `lots[0].tax_lot_status` | `OPEN` |" in methodology


def test_methodology_index_links_source_data_product_methodologies() -> None:
    index = _read("docs/methodologies/README.md")

    assert "source-data-products/holdings-as-of.md" in index
    assert "source-data-products/market-data-coverage-window.md" in index
    assert "source-data-products/dpm-source-readiness.md" in index
    assert "source-data-products/transaction-ledger-window.md" in index
    assert "source-data-products/portfolio-cashflow-projection.md" in index
    assert "source-data-products/portfolio-tax-lot-window.md" in index
    assert "source-data-products/transaction-cost-curve.md" in index
    assert "Effective-dated open and closed tax-lot state" in index
    assert "current-epoch snapshot reconciliation" in index
    assert "Held and target universe price and FX coverage diagnostics" in index
    assert "Fail-closed DPM source-family readiness" in index
    assert "Governed booked transaction-row windowing" in index
    assert "Observed booked-fee aggregation by security, transaction type, and currency" in index
