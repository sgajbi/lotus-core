# Lotus-Core Database Table Catalog and Schema Review

This document catalogs all application tables defined in `src/libs/portfolio-common/portfolio_common/database_models.py` and reviews schema fitness for current Lotus-Core architecture.

## Scope and Method

- Source of truth: SQLAlchemy models in `database_models.py` (39 tables).
- Usage evidence: code-reference scan across `src/` (model class and table-name hits).
- This review distinguishes: `actively used`, `partially implemented`, and `needs decision`.

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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/operations_repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`, `src/services/query_service/app/routers/portfolios.py`, `src/services/ingestion_service/app/routers/portfolios.py`, `src/services/query_service/app/repositories/analytics_timeseries_repository.py`
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
  - `advisor_id` (String): Identifier for advisor.
  - `status` (String): Current lifecycle status for the record/work item.
  - `cost_basis_method` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `simulation_sessions`

- **Purpose**: Tracks sandbox simulation sessions.
- **Description**: Session-level envelope for hypothetical changes against a base portfolio.
- **Relationships**: `portfolio_id` -> `portfolios.portfolio_id`
- **Usage (modules/features)**: `src/services/query_service/app/repositories/simulation_repository.py`, `src/services/query_service/app/services/simulation_service.py`, `src/services/query_control_plane_service/app/routers/simulation.py`, `src/services/query_service/app/dtos/simulation_dto.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/simulation_repository.py`, `src/services/query_service/app/services/simulation_service.py`, `src/services/query_service/app/dtos/simulation_dto.py`, `src/services/query_control_plane_service/app/routers/simulation.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/position_repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/query_service/app/services/position_service.py`, `src/services/calculators/position_calculator/app/repositories/position_repository.py`, `src/services/query_service/app/repositories/operations_repository.py`, `src/services/query_service/app/routers/positions.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/position_repository.py`, `src/services/query_service/app/repositories/operations_repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/calculators/position_calculator/app/repositories/position_repository.py`, `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`, `src/services/persistence_service/app/repositories/market_price_repository.py`
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
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `fx_rates`

- **Purpose**: Reference FX rates used by cost/valuation.
- **Description**: Daily currency conversion rates for trade and valuation normalization.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/fx_rate_repository.py`, `src/services/query_service/app/services/fx_rate_service.py`, `src/services/ingestion_service/app/services/ingestion_service.py`, `src/services/query_service/app/repositories/analytics_timeseries_repository.py`, `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/persistence_service/app/repositories/fx_rate_repository.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
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

## `model_portfolio_targets`

- **Purpose**: Effective-dated target weights and policy bands for discretionary model portfolios.
- **Description**: Stores instrument target rows for `DpmModelPortfolioTarget:v1`, including
  target weight, min/max bands, lifecycle status, and source lineage.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/query_service/app/dtos/reference_integration_dto.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/query_service/app/dtos/reference_integration_dto.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/services/reference_data_ingestion_service.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/query_service/app/dtos/reference_integration_dto.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`, `src/services/query_service/app/dtos/reference_integration_dto.py`
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
- **Usage (modules/features)**: `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/query_service/app/dtos/reference_integration_dto.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/services/integration_service.py`, `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/query_service/app/dtos/reference_integration_dto.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/reference_data_repository.py`, `src/services/query_control_plane_service/app/routers/integration.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/query_service/app/services/integration_service.py`, `src/services/query_service/app/dtos/reference_integration_dto.py`, `src/services/ingestion_service/app/DTOs/reference_data_dto.py`
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
- **Usage (modules/features)**: `src/services/calculators/cost_calculator_service/app/consumer.py`, `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`, `src/services/query_service/app/repositories/transaction_repository.py`, `src/services/ingestion_service/app/routers/transactions.py`, `src/services/calculators/cost_calculator_service/app/transaction_processor.py`, `src/services/calculators/cost_calculator_service/app/repository.py`
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
  - `economic_event_id` (String): Identifier for economic event.
  - `linked_transaction_group_id` (String): Identifier for linked transaction group.
  - `calculation_policy_id` (String): Identifier for calculation policy.
  - `calculation_policy_version` (String): Domain attribute used by the owning module.
  - `source_system` (String): Domain attribute used by the owning module.

## `transaction_costs`

