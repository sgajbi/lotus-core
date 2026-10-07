"""Statement shape proof, not PostgreSQL snapshot or execution certification."""

from datetime import date

import pytest
from sqlalchemy.dialects.postgresql import dialect

from src.services.query_control_plane_service.app.contracts.portfolio_source_observations import (
    ObservationSelector,
    PortfolioSourceObservationsRequest,
)
from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_source_observation_sources as sources,
)

observation_snapshot_statement = sources.observation_snapshot_statement

pytestmark = pytest.mark.unit


def _statement(latest):
    selector = ObservationSelector(
        producer_id="producer",
        source_record_id="record",
        latest_restated=latest,
        **(
            {}
            if latest
            else {
                "observation_id": "a" * 64,
                "content_hash": "a" * 64,
                "source_cut_id": "original-cut",
                "source_version": 1,
            }
        ),
    )
    request = PortfolioSourceObservationsRequest(
        as_of_date=date(2026, 1, 1), cash=selector, funding_investment=selector
    )
    return observation_snapshot_statement(
        tenant_id="tenant-owned", portfolio_id="portfolio-owned", request=request
    )


def test_both_original_families_are_one_statement_without_mutable_head_join():
    compiled = _statement(False).compile(dialect=dialect())
    sql = str(compiled)
    assert "portfolio_cash_availability_observations" in sql
    assert "portfolio_funding_investment_observations" in sql
    assert "observation_heads" not in sql
    assert list(compiled.params.values()).count("tenant-owned") == 2
    assert list(compiled.params.values()).count("portfolio-owned") == 2
    assert list(compiled.params.values()).count("original-cut") == 2
    assert "UPDATE" not in sql and "INSERT" not in sql


def test_latest_joins_scoped_heads_only_when_explicitly_requested():
    sql = str(_statement(True).compile(dialect=dialect()))
    assert "portfolio_cash_availability_observation_heads" in sql
    assert "portfolio_funding_investment_observation_heads" in sql
    assert "tenant_id =" in sql and "producer_id =" in sql and "source_record_id =" in sql
    assert "ORDER BY" not in sql  # No best-effort latest version guessing.
