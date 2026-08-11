"""Guard tenant isolation and bounded SQL for corporate-action support reads."""

from sqlalchemy.dialects import postgresql

from src.services.query_control_plane_service.app.infrastructure.corporate_action_support_reader import (  # noqa: E501
    _current_projection,
)


def test_projection_is_exact_scope_bounded_and_never_scans_members() -> None:
    statement = _current_projection(
        tenant_id="TENANT-SG",
        legal_book_id="PB-SG-01",
        portfolio_id="PORT-001",
        corporate_action_event_id="CA-EVENT-001",
        readiness_status="READY",
        execution_status="PROCESSING",
    ).order_by(None)
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "corporate_action_events.tenant_id = 'TENANT-SG'" in sql
    assert "corporate_action_events.legal_book_id = 'PB-SG-01'" in sql
    assert "corporate_action_events.portfolio_id = 'PORT-001'" in sql
    assert "corporate_action_events.corporate_action_event_id = 'CA-EVENT-001'" in sql
    assert "corporate_action_events.readiness_status = 'READY'" in sql
    assert "corporate_action_execution_releases.status = 'PROCESSING'" in sql
    assert "corporate_action_execution_members" not in sql
    assert "manifest_payload" not in sql
    assert "ordered_transaction_ids AS" not in sql
    assert "findings AS" not in sql
    assert "jsonb_array_length" in sql
    assert "jsonb_path_query_array" in sql
    assert "CURRENT_TIMESTAMP" in sql or "now()" in sql
