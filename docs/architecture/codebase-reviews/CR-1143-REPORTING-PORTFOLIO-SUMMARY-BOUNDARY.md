# CR-1143 Reporting Portfolio Summary Boundary

Date: 2026-06-22

## Scope

Portfolio summary response assembly in
`src/services/query_service/app/services/reporting_service.py`.

## Finding

`ReportingService.get_portfolio_summary(...)` mixed required portfolio resolution, default business
date resolution, portfolio/reporting currency normalization, snapshot and cash-account reads,
cash-balance totals, reporting-currency conversion, valuation-status counting, latest snapshot date
selection, total/invested value construction, and API response assembly in one C-ranked API-facing
service method.

Radon reported:

- `ReportingService.get_portfolio_summary`: `C (11)`

## Action Taken

Extracted focused helpers for:

- required portfolio resolution,
- portfolio summary date resolution,
- portfolio/reporting currency normalization,
- cash-balance totals,
- summary market-value and valuation-status rollup,
- summary totals,
- snapshot metadata,
- final response assembly.

The public response shape, repository call order, cash-account sequencing, FX conversion behavior,
and valuation-status semantics remain unchanged.

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
- Result: `ReportingService.get_portfolio_summary` is `A (3)`, and every function/class in
  `reporting_service.py` is A-ranked.

Measured movement:

- `ReportingService.get_portfolio_summary`: `C (11)` -> `A (3)`
- `reporting_service.py`: no B-or-worse functions/classes remain

## Residual Risk

This slice does not change reporting API contracts, OpenAPI, allocation calculation, cash-balance
methodology, FX conversion methodology, or repository query shape. Broader reporting router and
repository hotspots should remain separate measured work if they appear in future scans.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of API-facing portfolio summary assembly,
- separation of totals/metadata calculation from orchestration,
- direct proof through the reporting service behavior suite.

It does not claim full bank-buyable readiness for `lotus-core`.
