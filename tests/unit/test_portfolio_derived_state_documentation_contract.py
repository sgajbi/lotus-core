from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RETIRED_DERIVED_STATE_SERVICES = {
    "timeseries_generator_service",
    "portfolio_aggregation_service",
}


def _section(document: str, start: str, end: str) -> str:
    return document.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]


def test_current_derived_state_ownership_docs_exclude_retired_deployables() -> None:
    current_documents = [
        REPO_ROOT
        / "docs/features/cashflow_calculator/01_Feature_Cashflow_Calculator_Overview.md",
        REPO_ROOT / "docs/architecture/repository-output-shape-standard.md",
    ]
    for path in current_documents:
        content = path.read_text(encoding="utf-8")
        assert "portfolio_derived_state_service" in content
        for retired_service in RETIRED_DERIVED_STATE_SERVICES:
            assert retired_service not in content


def test_current_event_topology_sections_exclude_retired_deployables() -> None:
    rfc = (
        REPO_ROOT / "docs/RFCs/RFC-083 - Kafka Topic Naming and Event Taxonomy Standard.md"
    ).read_text(encoding="utf-8")
    current_sections = (
        _section(rfc, "### 7.5 Exact Current Producer and Consumer Matrix", "## 8."),
        _section(rfc, "### 12.3 Valuation and Day-Level Chain", "## 13."),
    )
    for section in current_sections:
        assert "portfolio_derived_state_service" in section
        for retired_service in RETIRED_DERIVED_STATE_SERVICES:
            assert f"`{retired_service}`" not in section
