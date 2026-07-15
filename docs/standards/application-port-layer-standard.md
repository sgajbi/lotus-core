# Application Port Layer Standard

Application use cases must depend on typed capability ports before depending on concrete
infrastructure.

## Required Pattern

1. Name ports by the capability required by the use case, not by the current implementation.
2. Put service-local ports in `src/services/<service>/app/ports/`.
3. Put reusable cross-service ports under the narrowest shared bounded context that has multiple
   demonstrated application consumers. Keep a single-consumer port in its owning service even when
   its domain records or infrastructure adapter are shared.
4. Keep concrete repositories, Kafka producers, helper functions, and runtime providers behind
   adapters or provider modules.
5. Use fake ports in unit tests for application orchestration and failure behavior.
6. Add the capability to `docs/architecture/application-port-capability-catalog.json` when it is a
   representative or governed pattern.
7. Add or extend a deterministic architecture guard when direct concrete dependencies are likely to
   return.

## Current Governed Families

The current representative families are:

1. audit and idempotency stores,
2. event publisher ports,
3. repository reader/writer ports,
4. clock, monotonic timer, and ID provider ports.

Shared domain records do not make a port shared automatically. For example, generation and
aggregation reuse timeseries market-data records and a SQL reader, while
`portfolio_derived_state_service.app.ports.timeseries_market_data` remains service-local because only
portfolio aggregation depends on that application capability.

Existing runtime-provider ports that predate the `app/ports` convention may remain in dedicated
provider modules while they are cataloged as `clock-id-provider` capabilities. New repository,
store, downstream-client, cache, and unit-of-work ports should use `app/ports` from the start.

## Enforcement

`make architecture-guard` validates the catalog and runs the dependency-inversion and specific
port-regression guards.

The catalog is not a claim that every application dependency has been inverted. It is the governed
entrypoint for implemented representative ports and the pattern future slices must extend.

See `docs/standards/application-dependency-inversion-standard.md` for the protected application
service dependency rules.

See `docs/standards/application-workflow-policy-standard.md` for reusable application command
context, idempotency, audit, and recovery-evidence workflow rules.

## Runtime Boundary

Application ports are an in-process design boundary. A runtime service split requires separate
evidence for scaling, failure isolation, data ownership, security isolation, and operational
supportability.
