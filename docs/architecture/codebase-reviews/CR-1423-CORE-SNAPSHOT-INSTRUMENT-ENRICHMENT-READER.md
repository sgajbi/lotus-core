# CR-1423 Core Snapshot Instrument Enrichment Reader

## Status

Fixed-local candidate on 2026-07-06.

## Scope

`CoreSnapshotService` repository-backed instrument enrichment lookup for GitHub issue #547.

## Finding

`CoreSnapshotService` still owned the instrument enrichment bulk read path: request identifier
normalization, empty-request rejection, instrument repository lookup, and DTO mapping delegation.
Pure enrichment mapping already lived in `core_snapshot_instrument_enrichment.py`, but the
repository-backed read contract still remained in the broad service.

## Action

Added `core_snapshot_instrument_enrichment_reader.py` with
`CoreSnapshotInstrumentEnrichmentReader`. `CoreSnapshotService.get_instrument_enrichment_bulk(...)`
is now a compatibility delegate to that reader. Moved repository-backed enrichment tests from the
broad service to the reader boundary.

## Compatibility

No API behavior change is intended. Security-id normalization, empty-request rejection message,
instrument repository call shape, output order, unknown-instrument placeholder records, returned
issuer/liquidity fields, router error mapping, response DTOs, and OpenAPI shape are unchanged.

## Issue Closure Impact

This completes the local issue #547 collaborator split when combined with CR-1416 through CR-1422:
delivery dependency wiring, governance, identity/fingerprint, quality classification, section
assembly, projected valuation, simulation validation, and repository-backed enrichment are now
bounded collaborators rather than direct `CoreSnapshotService` responsibilities.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_core_snapshot_instrument_enrichment_reader.py tests\unit\services\query_service\services\test_core_snapshot_instrument_enrichment.py tests\unit\services\query_service\services\test_core_snapshot_service.py tests\unit\services\query_control_plane_service\routers\test_integration_router.py -q
python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_instrument_enrichment.py src\services\query_service\app\services\core_snapshot_instrument_enrichment_reader.py tests\unit\services\query_service\services\test_core_snapshot_instrument_enrichment_reader.py tests\unit\services\query_service\services\test_core_snapshot_service.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_instrument_enrichment.py src\services\query_service\app\services\core_snapshot_instrument_enrichment_reader.py tests\unit\services\query_service\services\test_core_snapshot_instrument_enrichment_reader.py tests\unit\services\query_service\services\test_core_snapshot_service.py
python -m mypy src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_instrument_enrichment.py src\services\query_service\app\services\core_snapshot_instrument_enrichment_reader.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
