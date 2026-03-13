# CR-162: Outbox Retry Configurability Review

## Summary

`OutboxDispatcher` enforced terminal failure semantics after CR-155, but the retry ceiling was still a hardcoded module constant. That left a banking-critical failure control policy buried as a magic number inside a shared durable component.

## Findings

- `MAX_RETRIES = 3` lived in `portfolio_common.outbox_dispatcher`.
- The dispatcher is shared by multiple services, so retry policy belongs to the shared component contract rather than one service-local caller.
- The old `BASE_RETRY_DELAY` constant was dead code and provided no real behavior.

## Changes

- Added `OutboxRuntimeSettings` and `get_outbox_runtime_settings(...)`.
- `OutboxDispatcher` now reads `OUTBOX_DISPATCHER_MAX_RETRIES` when no explicit constructor override is provided.
- Constructor-level override remains available for deterministic tests and future targeted service control.
- Removed the dead backoff constant.
- Added unit proof for:
  - default settings
  - env override
  - constructor override precedence
- Added DB-backed integration proof that terminal failure behavior respects a non-default retry ceiling.

## Result

Outbox retry policy is now explicit, configurable, and testable instead of hidden as a magic number in a shared runtime path.
