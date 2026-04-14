# Temporal Vocabulary Standard

- Status: Draft
- Date: 2026-04-15
- Scope: `lotus-core`
- Governing RFC: `C:/Users/Sandeep/projects/lotus-platform/rfcs/RFC-0083-lotus-core-system-of-record-target-architecture.md`
- Related:
  - `docs/architecture/RFC-0083-target-state-gap-analysis.md`
  - `docs/architecture/RFC-0082-contract-family-inventory.md`
  - `docs/standards/api-vocabulary/README.md`

## Purpose

This is the RFC-0083 Slice 1 temporal vocabulary and schema policy for `lotus-core`.

It defines how `lotus-core` names time in public contracts, persistence models, source-data products,
and future migrations.

This slice does not rename fields, alter DTOs, change OpenAPI output, or add migrations. It records the
canonical vocabulary, classifies current temporal fields, and defines the guard plan for future code
changes.

## Canonical Terms

New downstream-facing contracts and source-data products must use these terms when the concept applies.

| Term | Meaning | Required where | Notes |
| --- | --- | --- | --- |
| `as_of_date` | Business date represented by a read product | snapshots, holdings, reporting source reads, analytics inputs | Request/read-model perspective. Do not use for transaction execution or settlement. |
| `valuation_date` | Date used for price, FX, or valuation state | valuation jobs, valuation-bearing read products, portfolio/position timeseries | Use when market value or valuation state is the primary temporal anchor. |
| `trade_date` | Date the trade occurred | transaction booking and position reconstruction | Current transaction contract uses `transaction_date`; new booking work must decide whether to keep `transaction_date` as legacy alias or migrate to `trade_date`. |
| `settlement_date` | Date cash/security settlement is expected or completed | transaction cash impacts, settlement-linked cash state, manage inputs | Must not be inferred from `trade_date`. |
| `booking_date` | Date a transaction or correction is recorded into the core ledger | booking, corrections, audit, transaction ledger products | Target term. Not yet a first-class persisted field in the current inventory. |
| `effective_date` | Business-effective date of a correction, simulation change, or state change | corrections, restatements, simulations | Must state whether the effect is real booking/correction or simulated. |
| `ingested_at` | Timestamp the source record entered Lotus | ingestion lineage and evidence bundles | Target term for source arrival into Lotus. |
| `observed_at` | Timestamp the upstream source/feed observed or emitted the data | market/reference feeds, replay/DLQ observation | Target term for source-observed time. Existing `source_timestamp` is legacy terminology. |
| `corrected_at` | Timestamp a correction was recorded | correction and restatement contracts | Target term. Not yet consistently present. |
| `restatement_version` | Version identifier for corrected historical truth | restated snapshots, exports, and source-data products | Target term. Not yet present in current models/contracts. |

## Naming Rules

1. Do not introduce a public field named only `date` unless the entity is itself a calendar date record
   and the field is local/private to that entity.
2. Do not introduce `timestamp` or `source_timestamp` in new downstream-facing contracts. Use
   `observed_at` for upstream/source observation and `ingested_at` for Lotus ingestion time.
3. Do not use `as_of_date` as a generic synonym for every date. It is a read-model representation date.
4. Do not use `business_date` when the meaning is actually valuation, trade, settlement, booking, or
   correction effectivity.
5. Use `start_date` and `end_date` only for request windows. Response records should use a domain term
   such as `valuation_date`, `series_date`, `position_date`, or `cashflow_date` until migrated.
6. Use `created_at` and `updated_at` only for row or resource lifecycle timestamps. They do not replace
   source lineage timestamps.
7. Every new source-data product must document its temporal scope, including request date, source
   observation time, ingestion time, and restatement behavior where applicable.

## Current Field Inventory And Decisions

### Keep As Canonical

These fields are already aligned with RFC-0083 and should remain canonical when their meaning matches
the definition.

| Field | Current evidence | Decision |
| --- | --- | --- |
| `as_of_date` | Read DTOs, reporting DTOs, integration/reference DTOs, snapshot DTOs | Keep. Use only for read-model representation date. |
| `valuation_date` | `PortfolioValuationJob`, valuation and analytics DTOs | Keep. Use for valuation-bearing work and products. |
| `settlement_date` | transaction DTOs and transaction model | Keep. Preserve separate settlement semantics. |
| `effective_date` | simulation change model and simulation DTOs | Keep with clearer documentation when real corrections are added. |
| `ingested_at` | ingestion and job paths | Keep and expand to source-data products. |
| `observed_at` | DLQ/ingestion operations evidence | Keep and use for new source-observed timestamps. |
| `created_at`, `updated_at` | model and support lifecycle fields | Keep for persistence/resource lifecycle only. |

### Keep With Domain-Specific Meaning

These fields are acceptable because they carry domain meaning, but future source-data product work must
document them explicitly.

| Field | Current evidence | Decision |
| --- | --- | --- |
| `business_date` | business-date ingestion, reconciliation controls, support diagnostics | Keep for calendar/control-day scope. Do not use for trade, settlement, or valuation semantics. |
| `position_date` | position history and position DTOs | Keep for position snapshot date. Slice 3 may align this with `as_of_date` at product boundary. |
| `price_date` | market price models and DTOs | Keep for price observation business date. Pair with `observed_at` when source observation time matters. |
| `rate_date` | FX rate models and DTOs | Keep for FX observation business date. Pair with `observed_at` when source observation time matters. |
| `cashflow_date` | cashflow model and buy/sell linkage DTOs | Keep for cashflow event date. Document settlement or booking relationship when cash ledger is hardened. |
| `acquisition_date` | lot state DTOs and lot-state model | Keep for lot acquisition semantics. |
| `open_date`, `close_date` | portfolio lifecycle | Keep for portfolio lifecycle. |
| `opened_on`, `closed_on` | cash account master | Keep for account lifecycle; future cleanup may align to `open_date`/`close_date` only if no semantic loss. |
| `maturity_date` | instrument master | Keep for contractual maturity. |
| `synthetic_flow_effective_date` | transaction cashflow DTO/model | Keep as a specific correction/CA effective-date variant until transaction booking hardening. |
| `watermark_date`, `earliest_impacted_date` | reprocessing/support paths | Keep as internal operational vocabulary. Do not expose as source-data product dates without definition. |

