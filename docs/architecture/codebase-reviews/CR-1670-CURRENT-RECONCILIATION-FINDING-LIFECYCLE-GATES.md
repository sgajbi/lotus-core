# CR-1670: Current Reconciliation Finding Lifecycle Gates

## Finding

Reconciliation run-list status, open counts, top blocker, and publication gate were derived from the
immutable error and warning totals stored when each run completed. Resolving, waiving, or
suppressing findings therefore could not clear the current gate. Reading a page one run at a time
would have introduced an N+1 query, while an in-place resolution committed after the response
timestamp could make list items contradict an as-of summary.

## Resolution

Query Control Plane now reads lifecycle-aware finding summaries for the bounded run page in one
grouped statement. Each run exposes current open and blocking counts, severity counts, and the top
blocking finding. Bundle status, gate, evidence timestamp, counts, and deterministic identity derive
from those current summaries. The existing run `summary` is preserved unchanged as completion-time
history, and terminal run failures continue to block even when findings close.

Effective lifecycle SQL treats a terminal finding as closed only when `resolved_at` is at or before
the response snapshot. A resolution committed concurrently after that timestamp remains open in
that response; item projection masks the future transition and a subsequent response observes the
closed state. Deterministic top finding selection uses severity, creation time, and persistence id
within each run.

## Compatibility

The run-record contract adds current lifecycle fields. Existing routes, filters, paging, immutable
summary values, persistence schema, migrations, Kafka contracts, product ownership, and runtime
topology are unchanged. Gate values and evidence identities intentionally change after finding
lifecycle transitions.

Existing run-id and finding-severity indexes support the route-bounded grouped read, so no index or
migration is added without representative plan evidence. Domain-product declarations and
supported-feature status do not change. OpenAPI descriptions, RFC/context, review ledger, and the
financial-reconciliation wiki change because the response semantics changed.

## Validation

- application and SQL-adapter tests for empty, closed, active, paged, as-of, and grouped behavior;
- API route contract proof for additive fields;
- real PostgreSQL mixed `OPEN`, `RESOLVED`, `WAIVED`, and `SUPPRESSED` lifecycle proof;
- two-session concurrent-resolution proof across consecutive response snapshots;
- MyPy, Ruff, operations contract, OpenAPI, RFC-0083, source-product, architecture, docs/wiki, and
  protected CI gates before closure.

Issue: #861.
