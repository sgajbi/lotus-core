# CR-027 Financial Reconciliation Swagger Depth Review

## Scope

Raise `financial_reconciliation_service` from baseline OpenAPI compliance to a
more audit-ready Swagger contract.

## Finding

The service already passed the OpenAPI quality gate, but the quality depth was
uneven:

- operation-level examples were present
- field-level schema descriptions were incomplete
- parameter documentation for headers and filters was thinner than the DTO
  examples implied
- not-found response behavior existed in runtime, but was not documented in the
  route contract

## Action Taken

1. Added field-level descriptions and examples across:
   - `ReconciliationRunRequest`
   - `ReconciliationRunResponse`
   - `ReconciliationFindingResponse`
   - list response wrappers
2. Added explicit documentation for:
   - `X-Correlation-ID` header
   - reconciliation list filters
   - `limit`
3. Added explicit `404` response documentation for
   `GET /reconciliation/runs/{run_id}`.
4. Added an OpenAPI integration test that asserts the schema exposes the richer
   descriptions and examples.

## Result

The reconciliation API now documents:

- what each field means
- what values look like
- what the primary error path returns

That makes Swagger materially more usable for operators and downstream
integrators.

## Evidence

- `src/services/financial_reconciliation_service/app/dtos.py`
- `src/services/financial_reconciliation_service/app/routers/reconciliation.py`
- `tests/integration/services/financial_reconciliation_service/test_financial_reconciliation_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
