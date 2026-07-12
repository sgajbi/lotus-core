# CR-1422 Core Snapshot Simulation Validation

## Status

In progress on 2026-07-06.

## Scope

`CoreSnapshotService` simulation option and session validation for GitHub issue #547.

## Finding

`CoreSnapshotService` still owned simulation request-option checks, simulation session lookup,
portfolio ownership validation, expected-version validation, and baseline-mode section validation.
Those checks are simulation contract validation and do not need response assembly, source metadata,
pricing, FX, enrichment, clocks, or delivery wiring.

The Core snapshot error classes also lived in the broad service, which forced new collaborators to
depend on that service module or define parallel exceptions.

## Action

Added `core_snapshot_simulation_validation.py` with
`CoreSnapshotSimulationSessionValidator`. Moved Core snapshot error classes to
`core_snapshot_errors.py` and kept compatibility re-exports from `core_snapshot_service.py` for
existing router and test imports.

## Compatibility

No API behavior change is intended. Simulation option requirements, not-found behavior, portfolio
mismatch behavior, expected-version mismatch behavior, baseline-mode projected/delta rejection,
HTTP router error mapping, exception messages, response DTOs, and OpenAPI shape are unchanged.

## Remaining Issue Scope

This is a partial issue #547 slice. Repository-backed snapshot enrichment still needs a bounded
collaborator before #547 should be marked fixed-local.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_core_snapshot_simulation_validation.py tests\unit\services\query_service\services\test_core_snapshot_service.py tests\unit\services\query_control_plane_service\routers\test_integration_router.py -q
python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_errors.py src\services\query_service\app\services\core_snapshot_simulation_validation.py tests\unit\services\query_service\services\test_core_snapshot_simulation_validation.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_errors.py src\services\query_service\app\services\core_snapshot_simulation_validation.py tests\unit\services\query_service\services\test_core_snapshot_simulation_validation.py
python -m mypy src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_errors.py src\services\query_service\app\services\core_snapshot_simulation_validation.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
