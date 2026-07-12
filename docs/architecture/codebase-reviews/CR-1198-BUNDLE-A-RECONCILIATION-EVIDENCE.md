# CR-1198: Bundle A Reconciliation Evidence

Date: 2026-06-30

## Objective

Address GitHub issue #680 by promoting Bundle A corporate-action reconciliation outcomes from
log-only diagnostics into durable operator evidence. Preserve existing reconciliation detection
logic while making balanced, basis-mismatch, insufficient-leg, and missing-dependency outcomes
queryable through the established financial reconciliation control plane.

## Change

- Added cost-consumer persistence of `corporate_action_bundle_a` reconciliation runs in
  `financial_reconciliation_runs`.
- Added durable reconciliation findings in `financial_reconciliation_findings` for:
  - `ca_bundle_a_basis_mismatch`
  - `ca_bundle_a_insufficient_legs`
  - `ca_bundle_a_missing_dependency`
- Kept balanced Bundle A groups finding-free while still recording a completed run summary.
- Used deterministic group/outcome signatures for run and finding identifiers so consumer retries
  do not multiply identical evidence rows.
- Preserved source-safe structured logs and added bounded financial reconciliation metrics through
  the existing reconciliation metric helper.

## Expected Improvement

Bundle A lifecycle support now follows the same durable control pattern as other reconciliation
families. Operators can find the relevant reconciliation run and finding rows through existing
support APIs instead of relying on transient process logs, and future corporate-action controls can
reuse the financial reconciliation run/finding surface rather than adding parallel diagnostics.

## Tests Added

- Consumer-path coverage proving a balanced Bundle A group records a completed reconciliation run
  with no findings and carries the processing correlation ID.
- Evidence-mapping coverage for basis mismatch, insufficient legs, and missing dependency outcomes,
  including stable finding types and reason codes.
- The existing shared Bundle A reconciliation helper tests continue proving the domain status
  classifier behavior.

## Validation Evidence

- `python -m pytest tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py tests/unit/libs/portfolio_common/test_ca_bundle_a_reconciliation.py -q`
  passed with 37 tests.
- `python -m ruff check src/services/calculators/cost_calculator_service/app/consumer.py src/services/calculators/cost_calculator_service/app/repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
  passed.
- `python -m ruff format --check src/services/calculators/cost_calculator_service/app/consumer.py src/services/calculators/cost_calculator_service/app/repository.py tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py`
  passed.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed.
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` reported
  existing published-wiki drift for `Event-Replay-Service.md`, `Financial-Reconciliation.md`,
  `Ingestion-Service.md`, `Mesh-Data-Products.md`, `Operations-Runbook.md`, `Outbox-Events.md`,
  and `Validation-and-CI.md`; repo-local wiki source validation passed.

## Downstream Compatibility

No route path, API DTO, Kafka topic, transaction event schema, cost calculation formula, or database
schema changed. The intentional behavior change is additive durable evidence in existing
reconciliation control tables, plus existing reconciliation metrics for the new
`corporate_action_bundle_a` control family.

## Documentation

- Updated the repo-local Financial Reconciliation wiki source with the new control family and
  operator lookup path.
- Updated the codebase review ledger.
- Updated the quality scorecard and refactor health report.

## Follow-Up

Issue #680 remains open for PR/CI/QA evidence and any broader replay/control workflow decisions
that should block downstream publication or trigger automated remediation. Issue #607 remains the
complementary lifecycle golden-scenario coverage backlog.
