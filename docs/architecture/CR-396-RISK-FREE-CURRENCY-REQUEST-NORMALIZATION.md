# CR-396: Risk-Free Currency Request Normalization

Date: 2026-05-28

## Scope

Query-service risk-free rate source-data products:

1. `RiskFreeSeriesWindow`
2. `DataQualityCoverageReport` for risk-free coverage

## Finding

Risk-free rate product methods uppercased the request currency for source-data product identity and
response fields, but passed the raw request currency into repository lookups. Padded lower-case
values such as ` usd ` could therefore create a canonical-looking product response while querying
with non-canonical input, risking missed data, inconsistent fingerprint intent, and avoidable data
quality false negatives.

## Change

Reused the existing query-service `normalize_currency_code(...)` helper at the risk-free service
boundary. The normalized currency now drives the request fingerprint identifier, repository lookup,
coverage lookup, and returned product identity. Added direct coverage proving padded lower-case
`usd` resolves to repository calls with canonical `USD`.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/integration_service.py tests/unit/services/query_service/services/test_integration_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a source-data
product lookup correctness and identity consistency slice.
