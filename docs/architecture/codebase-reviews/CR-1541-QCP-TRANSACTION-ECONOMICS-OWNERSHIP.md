# CR-1541: QCP Transaction Economics Ownership

## Status

Reconciled candidate on 2026-07-12. GitHub issue #715 remains open until all QCP package dependencies
are removed and the clean image passes startup and runtime proof.

## Objective

Move `TransactionCostCurve:v1` and `PerformanceComponentEconomics:v1` from a QCP route over a Query
Service facade to complete QCP ownership without changing route paths, request fields, response
fields, paging keys, formulas, error mapping, or downstream responsibility boundaries.

## Architecture

The implemented flow is:

`QCP route -> API contract -> TransactionEconomicsService -> domain policy ->
TransactionEconomicsReader -> SqlAlchemyTransactionEconomicsReader -> database`

The capability owns:

1. public transaction-cost and performance-economics contracts under `app/contracts`;
2. frozen booked-transaction, linked-cashflow, and cost-component evidence under `app/domain`;
3. keyset paging, fee identity, row mapping, totals, supportability, and response assembly under
   `app/application/transaction_economics`;
4. a narrow source-reader and page-token port under `app/ports`;
5. grouped curve-key reads, bounded transaction evidence, requested-security coverage, latest
   cashflow epoch selection, and ORM mapping under `app/infrastructure`.

Query Service no longer owns transaction-economics DTOs, read records, policies, facade methods,
repository methods, compatibility exports, or duplicate tests.

## Correctness And Runtime Improvement

The SQL adapter preserves grouped keyset selection and `page_size + 1` reads, so the move does not
reintroduce full-window materialization. Application policy consumes immutable Decimal-based domain
evidence instead of permissive ORM-shaped objects. Both products now use an injected UTC clock and
emit source-owned deterministic SHA-256 content hash, digest, source-batch fingerprint, source
reference, lineage, and freshness. `generated_at` is excluded from the evidence hash.

## Compatibility

The two HTTP paths, request and response schemas, validation rules, grouping keys, component totals,
supportability states, page-token scope, HTTP 400/404 problem details, and product identities are
preserved. Populating previously default proof metadata is an intentional additive evidence
improvement. Core still does not claim market-impact prediction, execution quality, best execution,
performance contribution or attribution, returns, or tax advice.

## Validation

- complete Query Service/QCP unit and QCP integration suite: `1757 passed`
- affected ownership and retirement suite: `250 passed`
- QCP router, dependency, and OpenAPI suite: `170 passed`
- old/new SQL contract parity suite: `43 passed`
- old/new economics policy parity suite: `64 passed`
- strict MyPy passed across contracts, domain, ports, application, adapter, dependencies, router,
  and touched Query Service files
- Ruff lint/format and architecture, domain, application, port, adapter, route, source-product,
  problem-details, and mapping anti-corruption guards passed

## Downstream Impact

No consumer migration is required because route paths and schemas are preserved. Downstream clients
may now validate deterministic source proof metadata instead of receiving unavailable defaults.

## Remaining Work

Issue #715 remains open. DPM readiness, benchmark/market products, operations/support, and advisory
compatibility still create Query Service imports in the QCP package and must be migrated or
intentionally consolidated before clean-image closure can be claimed.
