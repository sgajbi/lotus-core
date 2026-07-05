# Scalability and Availability Standard Alignment

Service: lotus-core

This repository adopts the platform-wide standard defined in lotus-platform/Scalability and Availability Standard.md.

## Implemented Baseline

- Stateless service behavior with externalized durable state.
- Explicit timeout and bounded retry/backoff for inter-service communication where applicable.
- Health/liveness/readiness endpoints for runtime orchestration.
- Observability instrumentation for latency/error/throughput diagnostics.

## Required Evidence

- Compliance matrix entry in lotus-platform/output/scalability-availability-compliance.md.
- Service-specific tests covering resilience and concurrency-critical paths.

## Database Scalability Fundamentals

- Critical read/write paths require documented query plan review during change approval.
- Index strategy is mandatory for high-volume transaction, valuation, and time-series access patterns.
- Data growth assumptions are maintained per domain table and reviewed before capacity changes.
- Retention and archival policies are defined for high-volume historical and supportability data.

## Caching Policy Baseline

- lotus-core does not allow hidden in-memory caches for persistence-critical transaction, position, or valuation state.
- Any cache use must define TTL, invalidation ownership, and stale-read behavior before release.
- Invalidation ownership remains with the service that owns the source domain entity and write path.
- Reference-data caches must carry source version or effective timestamp metadata, verify the
  source version before serving fresh cached values when rule changes affect calculations, and emit
  bounded hit/miss/reload/stale/missing-rule metrics.

## Availability Baseline

- Internal SLO baseline: p95 synchronous query API latency < 500 ms for bounded read endpoints; error rate < 1%.
- Recovery assumptions: RTO 30 minutes and RPO 15 minutes for persistent stores backing core lotus-core services.
- Backup and restore validation is mandatory per environment and must be evidenced in runbooks/drills.

## Scale Signal Metrics Coverage

- lotus-core services expose `/metrics` for request latency/error/throughput and dependency counters.
- Platform-shared CPU/memory, DB, and queue depth/lag signals are collected via:
  - `lotus-platform/platform-stack/prometheus/prometheus.yml`
  - `lotus-platform/platform-stack/docker-compose.yml`
  - `lotus-platform/Platform Observability Standards.md`

## Deviation Rule

Any deviation from this standard requires ADR/RFC with remediation timeline.

