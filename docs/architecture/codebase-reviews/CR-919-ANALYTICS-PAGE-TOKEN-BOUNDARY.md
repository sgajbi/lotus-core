# CR-919: Analytics Page Token Boundary

Date: 2026-06-04

## Scope

Move analytics timeseries page-token HMAC envelope handling out of
`AnalyticsTimeseriesService` without changing cursor payload semantics, invalid-signature error
mapping, malformed-token error mapping, page-token call sites, API contracts, or database schema.

## Finding

`AnalyticsTimeseriesService` still owned base64 envelope encoding, payload serialization, SHA-256
HMAC signing, signature comparison, blank-token handling, and malformed-token handling inline.
That security-sensitive cursor policy is stable cross-cutting behavior and should be isolated from
timeseries orchestration.

## Action

Extracted `analytics_page_tokens.py` with helpers for:

- deterministic payload serialization,
- deterministic envelope encoding,
- SHA-256 HMAC signature generation,
- constant-time signature comparison,
- blank-token decoding,
- malformed-token and invalid-signature error classification.

The service keeps thin `_encode_page_token` and `_decode_page_token` wrappers so existing
orchestration and tests continue to use the same service boundary while domain errors are still
mapped to `AnalyticsInputError`.

## Result

`analytics_timeseries_service.py` shrank from 1,770 SLOC after CR-918 to 1,751 SLOC after CR-919.
The new `analytics_page_tokens.py` module reports `A (59.76)` under Radon maintainability, and
all page-token helper functions report A-ranked cyclomatic complexity. `analytics_timeseries_service.py`
remains `C (0.00)` under Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 82 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_page_tokens.py tests\unit\services\query_service\services\test_analytics_page_tokens.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_page_tokens.py tests\unit\services\query_service\services\test_analytics_page_tokens.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_page_tokens.py`
  => `analytics_timeseries_service.py` 1,751 SLOC; `analytics_page_tokens.py` 41 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_page_tokens.py -s`
  => service `C (0.00)`, helper `A (59.76)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_page_tokens.py -s`
  => page-token service wrappers and helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal cursor-token security helper refactor that
preserves API contracts, supported features, operator workflows, pagination behavior, and public
documentation truth.
