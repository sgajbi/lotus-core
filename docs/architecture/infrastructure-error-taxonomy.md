# Infrastructure Error Taxonomy

## Purpose

Infrastructure adapters should translate concrete library failures into typed, source-safe errors
before application workflow policy handles them. This keeps retryability, audit persistence,
operator diagnostics, and API/worker mapping consistent without leaking credentials, connection
strings, request bodies, or raw payloads.

## Initial Taxonomy

The taxonomy will expand by adapter family. Current implemented type:

| Error | Reason codes | Usage |
| --- | --- | --- |
| `InfrastructureAuditWriteFailed` | `audit_session_unavailable`, `audit_persistence_failed` | Replay/audit store writes that cannot produce durable audit evidence. |

Future adapter slices should add typed database, Kafka/event-publisher, HTTP client, cache, storage,
and configuration failures only when a representative runtime path is moved behind that boundary.

## Mapping Guidance

- Infrastructure adapters should catch concrete library exceptions and raise typed infrastructure
  errors with safe `reason_code` values.
- Application workflows may map typed infrastructure errors to retry, DLQ, degraded response,
  operator attention, or structured API problem details.
- Logs and issue evidence should include the typed error class, safe reason code, correlation or
  replay identifiers when available, and no raw secret-bearing configuration or request payloads.
- Generic `RuntimeError` should not be introduced for infrastructure persistence or publishing
  failure paths when a typed error exists.

## Current Boundary

CR-1183 applies this policy to ingestion replay audit persistence:

- replay audit persistence now raises `InfrastructureAuditWriteFailed`;
- no-session and persistence-failure cases have distinct reason codes;
- existing successful audit write, metrics, replay IDs, and response behavior are unchanged.
