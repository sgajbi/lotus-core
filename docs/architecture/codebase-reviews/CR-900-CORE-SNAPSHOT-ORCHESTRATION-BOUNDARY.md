# CR-900: Core Snapshot Orchestration Boundary

Date: 2026-06-04

## Scope

Reduce `CoreSnapshotService.get_core_snapshot` complexity without changing public service methods,
repository reads, simulation validation semantics, requested section behavior, governance metadata,
request fingerprinting, or response DTOs.

## Finding

`CoreSnapshotService.get_core_snapshot` was an E-ranked method mixing portfolio lookup, currency
and FX context resolution, baseline position reads, simulation session validation, projected
position resolution, requested section population, governance metadata resolution, request
fingerprinting, data-quality classification, and response construction.

The method sits inside `core_snapshot_service.py`, which remains a C-ranked maintainability
hotspot. The immediate risk was that a single high-complexity orchestration block owned too many
independent snapshot policies.

## Action

Extracted focused private helpers inside `core_snapshot_service.py`:

- `_snapshot_currency_context(...)` resolves portfolio/reporting currency and reporting FX.
- `_snapshot_projection(...)` owns simulation-vs-baseline projection orchestration.
- `_validated_simulation_session(...)` owns simulation session validation.
- `_validate_baseline_snapshot_sections(...)` owns baseline-mode section rejection.
- `_populate_requested_snapshot_sections(...)` delegates requested section population.
- `_populate_projected_positions_section(...)`, `_populate_delta_section(...)`,
  `_populate_portfolio_totals_section(...)`, and `_populate_instrument_enrichment_section(...)`
  own section-specific response assembly.
- `_snapshot_governance_resolution(...)`, `_build_core_snapshot_response(...)`, and
  `_core_snapshot_request_fingerprint(...)` own governance metadata and response construction.

## Result

`CoreSnapshotService.get_core_snapshot` now reports `A (4)` instead of `E (39)` under Radon
cyclomatic complexity. The newly extracted orchestration helpers report A-ranked complexity.

`core_snapshot_service.py` still reports `C (0.00)` under Radon maintainability, and the source
C-hotspot count remains 7. This is a material orchestration complexity reduction, not final
closure for the core snapshot service.

## Evidence

Validation commands:

- `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  => `44 passed`
- `python -m ruff check src\services\query_service\app\services\core_snapshot_service.py`
- `python -m ruff format src\services\query_service\app\services\core_snapshot_service.py`
- `python -m radon cc src\services\query_service\app\services\core_snapshot_service.py -s`
- `python -m radon mi src\services\query_service\app\services\core_snapshot_service.py -s`
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`

No integration selection was run for this slice. The change is an internal service-helper
extraction covered by focused core snapshot unit tests.

## Wiki Decision

No wiki source update is required. This is an internal service-helper refactor and does not change
an operator-facing contract, API contract, or runbook.
