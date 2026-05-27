# CR-336 Support Overview Query Shape And Composition Review

## Scope

Review and harden the `query_service` operations support overview path after hosted
main releasability exposed:

- a valuation backlog snapshot failure in `test_valuation_jobs_hide_superseded_pending_epochs_in_backlog_views`
- a latency-gate failure for `support_overview`

This scope covers the support overview orchestration path, valuation/aggregation
support-health query shape, database indexes for the operations hot path, and the
service-level composition boundary.

## Findings

1. The actionable valuation-job predicate used a `CASE` expression to hide superseded
   pending valuation epochs. The intent was correct, but the generated predicate was
   harder to reason about and weaker as a reusable query-shape contract than an explicit
   boolean `OR` with a correlated `NOT EXISTS`.
2. `support_overview` is an operator hot path. Its valuation and aggregation health
   queries are portfolio-scoped, status-scoped, and date/timestamp ordered, but the job
   tables did not declare composite indexes aligned to that exact support-plane access
   pattern.
3. `OperationsService.get_support_overview(...)` mixed repository orchestration,
   derived backlog-age calculation, controls reconciliation projection, and DTO
   construction in one large method. That made the path harder to review and increased
   the chance that support-plane policy would drift into unrelated service logic.

## Actions Taken

1. Replaced the valuation actionable-job predicate with an explicit boolean expression:
   non-pending jobs remain visible, while pending jobs are hidden only when a newer
   same portfolio/security/date epoch exists as of the support snapshot.
2. Added explicit correlation to the superseding-epoch predicates.
3. Added operations hot-path indexes for valuation and aggregation jobs:
   `portfolio_id, status, updated_at` and
   `portfolio_id, status, business-date, updated_at, id`.
4. Added an Alembic migration so SQLAlchemy metadata and deployed database state stay
   aligned.
5. Extracted deterministic support overview composition into
   `support_overview_builder.py`, leaving `OperationsService.get_support_overview(...)`
   responsible for orchestration and repository calls.
6. Added direct builder tests for backlog-age derivation and controls/reconciliation
   projection, plus model metadata tests for the new indexes.

## Validation

- `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_support_overview_builder.py tests/unit/services/query_service/services/test_operations_service.py -q`
  - `126 passed`
- `python -m pytest tests/integration/services/query_service/test_int_operations_service.py -q`
  - `18 passed`
- `make test-integration-all`
  - `675 passed`
- `make migration-smoke`
  - passed; Alembic head is `7f8a9b0c1d2e`
- `make test-latency-gate`
  - passed; `support_overview` p95 `74.62ms` against `240ms` budget
- `make ci-local`
  - passed; `2112` unit tests passed, query-service integration-lite `118` tests passed,
    combined query-service coverage `99%`
- Touched-surface `ruff check`
  - passed

## Follow-Up

No API contract or wiki source change is required for this slice because the public
support overview response shape is unchanged. The next useful enterprise-grade review
target is to continue extracting operator support-plane composition helpers where the
same mapping and derived-state pattern still lives inside `OperationsService`.
