# CR-190: Reprocessing Key Support Listing Review

## Problem

The support plane exposed replay pressure only as an aggregate count on the portfolio overview.
Operators could see `active_reprocessing_keys`, but they could not inspect the durable
`position_state` rows that actually define replay scope, current epoch, watermark date, and stale
reprocessing status.

That forced support tooling to infer replay truth indirectly from:

- aggregate counters
- lineage endpoints scoped to a single `(portfolio_id, security_id)` key
- database inspection outside the supported control plane

For a banking system, that is too weak. Durable replay keys are first-class operational state and
must be inspectable through the same support plane as valuation jobs, aggregation jobs, analytics
exports, and reconciliation runs.

## Review Decision

Add a first-class support listing for durable replay keys:

- `GET /support/portfolios/{portfolio_id}/reprocessing-keys`

The listing must:

- be fenced by `portfolio_id`
- support pagination
- support optional filtering by replay status and security id
- expose current epoch and watermark date
- expose derived stale reprocessing truth
- expose a server-owned operator-facing lifecycle state

## Changes

### DTO contract

Added:

- `ReprocessingKeyRecord`
- `ReprocessingKeyListResponse`

These schemas expose:

- `security_id`
- `epoch`
- `watermark_date`
- `status`
- `updated_at`
- `is_stale_reprocessing`
- `operational_state`

### Repository

Added support queries in `OperationsRepository`:

- count query with optional status/security filters
- paged listing query ordered by replay severity first:
  - stale reprocessing
  - active reprocessing
  - current
  - then oldest updates and stable key ordering

### Service

Added `OperationsService.get_reprocessing_keys(...)`.

The service now computes:

- `is_stale_reprocessing`
- `operational_state`

using the same stale-threshold policy already applied to support job freshness.

### Router / OpenAPI

Added the control-plane endpoint to `query_control_plane_service` and extended OpenAPI contract
tests to verify:

- parameter descriptions
- 404 response example
- component schema depth for the new support response

## Why this is better

- Replay key state is now a first-class support object instead of hidden durable state.
- Operators no longer need to reverse-engineer replay scope from aggregates.
- Replay support semantics now match the rest of the operations surface:
  - valuation jobs
  - aggregation jobs
  - analytics export jobs
  - reconciliation runs
  - control stages

## Evidence

- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_control_plane_service/app/routers/operations.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`

Validation executed:

- targeted unit + integration support pack: `103 passed`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
- touched-surface `ruff check`
- touched-surface `ruff format --check`
