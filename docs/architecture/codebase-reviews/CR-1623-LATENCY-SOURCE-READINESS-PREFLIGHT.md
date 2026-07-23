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

Protected PR #821 run `29965622157` later reproduced the race after the original fix: one all-2xx
preflight sweep passed, but `analytics_position_timeseries` then returned seven consecutive 422
responses during measurement before recovering to 200. All successful timings remained inside the
420 ms budget. This proved query readiness can reopen immediately after one green observation.

## Change

The bounded source-readiness preflight after portfolio-context resolution and before warmup or
measurement now requires three consecutive ordered all-2xx sweeps. Any non-2xx or transport failure
resets the fence; a compose seed failure still propagates immediately, including after a green
sweep. The required sweep count and poll interval are additive CLI controls with governed defaults
of three and two seconds. Permanent failures time out with endpoint-specific diagnostics plus the
observed/required stability count. The CLI rejects a sweep count below one and a negative or
non-finite poll interval during argument parsing, before service readiness, seeding, context
resolution, or session setup; direct callers retain the same validation inside the helper.

## Compatibility

No API, OpenAPI, event, database, runtime topology, seed history, data-quality rule, latency budget,
warmup count, or measured-run count changed. HTTP 422 remains the correct application response when
analytics inputs are unavailable; only CI measurement orchestration now waits for query readiness.

README, wiki, API inventory, supported-feature, migration, and operator-runbook truth are unchanged.
Repository engineering context records the reusable separation between service health, ingestion
completion, point-in-time readiness, and readiness stability. No wiki publication is required.

## Validation

- `python scripts/development/repository_python.py -m pytest -W error
  tests/unit/scripts/test_latency_profile.py` (`33 passed`)
- focused Ruff lint and format checks
- strict MyPy on `scripts/operations/latency_profile.py`
- `git diff --check`
- exact-main `Main Releasability / Latency Gate` rerun is required after merge

The unit suite proves green-to-422 reset and three-sweep recovery, transport reset, permanent
non-success diagnostics, seed-failure propagation during the stability fence, exact case ordering
and poll cadence, option-specific fail-fast CLI rejection, default/positive/zero-delay CLI
acceptance, direct-helper invalid configuration rejection, health-case exclusion, and
readiness-before-measurement call order.
