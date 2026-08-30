# Lotus-Core Database Table Catalog and Schema Review

This document catalogs application tables defined in
`src/libs/portfolio-common/portfolio_common/database_models.py` and reviews schema fitness for
current Lotus-Core architecture.

## Scope and Method

- Source of truth: SQLAlchemy models in `database_models.py`, which currently declare **78 tables**.
- Usage evidence: code-reference scan across `src/` (model class and table-name hits).
- This review distinguishes: `actively used`, `partially implemented`, and `needs decision`.

### Coverage

**This catalog is partial: it documents 58 of the 78 declared tables.** Absence of a table below
means it has not been reviewed yet, not that it is unused or deprecated. The 20 tables still
awaiting a catalog entry are:

| Family | Tables |
| --- | --- |
| Corporate actions | `corporate_action_events`, `corporate_action_child_observations`, `corporate_action_execution_members`, `corporate_action_execution_releases`, `corporate_action_manifest_nodes`, `corporate_action_manifest_edges`, `corporate_action_manifest_versions`, `corporate_action_readiness_evaluations` |
| Lot lifecycle | `lot_basis_transfer_allocations`, `lot_basis_transfer_receipts`, `lot_disposal_allocations`, `lot_disposal_receipts` |
| Reconciliation | `financial_reconciliation_runs`, `financial_reconciliation_findings` |
| Valuation | `daily_position_valuation_receipts`, `instrument_valuation_policy_assignments` |
| Reference and instrument data | `cash_account_masters`, `instrument_lookthrough_components` |
| Platform and audit | `enterprise_security_audit_events`, `outbox_recovery_audit` |

Completing these entries is tracked as a repository issue. When adding one, follow the existing
section shape and derive the usage line from a fresh scan rather than copying a neighbouring table.

## `business_dates`

- **Purpose**: System business calendar boundary used by valuation, aggregation, and booked-state views.
- **Description**: Represents valid processing dates per calendar, not trade/event timestamps.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/ingestion_service/app/routers/business_dates.py`, `src/services/ingestion_service/app/services/ingestion_service.py`, `src/services/persistence_service/app/repositories/business_date_repository.py`, `src/services/persistence_service/app/consumers/business_date_consumer.py`, `src/services/event_replay_service/app/routers/ingestion_operations.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `calendar_code` (String): Controlled code value from a domain taxonomy/configuration.
  - `date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `market_code` (String): Controlled code value from a domain taxonomy/configuration.
  - `source_system` (String): Domain attribute used by the owning module.
  - `source_batch_id` (String): Identifier for source batch.
  - `created_at` (DateTime): Server timestamp when row was created.

## `portfolios`

- **Purpose**: Master record for portfolios.
- **Description**: Canonical portfolio identity and static attributes used across ingestion/query/calculators.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/operations/repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/query_service/app/routers/portfolios.py`, `src/services/ingestion_service/app/routers/portfolios.py`, `src/services/query_control_plane_service/app/infrastructure/analytics_timeseries_repository.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `base_currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `open_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `close_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `risk_exposure` (String): Domain attribute used by the owning module.
  - `investment_time_horizon` (String): Domain attribute used by the owning module.
  - `portfolio_type` (String): Domain type discriminator used to branch processing behavior.
  - `objective` (String): Domain attribute used by the owning module.
  - `booking_center_code` (String): Controlled code value from a domain taxonomy/configuration.
  - `client_id` (String): Identifier for client.
  - `is_leverage_allowed` (Boolean): Boolean flag controlling behavior/interpretation.
  - `advisor_id` (String): Compatibility-only adviser identifier for portfolios without governed party-role history; it must not be interpreted as a specific banking capacity.
  - `status` (String): Current lifecycle status for the record/work item.
  - `cost_basis_method` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `portfolio_party_role_assignments`

