# CR-1125 Performance Economics Component Family Boundary

Date: 2026-06-21

## Scope

Performance component economics supportability coverage in
`src/services/query_service/app/services/performance_component_economics.py`.

## Finding

`PerformanceComponentEconomics:v1` had a real core-owned source contract after CR-1124, but the
component-family coverage helper still concentrated eight independent source-signal predicates in
one branch-heavy function:

- `_observed_component_families`: `C (18)`

That helper drives the `observed_component_families` supportability signal used to prove whether
cashflow, fee, income, tax, realized P&L, and FX-context evidence exists in the returned source
rows. Keeping those rules inline made the new source product harder to review and easier to regress.

## Action Taken

Split component-family detection into:

- a stable ordered collector for the published component-family list,
- one row-level family collector,
- focused predicates for cashflow, fee, income, tax, realized capital P&L, realized FX P&L,
  realized total P&L, and FX context.

The public API response shape, source-contract version, query-control-plane route, DTOs, OpenAPI
schema, source-data catalog, and downstream integration contract remain unchanged.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\services\test_performance_component_economics.py -q`
- Result: `5 passed`

Focused static proof:

- `python -m ruff check src\services\query_service\app\services\performance_component_economics.py tests\unit\services\query_service\services\test_performance_component_economics.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\query_service\app\services\performance_component_economics.py -s`
- Result: `_observed_component_families` reduced from `C (18)` to `A (4)`;
  `_observed_row_component_families` reports `A (3)` and all new predicates report `A (1)` or
  `A (2)`.

Focused maintainability proof:

- `python -m radon mi src\services\query_service\app\services\performance_component_economics.py -s`
- Result: module maintainability remains A-ranked and improves from `A (27.59)` to `A (27.86)`.

## Residual Risk

This slice is intentionally internal. It does not add new component families, change supported
feature truth, alter the `lotus-performance` follow-up need, or claim source-backed downstream
contribution analytics readiness. Remaining local hotspots in the same module include
`_transaction_fee_components`, `_performance_component_economics_row`,
`build_performance_component_economics_response`, and
`build_performance_component_economics_totals`.

## Bank-Buyable Control Movement

This slice improves:

- reviewable supportability semantics for a cross-app source product,
- explicit domain predicates for each published component-family coverage signal,
- focused regression evidence for the existing source-product behavior.

It does not claim full bank-buyable readiness for `lotus-core`.
