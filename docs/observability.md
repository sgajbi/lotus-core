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

## Current Gaps

The initial quality baseline records observability as a documentation and gate gap. Future slices
should add automated checks for correlation ID propagation, metrics cardinality, sensitive logging,
and health/readiness completeness.
