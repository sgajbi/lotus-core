# CR-078 Financial Reconciliation Observability Review

## Scope
Add first-class Prometheus telemetry for `financial_reconciliation_service` and surface it in the bundled Grafana dashboard.

## Findings
- The service already exposed HTTP and generic runtime metrics, but it had no business-level telemetry for:
  - reconciliation run outcomes
  - reconciliation finding volume
  - reconciliation run duration
- That left operators dependent on database inspection or control-plane APIs to understand reconciliation behavior, even though the service is a post-RFC-81 control-plane component.

## Changes
1. Added shared Prometheus metrics in:
   - `src/libs/portfolio-common/portfolio_common/monitoring.py`
   - `financial_reconciliation_runs_total`
   - `financial_reconciliation_findings_total`
   - `financial_reconciliation_run_duration_seconds`
2. Instrumented the reconciliation service at the run-finalization boundary in:
   - `src/services/financial_reconciliation_service/app/services/reconciliation_service.py`
3. Added unit coverage proving the metrics hook is invoked for completed reconciliation runs:
   - `tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
4. Extended the bundled Grafana dashboard with:
   - reconciliation run outcomes panel
   - reconciliation findings panel

## Validation
- `python -m pytest tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/monitoring.py src/services/financial_reconciliation_service/app/services/reconciliation_service.py tests/unit/services/financial_reconciliation_service/test_reconciliation_service.py`
- parsed `grafana/dashboards/portfolio_analytics.json` as valid JSON after the dashboard update

## Residual Risk
- This adds service-level business telemetry, but it does not yet expose backlog gauges for reconciliation queue depth because the service is request-driven rather than worker-claim based. If operators later need richer pipeline-state views, add them as a separate batch rather than overloading these run-completion metrics.
