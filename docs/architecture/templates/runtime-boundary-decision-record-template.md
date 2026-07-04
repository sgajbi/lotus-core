# Runtime Boundary Decision Record: <Service Or Worker Name>

## Status

Choose one:

1. `runtime-split-approved`
2. `runtime-split-rejected`
3. `current-state-revalidation-required`

## Proposed Boundary

Describe the proposed deployable service, worker, scheduler, or runtime boundary.

## Current In-Process Boundary

Document the existing or proposed in-process design boundary:

1. package/module ownership,
2. application use cases,
3. domain policies/value objects,
4. ports/protocols,
5. infrastructure adapters,
6. tests with fake adapters.

## In-Process Evidence

Show that an in-process boundary was designed, implemented where safe, and tested before a runtime
split was accepted.

Required evidence:

1. architecture or standards links,
2. focused tests,
3. boundary guards,
4. complexity or operability gap that remains after in-process modularity,
5. downstream compatibility notes.

## Runtime Drivers

Approve a deployable split only when one or more are proven:

1. independent scaling,
2. independent deployment cadence,
3. distinct operational ownership,
4. distinct persistence ownership,
5. failure isolation,
6. security or trust boundary,
7. materially different latency or throughput SLO.

## Decision

State the decision and rationale. Include why a package/module boundary is insufficient or why a
runtime split is rejected/deferred.

## Compatibility

Document API, event, database, metric, runbook, deployment, and downstream compatibility impact.

## Validation

List local checks, CI checks, load/failure evidence, and rollback evidence.

## Catalog Update

Update `docs/architecture/runtime-boundary-decision-catalog.json` with the service path,
status, decision record path, in-process evidence, runtime drivers, and owner.
