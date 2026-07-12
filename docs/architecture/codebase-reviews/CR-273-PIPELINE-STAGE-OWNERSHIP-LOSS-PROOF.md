# CR-273 Pipeline Stage Ownership-Loss Proof

## Summary

The pipeline orchestrator already gated downstream completion events behind
`mark_stage_completed_if_pending(...)`, but we still lacked DB-backed proof that a late ownership
loss would suppress the outbox side effects too.

## Finding

- Class: concurrency correctness risk
- Consequence: without an integration proof, the pipeline transaction-processing stage still relied
  on repository-level idempotency confidence for the guarantee that a late caller does not publish
  `TransactionProcessingCompleted` and `PortfolioDayReadyForValuation` after another owner already
  completed the stage.

## Action Taken

- added an integration proof in
  `tests/integration/services/pipeline_orchestrator_service/test_int_pipeline_orchestrator_service.py`
- used a second database session to mark the same transaction-processing stage `COMPLETED`
  immediately before the real `mark_stage_completed_if_pending(...)` executes
- exercised the real `PipelineOrchestratorService` with the real repository and outbox repository
- proved that the late caller then:
  - emits no `TransactionProcessingCompleted` outbox event
  - emits no `PortfolioDayReadyForValuation` outbox event
  - leaves the durable stage row completed by the competing owner

## Evidence

- `python -m pytest tests/integration/services/pipeline_orchestrator_service/test_int_pipeline_orchestrator_service.py -q`
  - `1 passed`
- `python -m ruff check tests/integration/services/pipeline_orchestrator_service/test_int_pipeline_orchestrator_service.py`
  - passed

## Follow-up

- keep checking higher-level control-plane flows for any remaining path that can still emit durable
  follow-on events after stage ownership is lost
