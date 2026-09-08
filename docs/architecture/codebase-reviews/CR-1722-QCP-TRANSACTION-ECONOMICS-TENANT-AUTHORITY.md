# CR-1722: QCP Transaction-Economics Tenant Authority

## Finding

`TransactionCostCurve:v1` and `PerformanceComponentEconomics:v1` accepted an optional body
`tenant_id`, included it in request fingerprints and runtime lineage, but did not bind it to the
admitted `TenantContext`. Their SQL adapter selected portfolios and transactions by globally unique
`portfolio_id` alone. A foreign tenant could therefore read portfolio-owned economics evidence,
and a caller-controlled string could look like source provenance without having scoped a read.

## Financial And Security Invariant

Portfolio-owned transaction economics may be published only from facts belonging to the admitted,
source-owned tenant. A foreign portfolio is indistinguishable from absence. Continuation identity,
content identity and returned lineage use the same admitted tenant that scopes persistence.

## Correction

- The two routes bind the optional body tenant as an assertion. Omission uses admitted authority;
  blank or mismatched assertions fail with HTTP 403 before application or database I/O.
- `TransactionEconomicsService` accepts typed `TenantId` and overwrites the request copy used by
  application policy, page fingerprints and runtime metadata.
- `TransactionEconomicsReader` requires typed tenant authority on every portfolio and transaction
  read.
- The SQL adapter filters direct portfolio reads by `portfolios.tenant_id` and joins every bounded
  transaction-evidence selector to that tenant-owned portfolio.
- Existing economic formulas, exact transaction-date/as-of bounds, cost precedence, latest
  cashflow selection, paging order and response shape remain unchanged.

## Failure Model

| Condition | Result |
| --- | --- |
| Missing admitted tenant | Shared ingress refuses the request. |
| Blank or mismatched body tenant | HTTP 403 before service/database I/O. |
| Absent or foreign portfolio | The same HTTP 404 source-evidence response. |
| Continuation token minted for another tenant | HTTP 400 scope mismatch. |
| Persistence failure | Existing fail-closed transport error; never ready-empty evidence. |

## Scope Decision

This review covers one QCP ownership boundary: transaction-economics evidence. DPM readiness,
simulation, operations, outbox and durable replay/reprocessing state remain separate #798 slices.
Instrument reference, price history and FX-rate routes remain deliberately global source-owned
reference/market-data products; this slice does not add cosmetic portfolio tenancy to them.

## Evidence

- Focused router, application, port, SQL and OpenAPI suites pass.
- Compiled-SQL assertions prove the tenant predicate on direct portfolio, grouped cost-curve and
  paged performance-economics selectors.
- A checkout-specific PostgreSQL test creates portfolios for two tenants and proves owned reads
  succeed while the same portfolio evidence is absent to the foreign tenant for both products.
- Required PR review, exact-head gates, wiki publication and exact-main proof are recorded on #798
  and the delivery PR before closure.
