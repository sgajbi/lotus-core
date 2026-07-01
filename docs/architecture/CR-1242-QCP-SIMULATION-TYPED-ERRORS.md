# CR-1242 QCP Simulation Typed Errors

Date: 2026-07-01

## Objective

Continue GitHub issue #677 by removing the remaining simulation-router dependence on exception
message text when mapping query-control-plane failures to problem-details responses.

## Change

- Added typed `SimulationServiceError` subclasses for missing portfolio, missing session, missing
  simulation change, and invalid mutation conditions.
- Kept the simulation service exceptions compatible with existing `ValueError` callers while
  giving API routers a stable type taxonomy.
- Replaced router substring checks over exception text with type-based mappings to
  `QCP_SIMULATION_RESOURCE_NOT_FOUND`, `QCP_SIMULATION_MUTATION_INVALID`, and existing simulation
  not-found problem-details responses.
- Updated unit and query-control-plane integration tests to assert the typed exception contract.

## Expected Improvement

The simulation control-plane path no longer classifies API failures by parsing human-readable
messages such as "not found". Future wording changes in the service layer are less likely to break
HTTP status selection, problem-details error codes, or support metadata, and the issue #677
pattern now has both a static guard and a reusable service-error taxonomy pattern.

## Tests Added Or Updated

- `tests/unit/services/query_service/services/test_simulation_service.py`
- `tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py`

## Validation Evidence

- `python -m pytest tests/unit/services/query_service/services/test_simulation_service.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py -q --tb=short`
  - `49 passed`
- `make qcp-problem-details-guard`
  - `QCP problem-details guard passed.`
- `python -m ruff check src/services/query_service/app/services/simulation_service.py src/services/query_control_plane_service/app/routers/simulation.py tests/unit/services/query_service/services/test_simulation_service.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py`
  - `All checks passed!`
- `python -m mypy --config-file mypy.ini src/services/query_service/app/services/simulation_service.py src/services/query_control_plane_service/app/routers/simulation.py`
  - `Success: no issues found in 2 source files`

## Downstream Compatibility

Route paths, HTTP statuses, problem-details error codes, success DTOs, request DTOs, OpenAPI
success contracts, database schema, persistence behavior, Kafka topics, and source-data envelopes
are preserved. The intentional internal change is that simulation service failures now carry typed
exception classes; they still subclass `ValueError` for existing direct callers.

## Documentation And Wiki Decision

Updated this architecture record, the codebase review ledger, quality scorecard, refactor health
report, and repository context. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Keep `make qcp-problem-details-guard` enforced for active query-control-plane routers.
- Apply the typed service-error pattern to future QCP route families instead of message-text
  inspection.
