# CR-1203 Transaction Ledger Instrument Supportability

Date: 2026-06-30

## Scope

`TransactionLedgerWindow:v1` read-side supportability for returned transaction rows.

## Finding

GitHub issue #674 remains valid after the first write-side cost-consumer enforcement slice.
Historical transaction rows, or rows written through other paths, could still appear in the
transaction ledger as complete source evidence even when their `security_id` does not resolve to a
governed `instruments` master row.

That weakens downstream supportability because transaction-ledger consumers need to know whether
row-level product evidence has instrument-reference backing before using it for reporting, tax-lot,
performance-economics, or DPM workflows.

## Action Taken

Added returned-row instrument-reference supportability to `TransactionLedgerWindow:v1`:

1. transaction ledger reads now resolve returned row `security_id` values against the governed
   instrument master;
2. returned rows with missing instrument master references make the response
   `data_quality_status=PARTIAL`;
3. the response now includes bounded additive fields:
   - `reason_codes`,
   - `missing_instrument_reference_count`,
   - `missing_instrument_security_ids`;
4. pagination partiality and missing instrument references are both preserved in reason codes;
5. empty responses continue to return `UNKNOWN` with `TRANSACTION_LEDGER_EMPTY`.

The reusable platform pattern is that source-data products should keep legacy rows visible, but
they must surface degraded reference supportability instead of presenting unresolved reference data
as fully governed evidence.

## Compatibility

The API change is additive. Existing transaction rows, filters, pagination, sorting, linked
cashflow/cost evidence, reporting-currency restatement behavior, and database schema are preserved.

The intentional behavior change is that a returned ledger page with unresolved instrument master
references is now `PARTIAL` and carries explicit missing-security evidence.

## Evidence

Focused behavior proof:

- `python -m pytest tests/unit/services/query_service/services/test_transaction_metadata.py tests/unit/services/query_service/services/test_transaction_records.py tests/unit/services/query_service/services/test_transaction_service.py tests/unit/services/query_service/repositories/test_transaction_repository.py -q`
- Result: `73 passed`

Focused static proof:

- `python -m ruff check src/services/query_service/app/repositories/transaction_repository.py src/services/query_service/app/services/transaction_metadata.py src/services/query_service/app/services/transaction_reads.py src/services/query_service/app/services/transaction_records.py src/services/query_service/app/services/transaction_service.py src/services/query_service/app/dtos/transaction_dto.py tests/unit/services/query_service/services/test_transaction_metadata.py tests/unit/services/query_service/services/test_transaction_records.py tests/unit/services/query_service/services/test_transaction_service.py tests/unit/services/query_service/repositories/test_transaction_repository.py`
- Result: passed
- `python -m ruff format --check src/services/query_service/app/repositories/transaction_repository.py src/services/query_service/app/services/transaction_metadata.py src/services/query_service/app/services/transaction_reads.py src/services/query_service/app/services/transaction_records.py src/services/query_service/app/services/transaction_service.py src/services/query_service/app/dtos/transaction_dto.py tests/unit/services/query_service/services/test_transaction_metadata.py tests/unit/services/query_service/services/test_transaction_records.py tests/unit/services/query_service/services/test_transaction_service.py tests/unit/services/query_service/repositories/test_transaction_repository.py`
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

This slice covers transaction-ledger returned rows. CR-1204 adds the matching tax-lot read-side
supportability policy, and CR-1255 adds the raw transaction persistence policy for unresolved
instrument references.

## Documentation And Wiki Decision

Updated the implementation-backed transaction-ledger methodology and repo-authored mesh data
products wiki source because the source product contract now includes additive supportability
fields.

## Bank-Buyable Control Movement

This slice improves:

1. source-product supportability for unresolved instrument references,
2. downstream compatibility through additive response fields,
3. deterministic data-quality classification for legacy or orphan ledger rows,
4. a reusable read-side degraded-reference pattern for other Core source products.

This slice does not claim complete closure of issue #674 by itself; closure also depends on
CR-1201, CR-1204, and CR-1255 evidence.
