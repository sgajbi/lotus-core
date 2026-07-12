# CR-1421 Core Snapshot Projected Valuation

## Status

In progress on 2026-07-06.

## Scope

`CoreSnapshotService` simulation projected-position valuation for GitHub issue #547.

## Finding

`CoreSnapshotService` still owned simulation change normalization, missing instrument lookup,
projected position seeding, baseline-value reuse, market price lookup, market-to-portfolio FX
selection, and projected market-value calculation.

That logic is repository-backed projected valuation, not response orchestration. Keeping it inside
the broad service made the simulation path harder to test without full snapshot response assembly.

## Action

Added `core_snapshot_projected_valuation.py` with
`CoreSnapshotProjectedPositionResolver`. The snapshot service now delegates projected-position
resolution to that resolver. Added `core_snapshot_market_data.py` so FX lookup and decimal
validation are shared by currency-context resolution and projected valuation instead of remaining
as service-private helpers.

## Compatibility

No API behavior change is intended. Simulation session usage, simulation change normalization,
new-security instrument lookup, price lookup order, FX reuse per market currency, cash and
zero-quantity filters, missing instrument/price/FX error messages, response DTOs, OpenAPI shape,
and router error mapping are unchanged. `CoreSnapshotUnavailableSectionError` remains importable
from `core_snapshot_service.py` as a compatibility re-export.

## Remaining Issue Scope

This is a partial issue #547 slice. Simulation session validation and repository-backed snapshot
enrichment still need bounded collaborators before #547 should be marked fixed-local.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_core_snapshot_projected_valuation.py tests\unit\services\query_service\services\test_core_snapshot_market_data.py tests\unit\services\query_service\services\test_core_snapshot_projected_positions.py tests\unit\services\query_service\services\test_core_snapshot_sections.py tests\unit\services\query_service\services\test_core_snapshot_service.py -q
python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_market_data.py src\services\query_service\app\services\core_snapshot_projected_valuation.py tests\unit\services\query_service\services\test_core_snapshot_projected_valuation.py tests\unit\services\query_service\services\test_core_snapshot_market_data.py tests\unit\services\query_service\services\test_core_snapshot_service.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_market_data.py src\services\query_service\app\services\core_snapshot_projected_valuation.py tests\unit\services\query_service\services\test_core_snapshot_projected_valuation.py tests\unit\services\query_service\services\test_core_snapshot_market_data.py tests\unit\services\query_service\services\test_core_snapshot_service.py
python -m mypy src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_market_data.py src\services\query_service\app\services\core_snapshot_projected_valuation.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