- **Purpose**: Normalized transaction fee breakdown.
- **Description**: Per-transaction fee components (brokerage, duty, exchange fee, etc.).
- **Relationships**: `transaction_id` -> `transactions.transaction_id`; ORM relationship `transaction` -> `Transaction`
- **Usage (modules/features)**: `src/services/calculators/cost_calculator_service/app/repository.py`, `src/libs/portfolio-common/portfolio_common/models.py`, `src/services/calculators/cost_calculator_service/app/consumer.py`, `src/services/calculators/cost_calculator_service/app/cost_engine/processing/cost_calculator.py`, `src/services/calculators/cost_calculator_service/app/transaction_processor.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `transaction_id` (String) (FK `transactions.transaction_id`): Canonical transaction identifier.
  - `fee_type` (String): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `amount` (Numeric): Numeric financial measure used in valuation, cost, or analytics calculations.
  - `currency` (String): ISO currency code for monetary interpretation of related amounts.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `cashflows`

- **Purpose**: Derived cashflow ledger from transaction rules.
- **Description**: Position/portfolio cash impacts by date, type, and epoch.
- **Relationships**: `transaction_id` -> `transactions.transaction_id`; `portfolio_id` -> `portfolios.portfolio_id`; ORM relationship `transaction` -> `Transaction`
- **Usage (modules/features)**: `src/services/query_service/app/repositories/cashflow_repository.py`, `src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py`, `src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py`, `src/services/query_service/app/routers/cashflow_projection.py`, `src/services/query_service/app/services/cashflow_projection_service.py`, `src/services/calculators/cashflow_calculator_service/app/repositories/cashflow_repository.py`
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
- **Description**: Lot-level state for cost basis/disposition and lifecycle traceability.
- **Relationships**: `source_transaction_id` -> `transactions.transaction_id`; `portfolio_id` -> `portfolios.portfolio_id`
- **Usage (modules/features)**: `src/services/query_service/app/repositories/buy_state_repository.py`, `src/services/calculators/cost_calculator_service/app/repository.py`
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
  - `economic_event_id` (String): Identifier for economic event.
  - `linked_transaction_group_id` (String): Identifier for linked transaction group.
  - `calculation_policy_id` (String): Identifier for calculation policy.
  - `calculation_policy_version` (String): Domain attribute used by the owning module.
  - `source_system` (String): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `accrued_income_offset_state`

- **Purpose**: Accrued-income offset state for fixed income flows.
- **Description**: Tracks paid accrued interest and remaining offset to avoid double counting income.
- **Relationships**: `source_transaction_id` -> `transactions.transaction_id`; `portfolio_id` -> `portfolios.portfolio_id`
- **Usage (modules/features)**: `src/services/query_service/app/repositories/buy_state_repository.py`, `src/services/calculators/cost_calculator_service/app/repository.py`, `src/services/calculators/cost_calculator_service/app/consumer.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/analytics_timeseries_repository.py`, `src/services/query_service/app/dtos/analytics_input_dto.py`, `src/services/query_service/app/services/analytics_timeseries_service.py`, `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`, `src/services/timeseries_generator_service/app/consumers/position_timeseries_consumer.py`, `src/services/portfolio_aggregation_service/app/core/portfolio_timeseries_logic.py`
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/analytics_timeseries_repository.py`, `src/services/query_service/app/dtos/analytics_input_dto.py`, `src/services/portfolio_aggregation_service/app/repositories/timeseries_repository.py`, `src/services/query_service/app/services/analytics_timeseries_service.py`, `src/services/portfolio_aggregation_service/app/core/portfolio_timeseries_logic.py`, `src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py`
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
- **Description**: Stores domain events pending dispatch to Kafka topics.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py`, `src/libs/portfolio-common/portfolio_common/monitoring.py`, `src/libs/portfolio-common/portfolio_common/outbox_repository.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `aggregate_type` (String): Domain type discriminator used to branch processing behavior.
  - `aggregate_id` (String): Identifier for aggregate.
  - `event_type` (String): Domain type discriminator used to branch processing behavior.
  - `payload` (JSON): JSON payload storing structured request/result or metadata content.
  - `topic` (String): Domain attribute used by the owning module.
  - `status` (String): Current lifecycle status for the record/work item.
  - `correlation_id` (String): Trace/correlation id used across logs and events.
  - `retry_count` (Integer): Domain attribute used by the owning module.
  - `last_attempted_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `processed_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.

## `portfolio_aggregation_jobs`

