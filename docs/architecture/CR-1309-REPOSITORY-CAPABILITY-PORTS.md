# CR-1309 Repository Capability Ports

## Scope

Issue cluster: GitHub issue #652.

This slice introduces representative capability-specific repository ports for one source-data use
case and one reconciliation workflow family.

## Objective

Reduce broad concrete repository coupling in application/source-data orchestration without
changing query behavior, reconciliation behavior, persistence SQL, or runtime deployment topology.

## Changes

1. Added `PortfolioTaxLotReader` under `query_service.app.ports`.
2. Rewired `resolve_portfolio_tax_lot_window_response(...)` to depend on
   `PortfolioTaxLotReader` instead of `Any`.
3. Added financial reconciliation repository ports:
   `ReconciliationRunWriter`, `TransactionCashflowEvidenceReader`,
   `PositionValuationEvidenceReader`, `TimeseriesIntegrityEvidenceReader`, and the transitional
   aggregate `ReconciliationRepositoryPort`.
4. Rewired `ReconciliationService` to depend on `ReconciliationRepositoryPort` instead of the
   concrete `ReconciliationRepository` type.
5. Added type-contract tests proving the source-data resolver and reconciliation service depend on
   repository ports.
6. Added `scripts/repository_port_guard.py`, wired it into `make architecture-guard`, and added
   focused guard tests.
7. Added `docs/standards/repository-capability-port-standard.md`.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, repository SQL, database schema,
source-data product field, portfolio tax-lot page token, lineage field, reconciliation finding,
reconciliation summary, reconciliation status, metric name, or runtime wiring changed.

Concrete SQLAlchemy repositories still implement the required methods. This is design modularity
inside existing deployables, not a runtime service split.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/services/query_service/services/test_portfolio_tax_lot_window.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py tests/unit/scripts/test_repository_port_guard.py -q`
   - 32 passed.
2. `python scripts/repository_port_guard.py`
   - Passed.
3. Scoped Ruff lint passed.
4. Scoped Ruff format passed.

Final architecture guard, wiki/docs gate, and diff evidence are recorded before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger, repo-local engineering context, and repository capability port
standard.

No wiki update is required because this slice changes internal application-to-repository typing and
testability, not operator commands, route behavior, supported features, or published wiki truth.

The broader platform backend/codebase-review skills were updated in `lotus-platform` commit
`3cdaadd` to capture the repeated issue-driven port-refactor pattern.

## Remaining Work

GitHub issue #652 is locally fixed for representative source-data and reconciliation repository-port
acceptance criteria pending PR CI/QA and issue closure.

Follow-up slices should split additional concrete repository dependencies in `IntegrationService`,
`CoreSnapshotService`, simulation workflows, and remaining reconciliation methods into narrower
capability ports when those use cases are touched.

