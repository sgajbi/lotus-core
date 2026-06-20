# CR-1112 Latency Portfolio Timeseries Profile

Date: 2026-06-20

## Scope

The PR Merge Gate latency profile for `lotus-core` includes a real
`/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` call. The CI latency seed
uses `DEMO_DATA_PACK_HISTORY_DAYS=365`, so the gate must exercise a deterministic supported
analytics window rather than a relative horizon that can resolve outside the materialized seed
coverage.

## Change

- Changed the `analytics_portfolio_timeseries` latency case from `period: one_year` to an explicit
  90-day `window` ending at the resolved runtime `as_of_date`.
- Kept the endpoint in the enforced latency profile with the existing 30 measured runs and p95
  budget.
- Added non-2xx response-body sampling to latency JSON evidence so future gate failures include the
  API validation or data-quality detail needed for fix-forward work.
- Added unit coverage for the deterministic portfolio analytics window and response-error evidence
  sampling.

## Evidence

The local proof for this slice is:

- `python -m pytest tests/unit/scripts/test_latency_profile.py -q`
- `python -m ruff check scripts/latency_profile.py tests/unit/scripts/test_latency_profile.py`
- `python -m ruff format --check scripts/latency_profile.py tests/unit/scripts/test_latency_profile.py`

Remote proof is the PR Merge Gate latency job. The expected signal is 30/30 2xx measured calls for
`analytics_portfolio_timeseries` while preserving p95 enforcement and producing machine-readable
diagnostic evidence on any future non-2xx response.
