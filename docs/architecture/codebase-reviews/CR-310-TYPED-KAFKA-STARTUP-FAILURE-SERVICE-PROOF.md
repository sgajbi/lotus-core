# CR-310 Typed Kafka Startup Failure Service Proof

## Summary

`CR-309` moved Kafka topic verification failure out of library-level `sys.exit(1)` and into a
typed `KafkaTopicVerificationError`, but the startup path still needed a representative service
proof to show the typed failure reaches a real `ConsumerManager` cleanly.

## Why This Matters

Shared infrastructure changes are stronger when there is at least one service-level proof showing
the real startup path behaves correctly, not just a library unit test.

## Change

- added a representative startup-path proof in:
  - `tests/unit/services/valuation_orchestrator_service/unit/test_valuation_orchestrator_consumer_manager_runtime.py`

## What It Proves

- `ensure_topics_exist(...)` can raise `KafkaTopicVerificationError`
- the valuation-orchestrator `ConsumerManager.run()` propagates that typed startup failure
- no runtime tasks are started before the failure
- scheduler and reprocessing-worker stop paths are not falsely exercised on this pre-start failure

## Evidence

- validation:
  - `python -m pytest tests/unit/services/valuation_orchestrator_service/unit/test_valuation_orchestrator_consumer_manager_runtime.py -q`
    - `3 passed`
  - `python -m ruff check tests/unit/services/valuation_orchestrator_service/unit/test_valuation_orchestrator_consumer_manager_runtime.py`
    - passed

## Follow-up

- no need to duplicate this proof across every service unless a service-specific startup path
  diverges. One representative proof is enough for now.
