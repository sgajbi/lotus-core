# CR-1585: Transaction Idempotency Infrastructure Ownership

## Objective

Advance issue #719 by separating transaction claim persistence from SQLAlchemy unit-of-work
lifecycle and composition without changing duplicate, repair, or atomicity behavior.

## Finding

`sqlalchemy_unit_of_work.py` contained the concrete idempotency adapter, the stable processing
service identity, repository calls, and semantic outcome translation alongside session lifecycle,
adapter composition, commit, and rollback. The adapter was also re-exported from the broad
infrastructure package root, while its only unit test remained mixed with unit-of-work tests.

## Change

1. Added `app/infrastructure/idempotency/processing_claims.py` for physical and semantic claim
   persistence, service identity, and repository-outcome translation.
2. Added a narrow idempotency package front door and composed the adapter from the existing
   SQLAlchemy unit of work.
3. Removed the adapter and service identity from the broad infrastructure-root exports without a
   compatibility alias.
4. Moved claim behavior tests into the mirrored infrastructure package and expanded them across
   claimed, physical duplicate, semantic duplicate, semantic conflict, and repair-claim outcomes.
5. Updated integration evidence to import the persisted service identity from its owning package.
6. Added a no-return structure guard and cataloged idempotency as an application-port capability
   and critical lifecycle path.
7. Reconciled repository context, architecture catalog, consolidation ledger, wiki source, and the
   codebase-review ledger.

## Measurable Improvement

- Reduced `sqlalchemy_unit_of_work.py` from `208` to `164` lines.
- Removed one concrete repository adapter and one mapping responsibility from the unit-of-work
  module.
- Removed two unrelated symbols from the broad infrastructure package API.
- Replaced one claimed-only adapter test with six complete outcome and repair-result cases.
- Established one self-explanatory, mirrored idempotency infrastructure package.

## Compatibility

No service identity value, semantic key, payload fingerprint, physical/semantic outcome, repair
claim, database table, SQL repository method, transaction boundary, retry behavior, event, Kafka
topic, API, OpenAPI schema, metric, or downstream contract changed. Integration support queries
continue to use `portfolio-transaction-processing`; only their internal import path changed.

## Documentation Decision

Repository context, application-port catalog, critical-path coverage, consolidation ledger, wiki
source, and review ledger changed because package ownership and the internal infrastructure API
changed. README, supported-feature, database, API inventory, OpenAPI, and platform context require
no change because deployable topology, supported behavior, persistence schema, and external
contracts are unchanged.

## Validation

1. `31` focused idempotency, unit-of-work, and transaction-use-case tests passed.
2. The complete transaction-processing unit package passed `815` tests in `9.96s`.
3. Strict MyPy passed for the transaction-processing port, use case, idempotency adapter, and unit
   of work.
4. Application-port catalog and critical-path coverage contract guards passed, including staged
   discovery of the new package.
5. The complete PostgreSQL transaction-processing contract passed `73` atomicity, idempotency,
   replay, repair, epoch, lock, outbox, readiness, and concurrency scenarios in `290.65s`.
6. Repository-wide warning-budget collection passed `4,600` unit tests with `10` deselected and
   zero warnings in `196.49s`, proving no hidden consumer of the removed root exports remains.
7. Full lint, architecture, application-port catalog, critical-path coverage, docs/wiki, Ruff
   format, staged diff, and no-return checks passed.

## Remaining Work

Keep #719 open. Continue evidence-led decomposition of remaining flat transaction-processing
infrastructure and test ownership. Do not split the single transaction, duplicate the shared claim
repository, or move idempotency policy into delivery code.
