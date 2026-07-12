# CR-156 Outbox backlog and terminal failure observability review

## Scope

Outbox dispatcher operational visibility after introducing terminal `FAILED` rows.

## Findings

- The dispatcher now prevents permanently failing rows from poisoning the live `PENDING` queue, but operators still could not directly see:
  - how many rows had moved to durable `FAILED`
  - how old the oldest pending row was
- Existing dashboards only exposed:
  - pending count
  - published / failed / retried rates

That was insufficient to distinguish:
- healthy throughput
- transient retry pressure
- durable poison accumulation
- a quietly aging pending backlog

## Actions taken

- Added shared Prometheus gauges for:
  - `outbox_events_failed_stored`
  - `outbox_events_oldest_pending_age_seconds`
- Updated `OutboxDispatcher._read_pending_gauge()` to publish:
  - pending total
  - durable failed total
  - oldest pending age
- Added DB-backed integration proof that the gauge read reflects real pending/failed rows and oldest pending age.
- Surfaced the new metrics in Grafana on the existing outbox pressure panel.

## Result

Outbox operations now expose both:
- transport failure rate
- durable failure residue / backlog age

This makes the outbox path materially more operable under real failure conditions.
