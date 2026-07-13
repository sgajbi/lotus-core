# CR-1558: Position History Application Boundary

Date: 2026-07-13

Status: Fixed locally; PR proof pending

## Objective

Move active position-history materialization out of a mixed infrastructure workflow and into the
governed domain, application, ports, and infrastructure dependency flow without changing public,
event, database, or downstream contracts.

## Findings

The production position path mixed orchestration, epoch fencing, SQLAlchemy rows, event DTOs,
metrics, logging, and pure reduction in one infrastructure workflow. The compatibility adapter
converted `BookedTransaction` to `TransactionEvent` and back. Epoch fencing and application
processing each loaded or created the same position state, adding two avoidable SQL statements per
transaction. Position and transaction domain files also remained flat beside established domain
packages.

## Changes

1. Added immutable position history/state records and deterministic history construction under
   `app/domain/position`.
2. Added `PositionHistoryProcessor` and explicit repository, state-store, and observation ports.
3. Added SQLAlchemy history/state adapters and a failure-contained Prometheus/structured-log
   observer.
4. Routed the production unit of work directly from `BookedTransaction` to the application use
   case, preserving caller-owned commit/rollback and cashflow rebuild transactions.
5. Evaluated stale epochs from the single loaded state while preserving the existing
   `position-calculator` mismatch metric label contract.
6. Organized transaction, processing-stage, and cost-basis reconciliation domain files under
   cohesive packages, with structure tests preventing flat-module return.
7. Migrated active repository coverage and proved three unused legacy reads are absent from the new
   adapter.
8. Migrated PostgreSQL repository, rollback, replay, and concurrency tests to the application and
   adapter boundaries; deleted the legacy workflow/repository and added an absence guard.

## Compatibility

No HTTP/OpenAPI, Kafka event, database schema, transaction ordering, public DTO, or deployment
topology changed. Deterministic corporate-action ordering is now used consistently for current and
backdated history. This is an intentional correctness strengthening within the existing ordering
contract. The former workflow and repository are retired and guarded against reintroduction.

## Validation

- 526 transaction-processing and transaction-spec tests passed during domain package validation.
- 84 reducer/history compatibility tests passed before persistence extraction.
- 31 adapter, unit-of-work, and position tests passed for production cutover.
- 24 processor/observability tests passed, including one-state-load stale fencing.
- 10 active SQLAlchemy position-history repository tests passed.
- 6 live PostgreSQL repository, rollback, replay, and concurrency tests passed in 89.81 seconds.
- 81 focused position application/domain/adapter tests and the full architecture guard passed after
  legacy deletion.
- Focused Ruff check/format and `git diff --check` passed for each implementation commit.

## Governance Decisions

- README: no change; service entry points and public usage did not change.
- OpenAPI/API inventory: no change; no route or DTO changed.
- Data mesh and database migration: no change; ownership and schema stayed within Core.
- Wiki: updated because runtime ownership and support diagnostics changed.
- Skills/platform context: no change; the reusable layered-architecture rule already exists. Repo
  context now records the one-state-load fencing and direct booked-transaction requirements.

## Remaining Work

Issue #719 remains open for cost-runtime ownership, simulation/replay hardening, end-to-end
performance evidence, and broader legacy calculator retirement. The position history application
boundary and its former workflow/repository retirement are complete locally.
