# CR-1554 Managed Compose Validation Drivers

## Objective

Complete the direct-driver isolation sub-slice of GitHub issue #730 by moving latency,
performance-load, Docker-smoke, institutional-completion, and failure-recovery validation behind
one Compose lifecycle owner.

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
- Made latency seeding self-contained instead of relying on a previously populated shared volume.
  The gate enables its one-shot loader explicitly, limits seed data to the measured portfolio and
  supported 240-day history window, and uses seed-only mode before its own query-readiness check.
- Captured project identity and compose-file identity in every diagnostic log before teardown.
- Replaced workflow default-project log commands with driver/fixture-owned diagnostic artifacts.
- Extended the owner to failure recovery: its integration-profile runtime, migration wait,
  interruption lookup, connection endpoints, diagnostic capture, and teardown now use the same
  project. External `--skip-compose` runs retain explicit or environment-provided project identity.
- Added an AST regression guard preventing the four drivers from recreating Compose `up`, `down`,
  or `logs` commands.
- Removed duplicated driver startup helpers and the now-dead performance command runner.

## Measurement And Validation

- `114` focused managed-runtime, driver, workflow, and Docker-stack tests passed locally.
- A live Docker integration test starts a managed PostgreSQL project, connects through its dynamic
  port, captures project-identified service logs, tears the project down, and proves the port is no
  longer accepting connections.
- The existing live concurrency test still starts two independent PostgreSQL projects and proves
  disjoint ports.
- `make ci-local` passed `4,301` unit tests with zero warnings, `10` PostgreSQL tests, `135`
  integration-lite tests, combined coverage, and every configured architecture, security, API,
  data, event, observability, documentation, and repository guard.
- `make test-docker-smoke` passed all `66` endpoint checks and produced project-identified
  diagnostics before leaving zero project containers behind.
- `make test-latency-gate` passed from a clean isolated project with `30/30` successful samples per
  endpoint. The highest observed p95 was `60.12 ms` against a `320 ms` budget; the run captured a
  `5,746,292` byte project-identified diagnostic log and left zero project containers behind.
- Scoped Ruff lint/format, configured MyPy, workflow parsing/governance, documentation evidence,
  wiki validation, and `git diff --check` passed.
- The failure-recovery extension passed `56` focused lifecycle/workflow tests, configured MyPy,
  and the `227`-test operations contract suite.
- `make test-failure-recovery-gate` completed `FULLY_DRAINED`: `100` submitted records produced
  exactly `100` transaction, cost, cashflow, position, and processing-claim records; committed lag
  grew by `100` and returned to `0`; replay lag and added DLQ events were `0`; recovery took
  `8.148s`.
- The live run captured a `2,216,235` byte log naming project
  `lotus-integration-failure-recovery-gate-5a6b519c` and the exact Compose file before teardown,
  then left zero project containers.

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
app-certification diagnostic completeness, field-level polling evidence, and timing/queue/flake/
rerun trend reporting.
