# CR-1142 Reporting Allocation Look-Through Boundary

Date: 2026-06-22

## Scope

Reporting asset-allocation look-through row resolution in
`src/services/query_service/app/services/reporting_service.py`.

## Finding

`ReportingService._resolve_allocation_rows(...)` mixed snapshot reporting-value conversion,
normalized parent-security extraction, component-row grouping, decomposable-position detection,
direct-only capability reporting, look-through decomposition, undecomposed non-cash counting, and
supportability metadata assembly in one C-ranked API-facing service helper.

Radon reported:

- `ReportingService._resolve_allocation_rows`: `C (16)`
- `ReportingService._can_decompose_position`: `B (7)`

## Action Taken

Extracted focused helpers for:

- allocation parent-security normalization,
- resolved reporting rows,
- direct allocation rows,
- component grouping by parent,
- direct-only, unsupported, and applied look-through metadata,
- complete component-weight total validation,
- look-through row decomposition,
- component allocation row construction.

The public response shape, direct-only behavior, partial look-through posture, and source-owned
component weight semantics remain unchanged.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\services\test_reporting_service.py -q`
- Result: `20 passed`

Focused static proof:

- `python -m ruff check src/services/query_service/app/services/reporting_service.py tests/unit/services/query_service/services/test_reporting_service.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/query_service/app/services/reporting_service.py tests/unit/services/query_service/services/test_reporting_service.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/query_service/app/services/reporting_service.py -s --exclude "*/build/*"`
- Result: `_resolve_allocation_rows` is `A (3)`, `_can_decompose_position` is `A (2)`, and all
  newly extracted helpers are A-ranked.

Measured movement:

- `ReportingService._resolve_allocation_rows`: `C (16)` -> `A (3)`
- `ReportingService._can_decompose_position`: `B (7)` -> `A (2)`

## Residual Risk

This slice does not change reporting API contracts, allocation DTOs, OpenAPI, cash-balance
resolution, FX conversion, or allocation bucket calculation. `ReportingService.get_portfolio_summary`
remains C-ranked and should be handled as a separate measured reporting summary slice.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of source-owned look-through supportability posture,
- separation of decomposition metadata from row construction,
- direct proof through the existing reporting service behavior suite.

It does not claim full bank-buyable readiness for `lotus-core`.
