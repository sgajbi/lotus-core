# CR-1172 Metric Cardinality Hardening

## Objective

Begin GitHub issues #494 and #495 by reducing production Prometheus metric cardinality in shared
Lotus Core observability paths.

## Expected Improvement

- HTTP request metrics use FastAPI route templates instead of raw request paths.
- Unmatched HTTP routes use one fixed fallback bucket.
- Production Prometheus metric definitions no longer expose `portfolio_id` or `security_id` labels.
- Portfolio/security drilldown remains available through structured logs and support APIs rather
  than unbounded metric labels.

## Changes

- Added `http_metric_path_template(...)` in `portfolio_common.http_app_bootstrap`.
- Routed standard HTTP request counters and histograms through route-template labels.
- Removed business-key labels from stale-epoch, reprocessing epoch, watermark-lag, and valuation
  job metrics.
- Added a shared monitoring guard test that rejects production metric labels named `portfolio_id`
  or `security_id`.

## Compatibility

No product API, OpenAPI route, database schema, Kafka payload, support API response, or downstream
business contract changed. Prometheus label shape changed intentionally for the affected metrics;
dashboards and alerts should use bounded labels and support APIs for key-level drilldown.

## Validation

- `python -m pytest tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/unit/libs/portfolio-common/test_monitoring.py tests/unit/libs/portfolio-common/test_reprocessing.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py::test_calculate_re_emits_and_increments_metric_for_backdated_event tests/unit/services/valuation_orchestrator_service/core/test_valuation_scheduler.py::test_scheduler_creates_position_aware_backfill_jobs -q`
- `python -m pytest tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py -q`

## Documentation And Wiki Decision

Updated `docs/observability.md`, the position valuation operations guide, this ledger entry, and the
quality scorecard/health report. No wiki source change is required because the repo wiki does not
currently enumerate the changed Prometheus metric labels.

## Follow-Up

Issues #494 and #495 remain open pending PR, GitHub CI, and QA evidence. Broader follow-up should
extend the metric-cardinality guard to additional unbounded identifiers such as run IDs, replay IDs,
page tokens, request IDs, and raw error strings.
