# Infrastructure Error Taxonomy

Infrastructure adapters must translate concrete library failures into typed infrastructure errors
before application workflows decide retry, DLQ, degraded response, operator attention, or API
problem-detail behavior.

## Current Shared Taxonomy

The shared taxonomy lives in `portfolio_common.infrastructure_errors`.

| Error | Dependency | Retryable | Typical Source |
| --- | --- | --- | --- |
| `DatabaseUnavailable` | database | yes | transient database/session outage |
| `DatabaseIntegrityViolation` | database | no | constraint or integrity failure |
| `KafkaPublishBackPressure` | kafka | yes | producer local queue saturation |
| `KafkaPublishFailed` | kafka | no | terminal publish or serialization failure |
| `KafkaPublishUncertain` | kafka | yes | flush timeout or undelivered records |
| `InfrastructureAuditWriteFailed` | database | yes | audit persistence failure |

## Required Pattern

1. Concrete adapters catch library exceptions at the boundary.
2. Adapters raise or return typed infrastructure errors with safe reason codes.
3. Diagnostics may include bounded identifiers such as topic name, retryability, timeout, or
   correlation state.
4. Diagnostics must not include connection strings, credentials, request bodies, event payloads,
   raw SQL text, stack traces, or client-sensitive values.
5. Application code maps typed infrastructure errors to existing retry, DLQ, API, or operator
   contracts without inspecting concrete library exception classes.

## Application Error Mapping Guidance

Infrastructure errors are not API problem details by themselves. Application services should map
them into the existing workflow contract for the operation:

1. retryable publish back-pressure can become a retryable publish failure response or worker retry,
2. uncertain delivery confirmation should preserve ambiguous publish state and operator recovery
   evidence,
3. audit write failure should fail closed for replay workflows that require durable evidence,
4. terminal infrastructure defects should use bounded reason codes and avoid raw exception text in
   operator-facing diagnostics.

The broader application/API error taxonomy remains tracked separately by GitHub issue #643.

## Current Representative Coverage

1. `KafkaEventPublisher` maps publish back-pressure, terminal publish failure, and uncertain flush
   delivery into typed Kafka infrastructure errors while preserving existing event-publish result
   statuses.
2. Replay audit persistence maps database/audit write failure into
   `InfrastructureAuditWriteFailed` and preserves fail-closed replay behavior.

## Runtime Boundary

This taxonomy changes internal diagnostics and adapter contracts only. It does not change route
paths, event topics, event payloads, database schema, retry budgets, or deployment topology.
