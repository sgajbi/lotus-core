# CR-1553 Collision-Resistant Test Runtime Port Reservation

## Objective

Deliver the host-port isolation slice of GitHub issue #730 by eliminating the interval between
free-port discovery and Docker Compose startup, while preserving explicit operator overrides and
bounded startup recovery.

## Finding

The test runtime selected each dynamic host port by binding to port zero and closing the socket
immediately. Compose started only after image inspection, cleanup, and optional build work. Another
process could claim a selected port during that interval. Existing Compose retries reused the same
environment, so a host bind conflict could fail every attempt without changing the conflicting
assignment.

The suite launcher also allocated ports in its parent process before spawning pytest. That made the
parent, rather than the child that owns Compose, responsible for a short-lived allocation with no
reservation handoff.

## Change

- Added `PreparedTestRuntime` as the single owner of runtime environment and current endpoints.
- Added `RuntimePortReservation` to hold every dynamically assigned TCP port until each Compose
  startup attempt.
- Removed the allocate-then-release helper and the obsolete `build_test_runtime_env` API.
- Made endpoint and connection metadata derive from the current port generation.
- Made exported environments refresh atomically after reallocation.
- Passed the complete prepared runtime into Compose helpers so concurrent same-process projects use
  independent project identity and subprocess environments without global-environment mutation.
- Added explicit host-bind failure classification and complete dynamic-port reallocation before a
  bounded retry.
- Preserved caller-supplied fixed ports across automatic reallocation.
- Moved suite port ownership into the pytest child process.
- Updated failure recovery to resolve database, Kafka, and HTTP endpoints only after Compose has
  successfully claimed the current generation.
- Added bounded exhausted-retry diagnostics containing failure class, attempt count, reallocation
  count, and Compose project identity.
- Made the reservation the source authority for port generation and reallocation evidence.
- Split local image build from startup so builds run while reservations remain held and startup
  never widens the bind-race interval with `up --build`.

## Measurement And Validation

- `59` focused runtime-environment, Docker-stack, failure-recovery, test-manifest, and live
  isolation tests passed.
- Eight concurrently prepared runtimes held globally disjoint active port sets.
- Controlled bind-conflict tests proved one full reallocation and successful retry, plus bounded
  failure after retry exhaustion.
- A concurrent live run passed `135` integration-lite tests in `6.76s` and `10` unit-DB tests in
  `56.80s` in independent Compose projects without port collision or state contamination.
- One live integration test started two PostgreSQL Compose projects concurrently in the same pytest
  process, proved disjoint host ports, and connected to both in `20.26s`.
- Configured MyPy, scoped Ruff lint/format, and `git diff --check` passed.

## Compatibility

No application API, OpenAPI schema, database schema, migration, event, financial calculation,
service topology, or downstream contract changed. The removed builder was repository-internal test
support and all callers moved in the same commit.

## Remaining Work

Issue #730 remains open for scenario shards, change-impact selection, exact-SHA selective dispatch,
diagnostic completeness, field-level polling evidence, and timing/flake/rerun trend reporting.
The fixed-port latency, performance-load, institutional-completion, and endpoint-smoke drivers also
remain direct Compose callers and require a separate CLI-contract migration to prepared runtimes.

## Durable Guidance Decision

Repository context, testing strategy, CI operations guidance, wiki source, and the review ledger
change because runtime ownership and bind-recovery behavior changed. No central Lotus skill or
platform context change is required: the existing CI governance already requires isolated,
deterministic, diagnosable test execution; this slice implements that rule in `lotus-core`.