- **Purpose**: Source-owned, effective-dated private-banking capacity and responsibility assignments for portfolios.
- **Description**: Distinguishes relationship coverage, investment advice, portfolio management, delegated coverage, and client service without inferring authority from `portfolios.advisor_id`.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`; `party_id` remains an external source identity until the separately governed Party aggregate is implemented.
- **Usage (modules/features)**: reference-data ingestion, `PortfolioPartyRoleAssignment:v1`, and authoritative `PortfolioManagerBookMembership:v1` resolution.
- **Typical access patterns**: latest source-version selection followed by effective-date, quality, party, role, and scope filtering; portfolio history existence checks fence the legacy adviser projection.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `party_id` (String): Source-owned party identifier.
  - `role_type` (String): Governed private-banking capacity.
  - `role_scope` (String): Governed responsibility boundary.
  - `effective_from` / `effective_to` (Date): Inclusive effective interval.
  - `assignment_version` (Integer): Positive source-controlled version.
  - `source_system` / `source_record_id` (String): Required idempotent source identity.
  - `observed_at` (DateTime): Required source observation timestamp.
  - `quality_status` (String): Governed accepted, pending-review, quarantined, or rejected disposition.
  - `created_at` / `updated_at` (DateTime): Durable row audit timestamps.

## `simulation_sessions`

- **Purpose**: Tracks sandbox simulation sessions.
- **Description**: Session-level envelope for hypothetical changes against a base portfolio.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`
- **Usage (modules/features)**: QCP generic simulation via `app/infrastructure/simulation_store.py`, `app/application/simulation.py`, `app/contracts/simulation.py`, and `app/routers/simulation.py`; the QS `simulation_repository.py` remains a temporary Core-snapshot reader.
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `session_id` (String): Identifier for session.
  - `portfolio_id` (String) (FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `status` (String): Current lifecycle status for the record/work item.
  - `version` (Integer): Domain attribute used by the owning module.
  - `created_by` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `expires_at` (DateTime): Domain attribute used by the owning module.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `simulation_changes`

- **Purpose**: Stores hypothetical transactions within simulation sessions.
- **Description**: Proposed what-if changes that are not posted to canonical ledger.
- **Relationships**: `session_id` -> `simulation_sessions.session_id`
- **Usage (modules/features)**: QCP generic simulation via `app/infrastructure/simulation_store.py`, `app/application/simulation.py`, `app/contracts/simulation.py`, and `app/routers/simulation.py`; the QS `simulation_repository.py` remains a temporary Core-snapshot reader.
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `change_id` (String): Identifier for change.
  - `session_id` (String) (FK `simulation_sessions.session_id`): Identifier for session.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `security_id` (String): Canonical security identifier.
  - `transaction_type` (String): Domain type discriminator used to branch processing behavior.
  - `quantity` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `price` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `amount` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `effective_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `change_metadata` (None): JSON payload storing structured request/result or metadata content.
  - `created_at` (DateTime): Server timestamp when row was created.

## `position_history`

- **Purpose**: Event-driven ledger of position state over time.
- **Description**: Per-transaction derived position state (quantity/cost) by date and epoch.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`; `transaction_id` -> `transactions.transaction_id`
- **Usage (modules/features)**: `src/services/query_service/app/repositories/position_repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/query_service/app/services/position_service.py`, `src/services/portfolio_transaction_processing_service/app/infrastructure/position/history_repository.py`, `src/services/query_control_plane_service/app/infrastructure/operations/repository.py`, `src/services/query_service/app/routers/positions.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String) (FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `security_id` (String): Canonical security identifier.
  - `transaction_id` (String) (FK `transactions.transaction_id`): Canonical transaction identifier.
  - `position_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `epoch` (Integer): Deterministic reprocessing generation/version for state isolation.
  - `quantity` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `cost_basis` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `cost_basis_local` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `daily_position_snapshots`

- **Purpose**: Valuation snapshot store by day.
- **Description**: End-of-day (or latest available) valued/unvalued position records.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`
- **Usage (modules/features)**: `src/services/query_service/app/repositories/position_repository.py`, `src/services/query_control_plane_service/app/infrastructure/operations/repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/portfolio_transaction_processing_service/app/infrastructure/position/history_repository.py`, `src/services/persistence_service/app/repositories/market_price_repository.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String) (FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `security_id` (String): Canonical security identifier.
  - `date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `epoch` (Integer): Deterministic reprocessing generation/version for state isolation.
  - `quantity` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `cost_basis` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `cost_basis_local` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `market_price` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `market_value` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `market_value_local` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `unrealized_gain_loss` (Numeric): Domain attribute used by the owning module.
  - `unrealized_gain_loss_local` (Numeric): Domain attribute used by the owning module.
  - `valuation_status` (String): Domain attribute used by the owning module.
  - `valuation_source_currency` (String(3), nullable): Canonical currency of the price/local value actually used by the valuation; jointly present with `valuation_reporting_currency` for newly evaluated snapshots.
  - `valuation_reporting_currency` (String(3), nullable): Canonical portfolio reporting currency actually used by the valuation; jointly present with `valuation_source_currency` so mutable master data cannot relabel historical evidence.
  - `valuation_fx_rate_date` (Date, nullable): Exact effective date of the FX row used for a cross-currency valuation; null for same-currency, unvalued, failed, or legacy snapshots without authoritative lineage.
  - `valuation_fx_rate` (Numeric(18,10), nullable): Exact positive finite FX value paired with `valuation_fx_rate_date`; both fields must be present or both null so a same-date source correction changes lineage deterministically.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `fx_rates`

- **Purpose**: Reference FX rates used by cost/valuation.
- **Description**: Daily currency conversion rates for trade and valuation normalization.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/fx_rate_repository.py`, `src/services/query_service/app/services/fx_rate_service.py`, `src/services/ingestion_service/app/services/ingestion_service.py`, `src/services/query_control_plane_service/app/infrastructure/analytics_timeseries_repository.py`, `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/persistence_service/app/repositories/fx_rate_repository.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `from_currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `to_currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `rate_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `rate` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `market_prices`

- **Purpose**: Reference instrument prices.
- **Description**: Observed price series used by valuation and downstream timeseries.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/persistence_service/app/consumers/market_price_consumer.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/ingestion_service/app/services/ingestion_service.py`, `src/services/query_service/app/services/price_service.py`, `src/services/persistence_service/app/repositories/market_price_repository.py`, `src/services/ingestion_service/app/routers/market_prices.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `security_id` (String): Canonical security identifier.
  - `price_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `price` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `market_price_source_facts`

- **Purpose**: Append-only, exact-scope authority for valuation source values.
- **Description**: Source-versioned market-price facts with explicit quote representation,
  tenant/legal-book ownership, correction lineage, and lifecycle fencing. This table does not
  replace the legacy global `market_prices` projection.
- **Relationships**: `security_id` references `instruments.security_id`.
- **Usage (modules/features)**:
  `src/services/ingestion_service/app/services/market_price_source_fact_writer.py`,
  `src/services/calculators/position_valuation_calculator/app/infrastructure/market_price_source_fact_repository.py`,
  and `POST /ingest/authoritative-market-price-source-facts`.
- **Typical access patterns**: Append under stable source and old/new authority locks; rank the
  latest correction per `(source_system, source_record_id)` before exact-scope/date/lifecycle
  resolution; bounded 500-record batches with 100-key query chunks.
- **Column definitions**:
  - `id` (Integer): Surrogate append-history row identity.
  - `tenant_id` (String): Exact tenant authority.
  - `legal_book_id` (String): Exact legal-book authority.
  - `security_id` (String): Canonical instrument identifier.
  - `price_date` (Date): Business date governed by the fact.
  - `price` (Numeric): Positive finite source value stored without an undeclared precision/scale.
  - `currency` (String): Normalized ISO currency.
  - `quote_basis` (String): `UNIT_PRICE`, `PERCENT_OF_PRINCIPAL_CLEAN`, or
    `PERCENT_OF_PRINCIPAL_DIRTY`.
  - `fact_status` (String): `ACTIVE`, `SUSPENDED`, or `RETIRED`.
  - `fact_version` (Integer): Positive correction version for the stable source record.
  - `source_system` (String): Authoritative source system.
  - `source_record_id` (String): Stable source identity across corrections.
  - `source_revision` (String): Source-native revision.
  - `source_content_hash` (String): Lowercase SHA-256 source-content digest.
  - `observed_at` (DateTime): Timezone-aware source observation instant.
  - `created_at` (DateTime): Server timestamp when the append-history row was created.

## `instruments`

- **Purpose**: Security master reference.
- **Description**: Instrument metadata and issuer/classification attributes.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/ingestion_service/app/routers/instruments.py`, `src/services/query_service/app/services/instrument_service.py`, `src/services/query_service/app/repositories/instrument_repository.py`, `src/services/persistence_service/tests/integration/test_repositories.py`, `src/services/query_service/app/repositories/position_repository.py`, `src/services/query_service/app/routers/lookups.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `security_id` (String): Canonical security identifier.
  - `name` (String): Domain attribute used by the owning module.
  - `isin` (String): Domain attribute used by the owning module.
  - `currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `product_type` (String): Domain type discriminator used to branch processing behavior.
  - `asset_class` (String): Domain attribute used by the owning module.
  - `sector` (String): Domain attribute used by the owning module.
  - `country_of_risk` (String): Domain attribute used by the owning module.
  - `rating` (String): Domain attribute used by the owning module.
  - `maturity_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `issuer_id` (String): Identifier for issuer.
  - `issuer_name` (String): Domain attribute used by the owning module.
  - `ultimate_parent_issuer_id` (String): Identifier for ultimate parent issuer.
  - `ultimate_parent_issuer_name` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `portfolio_benchmark_assignments`

- **Purpose**: Historical assignment of benchmarks to portfolios.
- **Description**: Time-varying benchmark mapping used by downstream performance/risk.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String) (FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `benchmark_id` (String): Identifier for benchmark.
  - `effective_from` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `effective_to` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `assignment_source` (String): Domain attribute used by the owning module.
  - `assignment_status` (String): Domain attribute used by the owning module.
  - `policy_pack_id` (String): Identifier for policy pack.
  - `source_system` (String): Domain attribute used by the owning module.
  - `assignment_recorded_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `assignment_version` (Integer): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `portfolio_mandate_bindings`

- **Purpose**: Effective-dated discretionary mandate binding for stateful DPM source assembly.
- **Description**: Stores portfolio-to-mandate/model/policy bindings, source-owned mandate
  objective, authority status, jurisdiction, booking center, review cadence, review dates,
  rebalance constraints, and lineage for
  `DiscretionaryMandateBinding:v1`.
- **Relationships**: `portfolio_id` references `portfolios.portfolio_id`.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/infrastructure/dpm_reference_data_sources.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: Effective-date lookup by portfolio id and as-of date with optional
  mandate id and booking-center filters; idempotent upsert by portfolio id, mandate id, effective
  start date, and binding version.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `mandate_id` (String): Canonical discretionary mandate identifier.
  - `client_id` (String): Canonical client identifier bound to the mandate.
  - `mandate_type` (String): Mandate type; Slice 5 supports discretionary bindings.
  - `discretionary_authority_status` (String): Authority lifecycle state.
  - `booking_center_code` (String): Booking center governing the mandate.
  - `jurisdiction_code` (String): Legal or regulatory jurisdiction code.
  - `model_portfolio_id` (String): Approved model portfolio selected for the mandate.
  - `policy_pack_id` (String): Policy pack applied to DPM checks.
  - `mandate_objective` (String): Source-owned discretionary mandate objective.
  - `risk_profile` (String): Mandate risk profile.
  - `investment_horizon` (String): Mandate investment horizon classification.
  - `review_cadence` (String): Source-owned mandate review cadence.
  - `last_review_date` (Date): Most recent completed discretionary mandate review date.
  - `next_review_due_date` (Date): Next due discretionary mandate review date.
  - `leverage_allowed` (Boolean): Whether leverage is permitted by the mandate.
  - `tax_awareness_allowed` (Boolean): Whether tax-aware DPM execution is allowed.
  - `settlement_awareness_required` (Boolean): Whether settlement-aware DPM execution is required.
  - `rebalance_frequency` (String): Expected rebalance cadence.
  - `rebalance_bands` (JSON): Mandate-level rebalance bands and cash reserve policy.
  - `effective_from` (Date): Binding effective start date.
  - `effective_to` (Date): Optional binding effective end date.
  - `binding_version` (Integer): Version used for deterministic tie-breaks.
  - `source_system` (String): Upstream mandate administration source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the binding.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `model_portfolio_definitions`

- **Purpose**: Effective-dated model portfolio master for discretionary mandate source products.
- **Description**: Stores approved model versions, risk profile, mandate type, rebalance cadence,
  and source lineage used by `DpmModelPortfolioTarget:v1`.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/infrastructure/dpm_reference_data_sources.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: Approved effective-date lookup by `model_portfolio_id` and
  `as_of_date`; idempotent upsert by model id, version, and effective start date.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `model_portfolio_id` (String): Canonical model portfolio identifier.
  - `model_portfolio_version` (String): Approved model version.
  - `display_name` (String): Business display name.
  - `base_currency` (String): Model base currency.
  - `risk_profile` (String): Risk profile aligned to the model.
  - `mandate_type` (String): Mandate type for which the model is approved.
  - `rebalance_frequency` (String): Expected rebalance cadence.
  - `approval_status` (String): Model lifecycle approval status.
  - `approved_at` (DateTime): Timestamp at which the model version was approved.
  - `effective_from` (Date): Model effective start date.
  - `effective_to` (Date): Optional model effective end date.
  - `source_system` (String): Upstream model source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the model definition.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `instrument_eligibility_profiles`

- **Purpose**: Effective-dated DPM instrument eligibility, restriction, shelf, liquidity, issuer,
  and settlement profile source data.
- **Description**: Stores the source records behind `InstrumentEligibilityProfile:v1`. The table
  supports bulk stateful DPM source assembly without per-instrument product shelf lookups or local
  fallback truth in `lotus-manage`.
- **Relationships**: `security_id` references `instruments.security_id`.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/infrastructure/dpm_reference_data_sources.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: Bulk effective-date lookup by requested security ids and as-of date;
  response ordering is reconstructed to match request order and missing records are returned
  explicitly as `UNKNOWN`.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `security_id` (String): Canonical instrument/security identifier.
  - `eligibility_status` (String): DPM eligibility status such as `APPROVED`, `RESTRICTED`,
    `SELL_ONLY`, `BANNED`, or `UNKNOWN`.
  - `product_shelf_status` (String): Product shelf status used by DPM execution.
  - `buy_allowed` (Boolean): Whether DPM may create buy orders for this instrument.
  - `sell_allowed` (Boolean): Whether DPM may create sell orders for this instrument.
  - `restriction_reason_codes` (JSON): Bounded restriction codes exposed downstream.
  - `restriction_rationale` (Text): Operator-only source rationale retained for audit and not
    exposed by the DPM source API.
  - `settlement_days` (Integer): Expected settlement cycle in business days.
  - `settlement_calendar_id` (String): Settlement calendar identifier.
  - `liquidity_tier` (String): Liquidity tier used by DPM controls.
  - `issuer_id` (String): Direct issuer identifier.
  - `issuer_name` (String): Direct issuer name.
  - `ultimate_parent_issuer_id` (String): Ultimate parent issuer identifier.
  - `ultimate_parent_issuer_name` (String): Ultimate parent issuer name.
  - `asset_class` (String): Asset class label.
  - `country_of_risk` (String): Country of risk.
  - `effective_from` (Date): Eligibility effective start date.
  - `effective_to` (Date): Optional eligibility effective end date.
  - `eligibility_version` (Integer): Version used for deterministic tie-breaks.
  - `source_system` (String): Upstream shelf/compliance source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the profile.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `client_restriction_profiles`

- **Purpose**: Effective-dated client and mandate restriction source records for DPM buy/sell
  controls.
- **Description**: Stores the source records behind `ClientRestrictionProfile:v1`, including
  restriction scope, code, lifecycle status, buy/sell applicability, scoped identifiers, version,
  lineage, and quality status. The table lets `lotus-manage` consume source-owned restriction truth
  instead of maintaining local fallback restriction fixtures.
- **Relationships**: `portfolio_id` references `portfolios.portfolio_id`.
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/client_restriction_profile_sources.py`, `src/services/query_control_plane_service/app/application/client_restriction_profile.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: Effective-date lookup by portfolio id, client id, mandate id, and
  as-of date; active restrictions are returned by default and deterministic latest-version
  selection is applied by scope and restriction code.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `mandate_id` (String): Optional discretionary mandate identifier.
  - `client_id` (String): Canonical client identifier bound to the restriction profile.
  - `restriction_scope` (String): Scope such as client, mandate, instrument, asset class, issuer,
    or country.
  - `restriction_code` (String): Machine-readable restriction code.
  - `restriction_status` (String): Restriction lifecycle status.
  - `restriction_source` (String): Upstream source channel or authority.
  - `applies_to_buy` (Boolean): Whether the restriction blocks or constrains buys.
  - `applies_to_sell` (Boolean): Whether the restriction blocks or constrains sells.
  - `instrument_ids` (JSON): Instrument identifiers in scope.
  - `asset_classes` (JSON): Asset classes in scope.
  - `issuer_ids` (JSON): Issuer identifiers in scope.
  - `country_codes` (JSON): Country codes in scope.
  - `effective_from` (Date): Restriction effective start date.
  - `effective_to` (Date): Optional restriction effective end date.
  - `restriction_version` (Integer): Version used for deterministic tie-breaks.
  - `source_system` (String): Upstream restriction or mandate source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the record.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `sustainability_preference_profiles`

- **Purpose**: Effective-dated client and mandate sustainability preference source records for DPM
  portfolio construction.
- **Description**: Stores the source records behind `SustainabilityPreferenceProfile:v1`,
  including framework, preference code, allocation bounds, asset-class scope, exclusions, positive
  tilts, version, lineage, and quality status. The table is a source-owner contract and does not
  perform suitability adjudication or rebalance decisioning.
- **Relationships**: `portfolio_id` references `portfolios.portfolio_id`.
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/sustainability_preference_profile_sources.py`, `src/services/query_control_plane_service/app/application/sustainability_preference_profile.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: Effective-date lookup by portfolio id, client id, mandate id, and
  as-of date; active preferences are returned by default and deterministic latest-version
  selection is applied by framework and preference code.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `mandate_id` (String): Optional discretionary mandate identifier.
  - `client_id` (String): Canonical client identifier bound to the preference profile.
  - `preference_framework` (String): Framework or policy vocabulary for the preference.
  - `preference_code` (String): Machine-readable sustainability preference code.
  - `preference_status` (String): Preference lifecycle status.
  - `preference_source` (String): Upstream source channel or authority.
  - `minimum_allocation` (Numeric): Minimum allocation ratio, when applicable.
  - `maximum_allocation` (Numeric): Maximum allocation ratio, when applicable.
  - `applies_to_asset_classes` (JSON): Asset classes in scope.
  - `exclusion_codes` (JSON): Sustainability exclusion codes in scope.
  - `positive_tilt_codes` (JSON): Sustainability positive-tilt codes in scope.
  - `effective_from` (Date): Preference effective start date.
  - `effective_to` (Date): Optional preference effective end date.
  - `preference_version` (Integer): Version used for deterministic tie-breaks.
  - `source_system` (String): Upstream sustainability-preference source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the record.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `client_tax_profiles`

- **Purpose**: Effective-dated client and mandate tax-reference profile source records for DPM
  evidence.
- **Description**: Stores the source records behind `ClientTaxProfile:v1`, including tax
  residency, booking tax jurisdiction, bounded tax status, source-supplied withholding rate,
  lifecycle status, tax-applicability flags, treaty codes, eligible account types, version, lineage, and quality
  status. The table is source-reference evidence only and does not provide tax advice,
  after-tax optimization, tax-loss harvesting suitability, client-tax approval, or
  jurisdiction-specific recommendations.
- **Relationships**: `portfolio_id` references `portfolios.portfolio_id`.
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/client_tax_profile_sources.py`, `src/services/query_control_plane_service/app/application/client_tax_profile.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: Effective-date lookup by portfolio id, client id, mandate id, and
  as-of date; active profiles are returned by default and deterministic latest-version
  selection is applied by tax profile id.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `mandate_id` (String): Optional discretionary mandate identifier.
  - `client_id` (String): Canonical client identifier bound to the tax profile.
  - `tax_profile_id` (String): Source-owned tax profile identifier.
  - `tax_residency_country` (String): Client tax-residency country.
  - `booking_tax_jurisdiction` (String): Booking-center tax jurisdiction.
  - `tax_status` (String): Bounded tax status from the source system.
  - `profile_status` (String): Tax profile lifecycle status.
  - `withholding_tax_rate` (Numeric): Source-supplied withholding rate ratio, when applicable.
  - `capital_gains_tax_applicable` (Boolean): Source flag for capital-gains tax applicability.
  - `income_tax_applicable` (Boolean): Source flag for income-tax applicability.
  - `treaty_codes` (JSON): Treaty codes supplied by the source system.
  - `eligible_account_types` (JSON): Eligible account type codes supplied by the source system.
  - `effective_from` (Date): Tax profile effective start date.
  - `effective_to` (Date): Optional tax profile effective end date.
  - `profile_version` (Integer): Version used for deterministic tie-breaks.
  - `source_system` (String): Upstream tax-reference source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the record.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `client_tax_rule_sets`

- **Purpose**: Effective-dated client and mandate tax-rule reference source records for DPM
  evidence.
- **Description**: Stores the source records behind `ClientTaxRuleSet:v1`, including tax year,
  jurisdiction, rule code/category/status/source, applicability lists, source-supplied rates and
  thresholds, version, lineage, and quality status. The table is source-reference evidence only and
  does not provide tax advice, tax-loss harvesting suitability, after-tax optimization,
  client-tax approval, jurisdiction-specific recommendations, tax-reporting certification, best
  execution, or OMS acknowledgement.
- **Relationships**: `portfolio_id` references `portfolios.portfolio_id`.
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/client_tax_rule_set_sources.py`, `src/services/query_control_plane_service/app/application/client_tax_rule_set.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: Effective-date lookup by portfolio id, client id, mandate id, and
  as-of date; active rules are returned by default and deterministic latest-version selection is
  applied by rule set id, jurisdiction, and rule code.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `mandate_id` (String): Optional discretionary mandate identifier.
  - `client_id` (String): Canonical client identifier bound to the tax rule set.
  - `rule_set_id` (String): Source-owned tax rule-set identifier.
  - `tax_year` (Integer): Tax year for the source rule.
  - `jurisdiction_code` (String): Tax jurisdiction code.
  - `rule_code` (String): Machine-readable tax rule code.
  - `rule_category` (String): Bounded tax rule category.
  - `rule_status` (String): Rule lifecycle status.
  - `rule_source` (String): Upstream source channel or authority.
  - `applies_to_asset_classes` (JSON): Asset classes in rule scope.
  - `applies_to_security_ids` (JSON): Security identifiers in rule scope.
  - `applies_to_income_types` (JSON): Income types in rule scope.
  - `rate` (Numeric): Source-supplied rate ratio, when applicable.
  - `threshold_amount` (Numeric): Source-supplied threshold amount, when applicable.
  - `threshold_currency` (String): Currency for `threshold_amount`, when applicable.
  - `effective_from` (Date): Rule effective start date.
  - `effective_to` (Date): Optional rule effective end date.
  - `rule_version` (Integer): Version used for deterministic tie-breaks.
  - `source_system` (String): Upstream tax-rule source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the record.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `client_income_needs_schedules`

- **Purpose**: Effective-dated client and mandate income-needs source records for DPM evidence.
- **Description**: Stores the source records behind `ClientIncomeNeedsSchedule:v1`, including
  bounded need type/status, amount, currency, cadence, priority, funding-policy reference,
  lineage, and quality status. The table is source-reference evidence only and does not provide
  financial-planning advice, suitability approval, cashflow forecasting, funding recommendations,
  or OMS acknowledgement.
- **Relationships**: `portfolio_id` references `portfolios.portfolio_id`.
- **Usage (modules/features)**: QCP `client_liquidity_evidence` application and SQL source adapter,
  QCP integration routes, and reference-data ingestion DTO/router/service paths.
- **Typical access patterns**: Effective-date lookup by portfolio id, client id, mandate id, and
  as-of date; active schedules are returned by default and deterministic latest selection is
  applied by schedule id.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `mandate_id` (String): Optional discretionary mandate identifier.
  - `client_id` (String): Canonical client identifier bound to the schedule.
  - `schedule_id` (String): Source-owned income-needs schedule identifier.
  - `need_type` (String): Bounded income-needs type.
  - `need_status` (String): Income-needs lifecycle status.
  - `amount` (Numeric): Source-supplied income-needs amount.
  - `currency` (String): Currency for `amount`.
  - `frequency` (String): Source-supplied income-needs cadence.
  - `start_date` (Date): Schedule effective start date.
  - `end_date` (Date): Optional schedule effective end date.
  - `priority` (Integer): Source priority for reserve and withdrawal planning context.
  - `funding_policy` (String): Optional upstream funding policy reference.
  - `source_system` (String): Upstream income-needs source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the record.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `liquidity_reserve_requirements`

- **Purpose**: Effective-dated client and mandate liquidity reserve source records for DPM
  evidence.
- **Description**: Stores the source records behind `LiquidityReserveRequirement:v1`, including
  reserve type/status, required amount, currency, horizon, priority, policy source, version,
  lineage, and quality status. The table is source-reference evidence only and does not approve
  cash reserve recommendations, financial-planning advice, suitability, treasury instructions, or
  OMS acknowledgement.
- **Relationships**: `portfolio_id` references `portfolios.portfolio_id`.
- **Usage (modules/features)**: QCP `client_liquidity_evidence` application and SQL source adapter,
  QCP integration routes, and reference-data ingestion DTO/router/service paths.
- **Typical access patterns**: Effective-date lookup by portfolio id, client id, mandate id, and
  as-of date; active requirements are returned by default and deterministic latest-version
  selection is applied by reserve requirement id.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `mandate_id` (String): Optional discretionary mandate identifier.
  - `client_id` (String): Canonical client identifier bound to the requirement.
  - `reserve_requirement_id` (String): Source-owned reserve requirement identifier.
  - `reserve_type` (String): Bounded reserve requirement type.
  - `reserve_status` (String): Reserve lifecycle status.
  - `required_amount` (Numeric): Source-supplied reserve amount.
  - `currency` (String): Currency for `required_amount`.
  - `horizon_days` (Integer): Reserve horizon in calendar days.
  - `priority` (Integer): Source priority for reserve planning context.
  - `policy_source` (String): Upstream policy or bank authority reference.
  - `effective_from` (Date): Requirement effective start date.
  - `effective_to` (Date): Optional requirement effective end date.
  - `requirement_version` (Integer): Version used for deterministic tie-breaks.
  - `source_system` (String): Upstream reserve source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the record.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `planned_withdrawal_schedules`

- **Purpose**: Horizon-bounded client and mandate planned withdrawal source records for DPM
  evidence.
- **Description**: Stores the source records behind `PlannedWithdrawalSchedule:v1`, including
  withdrawal type/status, amount, currency, scheduled date, optional recurrence, purpose code,
  lineage, and quality status. The table is source-reference evidence only and does not provide a
  cashflow forecast, financial-planning advice, suitability approval, funding recommendation,
  treasury instruction, or OMS acknowledgement.
- **Relationships**: `portfolio_id` references `portfolios.portfolio_id`.
- **Usage (modules/features)**: QCP `client_liquidity_evidence` application and SQL source adapter,
  QCP integration routes, and reference-data ingestion DTO/router/service paths.
- **Typical access patterns**: Forward-window lookup by portfolio id, client id, mandate id,
  `as_of_date`, and `horizon_days`; active withdrawals are returned by default and deterministic
  latest selection is applied by withdrawal schedule id and scheduled date.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `mandate_id` (String): Optional discretionary mandate identifier.
  - `client_id` (String): Canonical client identifier bound to the withdrawal schedule.
  - `withdrawal_schedule_id` (String): Source-owned withdrawal schedule identifier.
  - `withdrawal_type` (String): Bounded withdrawal type.
  - `withdrawal_status` (String): Withdrawal lifecycle status.
  - `amount` (Numeric): Source-supplied withdrawal amount.
  - `currency` (String): Currency for `amount`.
  - `scheduled_date` (Date): Planned withdrawal date.
  - `recurrence_frequency` (String): Optional recurrence cadence.
  - `purpose_code` (String): Optional source purpose code.
  - `source_system` (String): Upstream planned withdrawal source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the record.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `model_portfolio_targets`

- **Purpose**: Effective-dated target weights and policy bands for discretionary model portfolios.
- **Description**: Stores instrument target rows for `DpmModelPortfolioTarget:v1`, including
  target weight, min/max bands, lifecycle status, and source lineage.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/infrastructure/dpm_reference_data_sources.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: Effective-date lookup by model id, model version, and instrument;
  active-target filtering by default; idempotent upsert by model id, version, instrument, and
  effective start date.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `model_portfolio_id` (String): Canonical model portfolio identifier.
  - `model_portfolio_version` (String): Approved model version.
  - `instrument_id` (String): Canonical instrument identifier.
  - `target_weight` (Numeric): Target instrument weight as a decimal ratio.
  - `min_weight` (Numeric): Optional minimum policy band.
  - `max_weight` (Numeric): Optional maximum policy band.
  - `target_status` (String): Target lifecycle status.
  - `effective_from` (Date): Target effective start date.
  - `effective_to` (Date): Optional target effective end date.
  - `source_system` (String): Upstream target source system.
  - `source_record_id` (String): Source record identifier.
  - `observed_at` (DateTime): Timestamp when the upstream source observed or published the model target.
  - `quality_status` (String): Data quality status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `benchmark_definitions`

- **Purpose**: Benchmark reference master with versioned effective dating.
- **Description**: Defines benchmark identity, conventions, provider metadata.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/query_control_plane_service/app/infrastructure/benchmark_definition_sources.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/query_control_plane_service/app/contracts/benchmark_definition.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `benchmark_id` (String): Identifier for benchmark.
  - `benchmark_name` (String): Domain attribute used by the owning module.
  - `benchmark_type` (String): Domain type discriminator used to branch processing behavior.
  - `benchmark_currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `return_convention` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `benchmark_status` (String): Domain attribute used by the owning module.
  - `benchmark_family` (String): Domain attribute used by the owning module.
  - `benchmark_provider` (String): Domain attribute used by the owning module.
  - `rebalance_frequency` (String): Domain attribute used by the owning module.
  - `classification_set_id` (String): Identifier for classification set.
  - `classification_labels` (JSON): JSON payload storing structured request/result or metadata content.
  - `effective_from` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `effective_to` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `source_timestamp` (DateTime): Domain attribute used by the owning module.
  - `source_vendor` (String): Domain attribute used by the owning module.
  - `source_record_id` (String): Identifier for source record.
  - `quality_status` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `index_definitions`

- **Purpose**: Index reference master with versioned effective dating.
- **Description**: Defines indices used in benchmark compositions and analytics.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/infrastructure/index_definition_sources.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/query_control_plane_service/app/contracts/index_catalog.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `index_id` (String): Identifier for index.
  - `index_name` (String): Domain attribute used by the owning module.
  - `index_currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `index_type` (String): Domain type discriminator used to branch processing behavior.
  - `index_status` (String): Domain attribute used by the owning module.
  - `index_provider` (String): Domain attribute used by the owning module.
  - `index_market` (String): Domain attribute used by the owning module.
  - `classification_set_id` (String): Identifier for classification set.
  - `classification_labels` (JSON): JSON payload storing structured request/result or metadata content.
  - `effective_from` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `effective_to` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `source_timestamp` (DateTime): Domain attribute used by the owning module.
  - `source_vendor` (String): Domain attribute used by the owning module.
  - `source_record_id` (String): Identifier for source record.
  - `quality_status` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `benchmark_composition_series`

- **Purpose**: Benchmark-to-index weights over time.
- **Description**: Time-varying benchmark composition for attribution workloads.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `benchmark_id` (String): Identifier for benchmark.
  - `index_id` (String): Identifier for index.
  - `composition_effective_from` (Date): Domain attribute used by the owning module.
  - `composition_effective_to` (Date): Domain attribute used by the owning module.
  - `composition_weight` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `rebalance_event_id` (String): Identifier for rebalance event.
  - `source_timestamp` (DateTime): Domain attribute used by the owning module.
  - `source_vendor` (String): Domain attribute used by the owning module.
  - `source_record_id` (String): Identifier for source record.
  - `quality_status` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `index_price_series`

- **Purpose**: Index price time series.
- **Description**: Reference index levels by date and convention.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/infrastructure/index_series_sources.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/query_control_plane_service/app/contracts/index_series.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `series_id` (String): Identifier for series.
  - `index_id` (String): Identifier for index.
  - `series_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `index_price` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `series_currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `value_convention` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `source_timestamp` (DateTime): Domain attribute used by the owning module.
  - `source_vendor` (String): Domain attribute used by the owning module.
  - `source_record_id` (String): Identifier for source record.
  - `quality_status` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `index_return_series`

- **Purpose**: Index return time series.
- **Description**: Reference index returns by period and convention.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/infrastructure/index_series_sources.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/query_control_plane_service/app/contracts/index_series.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `series_id` (String): Identifier for series.
  - `index_id` (String): Identifier for index.
  - `series_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `index_return` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `return_period` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `return_convention` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `series_currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `source_timestamp` (DateTime): Domain attribute used by the owning module.
  - `source_vendor` (String): Domain attribute used by the owning module.
  - `source_record_id` (String): Identifier for source record.
  - `quality_status` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `benchmark_return_series`

- **Purpose**: Benchmark return time series.
- **Description**: Benchmark-level returns used by performance/risk consumers.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/infrastructure/benchmark_return_series_sources.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/query_control_plane_service/app/contracts/benchmark_return_series.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `series_id` (String): Identifier for series.
  - `benchmark_id` (String): Identifier for benchmark.
  - `series_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `benchmark_return` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `return_period` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `return_convention` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `series_currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `source_timestamp` (DateTime): Domain attribute used by the owning module.
  - `source_vendor` (String): Domain attribute used by the owning module.
  - `source_record_id` (String): Identifier for source record.
  - `quality_status` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `risk_free_series`

- **Purpose**: Risk-free curve/reference series.
- **Description**: Time series required by analytics that need risk-free assumptions.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/risk_free_series_sources.py`, `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/query_control_plane_service/app/contracts/risk_free_series.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `series_id` (String): Identifier for series.
  - `risk_free_curve_id` (String): Identifier for risk free curve.
  - `series_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `value` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `value_convention` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `day_count_convention` (String): Domain attribute used by the owning module.
  - `compounding_convention` (String): Domain attribute used by the owning module.
  - `series_currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `source_timestamp` (DateTime): Domain attribute used by the owning module.
  - `source_vendor` (String): Domain attribute used by the owning module.
  - `source_record_id` (String): Identifier for source record.
  - `quality_status` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `classification_taxonomy`

- **Purpose**: Controlled classification dictionary.
- **Description**: Defines allowed classification sets/codes used by benchmark/index metadata.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/query_control_plane_service/app/infrastructure/classification_taxonomy_sources.py`, `src/services/query_control_plane_service/app/contracts/classification_taxonomy.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `classification_set_id` (String): Identifier for classification set.
  - `taxonomy_scope` (String): Domain attribute used by the owning module.
  - `dimension_name` (String): Domain attribute used by the owning module.
  - `dimension_value` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `dimension_description` (String): Domain attribute used by the owning module.
  - `effective_from` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `effective_to` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `source_timestamp` (DateTime): Domain attribute used by the owning module.
  - `source_vendor` (String): Domain attribute used by the owning module.
  - `source_record_id` (String): Identifier for source record.
  - `quality_status` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `transactions`

- **Purpose**: Canonical transaction ledger.
- **Description**: Ingested transactions enriched with cost and policy metadata.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`; ORM relationship `costs` -> `TransactionCost`; ORM relationship `cashflow` -> `Cashflow`
- **Usage (modules/features)**: `src/services/portfolio_transaction_processing_service/app/domain/cost_basis`, `src/services/portfolio_transaction_processing_service/app/application/cost_basis_processing/execution.py`, `src/services/portfolio_transaction_processing_service/app/infrastructure/cost_basis/transaction_repository.py`, `src/services/query_service/app/repositories/transaction_repository.py`, `src/services/ingestion_service/app/routers/transactions.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `transaction_id` (String): Canonical transaction identifier.
  - `portfolio_id` (String) (FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `instrument_id` (String): Identifier for instrument.
  - `security_id` (String): Canonical security identifier.
  - `transaction_type` (String): Domain type discriminator used to branch processing behavior.
  - `quantity` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `price` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `gross_transaction_amount` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `trade_currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `transaction_date` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `settlement_date` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `trade_fee` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.
  - `gross_cost` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `net_cost` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `realized_gain_loss` (Numeric): Domain attribute used by the owning module.
  - `transaction_fx_rate` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `net_cost_local` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `realized_gain_loss_local` (Numeric): Domain attribute used by the owning module.
  - `allocated_cost_basis_local` (Numeric): Cost basis allocated to non-security corporate-action consideration in local currency.
  - `allocated_cost_basis_base` (Numeric): Cost basis allocated to non-security corporate-action consideration in portfolio base currency.
  - `realized_capital_pnl_local` (Numeric): Realized capital P&L component in local currency.
  - `realized_fx_pnl_local` (Numeric): Realized FX P&L component in local currency.
  - `realized_total_pnl_local` (Numeric): Realized total P&L in local currency.
  - `realized_capital_pnl_base` (Numeric): Realized capital P&L component in portfolio base currency.
  - `realized_fx_pnl_base` (Numeric): Realized FX P&L component in portfolio base currency.
  - `realized_total_pnl_base` (Numeric): Realized total P&L in portfolio base currency.
  - `economic_event_id` (String): Identifier for economic event.
  - `linked_transaction_group_id` (String): Identifier for linked transaction group.
  - `calculation_policy_id` (String): Identifier for calculation policy.
  - `calculation_policy_version` (String): Domain attribute used by the owning module.
  - `source_system` (String): Domain attribute used by the owning module.

## `transaction_costs`

- **Purpose**: Normalized transaction fee breakdown.
- **Description**: Per-transaction fee components (brokerage, duty, exchange fee, etc.).
- **Relationships**: `transaction_id` -> `transactions.transaction_id`; ORM relationship `transaction` -> `Transaction`
- **Usage (modules/features)**: `src/services/portfolio_transaction_processing_service/app/infrastructure/cost_basis/transaction_repository.py`, `src/services/portfolio_transaction_processing_service/app/domain/cost_basis`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `transaction_id` (String) (FK `transactions.transaction_id`): Canonical transaction identifier.
  - `fee_type` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `amount` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

- **Integrity**: `amount > 0`; component identity is unique by transaction plus normalized fee type
  and currency.

## `cashflows`

- **Purpose**: Derived cashflow ledger from transaction rules.
- **Description**: Position/portfolio cash impacts by date, type, and epoch.
- **Relationships**: `transaction_id` -> `transactions.transaction_id`; `portfolio_id` -> `portfolios.portfolio_id`; ORM relationship `transaction` -> `Transaction`
- **Usage (modules/features)**: `src/services/query_service/app/repositories/cashflow_repository.py`, `src/services/portfolio_transaction_processing_service/app/domain/cashflow/calculation.py`, `src/services/portfolio_transaction_processing_service/app/infrastructure/cashflow/persistence.py`, `src/services/query_service/app/routers/cashflow_projection.py`, `src/services/query_service/app/services/cashflow_projection_service.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `transaction_id` (String) (FK `transactions.transaction_id`): Canonical transaction identifier.
  - `portfolio_id` (String) (FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `security_id` (String): Canonical security identifier.
  - `cashflow_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `epoch` (Integer): Deterministic reprocessing generation/version for state isolation.
  - `amount` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `classification` (String): Domain attribute used by the owning module.
  - `timing` (String): Domain attribute used by the owning module.
  - `calculation_type` (String): Domain type discriminator used to branch processing behavior.
  - `is_position_flow` (Boolean): Boolean flag controlling behavior/interpretation.
  - `is_portfolio_flow` (Boolean): Boolean flag controlling behavior/interpretation.
  - `economic_event_id` (String): Identifier for economic event.
  - `linked_transaction_group_id` (String): Identifier for linked transaction group.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `position_lot_state`

- **Purpose**: Durable lot inventory state.
- **Description**: Lot-level state for cost basis/disposition and lifecycle traceability. Strategy
  and tax acquisition basis remain in `lot_cost_local` and `lot_cost_base`; optional fixed-income
  accounting carrying amounts are persisted independently and never replace those basis fields.
- **Relationships**: `source_transaction_id` -> `transactions.transaction_id`; `portfolio_id` -> `portfolios.portfolio_id`
- **Usage (modules/features)**: `src/services/query_service/app/repositories/buy_state_repository.py`, `src/services/portfolio_transaction_processing_service/app/infrastructure/cost_basis/lot_state_repository.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `lot_id` (String): Identifier for lot.
  - `source_transaction_id` (String) (FK `transactions.transaction_id`): Identifier for source transaction.
  - `portfolio_id` (String) (FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `instrument_id` (String): Identifier for instrument.
  - `security_id` (String): Canonical security identifier.
  - `acquisition_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `original_quantity` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `open_quantity` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `lot_cost_local` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `lot_cost_base` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `accrued_interest_paid_local` (Numeric): Domain attribute used by the owning module.
  - `amortized_cost_profile_id` (String, nullable): Profile governing the current accounting carry.
  - `amortized_cost_profile_version` (Integer, nullable): Positive immutable profile version.
  - `amortized_cost_profile_content_hash` (String, nullable): Verified profile content identity.
  - `amortized_cost_recognized_through` (Date, nullable): Last recognized schedule boundary.
  - `amortized_cost_scheduled_local` (Numeric, nullable): Scheduled local carrying amount at that boundary.
  - `amortized_book_carrying_local` (Numeric, nullable): Residual accounting carrying amount in local currency.
  - `amortized_book_carrying_base` (Numeric, nullable): Residual accounting carrying amount in book base currency.
  - `amortized_cost_book_fx_rate_to_base` (Numeric, nullable): Governed book-cost FX rate.
  - `economic_event_id` (String): Identifier for economic event.
  - `linked_transaction_group_id` (String): Identifier for linked transaction group.
  - `calculation_policy_id` (String): Identifier for calculation policy.
  - `calculation_policy_version` (String): Domain attribute used by the owning module.
  - `source_system` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

- **Integrity**: `open_quantity >= 0`, `open_quantity <= original_quantity`,
  `lot_cost_local >= 0`, and `lot_cost_base >= 0`. Combined quantity checks also imply a
  nonnegative original quantity. Unique `(lot_id, portfolio_id, security_id)` supports exact-scope
  references from dependent accounting ledgers. Amortized-cost state is all-null or complete;
  amounts are finite and nonnegative, the FX rate is finite and positive, and closed lots cannot
  retain accounting carry.

## `lot_amortized_cost_authority`

- **Purpose**: Append-only source-version history for lot amortized-cost assignments, clean-cost
  basis, contractual schedules, and effective-yield facts.
- **Description**: Stores a shared governed envelope at exact tenant/legal-book/portfolio/security/
  source-lot scope while retaining a type-specific JSON payload. Decimal and date values in that
  payload are canonical strings so source identity is not changed by JSON number coercion. This is
  input authority, not calculated book cost or permission to book a lifecycle.
- **Relationships**: `(tenant_id, legal_book_id, portfolio_id)` -> the matching scoped portfolio;
  `(lot_id, portfolio_id, security_id)` -> the matching source lot; `security_id` ->
  `instruments.security_id`.
- **Usage (modules/features)**:
  `src/services/portfolio_transaction_processing_service/app/infrastructure/fixed_income_book_cost/source_authority_repository.py`.
- **Typical access patterns**: Per-source advisory-locked append; exact-retry classification;
  monotonic correction versions; deterministic exact-scope history load before domain resolution.
- **Integrity**: Unique authority type/scope/source/version identity; normalized scope and source;
  governed authority type and lifecycle; positive source version; ordered effective window;
  SHA-256 content hash; object payload; composite book/source-lot foreign keys.
- **Key columns**: Authority type, exact scope, effective window, lifecycle status, source version
  and identity, observation time, authority content hash, canonical payload, and `created_at`.

## `lot_amortized_cost_profiles`

- **Purpose**: Append-only source-lot amortized book-cost profile history.
- **Description**: Preserves active, parked, or ineligible effective-dated profile headers with
  exact tenant/legal-book/portfolio/security/lot scope, source references, calculation lineage,
  authority/content hashes, and reconciled monetary summary. This staged ledger does not replace
  original or tax basis in `position_lot_state` and does not by itself enable runtime bookability.
- **Relationships**: `(tenant_id, legal_book_id, portfolio_id)` -> the matching scoped portfolio;
  `(lot_id, portfolio_id, security_id)` -> the matching source lot; `security_id` ->
  `instruments.security_id`.
- **Usage (modules/features)**:
  `src/services/portfolio_transaction_processing_service/app/infrastructure/fixed_income_book_cost/profile_repository.py`.
- **Typical access patterns**: Locked contiguous append by stable `profile_id`; latest exact-scope
  lookup; effective-date/latest-version as-of lookup; parked/ineligible support scans.
- **Integrity**: Unique `(profile_id, profile_version)`; normalized nonblank scope; positive
  versions; governed lifecycle/direction/currency; finite and nonnegative monetary boundaries;
  SHA-256 authority/profile hashes; non-empty source array and complete economics/lineage for
  active profiles; no invented economics for parked/ineligible profiles. Composite foreign keys
  prevent a profile from combining a portfolio book scope with a different source lot or security.
- **Key columns**: `profile_id`, `profile_version`, exact scope fields, `effective_date`, `status`,
  `eligibility_reason`, policy/schedule identity, currency/direction, initial/redemption/final cost,
  residual, authority hash, source references, calculation lineage, profile hash, and `created_at`.

## `lot_amortized_cost_periods`

- **Purpose**: Immutable normalized recognition-period ledger for one profile version.
- **Description**: Stores every ordered period input/output and its calculation/output hashes.
  Monetary amounts use governed `NUMERIC(18,10)` exact binds; year fractions and derived period
  rates are exact-unbounded so persistence cannot truncate working-precision lineage evidence.
- **Relationships**: Composite `(profile_id, profile_version)` ->
  `lot_amortized_cost_profiles(profile_id, profile_version)` with restricted deletion.
- **Usage (modules/features)**:
  `src/services/portfolio_transaction_processing_service/app/infrastructure/fixed_income_book_cost/profile_repository.py`.
- **Typical access patterns**: One ordered bulk insert per new profile version and ordered
  reconstruction by `period_ordinal`; profile/date support reads use the parent profile indexes.
- **Integrity**: Unique `(profile_id, profile_version, period_ordinal)`; positive contiguous domain
  ordinal, ordered dates, positive finite year fraction, finite rates and amounts, nonnegative
  beginning/coupon/ending amounts, and SHA-256 calculation/period hashes.
- **Key columns**: Profile identity/version, ordinal and period dates, year fraction/rate,
  beginning cost, interest, coupon, amortization movement, ending cost, rounding adjustment,
  calculation output hash, period content hash, and `created_at`.

## `cost_basis_processing_state`

- **Purpose**: Versioned ordering checkpoint for incremental cost-basis processing.
- **Description**: Stores the latest canonical transaction-order boundary per portfolio/security so
  strictly later events can calculate from durable open-lot state while backdated, same-order,
  incompatible, or unsupported events fail over to deterministic full replay.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`
- **Usage (modules/features)**: `src/services/portfolio_transaction_processing_service/app/infrastructure/cost_basis/processing_state_repository.py`,
  `src/services/portfolio_transaction_processing_service/app/application/cost_basis_processing/execution.py`
- **Typical access patterns**: Primary-key lookup and atomic upsert inside the combined transaction
  processing unit of work; updated-time scans are operator/supportability only.
- **Column definitions**:
  - `portfolio_id` (String) (PK, FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `security_id` (String) (PK): Canonical security identifier.
  - `cost_basis_method` (String): Governed FIFO or AVCO method used to build the state.
  - `latest_transaction_date` (DateTime): Timestamp component of the canonical ordering boundary.
  - `latest_dependency_rank` (Integer): Corporate-action dependency rank.
  - `latest_cash_dependency_rank` (Integer): Same-timestamp cash dependency rank.
  - `latest_child_sequence` (Integer): Corporate-action target child sequence.
  - `latest_target_instrument_id` (String): Stable target-instrument ordering fallback.
  - `latest_quantity` (Numeric): Positive quantity used by the descending quantity sort component.
  - `latest_transaction_id` (String): Stable final ordering tiebreak and support identifier.
  - `engine_state_version` (String): Checkpoint compatibility version; mismatches force full replay.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `average_cost_pool_state`

- **Purpose**: Versioned aggregate state for bounded average-cost processing.
- **Description**: Stores current AVCO quantity plus local/base basis per portfolio/security so a
  strictly ordered acquisition or disposal can restore one aggregate source. It complements rather
  than replaces `position_lot_state`, whose source rows remain externally visible lineage truth.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`;
  `representative_source_transaction_id` -> `transactions.transaction_id`
- **Usage (modules/features)**: `src/services/portfolio_transaction_processing_service/app/infrastructure/cost_basis/average_cost_pool_repository.py`,
  `src/services/portfolio_transaction_processing_service/app/application/cost_basis_processing/execution.py`
- **Typical access patterns**: Composite-primary-key lookup with a table-scoped row lock, atomic
  upsert in the combined transaction-processing unit of work, and support scans by updated key.
- **Column definitions**:
  - `portfolio_id` (String) (PK, FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `security_id` (String) (PK): Canonical security identifier.
  - `instrument_id` (String): Canonical instrument identifier used for compatibility validation.
  - `representative_source_transaction_id` (String) (FK `transactions.transaction_id`): Source row
    that receives exact allocation residual and carries engine lineage for aggregate restoration.
  - `pool_quantity` (Numeric): Nonnegative current AVCO quantity.
  - `pool_cost_local` (Numeric): Nonnegative current cost basis in transaction/instrument currency.
  - `pool_cost_base` (Numeric): Nonnegative current cost basis in portfolio base currency.
  - `state_version` (String): Compatibility version; mismatches force full replay.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `accrued_income_offset_state`

- **Purpose**: Accrued-income offset state for fixed income flows.
- **Description**: Tracks paid accrued interest and remaining offset to avoid double counting income.
- **Relationships**: `source_transaction_id` -> `transactions.transaction_id`; `portfolio_id` -> `portfolios.portfolio_id`
- **Usage (modules/features)**: `src/services/query_service/app/repositories/buy_state_repository.py`, `src/services/portfolio_transaction_processing_service/app/infrastructure/income/accrued_income_offset_repository.py`, `src/services/portfolio_transaction_processing_service/app/application/cost_basis_processing/execution.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `offset_id` (String): Identifier for offset.
  - `source_transaction_id` (String) (FK `transactions.transaction_id`): Identifier for source transaction.
  - `portfolio_id` (String) (FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `instrument_id` (String): Identifier for instrument.
  - `security_id` (String): Canonical security identifier.
  - `accrued_interest_paid_local` (Numeric): Domain attribute used by the owning module.
  - `remaining_offset_local` (Numeric): Domain attribute used by the owning module.
  - `economic_event_id` (String): Identifier for economic event.
  - `linked_transaction_group_id` (String): Identifier for linked transaction group.
  - `calculation_policy_id` (String): Identifier for calculation policy.
  - `calculation_policy_version` (String): Domain attribute used by the owning module.
  - `source_system` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `position_timeseries`

- **Purpose**: Position-level analytical timeseries.
- **Description**: Daily BOD/EOD rollups per position and epoch for analytics inputs.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`; `security_id` -> `instruments.security_id`
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/analytics_timeseries_repository.py`, `src/services/query_control_plane_service/app/contracts/analytics_inputs.py`, `src/services/query_control_plane_service/app/application/analytics/analytics_timeseries_service.py`, `src/services/portfolio_derived_state_service/app/infrastructure/timeseries_generation_repository.py`, `src/services/portfolio_derived_state_service/app/application/position_timeseries/materialize_position_timeseries.py`, `src/services/portfolio_derived_state_service/app/infrastructure/portfolio_aggregation_repository.py`, `src/services/portfolio_derived_state_service/app/application/portfolio_timeseries/calculation.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `portfolio_id` (String) (FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `security_id` (String) (FK `instruments.security_id`): Canonical security identifier.
  - `date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `epoch` (Integer): Deterministic reprocessing generation/version for state isolation.
  - `bod_market_value` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `bod_cashflow_position` (Numeric): Domain attribute used by the owning module.
  - `eod_cashflow_position` (Numeric): Domain attribute used by the owning module.
  - `bod_cashflow_portfolio` (Numeric): Domain attribute used by the owning module.
  - `eod_cashflow_portfolio` (Numeric): Domain attribute used by the owning module.
  - `eod_market_value` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `fees` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `quantity` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `cost` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `portfolio_timeseries`

- **Purpose**: Portfolio-level analytical timeseries.
- **Description**: Daily BOD/EOD rollups per portfolio and epoch.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/analytics_timeseries_repository.py`, `src/services/query_control_plane_service/app/contracts/analytics_inputs.py`, `src/services/query_control_plane_service/app/application/analytics/analytics_timeseries_service.py`, `src/services/portfolio_derived_state_service/app/infrastructure/portfolio_aggregation_repository.py`, `src/services/portfolio_derived_state_service/app/application/portfolio_timeseries/materialize_portfolio_timeseries.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `portfolio_id` (String) (FK `portfolios.portfolio_id`): Canonical portfolio identifier.
  - `date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `epoch` (Integer): Deterministic reprocessing generation/version for state isolation.
  - `bod_market_value` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `bod_cashflow` (Numeric): Domain attribute used by the owning module.
  - `eod_cashflow` (Numeric): Domain attribute used by the owning module.
  - `eod_market_value` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `fees` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `processed_events`

- **Purpose**: Consumer idempotency registry.
- **Description**: Marks Kafka events already handled by service to prevent double processing.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/libs/portfolio-common/portfolio_common/idempotency_repository.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `event_id` (String): Identifier for event.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `service_name` (String): Domain attribute used by the owning module.
  - `correlation_id` (String): Trace/correlation id used across logs and events.
  - `processed_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.

## `outbox_events`

- **Purpose**: Transactional outbox for reliable publish-after-commit.
- **Description**: Stores domain events pending dispatch to Kafka topics. Unresolved rows form
  ordered `(topic, partition_key)` streams by `(created_at, id)`.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py`, `src/libs/portfolio-common/portfolio_common/monitoring.py`, `src/libs/portfolio-common/portfolio_common/outbox_repository.py`
- **Typical access patterns**: Claim eligible unresolved stream heads with
  `FOR UPDATE SKIP LOCKED`, publish outside the claim transaction, and persist token-fenced
  delivery results. The partial `(topic, partition_key, created_at, id)` index covers `PENDING`
  and `FAILED` stream barriers.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `aggregate_type` (String): Domain type discriminator used to branch processing behavior.
  - `aggregate_id` (String): Identifier for aggregate.
  - `partition_key` (String): Ordered Kafka transport-stream identity within `topic`.
  - `event_type` (String): Domain type discriminator used to branch processing behavior.
  - `payload` (JSON): JSON payload storing structured request/result or metadata content.
  - `topic` (String): Domain attribute used by the owning module.
  - `status` (String): Current lifecycle status for the record/work item.
  - `correlation_id` (String): Trace/correlation id used across logs and events.
  - `ingestion_job_id` (String): Durable ingestion-job owner propagated to Kafka; nullable for non-ingestion and legacy events.
  - `retry_count` (Integer): Domain attribute used by the owning module.
  - `last_attempted_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `next_attempt_at` (DateTime): Earliest retry-eligible timestamp; a future head blocks only its stream.
  - `claim_token` (String): Lease fencing token for delivery-result persistence.
  - `claim_expires_at` (DateTime): UTC expiry after which the stream head is reclaimable.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `processed_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.

## `portfolio_aggregation_jobs`

- **Purpose**: Durable aggregation work queue.
- **Description**: Portfolio/date tasks for timeseries aggregation with status, target-epoch, material-source, and lease tracking.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/operations/repository.py`, `src/services/portfolio_derived_state_service/app/infrastructure/portfolio_aggregation_repository.py`, `src/services/portfolio_derived_state_service/app/application/aggregation_jobs/scheduler.py`, `src/services/portfolio_derived_state_service/app/infrastructure/timeseries_generation_repository.py`, `src/services/portfolio_derived_state_service/app/main.py`
- **Typical access patterns**: Deterministic ready-job polling with `FOR UPDATE SKIP LOCKED`, token-fenced terminal writes, expiry-based recovery, and operator status reads.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `aggregation_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `status` (String): Current lifecycle status for the record/work item.
  - `correlation_id` (String): Trace/correlation id used across logs and events.
  - `attempt_count` (Integer): Number of durable claim attempts.
  - `target_epoch` (Integer): Highest authoritative source epoch the claimed calculation may materialize.
  - `source_revision` (Integer): Positive material-staging generation, including delayed lower-per-security epoch changes, used with target epoch and lease token to fence terminal writes.
  - `failure_reason` (Text): Durable reprocess or terminal-failure context.
  - `lease_owner` (String): Runtime instance that owns the active claim; nullable when unclaimed.
  - `lease_token` (String): Opaque fencing token required for terminal writes; nullable when unclaimed.
  - `lease_expires_at` (DateTime): UTC recovery boundary for the active claim; nullable when unclaimed.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `portfolio_valuation_jobs`

- **Purpose**: Durable valuation work queue.
- **Description**: Portfolio/security/date/epoch valuation tasks with retry, failure, and
  database-clock claim-lease metadata.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/operations/repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/libs/portfolio-common/portfolio_common/valuation_job_repository.py`, `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `security_id` (String): Canonical security identifier.
  - `valuation_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `epoch` (Integer): Deterministic reprocessing generation/version for state isolation.
  - `status` (String): Current lifecycle status for the record/work item.
  - `requeue_requested` (Boolean): Whether newer source readiness arrived during active processing and requires another claim after the current attempt.
  - `source_correction_id` (String): Stable identity of the source mutation that most recently armed or rearmed the job.
  - `correlation_id` (String): Trace/correlation id used across logs and events.
  - `correlation_missing_reason` (String): Diagnostic reason recorded when upstream correlation authority was unavailable.
  - `alternate_lookup_key` (String): Governed fallback lookup identity used for operational diagnostics.
  - `failure_reason` (Text): Human-readable reason for failure/exception status.
  - `attempt_count` (Integer): Domain attribute used by the owning module.
  - `claimed_readiness_outbox_id` (BigInteger): Maximum committed positive outbox sequence claimed for this exact portfolio/security/date/epoch scope; defaults to zero until source-owned sequence authority is available.
  - `valuation_lease_owner` (String): Stable scheduler-instance identity for an active claim;
    nullable only when the row is not processing.
  - `valuation_claim_token` (String): Opaque claim-generation token rotated on each claim;
    terminal and dispatch-recovery writes require an exact match.
  - `valuation_lease_expires_at` (DateTime): Finite PostgreSQL-clock expiry for the active claim;
    terminal writes require it to remain in the future and stale recovery rechecks it on the write.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `pipeline_stage_state`

- **Purpose**: Shared compatibility evidence for transaction readiness and portfolio-day financial controls.
- **Description**: Tracks epoch-fenced transaction readiness plus monotonic reconciliation control outcomes consumed by QCP support reads. The retired pipeline runtime does not own this table.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/portfolio_transaction_processing_service/app/infrastructure/transaction_readiness/stage_repository.py`, `src/services/financial_reconciliation_service/app/infrastructure/reconciliation_control_evidence_repository.py`, `src/services/query_control_plane_service/app/infrastructure/operations/repository.py`
- **Typical access patterns**: Epoch-fenced transaction-stage claims, monotonic reconciliation-control upserts, latest-epoch suppression, and status-filtered operational reads.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `stage_name` (String): Stage identifier (for example `TRANSACTION_PROCESSING`).
  - `transaction_id` (String): Canonical transaction identifier.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `security_id` (String): Canonical security identifier when stage is security-scoped.
  - `business_date` (Date): Business date for stage progression.
  - `epoch` (Integer): Deterministic reprocessing generation/version for stage isolation.
  - `status` (String): Stage lifecycle status.
  - `cost_event_seen` (Boolean): Whether cost-side prerequisite signal has been observed.
  - `cashflow_event_seen` (Boolean): Whether cashflow-side prerequisite signal has been observed.
  - `ready_emitted_at` (DateTime): Timestamp when readiness event was emitted.
  - `last_source_event_type` (String): Last source signal type processed for this stage key.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `ingestion_jobs`

- **Purpose**: Ingestion job tracking and ops visibility.
- **Description**: Tenant-bound batch/API submission lifecycle records with source-safe failure outcomes and versioned durable request-evidence and replay authority. Tenant authority is admitted independently of the retained domain payload.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/ingestion_service/app/services/ingestion_job_service.py`, `src/services/ingestion_service/app/services/ingestion_job_lifecycle.py`, `src/services/ingestion_service/app/services/ingestion_payload_evidence.py`, `src/services/ingestion_service/app/infrastructure/ingestion_idempotency_replay_reader.py`, `src/services/event_replay_service/app/routers/ingestion_operations.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/DTOs/ingestion_job_dto.py`, `src/libs/portfolio-common/portfolio_common/monitoring.py`, `src/services/ingestion_service/app/main.py`
- **Typical access patterns**: Tenant-scoped submission-time reads, idempotent submission checks against a keyed full-payload fingerprint, status-filtered job polling, and fail-closed replay authorization from persisted tenant/evidence policy and technical expiry.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `job_id` (String): Identifier for job.
  - `tenant_id` (String): Normalized, non-blank tenant authority admitted with the request and retained independently of the domain payload.
  - `endpoint` (String): Domain attribute used by the owning module.
  - `entity_type` (String): Domain type discriminator used to branch processing behavior.
  - `status` (String): Current lifecycle status for the record/work item.
  - `accepted_count` (Integer): Domain attribute used by the owning module.
  - `idempotency_key` (String): Domain attribute used by the owning module.
  - `correlation_id` (String): Trace/correlation id used across logs and events.
  - `request_id` (String): Identifier for request.
  - `trace_id` (String): Identifier for trace.
  - `submitted_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `completed_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `failure_reason` (Text): Human-readable reason for failure/exception status.
  - `failure_status_code` (Integer): Source HTTP status for the governed failure outcome; present only with a stable failure code.
  - `failure_code` (String): Stable product-safe failure code recorded with the failure status.
  - `failure_detail` (JSON): Source-safe structured failure detail; SQL `NULL` when no governed failure outcome exists.
  - `failure_headers` (JSON): Source-safe allowlisted failure headers needed for retry behavior; SQL `NULL` when absent.
  - `request_payload` (JSON): Source-safe replay payload when policy-authorized; SQL `NULL` for fingerprint-only evidence.
  - `request_payload_fingerprint` (String): Purpose-bound, key-versioned HMAC over the full canonical request used for equality/conflict proof; it does not authorize replay or reconstruct payload.
  - `request_payload_policy_version` (String): Version of the endpoint-family evidence policy applied when the job was accepted.
  - `request_payload_classification` (String): Governed sensitivity classification for the submitted payload evidence.
  - `request_payload_representation` (String): Durable evidence posture (`source_safe_replay`, `fingerprint_only`, or legacy-redacted compatibility evidence).
  - `request_payload_replay_eligible` (Boolean): Whether the durable source evidence authorizes full replay before technical expiry.
  - `request_payload_partial_replay_eligible` (Boolean): Whether the same policy explicitly authorizes record-subset replay; cannot be true when full replay is ineligible.
  - `request_payload_replay_expires_at` (DateTime): Finite UTC technical cutoff for replay authority; absent for non-replayable evidence.
  - `request_payload_retention_authority` (String): Named governing retention decision for the evidence posture; never caller-supplied free text.
  - `retry_count` (Integer): Domain attribute used by the owning module.
  - `last_retried_at` (DateTime): Domain attribute used by the owning module.

## `ingestion_job_failures`

- **Purpose**: Ingestion failure detail records.
- **Description**: Failure rows tied to ingestion jobs for remediation/replay.
- **Relationships**: `job_id` -> `ingestion_jobs.job_id`
- **Usage (modules/features)**: `src/services/ingestion_service/app/services/ingestion_job_service.py`, `src/services/event_replay_service/app/routers/ingestion_operations.py`, `src/services/ingestion_service/app/DTOs/ingestion_job_dto.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `failure_id` (String): Identifier for failure.
  - `job_id` (String) (FK `ingestion_jobs.job_id`): Identifier for job.
  - `failure_phase` (String): Domain attribute used by the owning module.
  - `failure_reason` (Text): Human-readable reason for failure/exception status.
  - `failed_record_keys` (JSON): Domain attribute used by the owning module.
  - `failed_at` (DateTime): Domain attribute used by the owning module.

## `ingestion_ops_control`

- **Purpose**: Operational control plane for ingestion mode.
- **Description**: Stores pause/drain/replay window controls.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/ingestion_service/app/services/ingestion_job_service.py`, `src/services/event_replay_service/app/routers/ingestion_operations.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `mode` (String): Operational control mode for service behavior.
  - `replay_window_start` (DateTime): Domain attribute used by the owning module.
  - `replay_window_end` (DateTime): Domain attribute used by the owning module.
  - `updated_by` (String): Domain attribute used by the owning module.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `consumer_dlq_events`

- **Purpose**: Dead-letter event archive.
- **Description**: Captured failed-consumer events with reason and context.
- **Relationships**: `ingestion_job_id` -> `ingestion_jobs.job_id`
- **Usage (modules/features)**: `src/services/ingestion_service/app/services/ingestion_job_service.py`, `src/services/event_replay_service/app/routers/ingestion_operations.py`, `src/services/ingestion_service/app/DTOs/ingestion_job_dto.py`, `src/libs/portfolio-common/portfolio_common/kafka_consumer.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `event_id` (String): Identifier for event.
  - `original_topic` (String): Domain attribute used by the owning module.
  - `consumer_group` (String): Domain attribute used by the owning module.
  - `dlq_topic` (String): Domain attribute used by the owning module.
  - `original_key` (String): Domain attribute used by the owning module.
  - `error_reason` (Text): Human-readable reason for failure/exception status.
  - `correlation_id` (String): Trace/correlation id used across logs and events.
  - `ingestion_job_id` (String) (FK `ingestion_jobs.job_id`): Durable evidence owner; correlation metadata is not an ownership key.
  - `correlation_missing_reason` (String): Explicit reason correlation_id is absent for replay and support diagnostics.
  - `alternate_lookup_key` (String): Durable alternate support lookup key when correlation_id is absent.
  - `payload_excerpt` (Text): Domain attribute used by the owning module.
  - `observed_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.

## `consumer_dlq_replay_audit`

- **Purpose**: Replay audit trail for DLQ remediation.
- **Description**: Records replay requests/outcomes for governance and incident forensics.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/ingestion_service/app/services/ingestion_job_service.py`, `src/services/event_replay_service/app/routers/ingestion_operations.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `replay_id` (String): Identifier for replay.
  - `recovery_path` (String): Domain attribute used by the owning module.
  - `event_id` (String): Identifier for event.
  - `replay_fingerprint` (String): Domain attribute used by the owning module.
  - `correlation_id` (String): Trace/correlation id used across logs and events.
  - `correlation_missing_reason` (String): Explicit reason correlation_id is absent for replay and support diagnostics.
  - `alternate_lookup_key` (String): Durable alternate support lookup key when correlation_id is absent.
  - `job_id` (String): Identifier for job.
  - `endpoint` (String): Domain attribute used by the owning module.
  - `replay_status` (String): Domain attribute used by the owning module.
  - `dry_run` (Boolean): Domain attribute used by the owning module.
  - `replay_reason` (Text): Human-readable reason for failure/exception status.
  - `requested_by` (String): Domain attribute used by the owning module.
  - `requested_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `completed_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.

## `position_state`

- **Purpose**: Current processing state per portfolio-security key.
- **Description**: Watermark/epoch/status pointer that orchestrates reprocessing and backlog advancement.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/position_repository.py`, `src/services/query_control_plane_service/app/infrastructure/operations/repository.py`, `src/libs/portfolio-common/portfolio_common/position_state_repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/portfolio_transaction_processing_service/app/infrastructure/position/recalculation_state.py`, `src/services/query_control_plane_service/app/infrastructure/operations/operations_position_scope_queries.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `security_id` (String): Canonical security identifier.
  - `epoch` (Integer): Deterministic reprocessing generation/version for state isolation.
  - `watermark_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `status` (String): Current lifecycle status for the record/work item.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `instrument_reprocessing_state`

- **Purpose**: Instrument-level trigger state for back-dated changes.
- **Description**: Earliest impacted date per security awaiting fan-out into reprocessing jobs.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/valuation_orchestrator_service/app/repositories/instrument_reprocessing_state_repository.py`, `src/services/valuation_orchestrator_service/app/consumers/price_event_consumer.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `security_id` (String): Canonical security identifier.
  - `earliest_impacted_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `reprocessing_jobs`

- **Purpose**: Durable reprocessing control queue.
- **Description**: System jobs that reset/advance watermarks and orchestrate historical recalculation.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`, `src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py`, `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Active payload integrity**: `PENDING` and `PROCESSING` Reset/FX jobs must carry complete,
  safely extractable string identity and temporal fields. Migration `c162b2c3d529` quarantines
  malformed pending rows with recorded type-level counts before installing the database CHECK
  constraint. A JSONB-compatibility preflight identifies legacy active JSON values that cannot be
  safely extracted while accepting harmless literal escape text. Terminal historical evidence is
  retained without payload rewriting. The database constraint is authoritative for post-cutover
  representability, normalized identities, and scalar types; application `fromisoformat`
  validation is authoritative for temporal grammar. The locked cutover applies that Python grammar
  before its auditable quarantine update, and runtime staging applies the same validator before SQL
  coalescing. Runtime quarantine remains required for predecessor-schema and restored rows.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `job_type` (String): Domain type discriminator used to branch processing behavior.
  - `payload` (JSON): JSON payload storing structured request/result or metadata content.
  - `status` (String): Current lifecycle status for the record/work item.
  - `correlation_id` (String, nullable): Durable request/event lineage when source correlation is available.
  - `correlation_missing_reason` (String, nullable): Governed explanation when correlation authority is unavailable.
  - `alternate_lookup_key` (String, nullable): Stable support lookup when correlation is unavailable.
  - `attempt_count` (Integer): Domain attribute used by the owning module.
  - `last_attempted_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `failure_reason` (Text): Human-readable reason for failure/exception status.
  - `lease_owner` (String, nullable): Bounded worker identity owning a `PROCESSING` claim.
  - `lease_token` (String, nullable): Opaque 32-character claim fence required for terminal writes.
  - `lease_expires_at` (DateTime, nullable): Database-clock expiry after which recovery may reclaim work.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `analytics_export_jobs`

- **Purpose**: Async export job lifecycle for analytics payloads.
- **Description**: Tracks request fingerprint, execution state, and persisted export result payloads.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/infrastructure/analytics_export_repository.py`, `src/services/query_control_plane_service/app/routers/analytics_inputs.py`, `src/services/query_control_plane_service/app/application/analytics/analytics_timeseries_service.py`, `src/services/query_control_plane_service/app/contracts/analytics_inputs.py`, `src/libs/portfolio-common/portfolio_common/monitoring.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `job_id` (String): Identifier for job.
  - `dataset_type` (String): Domain type discriminator used to branch processing behavior.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `status` (String): Current lifecycle status for the record/work item.
  - `request_fingerprint` (String): Domain attribute used by the owning module.
  - `request_payload` (JSON): JSON payload storing structured request/result or metadata content.
  - `result_payload` (JSON): JSON payload storing structured request/result or metadata content.
  - `result_row_count` (Integer): Domain attribute used by the owning module.
  - `result_format` (String): Domain attribute used by the owning module.
  - `compression` (String): Domain attribute used by the owning module.
  - `error_message` (Text): Human-readable reason for failure/exception status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `started_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `completed_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `cashflow_rules`

- **Purpose**: Rule catalog for transaction-to-cashflow mapping.
- **Description**: Configurable policy table describing classification/timing behavior by transaction type.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/portfolio_transaction_processing_service/app/application/cashflow_processing/use_case.py`, `src/services/portfolio_transaction_processing_service/app/infrastructure/cashflow/rule_cache.py`, `src/services/portfolio_transaction_processing_service/app/infrastructure/cashflow/rule_repository.py`, `src/services/portfolio_transaction_processing_service/app/infrastructure/cashflow/rule_resolver.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Governed cash-in-lieu rule**: `CASH_IN_LIEU` is a position-level, non-portfolio `TRANSFER` rule. It represents fractional product disposal and must not be classified as income; the linked `ADJUSTMENT` owns the real cash-account settlement.
- **Column definitions**:
  - `transaction_type` (String): Domain type discriminator used to branch processing behavior.
  - `classification` (String): Domain attribute used by the owning module.
  - `timing` (String): Domain attribute used by the owning module.
  - `is_position_flow` (Boolean): Boolean flag controlling behavior/interpretation.
  - `is_portfolio_flow` (Boolean): Boolean flag controlling behavior/interpretation.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## Schema Review Findings

### Actively Used and Architecturally Required
- Core ledger/state: `transactions`, `position_history`, `daily_position_snapshots`, `position_state`, `position_lot_state`, `lot_amortized_cost_authority`, `lot_amortized_cost_profiles`, `lot_amortized_cost_periods`, `average_cost_pool_state`, `cashflows`, `portfolio_timeseries`, `position_timeseries`.
- Processing reliability: `processed_events`, `outbox_events`, `portfolio_valuation_jobs`, `portfolio_aggregation_jobs`, `reprocessing_jobs`, `instrument_reprocessing_state`.
- Ingestion/ops governance: `ingestion_jobs`, `ingestion_job_failures`, `ingestion_ops_control`, `consumer_dlq_events`, `consumer_dlq_replay_audit`.
- Reference data: `business_dates`, `portfolios`, `instruments`, `market_prices`, `fx_rates`, benchmark/index/risk-free tables.

### Partially Implemented or Maturity Gaps
- `transaction_costs`: now populated by cost calculator, but current upstream payload commonly provides aggregated `trade_fee`; richer fee-type coverage depends on ingestion payload maturity.
- Simulation tables (`simulation_sessions`, `simulation_changes`): present and usable, but long-term retention/expiry cleanup policy and ops runbook should be formalized if high-volume adoption is expected.
- `classification_taxonomy`: used for taxonomy governance; enforcement hooks across all ingestion endpoints should remain mandatory to avoid free-text drift.

### Potential Redundancy / Decision Points (Not immediate deletions)
- `position_history` and `daily_position_snapshots` are intentionally separate (transaction-derived ledger vs valuation snapshot). Keep both; do not merge.
- `portfolio_valuation_jobs` and `portfolio_aggregation_jobs` are separate by design (different grains/workflows). Keep both.
- `instrument_reprocessing_state` and `reprocessing_jobs` can look similar but serve trigger-vs-work separation; keep both for resilience and bounded fan-out.

### Consistency and Design Notes
- Enforce `epoch` in all state/job updates and queries for deterministic reprocessing isolation.
- Keep business date as booked-state boundary; allow future-dated transactions but avoid treating future dates as booked valuations unless explicitly projected.
- Continue API-first policy: no downstream direct DB reads; these tables are internal persistence and ops surfaces should be via query/ingestion APIs.
- For long-lived job tables, add periodic archival/compaction strategy and monitoring SLOs (pending age, stale processing count, failure-rate trends).

## Recommended Next Actions
1. Add an automated schema-doc generation check in CI to keep this catalog synchronized with model changes.
2. Add table-level ownership tags (service owner + runbook link) for incident response clarity.
3. Add data retention policy RFC for job/audit tables (`*_jobs`, `consumer_dlq_*`, `processed_events`, `outbox_events`).
