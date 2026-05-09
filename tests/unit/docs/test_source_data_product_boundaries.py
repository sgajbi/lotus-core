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
    assert "flowchart LR" in wiki
