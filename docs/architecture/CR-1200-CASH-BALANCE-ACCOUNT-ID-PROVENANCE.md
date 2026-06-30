# CR-1200 Cash Balance Account ID Provenance

Date: 2026-06-30

## Scope

`HoldingsAsOf:v1` cash-balance assembly for `GET /portfolios/{portfolio_id}/cash-balances`.

## Finding

GitHub issue #673 is valid. Cash-balance fallback resolution used
`transactions.settlement_cash_account_id` as the latest account identity for a cash instrument
when active `cash_account_masters` rows were missing. That transaction field is a string, not a
governed account-reference boundary by itself, so an orphan, stale, or mistyped settlement account
could be returned in `cash_account_id` without telling consumers that the identity was not
governed master data.

That is a reporting and supportability risk because downstream consumers can treat cash-balance
rows as account-level evidence.

## Action Taken

The fallback repository path now validates transaction-derived settlement account ids against
active and effective `cash_account_masters` before returning them:

1. the transaction cash instrument must match the cash-account master `security_id`,
2. the settlement cash account id must match `cash_account_masters.cash_account_id`,
3. the cash-account master row must be `ACTIVE`,
4. the cash-account master effective window must include the cash-balance `as_of_date`.

Cash-balance records now include additive provenance field `cash_account_id_source` with values:

1. `cash_account_master`,
2. `validated_transaction_mapping`,
3. `cash_security_fallback`.

When no active/effective master-backed identity exists, the response still preserves the legacy
cash-security fallback in `cash_account_id`, but marks `cash_account_id_source` as
`cash_security_fallback` and returns `data_quality_status=PARTIAL` instead of presenting the row as
fully governed.

## Compatibility

Existing consumers can continue reading `cash_account_id`; the API change is additive. The
intentional behavior change is that orphan transaction settlement account ids are no longer
promoted to governed cash-account identifiers, and unresolved cash-account identity is explicitly
partial quality.

## Evidence

Focused behavior proof:

- `python -m pytest tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/services/test_cash_balance_service.py -q`
- Result: `31 passed`
- `python -m pytest tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/services/test_cash_balance_service.py tests/integration/services/query_service/test_main_app.py::test_openapi_describes_reporting_and_enhanced_discovery_contracts -q`
- Result: `32 passed`

Focused static proof:

- `python -m ruff check src/services/query_service/app/services/cash_balance_service.py src/services/query_service/app/dtos/reporting_dto.py src/services/query_service/app/repositories/reporting_repository.py tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/services/test_cash_balance_service.py`
- Result: passed
- `python -m ruff format --check src/services/query_service/app/services/cash_balance_service.py src/services/query_service/app/dtos/reporting_dto.py src/services/query_service/app/repositories/reporting_repository.py tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/services/test_cash_balance_service.py tests/integration/services/query_service/test_main_app.py`
- Result: passed
- `make typecheck`
- Result: passed, no issues in 50 source files
- `make openapi-gate`
- Result: passed
- `make api-vocabulary-gate`
- Result: passed
- `make quality-wiki-docs-gate`
- Result: passed
- `git diff --check`
- Result: passed
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- Result: failed because the published GitHub wiki is not synchronized with repo-authored wiki
  source. Reported drift: `Data-Models.md`, `Event-Replay-Service.md`,
  `Financial-Reconciliation.md`, `Ingestion-Service.md`, `Mesh-Data-Products.md`,
  `Operations-Runbook.md`, `Outbox-Events.md`, `Validation-and-CI.md`.

## Residual Risk

This slice hardens the query-side read boundary. A future ingestion-side reference-integrity slice
should validate or persist deterministic orphan evidence at transaction ingestion time when
settlement cash-account references are supplied before cash-account master data arrives.

Issue #673 remains open for PR/CI/QA evidence.

## Bank-Buyable Control Movement

This slice improves:

1. reference-data correctness for cash-account identity,
2. source-product supportability through response-level provenance,
3. deterministic degraded posture for unknown account mappings,
4. reusable validation pattern for transaction-derived reference fallbacks.

It does not claim full bank-buyable readiness for `lotus-core`.
