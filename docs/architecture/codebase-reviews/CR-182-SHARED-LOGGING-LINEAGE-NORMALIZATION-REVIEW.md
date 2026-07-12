# CR-182 Shared Logging Lineage Normalization Review

## Finding

Runtime logs still serialized the sentinel lineage values from the shared context variables. That meant transport, persistence, audit, and metrics could all be normalized while structured logs still showed fake `"<not-set>"` lineage.

## Change

- Normalized `correlation_id`, `request_id`, and `trace_id` inside `CorrelationIdFilter`
- Added unit proof that the filter emits `None` for unset lineage values

## Why it matters

Structured logs now align with the same lineage contract enforced at transport, audit, and persistence boundaries. Operators no longer have to treat log lineage as a separate, weaker contract.
