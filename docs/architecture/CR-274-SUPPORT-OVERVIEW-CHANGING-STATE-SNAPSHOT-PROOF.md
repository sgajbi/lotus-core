# CR-274 Support Overview Changing-State Snapshot Proof

## Summary

The support overview now carries extensive snapshot fencing, but we still lacked a DB-backed proof
that one real response stays coherent when newer business dates, epoch state, control stages,
reconciliation runs, and reconciliation findings already exist in durable storage by the time the
call finishes. That proof also exposed a real production bug: the service assumed
`PipelineStageState.failure_reason` existed on the durable control-stage model when it does not.

## Finding

- Class: support/control snapshot correctness risk
- Consequence: without an integration proof, the support overview still relied on layered unit and
  repository confidence for its strongest promise: one response should describe one coherent durable
  moment, even while adjacent control state keeps moving.

## Action Taken

- added an integration proof in
  `tests/integration/services/query_service/test_int_operations_service.py`
- fixed the service snapshot time at one durable instant
- fixed `OperationsService.get_support_overview(...)` to treat
  `controls_failure_reason` as optional against the real `PipelineStageState` model via `getattr(...)`
- seeded:
  - a later business date created after the response snapshot
  - a later portfolio epoch state updated after the response snapshot
  - a later financial-reconciliation control stage updated after the response snapshot
  - a later reconciliation run for the same portfolio-day and epoch updated after the control
    anchor
  - a later blocking finding for the older run created after that same control anchor
- proved that one real `get_support_overview(...)` response still returns:
  - the older business date
  - the older current epoch
  - the older control stage
  - the older linked reconciliation run
  - only the older finding summary
  - and no longer crashes when the real control-stage row has no `failure_reason` attribute

## Evidence

- `python -m pytest tests/integration/services/query_service/test_int_operations_service.py -q`
  - `1 passed`
- `python -m ruff check tests/integration/services/query_service/test_int_operations_service.py`
  - passed

## Follow-up

- keep adding DB-backed characterization where support summaries combine multiple “latest” reads,
  especially if later runtime changes can still create parent-child drift inside one response
