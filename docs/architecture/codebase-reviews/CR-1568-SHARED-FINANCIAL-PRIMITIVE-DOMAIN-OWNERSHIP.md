# CR-1568: Shared Financial Primitive Domain Ownership

## Objective

Give reusable cost-basis vocabulary, analytics cashflow semantics, currency normalization, and
decimal amount policy an explicit framework-independent owner, while keeping service-specific
acceptance and persistence expressions at their owning layers.

## Finding

The four policies were legitimate cross-service dependencies, but their flat placement at the
`portfolio_common` root made the shared distribution look like an unbounded utility bucket.
Query Service also kept strict decimal acceptance under `app/services` and mixed reusable currency
normalization with SQL expressions under one repository module. Moving the source files without
their active coverage contract left `critical-path-coverage.v1.json` naming the deleted
`portfolio_common/cost_basis.py` path.

The same-pattern scan found no other live Python import of the four retired roots. Historical CR
records still name paths that existed when their evidence was produced and remain archival truth.

## Change

1. Moved cost-basis method, currency, decimal amount, and analytics cashflow policy under
   `portfolio_common.domain`, with a dedicated analytics subpackage.
2. Migrated ingestion, persistence, transaction processing, Query Service, QCP, valuation,
   reconciliation, aggregation, timeseries, event, and shared-policy consumers directly to the
   canonical owners.
3. Moved Query Service strict decimal policy into `app/domain` and isolated SQL currency
   expressions in repository infrastructure.
4. Removed the four root compatibility modules and guarded both retired imports and framework
   dependencies inside `portfolio_common.domain`.
5. Rejected non-finite decimal values consistently at shared, Query Service, and QCP boundaries.
6. Updated risk-based and critical-path coverage contracts to the canonical source and test paths.

## Compatibility

No HTTP route, request or response schema, OpenAPI contract, event schema, database schema, topic,
deployment topology, rounding rule, or supported financial calculation changed. Existing currency
canonicalization and valid finite Decimal behavior are preserved. `NaN`, positive infinity, and
negative infinity are intentionally rejected instead of entering financial calculations.

The deleted Python roots were repository-internal compatibility paths. All tracked production and
test consumers were migrated in the same batch.

## Validation

- canonical shared-domain, Query Service, QCP, repository, and ownership proof: `104 passed`;
- affected transaction-processing cost workflow proof: `34 passed`;
- integration-lite: `136 passed`;
- database unit gate: `10 passed`;
- risk-based and critical-path coverage guards: passed;
- strict MyPy over the configured source set: passed;
- complete architecture guard and documentation gate: passed;
- repository-wide Ruff and final diff checks: passed before commit.

## Documentation Decision

Repository context and architecture review evidence changed because code-placement truth changed.
README, OpenAPI, API inventory, supported-features material, and wiki source require no change
because no external capability, request shape, deployment, or operator workflow changed.