### Legacy Or Ambiguous

These fields are allowed only as current-state legacy or internal implementation detail until the
owning future slice changes them.

| Field | Current evidence | Decision | Owner slice |
| --- | --- | --- | --- |
| `source_timestamp` | reference-data DTOs and reference/series tables | Legacy accepted for existing reference contracts. New contracts must use `observed_at`; migrations should map `source_timestamp` to source-observed time. | Slice 7 |
| `series_date` | benchmark, index, and risk-free series DTOs/tables | Accept as current product-local term. Source-data product catalog must decide whether each series exposes `series_date`, `valuation_date`, or another domain-specific term. | Slice 6 or Slice 7 |
| `date` | `BusinessDate.date`, daily snapshots, position/portfolio timeseries | Legacy/internal depending on table. New public contracts must avoid bare `date`; source products must expose a domain term. | Slice 3, Slice 6, Slice 7 |
| `transaction_date` | transaction DTO/model and current query contracts | Current canonical API term. Slice 3 must decide whether this remains the ledger event timestamp or is migrated/mapped to `trade_date` plus `booking_date`. | Slice 3 |
| `snapshot_date` | reporting DTOs | Accept as response-local wording today. Future holdings/snapshot products should prefer `as_of_date` or explicit `snapshot_id` plus temporal scope. | Slice 6 |
| `projection_date` | cashflow projection DTOs | Accept for projection point date. Must remain core-derived projected cashflow state, not performance forecast semantics. | Slice 8 |
| `aggregation_date` | portfolio aggregation jobs | Internal job date. Do not expose as source-data product date. | Slice 10 |
| `submitted_from`, `submitted_to` | ingestion operations filters | Accept as operational filter timestamps. Do not use for source observation or ingestion event time. | Slice 4 |
| `replay_window_start`, `replay_window_end` | ingestion operations control | Accept as operational replay window timestamps. | Slice 4 |

### Missing Target Terms

| Term | Current state | Required decision |
| --- | --- | --- |
| `booking_date` | Not a first-class persisted field in current inventory | Slice 3 must define whether booking date is persisted, derived from ingestion/job lifecycle, or introduced first at contract level. |
| `corrected_at` | Not consistently present | Correction/restatement work must add this where historical truth can change. |
| `restatement_version` | Not present | Snapshot/export/source-data product work must define the version strategy before consumer migration. |

## Source Timestamp Decision

For Slice 1, `source_timestamp` is classified as legacy source-observed time.

The target name is `observed_at`.

Implementation rule:

1. new source-observation fields use `observed_at`,
2. existing `source_timestamp` fields remain stable until their owning product slice changes the
   contract or persistence model,
3. when a response contains both names during a migration, documentation must state that
   `source_timestamp` is the legacy name and `observed_at` is canonical,
4. generated OpenAPI vocabulary must not add new `source_timestamp` occurrences after this standard.

## Booking Date Decision

For Slice 1, `booking_date` is a target concept, not an immediate migration.

Implementation rule:

1. no schema change is made in Slice 1,
2. future transaction booking and portfolio reconstruction work must define `booking_date` before
   changing transaction ledger behavior,
3. `transaction_date` must not be overloaded to mean booking date,
4. if booking date is initially derived, the derivation must be documented in the product contract.

## Restatement Decision

For Slice 1, `restatement_version` is reserved as the canonical term for corrected historical truth.

Implementation rule:

1. source-data products that can change historical results must define whether they are restatable,
2. restatable products must eventually expose `restatement_version` or an equivalent version field
   mapped to that semantic,
3. downstream analytics services must not infer restatement by comparing payload timestamps.

## Guard

The practical guard is implemented as:

- `scripts/temporal_vocabulary_guard.py`
- `docs/standards/temporal-vocabulary-allowlist.json`

Guard requirements:

1. scan downstream-facing DTO and router modules for newly introduced bare `date`, `timestamp`, or
   `source_timestamp` fields,
2. allow current legacy fields through an explicit allowlist with owner slice and removal condition,
3. fail on new generic temporal names unless they are explicitly approved by this standard,
4. run in the fast contract/schema validation lane with OpenAPI and vocabulary gates,
5. update `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json` only through the existing
   generator when schema output actually changes.

Recommended command once implemented:

```powershell
python scripts/temporal_vocabulary_guard.py
```

The guard is also wired into `make lint` through `temporal-vocabulary-guard`.

## Validation Policy

For this Slice 1 documentation pass:

1. `git diff --check` is sufficient,
2. `python scripts/temporal_vocabulary_guard.py` proves the current allowlist and scanner agree,
3. no runtime tests are required,
4. no OpenAPI or vocabulary regeneration is required because no DTO/schema output changed.

For future Slice 1 runtime-adjacent changes:

1. run `python scripts/temporal_vocabulary_guard.py`,
2. run `python scripts/api_vocabulary_inventory.py --validate-only` when OpenAPI vocabulary changes,
3. run `python scripts/openapi_quality_gate.py` when route or schema documentation changes,
4. run targeted contract tests for any affected DTO or router.
