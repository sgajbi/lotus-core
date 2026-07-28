# CR-1655: Finite Financial Numeric Persistence

## Scope

This review owns GitHub issue #827. It inventories every persisted SQLAlchemy `Numeric` column and
governs finite-value enforcement across source facts, client policy, position state, transaction
economics, cashflows, derived timeseries, and reconciliation controls.

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
  classifies all 96 columns across 30 tables by nullability and signed, positive, or nonnegative
  semantics. All entries are now `orm-enforced`; no planned entry remains.
- V1 records ORM enforcement only. Alembic migration and PostgreSQL integration evidence remain
  the source of database-enforcement truth; V1 cannot be extended with an unsupported
  `database-enforced` claim.
- One canonical model helper builds explicit PostgreSQL finite-value checks without copying the
  three special-value literals across every table. The inventory guard understands only
  literal-column calls to that helper and fails closed on dynamic indirection.
- ORM and migration predicates reject `NaN`, `Infinity`, and `-Infinity` independently from
  sign/range constraints. Signed cashflow, cost, return, market-value, and P&L fields remain signed;
  positive and nonnegative checks apply only to their classified domain fields.
- Migration `c120b2c3d4f9` follows the reconciled #451 `c119` head. It adds each existing-table check
  as `NOT VALID`, then validates retained rows transactionally. Contaminated history fails the
  migration without coercion or partial committed enforcement.
- Ordered migrations `c122b2c3d4fb` through `c126b2c3d4ff` follow the deterministic ingestion
  outcome migration at `c121`. They close the remaining 82 columns in five domain-coherent
  boundaries: reference inputs, client policy, position state, transaction economics, and derived
  timeseries/reconciliation. Each table's new constraints are installed `NOT VALID` and validated
  together in one statement.
- Domain constructors reject non-finite Decimal values before persistence, including signaling
  NaN. Database constraints remain mandatory protection for non-application writers.

## Compatibility and operational impact

Finite values retain their existing precision, scale, nullability, and sign semantics. No public
API, OpenAPI, event, topic, or runtime ownership contract changes. Invalid non-finite values are no
longer accepted. Existing Pydantic Decimal boundaries reject non-finite source values; explicit
event/domain validators retain their established positive or nonnegative rules. SQLAlchemy and
PostgreSQL checks protect internal calculators, direct writers, bulk loaders, migrations, repair
tools, and backfills even when they bypass an API model.

The new migrations validate 24 additional existing tables. Operations should schedule them with
normal migration lock and scan monitoring. `NOT VALID` installation avoids table rewrites and
blocks new invalid rows before retained-row validation; grouped per-table validation avoids
repeated scans. Contaminated history stops the deployment atomically and requires governed
remediation rather than coercion.

Issue #829 remains deliberately separate. This review does not change `NUMERIC(18,10)` or
`NUMERIC(18,4)` precision/scale, declare a new rounding policy, or convert bounded columns to
unbounded numeric.

## Evidence

- machine guard: `python scripts/quality/financial_numeric_persistence_guard.py`
- migration lineage: `python scripts/development/repository_python.py -m alembic heads`
- warning-strict domain, ORM, guard, and migration tests recorded on #827
- complete isolated PostgreSQL proof: `1 passed in 58.67s`, covering all 82 newly governed
  columns, contaminated-history atomic rollback, `NaN`/`Infinity`/`-Infinity`, sign and nullability
  preservation, exact typmod boundaries, catalog validation, downgrade, and reapply
- exact offline DDL compilation proving `NOT VALID` followed by grouped `VALIDATE CONSTRAINT`
- signed commits and independent review evidence recorded on #827 and the delivery PR
