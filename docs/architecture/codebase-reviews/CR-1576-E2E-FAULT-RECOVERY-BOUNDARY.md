# CR-1576: E2E Fault-Recovery Boundary

## Objective

Make destructive end-to-end fault scenarios self-reconciling so one failed assertion cannot leave
shared infrastructure unavailable for the remainder of the suite.

## Finding

The PostgreSQL outage scenario stopped the Compose service and restored it with the legacy
`docker compose start` command. The exact-main E2E lane then timed out waiting for PostgreSQL and
left it stopped. The original failure cascaded into dependent failures and 46 setup errors, hiding
the root cause and making the lane non-deterministic.

The scenario also placed cleanup at the end of the successful path. Any assertion or readiness
failure before that block bypassed recovery of PostgreSQL and its dependent Core services.

## Change

1. Added a runtime-owned test-support boundary for destructive Compose fault injection.
2. Reconciled the stopped service with `docker compose up --detach --no-deps --wait`, followed by a
   database-backed readiness probe.
3. Restarted the governed E2E recovery service set and verified every service readiness endpoint.
4. Made cleanup unconditional and idempotent while preserving an earlier test failure as primary.
5. Moved runtime lifecycle support and its tests into mirrored `test_support/runtime` packages
   instead of extending the existing flat test-support root.
6. Added focused tests for command order, successful cleanup, dual-failure diagnostics, and cleanup
   failure propagation.

## Validation

- focused runtime recovery unit tests: `4 passed`;
- focused Ruff lint and format checks passed;
- strict MyPy, documentation gates, and the exact-main E2E lane are required before closure; and
- the #719 remote feature lane remained green independently of this fix-forward branch.

## Compatibility

No production API, event, database, image, deployment, or downstream contract changed. This change
only hardens test-runtime lifecycle behavior after an intentional infrastructure outage.

## Documentation Decision

Repository engineering context and codebase-review evidence changed because this is a repeatable CI
and test-lifecycle rule. README, wiki, API inventory, supported features, and operator runbooks do
not change because production behavior and operator workflows are unchanged.
