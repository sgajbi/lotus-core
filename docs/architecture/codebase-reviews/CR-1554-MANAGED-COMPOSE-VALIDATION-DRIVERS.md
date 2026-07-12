# CR-1554 Managed Compose Validation Drivers

## Objective

Complete the direct-driver isolation sub-slice of GitHub issue #730 by moving latency,
performance-load, Docker-smoke, and institutional-completion validation behind one Compose
lifecycle owner.

## Finding

The four validation drivers independently assembled `docker compose up` commands, inherited the
default project, used fixed endpoint defaults, and left workflow steps to capture logs from that
implicit project. This bypassed the collision-resistant runtime introduced by CR-1553. It also
made diagnostics incorrect once a unique dynamic project was used and duplicated startup/retry
policy across scripts.

The same-pattern review found pytest E2E/integration jobs already captured their dynamic project
through the session fixture, but workflows discarded that authority and ran a second
default-project log command.

## Change

- Added `ManagedComposeRun` as the lifecycle owner for prepared runtime, service set, startup,
  project-bound inspection, diagnostics, and teardown.
- Made inherited parent runtime ports non-authoritative. Managed runs allocate a fresh port set and
  preserve only explicit local endpoint/database URL overrides.
- Migrated all four direct drivers to unique Compose projects and runtime-derived database, Kafka,
  transaction-processing, ingestion, query, QCP, and replay endpoints.
- Preserved external-target execution through `--skip-compose` and local diagnosis through the
  explicit keep-stack option.
- Passed the exact managed environment to institutional child evidence generators and bound Docker
  smoke database cleanup plus latency seed inspection to the exact project.
- Captured project identity and compose-file identity in every diagnostic log before teardown.
- Replaced workflow default-project log commands with driver/fixture-owned diagnostic artifacts.
- Added an AST regression guard preventing the four drivers from recreating Compose `up`, `down`,
  or `logs` commands.
- Removed duplicated driver startup helpers and the now-dead performance command runner.

## Measurement And Validation

- Focused managed-runtime, driver, workflow, and Docker-stack tests pass locally.
- A live Docker integration test starts a managed PostgreSQL project, connects through its dynamic
  port, captures project-identified service logs, tears the project down, and proves the port is no
  longer accepting connections.
- The existing live concurrency test still starts two independent PostgreSQL projects and proves
  disjoint ports.
- Final repository-native aggregate counts and CI evidence are recorded in the issue/PR evidence
  after the bounded slice completes.

## Compatibility

No application API, OpenAPI schema, database schema, migration, event, financial calculation,
service image, or downstream contract changed. Explicit endpoint URLs and `--skip-compose` retain
their existing external-target behavior. Managed local runs now clean up their isolated stack after
capturing diagnostics by default; `--keep-compose` preserves an explicit post-run inspection path.

README, repository context, testing/operations guidance, wiki source, and the review ledger change
because operator lifecycle and diagnostic ownership changed. No central Lotus skill or platform
context change is required: existing CI governance already mandates isolated, deterministic,
project-correct diagnostics. OpenAPI, API inventory, database docs, event docs, and calculation
methodology do not change because their contracts are untouched.

## Remaining Work

Issue #730 remains open for scenario shards, change-impact selection, exact-SHA selective dispatch,
failure-recovery and app-certification diagnostic completeness, field-level polling evidence, and
timing/queue/flake/rerun trend reporting.
