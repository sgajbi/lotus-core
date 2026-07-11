from __future__ import annotations

from portfolio_common.database_models import PipelineStageState
from sqlalchemy import select

from src.services.query_service.app.repositories.operations_portfolio_control_queries import (
    apply_portfolio_control_stage_scope,
)


def _compiled_sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_portfolio_control_stage_scope_keeps_optional_filters_absent_by_default() -> None:
    stmt = apply_portfolio_control_stage_scope(
        select(PipelineStageState),
        portfolio_id="PB_SG_GLOBAL_BAL_001",
    )

    compiled = _compiled_sql(stmt)

    assert "pipeline_stage_state.portfolio_id = 'PB_SG_GLOBAL_BAL_001'" in compiled
    assert "pipeline_stage_state.transaction_id LIKE 'portfolio-stage:%'" in compiled
    assert "pipeline_stage_state.id =" not in compiled
    assert "pipeline_stage_state.stage_name =" not in compiled
    assert "pipeline_stage_state.business_date =" not in compiled
    assert "pipeline_stage_state.status =" not in compiled
    assert "pipeline_stage_state.updated_at <=" not in compiled
