# Ingestion SLO Alerts and Dashboards

This runbook defines baseline operational thresholds for ingestion reliability.

## SLO Signals

- `failure_rate_1h`: `failed_jobs / total_jobs` over the last 60 minutes.
- `p95_queue_latency_seconds`: 95th percentile of `completed_at - submitted_at`.
- `backlog_age_seconds`: age of oldest non-terminal ingestion job (`accepted|queued`).
- `consumer_dlq_events`: count/rate of `consumer_dlq_events` records.
- `ingestion_replay_duplicate_blocked_total`: duplicate deterministic replay attempts blocked.
- `ingestion_replay_failure_total`: replay attempts that failed or were not replayable.

## Recommended Thresholds

- Failure rate: warn at `> 1%`, critical at `> 3%`.
- Queue latency p95: warn at `> 3s`, critical at `> 5s`.
- Backlog age: warn at `> 120s`, critical at `> 300s`.
- Consumer DLQ rate: warn at `>= 1 event / 10m`, critical at `>= 5 events / 10m`.
- Duplicate replay blocked: warn at `>= 1 / 15m`, critical at `>= 3 / 15m`.
- Replay failures/not_replayable: warn at `>= 2 / 15m`, critical at `>= 5 / 15m`.

## Prometheus Rule Examples

```yaml
groups:
  - name: lotus_core_ingestion_slo
    rules:
      - alert: LotusCoreIngestionFailureRateCritical
        expr: (sum(rate(ingestion_jobs_failed_total[1h])) / clamp_min(sum(rate(ingestion_jobs_created_total[1h])), 1)) > 0.03
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Lotus Core ingestion failure rate above 3% (1h)"

      - alert: LotusCoreIngestionQueueLatencyP95Critical
        expr: histogram_quantile(0.95, sum by (le) (rate(http_request_latency_seconds_bucket{service="ingestion_service",path=~"/ingest/.*"}[10m]))) > 5
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Lotus Core ingestion API p95 latency above 5s"

      - alert: LotusCoreIngestionBacklogAgeCritical
        expr: ingestion_backlog_age_seconds > 300
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Lotus Core ingestion backlog age above 300s"

      - alert: LotusCoreIngestionReplayDuplicateBlockedWarning
        expr: sum(rate(ingestion_replay_duplicate_blocked_total[15m])) >= 1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Lotus Core replay duplicate blocking detected"

      - alert: LotusCoreIngestionReplayFailureCritical
        expr: sum(rate(ingestion_replay_failure_total[15m])) >= 5
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Lotus Core replay failures/not-replayable events are elevated"
```

## Dashboard Panels

- Ingestion jobs created/failed/retried by endpoint and entity type.
- Ingestion mode state (`normal=0`, `paused=1`, `drain=2`).
- Backlog age trend and backlog size (`accepted + queued`).
- Consumer DLQ events by original topic and consumer group.
- Replay duplicate-blocked and replay-failure trend by recovery path.

## Operational API Surfaces
These protected operational endpoints are served by `event_replay_service`; `ingestion_service`
retains only canonical write-ingress APIs.

- `GET /ingestion/health/summary`
- `GET /ingestion/health/lag`
- `GET /ingestion/health/slo`
- `GET /ingestion/health/backlog-breakdown`
- `GET /ingestion/health/stalled-jobs`
- `GET /ingestion/dlq/consumer-events`
- `GET /ingestion/audit/replays`
- `GET /ingestion/audit/replays/{replay_id}`
- `GET /ingestion/ops/control`
- `PUT /ingestion/ops/control`

## Triage Workflow

- Start with `/ingestion/health/slo` to confirm threshold breaches.
- Use `/ingestion/health/backlog-breakdown` to isolate the worst endpoint/entity group.
- Use `/ingestion/health/stalled-jobs` to identify the oldest impacted jobs and act on the suggested actions.
- Validate consumer fault patterns via `/ingestion/dlq/consumer-events`.
- Use `/ingestion/audit/replays` to detect duplicate-blocked/failure replay patterns and recovery-path hotspots.
