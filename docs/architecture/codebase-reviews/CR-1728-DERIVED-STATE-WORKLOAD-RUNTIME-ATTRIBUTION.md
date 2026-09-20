# CR-1728: Derived-State Workload Runtime Attribution

## Scope and status

Review date: 2026-09-16; CI correction 2026-09-20. Owner: Core Codex `/root`.
Status: `In Review`.
Owning issue: [#714](https://github.com/sgajbi/lotus-core/issues/714).
Control classes: capacity evidence, database observability, testing/CI and
documentation/evidence.

This is a bounded evidence-contract correction. It does not claim the outstanding
100,000-transaction / 1,000-portfolio capacity target, qualified-image rehearsal,
or production acceptance.

## Finding and correction

The bank-day workload already exercised transaction processing, valuation
orchestration, position valuation and portfolio derived-state runtimes, but its
database-operation artifact scraped only the transaction-processing `/metrics`
endpoint. A run could therefore report database evidence while omitting the
services that claim valuation work and write position or portfolio timeseries.
That made an unfinished tail difficult to attribute and allowed a missing runtime
sample to look like successful evidence collection.

The workload now collects the existing `db_operation_latency_seconds` series from
all four runtimes and records a closed runtime identity on every sample. Required
hot-path evidence covers valuation claims, daily-snapshot writes and both
position/portfolio timeseries writes in addition to the existing transaction
operations. A missing required runtime/repository/method sample fails the report;
an unknown runtime is refused before network access. The original
transaction-processing helper remains as a compatibility wrapper.

Managed isolated runs receive generated endpoints for all four services. Endpoint
locations remain transient orchestration inputs and are not copied into durable
report configuration. The change does not alter work partitioning, retry/lease
semantics, transaction ordering, financial calculations, database schema, API
contracts, or the existing twelve-partition ceiling. The subsequent security
correction does change the locked AnyIO dependency installed in runtime images;
it does not change the service topology or financial behavior.

The first signed-head Feature and PR lint/security jobs then failed at the
unsuppressed dependency audit: the previously locked transitive `anyio 4.12.1`
was reported under CVE-2026-63374 and CVE-2026-64847, with `4.14.2` as the
fixed version. The governed runtime compiler selected `4.14.2` on both Linux
and Windows. The CI/test closures carry the same version while retaining every
unrelated pre-existing transitive pin; both platform lock replay checks passed.
The lock-bound dependency-technology inventory was refreshed from exact PyPI
release metadata for all 104 components, including the new AnyIO release and
four changed lock hashes. It remains `blocked`/non-certifying because upstream
release metadata does not grant Lotus technology support approval. No
vulnerability exception, support classification or audit threshold was changed.

## Evidence

- Focused workload/support/runtime suite: 84 passed.
- Native `make typecheck`: 329 source files passed.
- Lock-backed Python 3.11.9 / FastAPI 0.136.3 `make check`: exit 0,
  including Ruff, architecture, contract and MyPy gates; both complete unit
  executions passed 9,924 each, with 3 existing skips and 16 intentional
  database-runtime deselections. The warning budget remained zero.
- Native `make outbox-capacity-profile-guard`, `make docs-evidence-pack`, and
  `make quality-wiki-docs-gate`: passed.
- Clean, isolated Windows dependency-health install/audit from the updated
  lock graph: exit 0, no broken requirements, no known vulnerabilities;
  `anyio 4.14.2` installed. The first failed GitHub Feature and PR jobs were
  at commit `55246b4ec54cf9481fdbd15fbcf5a8b47126aaac`; new final-head CI
  is required after the lock correction.
- Native `make dependency-technology-inventory`: guard passed with 104
  components, 120 findings and certification decision `blocked`; this is
  inventory integrity, not a production support decision.
- The updated Windows runtime/test closure passed a fresh native `make check`:
  both complete unit executions passed 9,924 each, with the same 3 existing
  skips, 16 intentional database-runtime deselections and zero warnings.
  Focused workload/support/runtime tests again passed 84; ops contracts passed
  330, and the refreshed docs/wiki gates passed.
- Isolated app-local `make test-derived-state-workload-smoke`: 10 transactions,
  10 snapshots, 10 position rows, 2 portfolio rows, zero open valuation or
  aggregation work and zero pending/failed outbox rows in 26.762 seconds. The
  artifact contained database observations from all four required runtimes:
  transaction processing (166), valuation orchestration (240), position valuation
  (66), and portfolio derived state (124). The exact owned Compose resources were
  absent after normal teardown.
- Unit controls prove the valid four-runtime report and representative failure
  when one required runtime sample is absent. The runtime vocabulary control proves
  that an unsupported identity is rejected without scraping a metrics endpoint.

These are bounded developer receipts. Exact final-head runtime and required CI
receipts belong in the PR and owning issue before merge. No throughput,
percentile-latency, resource-envelope, release, or production conclusion is
inferred from the small smoke run.

An earlier diagnostic shell resolved unpinned Python 3.13/FastAPI 0.141.1 and
failed an unrelated route-introspection test that passes in the lock-backed
environment. A subsequent locked `make check` was suspended across four days;
its Windows pytest temporary root disappeared during the pause, yielding 30
late fixture-setup errors after 9,894 passes. Neither failed run is a green
gate or evidence of a Core product fault. The fresh complete locked run above
is the accepted local gate receipt.

## Ownership and no-change decisions

Core retains transport, application, persistence, valuation and derived-state
ownership. The change reads service-owned metrics only and creates no IAM grants,
shared-stack ownership or new service boundary. Existing recovery controls and
independent position/portfolio modules remain unchanged.

Repository engineering context, the operations runbook, workload guide and wiki
source now state the four-runtime evidence requirement. The four generated
runtime/CI dependency locks carry only the CI-blocking AnyIO security repair.
The dependency-technology inventory carries the corresponding source metadata
and lock digests. No README, OpenAPI, migration, supported-feature,
financial-methodology, central Platform context or skill change is required
because external behavior and authority did not change. Publish the changed
wiki source after merge and verify committed parity.

## Remaining acceptance

Final-head review, required checks, linear merge, exact-main verification and wiki
publication remain required for this slice. Keep #714 open for the 100,000 / 1,000
capacity and recovery campaign, qualified-image rollout/rollback rehearsal and
downstream QA. Related #794 and #795 remain open for their broader throughput and
resource-envelope acceptance.
