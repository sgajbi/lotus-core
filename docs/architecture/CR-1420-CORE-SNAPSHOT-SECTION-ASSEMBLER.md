# CR-1420 Core Snapshot Section Assembler

## Status

In progress on 2026-07-06.

## Scope

`CoreSnapshotService` response section assembly for GitHub issue #547.

## Finding

`CoreSnapshotService` still owned response section selection and population for baseline positions,
portfolio state, projected positions, delta records, portfolio totals, and snapshot instrument
enrichment. That logic is pure response composition over already-loaded baseline/projected position
maps and does not need portfolio repositories, simulation repositories, market price repositories,
FX repositories, clocks, source metadata assembly, or FastAPI delivery wiring.

Keeping it in the broad service made the section contract harder to test independently from the
full snapshot orchestration path.

## Action

Added `core_snapshot_sections.py` with `build_core_snapshot_sections(...)`. The snapshot service now
passes requested sections, baseline positions, projected positions, and totals to the focused
section assembler. Moved the unavailable-section exception to `core_snapshot_errors.py` so the
assembler can raise the same error type without importing the broad service module.

## Compatibility

No API behavior change is intended. Requested section names, baseline position payloads,
portfolio-state payloads, projected position weight assignment, delta records, portfolio totals,
instrument enrichment fields, unavailable section messages, response DTOs, OpenAPI shape, and
router error mapping are unchanged.

## Remaining Issue Scope

This is a partial issue #547 slice. Further bounded collaborators are still needed for simulation
projection, projected valuation, and repository-backed enrichment before #547 should be marked
fixed-local.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_core_snapshot_sections.py tests\unit\services\query_service\services\test_core_snapshot_service.py tests\unit\services\query_control_plane_service\routers\test_integration_router.py -q
python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_sections.py src\services\query_service\app\services\core_snapshot_errors.py tests\unit\services\query_service\services\test_core_snapshot_sections.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_sections.py src\services\query_service\app\services\core_snapshot_errors.py tests\unit\services\query_service\services\test_core_snapshot_sections.py
python -m mypy src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_sections.py src\services\query_service\app\services\core_snapshot_errors.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
