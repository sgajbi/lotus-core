# CR-1160 Latency Analytics Window Seed Alignment

Date: 2026-06-22

## Scope

Fix-forward for the PR Merge Gate latency profile used by `lotus-core`.

## Finding

PR #434 run `27916210920` failed only `PR Merge Gate / Latency Gate`. The latency artifact showed
that both analytics timeseries probes returned deterministic HTTP `422` responses:

- `analytics_portfolio_timeseries`: `0/30`, missing `USD/EUR` FX on `2026-03-21`
- `analytics_position_timeseries`: `0/30`, missing `USD/EUR` FX on `2026-03-21`

The bounded CI seed uses one year of deterministic demo data and business-day reference coverage.
The latency profile's 90-day relative analytics horizon could start on a weekend, which requested an
unsupported FX date even though the endpoint and service were otherwise healthy.

## Change

- Aligned the analytics latency window start to the next business day when the 90-day start lands on
  a weekend.
- Changed `analytics_position_timeseries` from a relative `period: three_months` request to the same
  explicit analytics window used by `analytics_portfolio_timeseries`.
- Preserved real endpoint calls, 30 measured runs, p95 budgets, and non-2xx response-body evidence.

## Behavior And Risk

This changes only the latency probe payloads. It does not change API contracts, service behavior,
database schema, seed data, or latency budgets. The profile continues to fail on non-2xx responses
and p95 budget breaches, but now measures a deterministic supported window inside seeded reference
coverage.

## Evidence

Local validation:

- `python -m pytest tests/unit/scripts/test_latency_profile.py -q`
- `python -m ruff check scripts/latency_profile.py tests/unit/scripts/test_latency_profile.py`
- `python -m ruff format --check scripts/latency_profile.py tests/unit/scripts/test_latency_profile.py`

Remote validation:

- PR Merge Gate latency job must rerun and pass on PR #434.

