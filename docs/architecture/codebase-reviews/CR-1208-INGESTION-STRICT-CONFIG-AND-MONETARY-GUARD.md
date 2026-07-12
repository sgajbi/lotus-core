# CR-1208 Ingestion Strict Configuration And Monetary Guard

Date: 2026-06-30

## Objective

Advance GitHub issue #600 by making ingestion resilience configuration fail fast in strict and
non-local profiles, while restoring `make monetary-float-guard` as a reliable high-signal CI gate.

## Change

- Added `IngestionConfigurationError` and profile-aware strict ingestion configuration validation.
- Invalid ingestion int, float, decimal, boolean, choice, and calculator-lag JSON settings now log
  and fall back in local profiles, and raise in strict mode.
- Strict mode is enabled by `LOTUS_CORE_STRICT_CONFIG_VALIDATION=true` or a non-local `ENVIRONMENT`.
- Added lower-bound validation for resilience-critical ingestion settings covering rate limits,
  replay caps, DLQ budgets, worker polling and batching, valuation scheduler dispatch, operating
  bands, and calculator lag thresholds.
- Reworked the monetary float guard from substring matching to token-aware identifier matching, so
  financial identifiers still fail while operational delay/seconds/parser conversions do not.
- Added stale allowlist rejection and removed stale monetary-float allowlist entries; the current
  baseline is zero active findings and zero allowlisted suppressions.

## Expected Improvement

Production and non-local deployments no longer silently boot with malformed ingestion resilience
settings. CI monetary precision enforcement no longer fails on operational duration conversions and
no longer carries stale suppressions.

## Tests Added

- Strict profile rejects invalid numeric seconds settings.
- Strict profile rejects out-of-range integer settings.
- Strict profile rejects invalid calculator lag JSON.
- Local profile logs explicit fallback for invalid settings.
- Monetary float guard catches money-like float conversions.
- Monetary float guard ignores operational delay conversions.
- Monetary float guard ignores generic parser `value = float(raw)` conversions.
- Monetary float guard fails stale allowlist entries.

## Validation Evidence

- `python -m pytest tests/unit/services/ingestion_service/test_settings.py tests/unit/scripts/test_monetary_float_guard.py -q`
  passed with 13 tests.
- `make monetary-float-guard` passed with `Findings=0, allowlisted=0`.
- `python -m ruff check scripts/check_monetary_float_usage.py tests/unit/scripts/test_monetary_float_guard.py src/services/ingestion_service/app/settings.py tests/unit/services/ingestion_service/test_settings.py`
  passed.
- `python -m ruff format --check scripts/check_monetary_float_usage.py tests/unit/scripts/test_monetary_float_guard.py src/services/ingestion_service/app/settings.py tests/unit/services/ingestion_service/test_settings.py`
  passed.
- `make quality-ruff-gate` passed.
- `make quality-ruff-format-gate` passed with 1,236 files already formatted.
- `make typecheck` passed with 50 source files checked.
- `make quality-complexity-gate` passed.
- `make quality-maintainability-gate` passed.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed.

## Downstream Compatibility

Default local behavior remains fallback with explicit warning, and existing unset env defaults are
unchanged. The intentional behavior change is that strict and non-local profiles now fail startup
when invalid resilience-related ingestion environment values are present. There is no API,
OpenAPI, database schema, Kafka contract, or downstream response-shape change.

## Documentation And Wiki

Repository context, the codebase review ledger, quality scorecard, refactor health report, and
monetary precision standard were updated. No repo-local wiki page changed because this slice did
not add or change an operator command, endpoint, runbook workflow, or published API contract.

## Remaining Follow-Up

Issue #600 remains open for query-service and query-control-plane settings modules, shared
configuration-pattern adoption where appropriate, and broader profile-by-profile coverage.
