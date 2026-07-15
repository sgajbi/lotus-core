# CR-1623: Latency Source Readiness Preflight

## Objective

Prevent the compose-backed latency gate from measuring endpoints while asynchronous valuation and
timeseries materialization is still converging, without weakening latency budgets or API failure
semantics.

## Finding

Main Releasability run `29377270994` at exact main SHA
`0d1420710fad5f7780a6fa89290708312ba493bf` failed `Main Releasability / Latency Gate` after
`analytics_position_timeseries` returned HTTP 422 `QCP_ANALYTICS_INSUFFICIENT_DATA` for 9 of 30
measured requests. The remaining 21 requests returned 200 with p95 30.96 ms against the unchanged
420 ms budget.

The gate waited for `demo_data_loader` to exit successfully, but that loader runs with
`ingest_only=true`. Its exit proves source ingestion completed; it does not prove downstream
valuation and position-timeseries materialization is query-ready. Compose logs confirmed those
consumers were still processing during measurement.

## Change

Added a bounded source-readiness preflight after portfolio-context resolution and before warmup or
measurement. It probes every measured non-health contract in one sweep until all return 2xx.
Transient non-success responses may converge before timing starts; permanent HTTP or transport
failures time out with endpoint-specific diagnostics. The existing compose seed-failure callback
continues to propagate immediately.

## Compatibility

No API, OpenAPI, event, database, runtime topology, seed history, data-quality rule, latency budget,
warmup count, or measured-run count changed. HTTP 422 remains the correct application response when
analytics inputs are unavailable; only CI measurement orchestration now waits for query readiness.

README, wiki, API inventory, supported-feature, migration, and operator-runbook truth are unchanged.
Repository engineering context records the reusable separation between service health, ingestion
completion, and data-product readiness.

## Validation

- `python -m pytest tests/unit/scripts/test_latency_profile.py -q`
- focused Ruff lint and format checks
- `git diff --check`
- exact-main `Main Releasability / Latency Gate` rerun is required after merge

The unit suite proves transient 422-to-200 convergence, permanent non-success diagnostics,
transport-failure diagnostics, seed-failure propagation, health-case exclusion, and readiness-before-
measurement call order.
