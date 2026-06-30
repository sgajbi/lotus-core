# lotus-core Observability

## Objective

`lotus-core` should provide structured, correlation-aware operational evidence for API calls,
workers, ingestion, reconciliation, supportability, and source-data product freshness.

## Baseline Expectations

1. Every request supports or propagates correlation ID.
2. Logs are structured and avoid sensitive data.
3. Health, readiness, liveness, and metrics endpoints are separated from public business APIs.
4. Operational supportability APIs expose evidence timestamps, stale/backlog state, and reason
   codes where relevant.
5. Source-data product responses expose runtime metadata and data-quality posture.
6. Prometheus metric labels use bounded operational dimensions. Portfolio, security, run, replay,
   page-token, or raw-path drilldown belongs in structured logs, audit records, support APIs, or
   queryable operational tables, not production metric labels.
7. HTTP request metrics use FastAPI route templates such as
   `/portfolios/{portfolio_id}/positions` and fall back to a fixed unmatched bucket for routes that
   do not resolve.
8. API services and health-only worker web apps use the standard HTTP bootstrap so `/metrics`,
   `/health/live`, and `/health/ready` responses carry correlation, request, trace, and
   `traceparent` headers and emit route-template HTTP metrics.

## Current Gaps

The initial quality baseline records observability as a documentation and gate gap. The shared
monitoring unit guard now rejects `portfolio_id` and `security_id` as production Prometheus metric
labels. Future slices should add automated checks for additional high-cardinality identifiers,
correlation ID propagation, sensitive logging, health/readiness completeness, and inventory
enforcement that prevents new runtime web apps from bypassing the shared bootstrap.
