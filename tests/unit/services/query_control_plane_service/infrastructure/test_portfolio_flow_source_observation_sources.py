"""Exact JSON pins and receipt joins execute in one bounded source statement."""

import pytest
from sqlalchemy.dialects.postgresql import dialect

from src.services.query_control_plane_service.app.contracts import (
    portfolio_flow_source_observations as flow_contracts,
)
from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_flow_source_observation_sources as flow_sources,
)
from tests.test_support.portfolio_flow_source_fixtures import cut

pytestmark = pytest.mark.unit


def test_single_statement_scopes_every_pin_and_completed_receipt():
    manifest = cut()
    request = flow_contracts.PortfolioFlowObservationsRequest.model_validate(
        {
            "source_system": manifest.source_system,
            "source_cut_id": manifest.source_cut_id,
            "cut_revision": 1,
            "manifest_hash": manifest.content_hash,
            "currency": "SGD",
            "window": {"from_date": "2026-01-01", "to_date": "2026-01-31"},
            "page": {"page_size": 100},
        }
    )
    sql = str(
        flow_sources.flow_cut_snapshot_statement(
            tenant_id=manifest.tenant_id, portfolio_id=manifest.portfolio_id, request=request
        ).compile(dialect=dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "LATERAL jsonb_array_elements" in sql
    assert "->> 'observation_id'" in sql and "->> 'content_hash'" in sql
    assert "->> 'flow_source_record_revision'" in sql and "->> 'source_record_id'" in sql
    assert sql.count("completed_at IS NOT NULL") == 2
    assert (
        "portfolio_flow_event_observations.tenant_id = portfolio_flow_source_cuts.tenant_id" in sql
    )
    assert (
        "portfolio_flow_event_observations.portfolio_id = portfolio_flow_source_cuts.portfolio_id"
        in sql
    )
    assert (
        "portfolio_flow_event_observations.producer_id = portfolio_flow_source_cuts.source_system"
        in sql
    )
    assert "observation_heads" not in sql
