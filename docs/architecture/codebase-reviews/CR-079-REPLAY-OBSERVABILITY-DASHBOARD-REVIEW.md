# CR-079 Replay Observability Dashboard Review

## Scope
Surface the existing ingestion replay telemetry in the bundled Grafana dashboard so replay pressure is visible without starting from the control-plane API.

## Findings
- `portfolio_common.monitoring` already exposed replay telemetry:
  - `ingestion_replay_audit_total`
  - `ingestion_replay_duplicate_blocked_total`
  - `ingestion_replay_failure_total`
- Those metrics were already incremented by `ingestion_job_service`, but the bundled Grafana dashboard did not visualize them.
- That left operators with no immediate replay-pressure panel even though the instrumentation already existed.

## Changes
1. Added a replay audit outcomes panel keyed by:
   - `recovery_path`
   - `replay_status`
2. Added a replay duplicate/failure pressure panel keyed by:
   - `recovery_path`
   - `replay_status`
3. Kept this slice dashboard-only because the underlying metrics were already live.

## Validation
- Parsed `grafana/dashboards/portfolio_analytics.json` as valid JSON after the update.
- Verified the new PromQL expressions reference only live replay metrics exported by the current codebase.

## Residual Risk
- This closes the dashboard visibility gap, not the metrics-production gap.
- If operators later need correlation to ingestion backlog or DLQ volume on the same screen, add that as a separate dashboard composition slice instead of overloading these replay-focused panels.
