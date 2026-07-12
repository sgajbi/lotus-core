# CR-074 Grafana Service Topology Review

## Scope
Review the live Grafana dashboard for post-RFC-81 service-topology visibility and align it to the current Prometheus scrape set.

## Findings
- `prometheus/prometheus.yml` already scrapes the post-RFC-81 service set, including:
  - `query_control_plane_service`
  - `event_replay_service`
  - `financial_reconciliation_service`
  - `portfolio_aggregation_service`
  - `valuation_orchestrator_service`
- The only bundled Grafana dashboard, `grafana/dashboards/portfolio_analytics.json`, was still too generic:
  - DB latency
  - outbox publish rate
  - total HTTP requests
  - pending outbox events
- That left operators without direct visibility into per-service request load and scrape availability for the actual split service topology.

## Changes
1. Added a service-scoped HTTP request-rate panel keyed by Prometheus `job`.
2. Added a service-availability panel keyed by Prometheus `job`.
3. Aligned the job filter exactly to the current scrape names from `prometheus/prometheus.yml`:
   - `ingestion_service`
   - `query_service`
   - `query_control_plane_service`
   - `event_replay_service`
   - `financial_reconciliation_service`
   - `persistence_service`
   - `position_calculator_service`
   - `pipeline_orchestrator_service`
   - `valuation_orchestrator_service`
   - `cashflow_calculator_service`
   - `cost_calculator_service`
   - `position_valuation_calculator`
   - `timeseries_generator_service`
   - `portfolio_aggregation_service`

## Validation
- Parsed `grafana/dashboards/portfolio_analytics.json` as valid JSON after the edit.
- Verified the new PromQL panel expressions use only live scrape job names from `prometheus/prometheus.yml`.

## Residual Risk
- This closes the biggest topology-visibility gap in the bundled dashboard, but it does not yet add domain-specific health panels for reconciliation backlog, replay pressure, or stage-gate state. Those should be handled as separate observability batches if operators need deeper runtime diagnosis from Grafana rather than the current scripts and APIs.
