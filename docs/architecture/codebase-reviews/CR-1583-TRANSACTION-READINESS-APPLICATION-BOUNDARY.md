# CR-1583: Transaction Readiness Application Boundary

## Objective

Advance issue #719 by removing application coordination and integration-event mapping from the
transaction processor's flat pipeline-stage infrastructure adapter.

## Finding

`PipelineStageProcessingAdapter` acquired exact-key locks, applied monotonic epoch policy, upserted
stage state, claimed completion, constructed two governed event DTOs, and wrote both outbox records.
The class therefore mixed application sequencing, persistence, and transport mapping. Its tests
targeted the infrastructure facade rather than the actual responsibility owners.

## Change

1. Added `RegisterTransactionReadinessUseCase` under a domain-owned application package.
2. Added narrow repository and transactional event-staging ports.
3. Added `TransactionalTransactionReadinessEventStager` for governed transaction-completion and
   valuation-readiness event mapping.
4. Reduced the existing adapter to temporary composition over the application use case so the
   unit-of-work contract remains unchanged until the next deletion slice.
5. Replaced four mixed facade tests with five application policy scenarios and two event-mapping
   scenarios, including stale epoch, completed stage, missing cost fact, lost claim, and
   security-less transaction behavior.
6. Cataloged the port capability and aligned critical-path coverage, supported features,
   architecture guidance, repository context, and wiki source.

## Measurable Improvement

- The compatibility adapter fell from 116 lines of mixed behavior to 25 lines of composition.
- Application policy no longer imports SQLAlchemy, ORM models, Kafka topics, event DTOs, or the
  outbox repository.
- Integration mapping no longer decides epoch or completion policy.
- Seven responsibility-owned tests replace four facade-coupled tests.

## Compatibility

No stage name, exact-key lock, epoch comparison, completion claim, event schema, topic, aggregate
identity, payload, correlation field, database schema, transaction boundary, API, OpenAPI, or
downstream behavior changed. Input order and the existing `register_processed_transactions` method
contract remain stable.

## Documentation Decision

Repository context, architecture guidance, wiki source, the supported-feature contract,
critical-path coverage, application-port catalog, and review ledger changed because ownership
changed. Database catalog, API inventory, and OpenAPI remain unchanged because storage and HTTP
contracts did not change.

## Validation

1. The first test run failed at collection because the application and infrastructure packages did
   not yet exist; this records the TDD red state.
2. `32` focused transaction-readiness, process-transaction, and unit-of-work tests passed, including
   all seven new responsibility-owned scenarios.
3. The complete transaction-processing unit package passed `808` tests in `9.03s`.
4. Strict MyPy passed for nine domain, application, port, repository, event-staging, compatibility,
   and composition modules.
5. Full `make lint` and `make architecture-guard` passed, including dependency inversion,
   application workflow, repository transaction, event contract, and supported-feature guards.
6. Application-port catalog, critical-path coverage, docs/wiki, scoped Ruff/format, staged diff,
   and `git diff --check` passed.
7. No PostgreSQL rerun is required for this slice because SQL statements, locks, repository code,
   schema, and unit-of-work composition did not change; the direct-composition deletion slice will
   rerun the database transaction contract.

## Remaining Work

CR-1584 composes the use case directly, moves stage persistence into the transaction-readiness
package, deletes the compatibility adapter without an alias, and guards every retired flat path.
Keep #719 open for the broader persistence and runtime consolidation campaign.
