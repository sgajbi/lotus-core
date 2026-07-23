# CR-1655: Finite Financial Numeric Persistence

## Scope

This review owns GitHub issue #827. It inventories persisted SQLAlchemy `Numeric` columns and
delivers the first bounded database-enforcement slice for transaction and cost-ledger state.

## Finding

PostgreSQL constrained `NUMERIC(18,10)` rejects infinities through its typmod but can persist
`NaN`. PostgreSQL also orders `NaN` above ordinary values, so positive and nonnegative checks do
not establish finiteness. Direct writers, migrations, or repair tools could therefore contaminate
quantity ordering, positive-cost indexes, cost-basis state, reconciliation, and downstream
valuation even when application validation was correct.

The integrated #451 authority adds one unbounded exact-price `NUMERIC`; unlike constrained numeric,
that column can represent all three PostgreSQL special values and therefore requires an explicit
finite check.

## Decision

- `docs/standards/financial-numeric-persistence.v1.json` is the deduplicated ORM inventory and
  classifies 96 columns across 30 tables by nullability and signed, positive, or nonnegative
  semantics.
- V1 records ORM enforcement only. Alembic migration and PostgreSQL integration evidence remain
  the source of database-enforcement truth; V1 cannot be extended with an unsupported
  `database-enforced` claim.
- The first enforcement slice covers 13 transaction/cost-ledger values plus the exact market-price
  source fact. ORM and migration predicates reject `NaN`, `Infinity`, and `-Infinity` independently
  from existing sign/range constraints.
- Migration `c120b2c3d4f9` follows the reconciled #451 `c119` head. It adds each existing-table check
  as `NOT VALID`, then validates retained rows transactionally. Contaminated history fails the
  migration without coercion or partial committed enforcement.
- Domain constructors reject non-finite Decimal values before persistence, including signaling
  NaN. Database constraints remain mandatory protection for non-application writers.

## Compatibility and operational impact

Finite values retain their existing precision, scale, nullability, and sign semantics. No public
API, OpenAPI, event, topic, or runtime ownership contract changes. Invalid non-finite values are no
longer accepted. Validation scans the six affected existing tables and should be scheduled with
normal migration lock monitoring; adding constraints as `NOT VALID` avoids a table rewrite and
blocks new invalid rows before retained-row validation. Each table's constraints are validated in
one statement to avoid repeated validation scans.

The 82 inventory entries still marked `planned` remain explicit #827 closure blockers. They must be
delivered in domain-coherent migrations with direct PostgreSQL acceptance/rejection evidence; this
slice does not imply repository-wide database enforcement.

## Evidence

- machine guard: `python scripts/quality/financial_numeric_persistence_guard.py`
- migration lineage: `python scripts/development/repository_python.py -m alembic heads`
- warning-strict domain, ORM, guard, and migration tests recorded on #827
- isolated PostgreSQL migration proof: `1 passed in 58.81s`, including contaminated-history
  atomic failure, remediation, finite boundaries, downgrade, and reapply
- exact offline DDL compilation proving `NOT VALID` followed by grouped `VALIDATE CONSTRAINT`
- signed commits and independent review evidence recorded on #827 and the delivery PR
