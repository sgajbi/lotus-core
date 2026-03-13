# CR-162: Outbox Retry Configurability Review

## Summary

`OutboxDispatcher` enforced terminal failure semantics after CR-155, but the retry ceiling was still a hardcoded module constant and the shared dispatcher's polling and batch policy still lived as constructor defaults. That left banking-critical delivery controls buried inside a shared durable component.

## Findings

- `MAX_RETRIES = 3` lived in `portfolio_common.outbox_dispatcher`.
- shared services instantiate `OutboxDispatcher(...)` without overriding poll or batch size, so the default event-plane throughput policy was effectively hardcoded too.
- The dispatcher is shared by multiple services, so retry policy belongs to the shared component contract rather than one service-local caller.
- The old `BASE_RETRY_DELAY` constant was dead code and provided no real behavior.

## Changes

- Added `OutboxRuntimeSettings` and `get_outbox_runtime_settings(...)`.
- `OutboxDispatcher` now reads:
  - `OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS`
  - `OUTBOX_DISPATCHER_BATCH_SIZE`
  - `OUTBOX_DISPATCHER_MAX_RETRIES`
  when explicit constructor overrides are not provided.
- Constructor-level override remains available for deterministic tests and future targeted service control.
- Removed the dead backoff constant.
- Added unit proof for:
  - default settings
  - env override
  - constructor override precedence
  - runtime-default constructor behavior
- Added DB-backed integration proof that terminal failure behavior respects a non-default retry ceiling.

## Result

Outbox retry policy is now explicit, configurable, and testable instead of hidden as a magic number in a shared runtime path.
