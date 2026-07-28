# CR-1657: Exact Financial Numeric Bind Boundary

## Scope

This review is a bounded part of GitHub issue #829. It covers the final SQLAlchemy bind boundary
for every financial `NUMERIC` column. It does not claim that all producer DTOs or calculated-output
policies are aligned.

## Finding

PostgreSQL accepts excess fractional digits for bounded `NUMERIC(p,s)` and rounds them to the
declared scale. Sign and finiteness checks cannot detect that normalization. The repository had
explicit storage shapes, but internally calculated values and producer paths not yet covered by
ingress validators could still be changed silently during persistence.

## Resolution

- Added `ExactNumeric`, a SQLAlchemy type decorator that compiles to the existing `NUMERIC` DDL.
- Replaced all 96 governed ORM declarations with `ExactNumeric`.
- Bounded `18,10` and `18,4` values are accepted only when exactly representable; excess scale and
  magnitude overflow are rejected before the database operation.
- The authoritative market-price source fact remains finite exact-unbounded.
- Extended the numeric persistence guard so the versioned contract requires exact bind
  enforcement and rejects restoration of a plain SQLAlchemy `Numeric` declaration.
- Added real PostgreSQL proof for maximum accepted values, exact unbounded round-trip, identical
  replay, excess scale, magnitude overflow, and zero residual rejected rows.

The database schema and migration chain do not change: the decorator retains the declared
PostgreSQL type and typmod.

## Compatibility

Values already exactly representable by their declared storage shape are unchanged. Values that
PostgreSQL previously would have rounded or rejected now fail deterministically at the
persistence bind boundary. This is intentional correctness hardening.

Calculated outputs are not blanket-rounded. Domain owners must define explicit, lineage-aware
output precision before any rounding is introduced. External producer DTO/event paths should move
the same rejection earlier so clients receive synchronous contract errors rather than downstream
processing failures.

## Evidence

- Signed commit `c33a9b3b213d05981731665a07fb56bbb938a0b9`.
- 116 focused model, guard, type, and migration-parity tests passed with warnings as errors.
- Real PostgreSQL exact-bind proof passed.
- `make test-fast`, `make typecheck`, `make financial-numeric-persistence-guard`, Ruff, formatting,
  and diff hygiene passed.
- Guard inventory: 96 columns, 30 tables, 95 bounded, one exact-unbounded, ten domain families.

## Remaining #829 work

Producer-boundary review found these bounded follow-ups:

1. client-policy DTOs;
2. benchmark and instrument reference DTO/events;
3. simulation and reconciliation command DTOs;
4. transaction DTO/events;
5. transaction, cost-basis, and position calculated-output policies;
6. valuation and derived-timeseries lineage-aware output policies.

Issue #829 remains open until those owner-specific contracts and their downstream proofs are
complete.
