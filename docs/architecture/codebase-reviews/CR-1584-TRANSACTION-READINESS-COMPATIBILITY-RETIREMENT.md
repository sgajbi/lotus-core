# CR-1584: Transaction Readiness Compatibility Retirement

## Objective

Complete the CR-1583 boundary by removing the flat readiness compatibility facade and giving the
unit of work and infrastructure package clear transaction-readiness ownership.

## Finding

After CR-1583, `PipelineStageProcessingAdapter` contained only composition, but the SQLAlchemy unit
of work still depended on it through a vague `pipeline` property. The stage repository also remained
flat in the infrastructure root. Keeping those names would preserve misleading architecture and an
easy path back to mixed orchestration.

## Change

1. Renamed the internal unit-of-work capability and protocol to transaction readiness.
2. Composed `RegisterTransactionReadinessUseCase` directly from the stage repository and
   transactional event stager.
3. Moved the SQLAlchemy stage repository to
   `infrastructure/transaction_readiness/stage_repository.py` and exported both package adapters
   through one front door.
4. Deleted `pipeline_stage_processing_adapter.py` and its infrastructure-root export without an
   alias.
5. Added a no-return structure test for the facade, flat repository, and former mixed test path.
6. Updated application tests, port catalog, repository context, architecture decision, wiki source,
   CR-1583 closure, and the review ledger.
7. Made repository-wide warning-budget collection mandatory for future facade or package-root
   re-export deletion after the prior cashflow slice exposed a cross-package test consumer.

## Measurable Improvement

- Removed one compatibility class and one flat infrastructure module.
- Removed the ambiguous `pipeline` unit-of-work property and `_pipeline` state.
- Reduced one production indirection from the transaction hot path.
- Established one self-explanatory package for readiness persistence and outbox delivery.

## Compatibility

No SQL statement, advisory lock key, table, stage name, epoch rule, completion claim, outbox write,
event schema, Kafka topic, metric label, transaction boundary, API, OpenAPI, or downstream contract
changed. `TransactionProcessingOperation.PIPELINE` remains unchanged as an existing bounded metric
label. The renamed unit-of-work property is internal to the transaction-processing application.

## Documentation Decision

Repository context, architecture guidance, wiki source, application-port catalog, CR-1583, and the
review ledger changed because runtime composition and package ownership changed. Supported-feature,
critical-path, database, API inventory, and OpenAPI truth remain unchanged because their package
coverage and external contracts already describe the resulting state.

## Validation

1. The no-return structure test failed before the repository move and facade deletion, recording the
   TDD red state; `33` focused readiness, process-transaction, and unit-of-work tests then passed.
2. The complete transaction-processing unit package passed `809` tests in `10.86s`.
3. The complete PostgreSQL transaction-processing contract passed `73` atomicity, idempotency,
   replay, epoch, lock, outbox, readiness, and concurrency scenarios in `285.22s`.
4. Repository-wide warning-budget collection passed `4,594` unit tests with `10` deselected and
   zero warnings in `204.89s`, proving no hidden facade or package-root consumer remains.
5. Strict MyPy passed for ten domain, application, port, UoW, repository, and readiness adapter
   modules.
6. Full `make lint` and `make architecture-guard` passed, including application dependency,
   repository transaction, event contract, critical-path, supported-feature, and image-provenance
   guards.
7. Application-port catalog, docs/wiki, scoped Ruff/format, retired-name scans, staged diff, and
   `git diff --check` passed.

## Remaining Work

Keep #719 open. Review remaining flat transaction-processing infrastructure by measured ownership
and usage; do not move files cosmetically or collapse independently justified ports.
