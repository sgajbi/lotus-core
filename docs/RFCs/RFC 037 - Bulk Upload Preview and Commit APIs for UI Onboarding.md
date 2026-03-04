# RFC 037 - Bulk Upload Preview and Commit APIs for UI Onboarding

## Status
Accepted

## Context
UI-led onboarding requires file-based upload flows that can validate data before publishing events into lotus-core. Existing ingestion APIs accept JSON payloads but do not provide row-level validation feedback for CSV/XLSX uploads.

## Decision
Add two ingestion APIs in `ingestion_service`:

- `POST /ingest/uploads/preview`
  - Input: multipart form (`entityType`, `file`, optional `sampleSize`)
  - Behavior: parse CSV/XLSX, validate each row against existing ingestion DTO contracts, return row-level errors and normalized sample rows.
  - No Kafka publish.
- `POST /ingest/uploads/commit`
  - Input: multipart form (`entityType`, `file`, optional `allowPartial`)
  - Behavior: validate rows, publish valid rows to existing topic routes.
  - Default is strict (`allowPartial=false`) and rejects mixed-validity files with `422`.
  - `allowPartial=true` publishes valid rows and reports skipped invalid rows.

Supported entities:

- `portfolios`
- `instruments`
- `transactions`
- `market_prices`
- `fx_rates`
- `business_dates`

## Rationale
- Reuses canonical DTO validation to avoid divergence between JSON and file ingestion.
- Preserves existing downstream event contracts and consumers.
- Enables UI/lotus-gateway guided correction loops with deterministic error reporting.

## Implementation Notes
- Parser supports `.csv` and `.xlsx`.
- Header normalization supports snake_case and camelCase field names.
- Row numbers in errors are 1-based and include header offset.
- Empty file uploads or uploads with no valid rows are rejected with explicit errors.

## Consequences
### Positive
- Faster onboarding of portfolios/transactions through UI file flows.
- Reduced support burden by returning structured row-level validation errors.
- No architectural churn in persistence/calculator/query services.

### Negative
- Adds dependency on `openpyxl` in ingestion service.
- Validation complexity now includes parser behavior (handled with unit/integration coverage).
