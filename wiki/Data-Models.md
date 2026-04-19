# Data Models

## Purpose

`lotus-core` owns the canonical operational data model for foundational portfolio and transaction
state.

This page is an orientation map, not a schema dump. For exact fields and indexes, use:

- [database_models.py](../src/libs/portfolio-common/portfolio_common/database_models.py)
- [RFC-0083 Portfolio Reconstruction Target Model](../docs/architecture/RFC-0083-portfolio-reconstruction-target-model.md)
- [RFC-0083 Ingestion Source Lineage Target Model](../docs/architecture/RFC-0083-ingestion-source-lineage-target-model.md)
- [RFC-0083 Reconciliation Data Quality Target Model](../docs/architecture/RFC-0083-reconciliation-data-quality-target-model.md)
- [RFC-0083 Source Data Product Catalog](../docs/architecture/RFC-0083-source-data-product-catalog.md)
- [RFC-0083 Market Reference Data Target Model](../docs/architecture/RFC-0083-market-reference-data-target-model.md)

## Core model groups

### Portfolio and reference masters

Primary master and reference tables include:

- `portfolios`
- `instruments`
- `portfolio_benchmark_assignments`
- `benchmark_definitions`
- `index_definitions`
- `classification_taxonomies`
- `cash_account_masters`
- `instrument_lookthrough_components`

These tables define the static or slowly changing portfolio and instrument context consumed by
downstream operational and analytics-input contracts.

### Transactions and cashflows

Primary transaction-flow tables include:

- `transactions`
- `transaction_costs`
- `cashflows`

This layer is the canonical transaction ledger and normalized cash movement foundation. Downstream
services should not recreate these semantics independently.

### Position and valuation state

Primary position and valuation tables include:

- `position_history`
- `position_lot_states`
- `accrued_income_offset_states`
- `daily_position_snapshots`
- `position_states`

This layer carries the reconstruction and valuation state needed to explain holdings as of a given
business date.

### Timeseries and analytics-input foundations

Primary time-series tables include:

- `position_timeseries`
- `portfolio_timeseries`

These are upstream foundations for downstream analytics services. `lotus-core` owns the canonical
input products, not the downstream performance or risk conclusions built from them.

### Operations, lineage, and supportability

Primary operational tables include:

- `processed_events`
- `outbox_events`
- `portfolio_aggregation_jobs`
- `portfolio_valuation_jobs`
- `ingestion_jobs`
- `ingestion_job_failures`
- `ingestion_ops_controls`
- `consumer_dlq_events`
- `consumer_dlq_replay_audits`
- `reprocessing_jobs`
- `analytics_export_jobs`
- `pipeline_stage_states`
- `financial_reconciliation_runs`
- `financial_reconciliation_findings`

These tables are part of the supported operational contract. Replay, support, lineage, and
reconciliation behavior is not incidental implementation detail in `lotus-core`.

## Model rules that matter

1. New temporal semantics must follow
   [Temporal Vocabulary](../docs/standards/temporal-vocabulary.md).
2. New source-data or analytics-input products must align with
   [RFC-0083 Source Data Product Catalog](../docs/architecture/RFC-0083-source-data-product-catalog.md).
3. New security, retention, or operator-surface changes must align with
   [RFC-0083 Security Tenancy Lifecycle Target Model](../docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md).
4. New event or replay supportability changes must align with
   [RFC-0083 Eventing Supportability Target Model](../docs/architecture/RFC-0083-eventing-supportability-target-model.md).

## When to update this page

Update this page when:

- a new durable table family becomes part of normal engineering work
- a target-model RFC introduces a new governed model group
- the operational supportability or reconciliation model materially changes

Do not copy every field here. Keep this page focused on stable ownership and navigation.