- **Purpose**: Durable aggregation work queue.
- **Description**: Portfolio/date tasks for timeseries aggregation with status tracking.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/operations_repository.py`, `src/services/portfolio_aggregation_service/app/repositories/timeseries_repository.py`, `src/services/timeseries_generator_service/app/consumers/position_timeseries_consumer.py`, `src/services/portfolio_aggregation_service/app/core/aggregation_scheduler.py`, `src/services/portfolio_aggregation_service/app/main.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `aggregation_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `status` (String): Current lifecycle status for the record/work item.
  - `correlation_id` (String): Trace/correlation id used across logs and events.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `portfolio_valuation_jobs`

- **Purpose**: Durable valuation work queue.
- **Description**: Portfolio/security/date/epoch valuation tasks with retry and failure metadata.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/operations_repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/libs/portfolio-common/portfolio_common/valuation_job_repository.py`, `src/services/valuation_orchestrator_service/app/core/valuation_scheduler.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `portfolio_id` (String): Canonical portfolio identifier.
  - `security_id` (String): Canonical security identifier.
  - `valuation_date` (Date): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `epoch` (Integer): Deterministic reprocessing generation/version for state isolation.
  - `status` (String): Current lifecycle status for the record/work item.
  - `correlation_id` (String): Trace/correlation id used across logs and events.
  - `failure_reason` (Text): Human-readable reason for failure/exception status.
  - `attempt_count` (Integer): Domain attribute used by the owning module.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `pipeline_stage_state`

- **Purpose**: Durable stage-gate state for orchestrated pipeline readiness.
- **Description**: Tracks prerequisite completion signals and emission state for gate events at transaction scope.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/pipeline_orchestrator_service/app/repositories/pipeline_stage_repository.py`, `src/services/pipeline_orchestrator_service/app/services/pipeline_orchestrator_service.py`
- **Typical access patterns**: Idempotent upserts from independent completion streams, conditional status transition updates, and status-filtered operational reads.
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
- **Description**: Batch/API submission lifecycle records with status and correlation.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/ingestion_service/app/services/ingestion_job_service.py`, `src/services/event_replay_service/app/routers/ingestion_operations.py`, `src/services/ingestion_service/app/routers/reference_data.py`, `src/services/ingestion_service/app/DTOs/ingestion_job_dto.py`, `src/libs/portfolio-common/portfolio_common/monitoring.py`, `src/services/ingestion_service/app/main.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `job_id` (String): Identifier for job.
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
  - `request_payload` (JSON): JSON payload storing structured request/result or metadata content.
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
- **Relationships**: No explicit foreign-key relationships declared.
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
- **Usage (modules/features)**: `src/services/query_service/app/repositories/position_repository.py`, `src/services/query_service/app/repositories/operations_repository.py`, `src/libs/portfolio-common/portfolio_common/position_state_repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/calculators/position_calculator/app/core/position_logic.py`, `src/services/query_service/app/services/operations_service.py`
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
- **Usage (modules/features)**: `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`, `src/services/calculators/position_valuation_calculator/app/repositories/instrument_reprocessing_state_repository.py`, `src/services/valuation_orchestrator_service/app/consumers/price_event_consumer.py`
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
- **Column definitions**:
  - `id` (Integer): Surrogate primary key for internal row identity.
  - `job_type` (String): Domain type discriminator used to branch processing behavior.
  - `payload` (JSON): JSON payload storing structured request/result or metadata content.
  - `status` (String): Current lifecycle status for the record/work item.
  - `attempt_count` (Integer): Domain attribute used by the owning module.
  - `last_attempted_at` (DateTime): Business/event date or timestamp used for ordering, as-of queries, or lifecycle tracking.
  - `failure_reason` (Text): Human-readable reason for failure/exception status.
  - `created_at` (DateTime): Server timestamp when row was created.
  - `updated_at` (DateTime): Server timestamp when row was last updated.

## `analytics_export_jobs`

- **Purpose**: Async export job lifecycle for analytics payloads.
- **Description**: Tracks request fingerprint, execution state, and persisted export result payloads.
- **Relationships**: No explicit foreign-key relationships declared.
- **Usage (modules/features)**: `src/services/query_service/app/repositories/analytics_export_repository.py`, `src/services/query_control_plane_service/app/routers/analytics_inputs.py`, `src/services/query_service/app/services/analytics_timeseries_service.py`, `src/services/query_service/app/dtos/analytics_input_dto.py`, `src/libs/portfolio-common/portfolio_common/monitoring.py`
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
- **Usage (modules/features)**: `src/services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py`, `src/services/calculators/cashflow_calculator_service/app/repositories/cashflow_rules_repository.py`, `src/services/calculators/cashflow_calculator_service/app/core/cashflow_logic.py`
- **Typical access patterns**: As-of/date-range reads, idempotent upserts for event processing, status-filtered job polling where applicable.
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
- Core ledger/state: `transactions`, `position_history`, `daily_position_snapshots`, `position_state`, `position_lot_state`, `cashflows`, `portfolio_timeseries`, `position_timeseries`.
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
