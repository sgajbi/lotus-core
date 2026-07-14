# CR-1590: Transaction Unit-of-Work Package Ownership

## Objective

Advance issue #719 by colocating the concrete atomic transaction boundary with aggregate
transaction-processing infrastructure and removing its flat module, broad root export, and
service-root test surface.

## Finding

`infrastructure/sqlalchemy_unit_of_work.py` was one of two remaining implementation files in the
flat infrastructure root. It composes cost, cashflow, position, readiness, idempotency, and outbox
adapters over one SQLAlchemy transaction, but its class was broadly exported and its test remained
at the service test root. Image import proof, durability evidence, and an idempotency ownership guard
also encoded the flat path.

## Change

1. Moved the atomic boundary to
   `app/infrastructure/transaction_processing/unit_of_work.py` with explicit module and class
   docstrings.
2. Exported the concrete class only through the aggregate transaction-processing package.
3. Updated composition and internal tests to import from that package and removed the broad
   infrastructure-root export without an alias.
4. Moved unit-of-work tests into the mirrored transaction-processing infrastructure package.
5. Extended the no-return guard to the flat source, service-root test, and exact root export.
6. Updated installed-image import proof, its contract test, idempotency ownership evidence, the
   durability standard, repository context, consolidation ledger, wiki source, and review ledger.

## Measurable Improvement

- Removed one of the final two implementation modules from the flat infrastructure root.
- Removed one infrastructure test from the service test root.
- Removed one concrete adapter class from the broad infrastructure API.
- Preserved one session, one transaction, one commit, and caller-owned module adapters.
- Left `composition.py` for a separate composition-root decision instead of mixing runtime assembly
  relocation into this persistence boundary slice.

## Compatibility

No SQL statement, repository, adapter construction, session lifecycle, rollback, commit, financial
calculation, API, OpenAPI schema, event, topic, consumer group, metric, database structure, image
entrypoint, runtime topology, or downstream contract changed. Only internal import and installed
image smoke-proof paths changed.

## Documentation Decision

Repository context, durability evidence, consolidation evidence, transaction-processing wiki,
image import proof, critical-path coverage through the existing package glob, and the review ledger
changed because ownership truth changed. README, supported features, database catalog, API
inventory, OpenAPI, and platform context require no change because behavior and topology are
unchanged.

## Validation

1. `16` focused unit-of-work, composition, package-structure, idempotency-ownership, and image
   package tests passed.
2. Strict MyPy passed for the transaction-processing port, concrete unit of work, and composition.
3. The complete transaction-processing unit package passed `820` tests in `7.23s`.
4. Repository-wide warning-budget collection passed `4,611` unit tests with `10` deselected and
   zero warnings in `181.22s`, proving no hidden consumer of the removed flat/root surfaces remains.
5. Full Ruff lint/format, architecture, image provenance, critical-path coverage, docs/wiki,
   staged-diff, and no-return checks passed.

## Remaining Work

Keep #719 open. Decide the final composition-root ownership separately, preserving explicit runtime
assembly and avoiding a generic transaction-processing infrastructure package.
