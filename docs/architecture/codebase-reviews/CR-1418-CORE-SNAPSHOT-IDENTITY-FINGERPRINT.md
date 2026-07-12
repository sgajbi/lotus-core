# CR-1418 Core Snapshot Identity Fingerprint

## Status

In progress on 2026-07-06.

## Scope

`CoreSnapshotService` request identity and fingerprint construction for GitHub issue #547.

## Finding

`CoreSnapshotService` still owned canonical request identity construction and request fingerprint
payload assembly. This logic is pure request/governance canonicalization and does not need portfolio
repositories, pricing, FX, simulation, enrichment, or response assembly dependencies.

Keeping it in the broad service increased design-time complexity and made fingerprint behavior less
directly testable as a reusable snapshot contract concern.

## Action

Added `core_snapshot_identity.py` with `core_snapshot_identity_command_from_request(...)` and
`core_snapshot_request_fingerprint(...)`. The snapshot service now calls the focused identity
collaborator when building response metadata.

Updated the application command/result guard so canonical Core snapshot command usage is enforced in
`core_snapshot_identity.py` while the broad service remains protected from shortcut
`request.model_dump(mode="json")` fingerprint construction.

## Compatibility

No API behavior change is intended. Canonical request payload shape, request fingerprint semantics,
governance-sensitive fingerprint inputs, response DTOs, source metadata, OpenAPI shape, and error
behavior are unchanged.

## Remaining Issue Scope

This is a partial issue #547 slice. Further bounded collaborators are still needed for simulation
projection, projected valuation, section assembly, and enrichment before #547 should be marked
fixed-local.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_core_snapshot_identity.py tests\unit\services\query_service\services\test_core_snapshot_governance.py tests\unit\services\query_service\services\test_core_snapshot_service.py -q
python -m pytest tests\unit\scripts\test_application_command_result_guard.py tests\unit\services\query_service\services\test_core_snapshot_identity.py tests\unit\services\query_service\services\test_core_snapshot_governance.py tests\unit\services\query_service\services\test_core_snapshot_service.py -q
python scripts\application_command_result_guard.py
python -m ruff check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_identity.py tests\unit\services\query_service\services\test_core_snapshot_identity.py --ignore E501,I001
python -m ruff check scripts\application_command_result_guard.py tests\unit\scripts\test_application_command_result_guard.py src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_identity.py tests\unit\services\query_service\services\test_core_snapshot_identity.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_identity.py tests\unit\services\query_service\services\test_core_snapshot_identity.py tests\unit\services\query_service\services\test_core_snapshot_service.py
python -m ruff format --check scripts\application_command_result_guard.py tests\unit\scripts\test_application_command_result_guard.py src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_identity.py tests\unit\services\query_service\services\test_core_snapshot_identity.py tests\unit\services\query_service\services\test_core_snapshot_service.py
python -m mypy src\services\query_service\app\services\core_snapshot_service.py src\services\query_service\app\services\core_snapshot_identity.py scripts\application_command_result_guard.py
make architecture-guard
make quality-wiki-docs-gate
make lint
git diff --check
```
