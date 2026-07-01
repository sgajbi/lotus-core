# CR-1225 Ingestion Rate-Limit Scope Guard

Date: 2026-07-01

## Objective

Continue fixing GitHub issue #684 by turning the ingestion write rate-limit scope contract into a
deterministic CI guard. CR-1196 made the runtime contract explicit; this slice prevents future code
or documentation drift from claiming global scaled-service enforcement while the default limiter is
still local-process state.

## Change

- Added `scripts/ingestion_rate_limit_scope_guard.py`.
- Added `make ingestion-rate-limit-scope-guard` and wired it into `make lint`.
- Added guard tests for:
  - current repository truth passing,
  - missing required local/global documentation anchors failing,
  - `local_process` runtime contracts incorrectly claiming global enforcement failing.
- The guard validates:
  - the default runtime contract does not claim global enforcement,
  - local and gateway-backed scope sets match the governed contract,
  - operations docs and quality evidence keep the required local-process and upstream-gateway
    language.

## Expected Improvement

The rate-limit abuse-protection contract is now regression-blocked instead of relying on reviewers
to remember the scaled deployment caveat. Future changes can still add a gateway-backed or
shared-store global limiter, but they cannot silently reword the local limiter as a global
production control.

## Tests Added

- Unit coverage for the guard accepting current truth.
- Unit coverage for documentation-anchor drift.
- Unit coverage for a local-process runtime contract that incorrectly claims global enforcement.

## Validation Evidence

- Focused guard tests passed with 3 tests:
  `python -m pytest tests\unit\scripts\test_ingestion_rate_limit_scope_guard.py -q`.
- `make ingestion-rate-limit-scope-guard` passed.
- Scoped Ruff formatting and lint checks passed for the new guard and tests.
- `make lint` passed, including the new `ingestion-rate-limit-scope-guard` target.
- `make typecheck` passed.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed.

## Downstream Compatibility

This is a CI/documentation contract guard only. It does not change ingestion route behavior, HTTP
status mapping, request or response DTOs, rate-limit budgets, default local-process enforcement,
gateway-backed startup validation, metrics, logs, database schema, Kafka topics, or runtime
deployment topology.

## Documentation And Wiki Decision

This architecture record, codebase review ledger, ingestion operations runbook, repository context,
quality scorecard, and refactor health report were updated because a new repo-native guard changed
development and CI truth. No repo-local wiki update is required because ingestion rate-limit
operator truth is authored in `docs/operations/ingestion-api-gold-standard.md`, not in wiki source.

## Remaining Follow-Up

- Keep issue #684 open for PR/CI/QA evidence and platform-ingress validation of the concrete
  gateway policy.
- Consider a Redis/shared-store token bucket if Lotus chooses service-owned global enforcement
  instead of gateway-owned enforcement.
