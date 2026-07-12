# CR-087 Stale Control Epoch Emission Review

## Scope

- `src/services/pipeline_orchestrator_service/app/services/pipeline_orchestrator_service.py`
- `src/services/pipeline_orchestrator_service/app/repositories/pipeline_stage_repository.py`
- `tests/unit/services/pipeline_orchestrator_service/services/test_pipeline_orchestrator_service.py`
- `tests/integration/services/pipeline_orchestrator_service/test_int_pipeline_stage_repository.py`

## Finding

The `FINANCIAL_RECONCILIATION` control-stage storage model was already monotonic within an
epoch and the read path correctly resolved the latest control row by
`business_date desc, epoch desc`.

The remaining gap was at event emission time: an older reconciliation completion could still
publish a `PortfolioDayControlsEvaluated` event for an outdated epoch after a newer epoch
already existed for the same `(portfolio_id, business_date, stage_name)` scope.

That would not corrupt the durable stage row, but it could still emit a semantically stale
control outcome onto the bus.

## Change

- Added `get_latest_portfolio_control_stage_epoch(...)` to `PipelineStageRepository`
- Hardened `PipelineOrchestratorService.register_portfolio_day.reconciliation.completed(...)`
  to suppress control-event emission when the just-updated epoch is not the latest epoch
  for that portfolio-day control stage
- Added:
  - unit coverage proving an older epoch completion does not emit a stale control event
  - integration coverage proving latest-epoch resolution returns the highest epoch

## Result

Control-stage behavior is now correct at both layers:

- storage stays monotonic within an epoch
- stale older-epoch completions no longer emit misleading control events once a newer epoch
  exists

## Evidence

- `python -m pytest tests/unit/services/pipeline_orchestrator_service/services/test_pipeline_orchestrator_service.py tests/integration/services/pipeline_orchestrator_service/test_int_pipeline_stage_repository.py -q`
  - `14 passed`
