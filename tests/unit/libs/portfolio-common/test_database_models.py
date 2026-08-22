import pytest
from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    AnalyticsExportJob,
    AverageCostPoolState,
    Base,
    BenchmarkCompositionSeries,
    BenchmarkDefinition,
    CashAccountMaster,
    Cashflow,
    ClientIncomeNeedsSchedule,
    ClientRestrictionProfile,
    ClientTaxProfile,
    ClientTaxRuleSet,
    CorporateActionChildObservationRecord,
    CorporateActionExecutionMemberRecord,
    CorporateActionExecutionReleaseRecord,
    DailyPositionSnapshot,
    DailyPositionValuationReceiptRecord,
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    IndexDefinition,
    IngestionJob,
    Instrument,
    InstrumentEligibilityProfile,
    InstrumentLookthroughComponent,
    InstrumentValuationPolicyAssignmentRecord,
    LiquidityReserveRequirement,
    LotAmortizedCostPeriodRecord,
    LotAmortizedCostProfileRecord,
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    MarketPrice,
    MarketPriceSourceFactRecord,
    ModelPortfolioDefinition,
    ModelPortfolioTarget,
    PipelineStageState,
    PlannedWithdrawalSchedule,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioMandateBinding,
    PortfolioPartyRoleAssignment,
    PortfolioTimeseries,
    PortfolioValuationJob,
    PositionHistory,
    PositionLotState,
    PositionState,
    PositionTimeseries,
    ReprocessingJob,
    SustainabilityPreferenceProfile,
    Transaction,
    TransactionCost,
)
from portfolio_common.domain.transaction.numeric_policy import (
    TRANSACTION_PERSISTED_DECIMAL_FIELDS,
)
from portfolio_common.financial_numeric import ExactNumeric
from portfolio_common.source_lifecycle_predicates import (
    BENCHMARK_DEFINITION_ACTIVE,
    CLIENT_INCOME_NEEDS_ACTIVE,
    CLIENT_RESTRICTION_ACTIVE,
    CLIENT_TAX_PROFILE_ACTIVE,
    CLIENT_TAX_RULE_SET_ACTIVE,
    DPM_DISCRETIONARY_MANDATE_ACTIVE,
    INDEX_DEFINITION_ACTIVE,
    LIQUIDITY_RESERVE_ACTIVE,
    MODEL_PORTFOLIO_TARGET_ACTIVE,
    PLANNED_WITHDRAWAL_ACTIVE,
    SUSTAINABILITY_PREFERENCE_ACTIVE,
)


def test_database_identifier_names_fit_postgresql_limit():
    names: list[str] = []
    for table in Base.metadata.tables.values():
        names.extend(index.name for index in table.indexes if index.name)
        names.extend(constraint.name for constraint in table.constraints if constraint.name)

    too_long = sorted(name for name in names if len(name) > 63)

    assert too_long == []


def test_corporate_action_execution_release_declares_fenced_state_contract() -> None:
    release = CorporateActionExecutionReleaseRecord.__table__
    member = CorporateActionExecutionMemberRecord.__table__
    observation = CorporateActionChildObservationRecord.__table__
    release_constraints = {constraint.name for constraint in release.constraints}
    member_constraints = {constraint.name for constraint in member.constraints}
    release_indexes = {index.name: index for index in release.indexes}
    member_indexes = {index.name: index for index in member.indexes}
    observation_constraints = {constraint.name for constraint in observation.constraints}

    assert observation.columns["transaction_payload_fingerprint"].type.length == 71
    assert observation.columns["transaction_payload_fingerprint"].nullable is False
    assert "ck_ca_observation_transaction_fingerprint" in observation_constraints

    assert release.columns["structural_plan_content_hash"].type.length == 64
    assert release.columns["release_authority_hash"].type.length == 64
    assert release.columns["lease_owner"].type.length == 128
    assert release.columns["lease_token"].type.length == 64
    assert release.columns["lease_expires_at"].type.timezone is True
    assert {
        "uq_ca_execution_release_readiness",
        "uq_ca_execution_release_authority",
        "ck_ca_execution_release_hashes",
        "ck_ca_execution_release_status",
        "ck_ca_execution_release_counters",
        "ck_ca_execution_release_lease_complete",
        "ck_ca_execution_release_owner_normalized",
        "ck_ca_execution_release_lease_token",
        "ck_ca_execution_release_lease_expiry_finite",
        "ck_ca_execution_release_state_shape",
        "ck_ca_execution_release_completed_finite",
    } <= release_constraints
    assert [column.name for column in release_indexes["ix_ca_execution_release_claim"].columns] == [
        "status",
        "lease_expires_at",
        "id",
    ]
    assert member.columns["observed_child_content_hash"].type.length == 64
    assert member.columns["transaction_payload_fingerprint"].type.length == 71
    assert {
        "uq_ca_execution_member_ordinal",
        "uq_ca_execution_member_transaction",
        "uq_ca_execution_member_observation",
        "ck_ca_execution_member_ordinal",
        "ck_ca_execution_member_transaction_normalized",
        "ck_ca_execution_member_epoch",
        "ck_ca_execution_member_hashes",
        "ck_ca_execution_member_status",
        "ck_ca_execution_member_state_shape",
        "ck_ca_execution_member_completed_finite",
    } <= member_constraints
    assert [column.name for column in member_indexes["ix_ca_execution_member_pending"].columns] == [
        "release_id",
        "status",
        "execution_ordinal",
    ]
    assert [
        column.name for column in member_indexes["ix_ca_execution_member_transaction"].columns
    ] == ["transaction_id"]


def test_transaction_precision_policy_covers_every_numeric_ledger_column() -> None:
    exact_numeric_columns = {
        column.name
        for column in Transaction.__table__.columns
        if isinstance(column.type, ExactNumeric)
    }

    assert exact_numeric_columns == set(TRANSACTION_PERSISTED_DECIMAL_FIELDS)


def test_ingestion_job_declares_complete_failure_outcome_contract() -> None:
    table = IngestionJob.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert {
        "failure_status_code",
        "failure_code",
        "failure_detail",
        "failure_headers",
    } <= set(table.columns.keys())
    assert "ck_ingestion_jobs_failure_outcome_complete" in constraints
    fingerprint_constraint = str(
        constraints["ck_ingestion_jobs_payload_fingerprint_format"].sqltext
    )
    assert "hmac-sha256:v1:" in fingerprint_constraint
    assert "^sha256:" not in fingerprint_constraint


def test_average_cost_pool_state_declares_integrity_constraints_and_support_index() -> None:
    table = AverageCostPoolState.__table__
    constraint_names = {constraint.name for constraint in table.constraints}
    indexes = {index.name: index for index in table.indexes}

    assert set(table.primary_key.columns.keys()) == {"portfolio_id", "security_id"}
    assert {
        "ck_average_cost_pool_state_quantity_nonnegative",
        "ck_average_cost_pool_state_local_cost_nonnegative",
        "ck_average_cost_pool_state_base_cost_nonnegative",
        "ck_average_cost_pool_state_positive_source",
    } <= constraint_names
    assert [
        str(expression)
        for expression in indexes["ix_average_cost_pool_state_updated_key"].expressions
    ] == [
        "average_cost_pool_state.updated_at DESC",
        "average_cost_pool_state.portfolio_id",
        "average_cost_pool_state.security_id",
    ]


def test_lot_amortized_cost_records_declare_append_only_integrity_contract() -> None:
    portfolio_constraints = {constraint.name for constraint in Portfolio.__table__.constraints}
    lot_constraints = {constraint.name for constraint in PositionLotState.__table__.constraints}
    profile_table = LotAmortizedCostProfileRecord.__table__
    period_table = LotAmortizedCostPeriodRecord.__table__
    profile_constraints = {constraint.name for constraint in profile_table.constraints}
    period_constraints = {constraint.name for constraint in period_table.constraints}
    profile_indexes = {index.name: index for index in profile_table.indexes}
    period_indexes = {index.name: index for index in period_table.indexes}

    assert "uq_portfolios_book_scope_identity" in portfolio_constraints
    assert "uq_position_lot_scope_identity" in lot_constraints
    assert {
        "uq_lot_amort_profile_version",
        "fk_lot_amort_profile_book_scope",
        "fk_lot_amort_profile_lot_scope",
    } <= profile_constraints
    assert {
        "ck_lot_amort_profile_lifecycle_shape",
        "ck_lot_amort_profile_amounts_finite",
        "ck_lot_amort_profile_sources_array",
    } <= profile_constraints
    assert "uq_lot_amort_period_ordinal" in period_constraints
    assert {
        "ck_lot_amort_period_amounts_finite",
        "ck_lot_amort_period_amounts_governed",
        "fk_lot_amort_period_profile_version",
    } <= period_constraints
    assert "ix_lot_amort_profile_scope_version" in profile_indexes
    assert "ix_lot_amort_profile_parked_effective" in profile_indexes
    assert "ix_lot_amort_profile_id_effective_version" in profile_indexes
    assert "ix_lot_amort_period_profile_end" in period_indexes
    assert all(
        isinstance(profile_table.columns[column_name].type, ExactNumeric)
        for column_name in (
            "initial_amortized_cost_local",
            "redemption_value_local",
            "final_amortized_cost_local",
            "residual_local",
        )
    )
    assert period_table.columns.year_fraction.type.precision is None
    assert period_table.columns.year_fraction.type.scale is None
    assert period_table.columns.period_rate.type.precision is None
    assert period_table.columns.period_rate.type.scale is None


def test_lot_disposal_records_declare_versioned_immutable_integrity_contract() -> None:
    receipt_table = LotDisposalReceiptRecord.__table__
    allocation_table = LotDisposalAllocationRecord.__table__
    receipt_constraints = {constraint.name for constraint in receipt_table.constraints}
    allocation_constraints = {constraint.name for constraint in allocation_table.constraints}
    receipt_indexes = {index.name for index in receipt_table.indexes}
    allocation_indexes = {index.name for index in allocation_table.indexes}

    assert {
        "uq_lot_disposal_receipt_version",
        "uq_lot_disposal_receipt_scope_version",
        "uq_lot_disposal_transaction_version",
        "ck_lot_disposal_receipt_lifecycle",
        "ck_lot_disposal_receipt_chain",
        "ck_lot_disposal_receipt_hashes",
        "ck_lot_disposal_receipt_amounts_finite",
    } <= receipt_constraints
    assert {
        "fk_lot_disposal_allocation_receipt",
        "fk_lot_disposal_allocation_source_tx",
        "fk_lot_disposal_allocation_lot_scope",
        "uq_lot_disposal_allocation_ordinal",
        "uq_lot_disposal_allocation_source_lot",
        "ck_lot_disposal_allocation_amounts_finite",
    } <= allocation_constraints
    assert {
        "ix_lot_disposal_receipt_scope_time",
        "ix_lot_disposal_receipt_tx_version",
    } <= receipt_indexes
    assert "ix_lot_disposal_allocation_source" in allocation_indexes
    assert all(
        isinstance(receipt_table.columns[column_name].type, ExactNumeric)
        for column_name in (
            "consumed_quantity",
            "consumed_cost_local",
            "consumed_cost_base",
        )
    )
    assert all(
        isinstance(allocation_table.columns[column_name].type, ExactNumeric)
        for column_name in (
            "consumed_quantity",
            "consumed_cost_local",
            "consumed_cost_base",
        )
    )


def test_reprocessing_job_declares_pending_reset_watermarks_uniqueness_index():
    indexes = {index.name: index for index in ReprocessingJob.__table__.indexes}

    uniqueness_index = indexes["uq_reprocessing_jobs_pending_reset_watermarks_security"]
    security_support_index = indexes["ix_reproc_resetwm_sec_status_created_id"]
    correlation_support_index = indexes["ix_reproc_resetwm_corr_status_created_id"]

    assert uniqueness_index.unique is True
    assert str(next(iter(uniqueness_index.expressions))) == "(payload->>'security_id')"
    assert (
        str(uniqueness_index.dialect_options["postgresql"]["where"])
        == "job_type = 'RESET_WATERMARKS' AND status = 'PENDING'"
    )
    assert [str(expression) for expression in security_support_index.expressions] == [
        "trim(payload->>'security_id')",
        "reprocessing_jobs.status",
        "reprocessing_jobs.created_at",
        "reprocessing_jobs.id",
    ]
    assert (
        str(security_support_index.dialect_options["postgresql"]["where"])
        == "job_type = 'RESET_WATERMARKS'"
    )
    assert [column.name for column in correlation_support_index.columns] == [
        "correlation_id",
        "status",
        "created_at",
        "id",
    ]
    assert (
        str(correlation_support_index.dialect_options["postgresql"]["where"])
        == "job_type = 'RESET_WATERMARKS'"
    )


def test_analytics_export_job_declares_hot_path_indexes():
    indexes = {index.name: index for index in AnalyticsExportJob.__table__.indexes}

    portfolio_status_created = indexes["ix_analytics_export_jobs_portfolio_status_created_at"]
    status_updated = indexes["ix_analytics_export_jobs_status_updated_at"]
    dataset_fingerprint_id = indexes["ix_analytics_export_jobs_dataset_fingerprint_id"]

    assert [column.name for column in portfolio_status_created.columns] == [
        "portfolio_id",
        "status",
        "created_at",
    ]
    assert [column.name for column in status_updated.columns] == ["status", "updated_at"]
    assert [str(expression) for expression in dataset_fingerprint_id.expressions] == [
        "analytics_export_jobs.dataset_type",
        "analytics_export_jobs.request_fingerprint",
        "analytics_export_jobs.id DESC",
    ]


def test_portfolio_declares_portfolio_manager_book_index():
    indexes = {index.name: index for index in Portfolio.__table__.indexes}

    advisor_status_open_close = indexes["ix_portfolios_advisor_status_open_close_portfolio"]

    assert [column.name for column in advisor_status_open_close.columns] == [
        "advisor_id",
        "status",
        "open_date",
        "close_date",
        "portfolio_id",
    ]


def test_portfolio_declares_complete_valuation_book_scope_contract():
    table = Portfolio.__table__
    constraints = {
        constraint.name: constraint
        for constraint in table.constraints
        if constraint.name is not None
    }

    assert "ck_portfolios_valuation_book_scope_complete" in constraints
    scope_sql = str(constraints["ck_portfolios_valuation_book_scope_complete"].sqltext)
    assert "tenant_id = btrim(tenant_id)" in scope_sql
    assert "legal_book_id = btrim(legal_book_id)" in scope_sql
    assert "tenant_id <> ''" in scope_sql
    assert "legal_book_id <> ''" in scope_sql
    assert "ix_portfolios_valuation_book_scope" not in {index.name for index in table.indexes}


def test_portfolio_mandate_binding_declares_dpm_source_index():
    indexes = {index.name: index for index in PortfolioMandateBinding.__table__.indexes}

    dpm_source = indexes["ix_mandate_binding_dpm_model_book_eff"]

    assert [column.name for column in dpm_source.columns] == [
        "model_portfolio_id",
        "booking_center_code",
        "effective_from",
        "effective_to",
        "portfolio_id",
        "mandate_id",
    ]
    assert (
        str(dpm_source.dialect_options["postgresql"]["where"])
        == DPM_DISCRETIONARY_MANDATE_ACTIVE.sql
    )


def test_portfolio_party_role_assignment_enforces_identity_and_vocabulary() -> None:
    table = PortfolioPartyRoleAssignment.__table__
    constraint_names = {constraint.name for constraint in table.constraints}
    indexes = {index.name: index for index in table.indexes}

    assert {
        "uq_party_role_source_record_version",
        "ck_party_role_effective_window",
        "ck_party_role_assignment_version_positive",
        "ck_party_role_type_governed",
        "ck_party_role_scope_governed",
        "ck_party_role_quality_governed",
    } <= constraint_names
    assert [column.name for column in indexes["ix_party_role_portfolio_effective"].columns] == [
        "portfolio_id",
        "effective_from",
        "effective_to",
        "role_type",
    ]
    assert [column.name for column in indexes["ix_party_role_portfolio_history"].columns] == [
        "portfolio_id"
    ]
    assert [column.name for column in indexes["ix_party_role_party_effective"].columns] == [
        "party_id",
        "role_type",
        "role_scope",
        "effective_from",
        "effective_to",
        "portfolio_id",
    ]
    assert all(
        str(index.dialect_options["postgresql"]["where"]) == "quality_status = 'accepted'"
        for index_name, index in indexes.items()
        if index_name != "ix_party_role_portfolio_history"
    )


def test_instrument_valuation_policy_assignment_enforces_source_safe_history() -> None:
    table = InstrumentValuationPolicyAssignmentRecord.__table__
    constraint_names = {constraint.name for constraint in table.constraints}
    indexes = {index.name: index for index in table.indexes}

    assert {
        "uq_inst_val_policy_source_version",
        "ck_inst_val_policy_effective_window",
        "ck_inst_val_policy_version_positive",
        "ck_inst_val_assignment_version_positive",
        "ck_inst_val_assignment_status_governed",
    } <= constraint_names
    assert [column.name for column in indexes["ix_inst_val_policy_scope_effective"].columns] == [
        "tenant_id",
        "legal_book_id",
        "security_id",
        "valid_from",
        "valid_to",
    ]
    assert (
        str(indexes["ix_inst_val_policy_scope_effective"].dialect_options["postgresql"]["where"])
        == "assignment_status = 'ACTIVE'"
    )
    assert [
        str(expression) for expression in indexes["ix_inst_val_policy_source_history"].expressions
    ] == [
        "instrument_valuation_policy_assignments.tenant_id",
        "instrument_valuation_policy_assignments.legal_book_id",
        "instrument_valuation_policy_assignments.security_id",
        "instrument_valuation_policy_assignments.source_system",
        "instrument_valuation_policy_assignments.source_record_id",
        "instrument_valuation_policy_assignments.assignment_version DESC",
    ]


def test_market_price_source_fact_model_preserves_exact_append_history() -> None:
    table = MarketPriceSourceFactRecord.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert {
        "uq_market_price_source_fact_version",
        "ck_market_price_source_fact_scope_normalized",
        "ck_market_price_source_fact_price_positive",
        "ck_market_price_source_fact_price_finite",
        "ck_market_price_source_fact_currency_normalized",
        "ck_market_price_source_fact_quote_basis",
        "ck_market_price_source_fact_status",
        "ck_market_price_source_fact_version_positive",
        "ck_market_price_source_fact_source_normalized",
        "ck_market_price_source_fact_source_hash",
        "ck_market_price_source_fact_observed_at_finite",
    } <= constraints.keys()
    unique = constraints["uq_market_price_source_fact_version"]
    assert [column.name for column in unique.columns] == [
        "source_system",
        "source_record_id",
        "fact_version",
    ]
    assert (
        str(constraints["ck_market_price_source_fact_price_finite"].sqltext)
        == "price NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)"
    )
    assert (
        str(constraints["ck_market_price_source_fact_observed_at_finite"].sqltext)
        == "isfinite(observed_at)"
    )
    assert table.columns.price.type.precision is None
    assert table.columns.price.type.scale is None
    assert MarketPrice.__table__.columns.price.type.precision == 18
    assert MarketPrice.__table__.columns.price.type.scale == 10
    assert "updated_at" not in table.columns
    scope_history = {index.name: index for index in table.indexes}[
        "ix_market_price_fact_scope_history"
    ]
    assert [column.name for column in scope_history.columns] == [
        "tenant_id",
        "legal_book_id",
        "security_id",
        "price_date",
        "source_system",
        "source_record_id",
    ]


def test_daily_position_valuation_receipt_enforces_complete_one_to_one_evidence() -> None:
    table = DailyPositionValuationReceiptRecord.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert {
        "ck_daily_position_valuation_receipt_supportability",
        "ck_daily_position_valuation_receipt_reasons_nonempty",
        "ck_daily_position_valuation_receipt_evidence_complete",
        "ck_daily_position_valuation_receipt_assignment_hash",
        "ck_daily_position_valuation_receipt_price_hash",
        "ck_daily_position_valuation_receipt_hash",
    } <= constraints.keys()
    assert table.columns.snapshot_id.unique is True
    evidence_constraint = str(
        constraints["ck_daily_position_valuation_receipt_evidence_complete"].sqltext
    )
    assert "market_price_source IS NULL" in evidence_constraint
    assert "market_price_source IS NULL AND calculation_lineage IS NULL" not in evidence_constraint
    for field_name in (
        "policy_assignment_source",
        "market_price_source",
        "calculation_lineage",
    ):
        assert table.columns[field_name].type.none_as_null is True
    foreign_key = next(iter(table.columns.snapshot_id.foreign_keys))
    assert foreign_key.target_fullname == "daily_position_snapshots.id"
    assert foreign_key.ondelete == "CASCADE"
    supportability_index = {index.name: index for index in table.indexes}[
        "ix_daily_position_valuation_receipt_supportability_snapshot"
    ]
    assert [column.name for column in supportability_index.columns] == [
        "supportability",
        "snapshot_id",
    ]


@pytest.mark.parametrize(
    "column_name",
    ("request_payload", "failure_detail", "failure_headers"),
)
def test_ingestion_job_persists_absent_json_evidence_as_database_null(
    column_name: str,
) -> None:
    column = IngestionJob.__table__.columns[column_name]

    assert column.nullable is True
    assert column.type.none_as_null is True


@pytest.mark.parametrize(
    (
        "table_name",
        "finite_constraint_name",
        "finite_columns",
        "sign_constraint_name",
        "sign_terms",
    ),
    [
        (
            "fx_rates",
            "ck_fx_rates_rate_finite",
            ("rate",),
            "ck_fx_rates_rate_positive",
            ("rate > 0",),
        ),
        (
            "market_prices",
            "ck_market_prices_price_finite",
            ("price",),
            "ck_market_prices_price_positive",
            ("price > 0",),
        ),
        (
            "instruments",
            "ck_instruments_fx_terms_finite",
            ("buy_amount", "sell_amount", "contract_rate"),
            "ck_instruments_fx_terms_positive",
            ("buy_amount > 0", "sell_amount > 0", "contract_rate > 0"),
        ),
        (
            "benchmark_composition_series",
            "ck_benchmark_composition_weight_finite",
            ("composition_weight",),
            "ck_benchmark_composition_weight_nonnegative",
            ("composition_weight >= 0",),
        ),
        (
            "index_price_series",
            "ck_index_price_series_price_finite",
            ("index_price",),
            "ck_index_price_series_price_positive",
            ("index_price > 0",),
        ),
        (
            "index_return_series",
            "ck_index_return_series_return_finite",
            ("index_return",),
            None,
            (),
        ),
        (
            "benchmark_return_series",
            "ck_benchmark_return_series_return_finite",
            ("benchmark_return",),
            None,
            (),
        ),
        (
            "risk_free_series",
            "ck_risk_free_series_value_finite",
            ("value",),
            None,
            (),
        ),
        (
            "instrument_lookthrough_components",
            "ck_instrument_lookthrough_weight_finite",
            ("component_weight",),
            "ck_instrument_lookthrough_weight_nonnegative",
            ("component_weight >= 0",),
        ),
    ],
)
def test_reference_numeric_models_enforce_finite_domain_policy(
    table_name: str,
    finite_constraint_name: str,
    finite_columns: tuple[str, ...],
    sign_constraint_name: str | None,
    sign_terms: tuple[str, ...],
) -> None:
    table = Base.metadata.tables[table_name]
    constraints = {
        constraint.name: constraint
        for constraint in table.constraints
        if constraint.name is not None
    }

    finite_sql = str(constraints[finite_constraint_name].sqltext)
    for column_name in finite_columns:
        assert f"CAST({column_name} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')" in finite_sql
    if sign_constraint_name is not None:
        sign_sql = str(constraints[sign_constraint_name].sqltext)
        assert all(term in sign_sql for term in sign_terms)


@pytest.mark.parametrize(
    (
        "table_name",
        "finite_constraint_name",
        "finite_columns",
        "sign_constraint_name",
        "sign_terms",
    ),
    [
        (
            "sustainability_preference_profiles",
            "ck_sustainability_allocations_finite",
            ("minimum_allocation", "maximum_allocation"),
            "ck_sustainability_allocations_nonnegative",
            ("minimum_allocation >= 0", "maximum_allocation >= 0"),
        ),
        (
            "client_tax_profiles",
            "ck_client_tax_withholding_rate_finite",
            ("withholding_tax_rate",),
            "ck_client_tax_withholding_rate_nonnegative",
            ("withholding_tax_rate >= 0",),
        ),
        (
            "client_tax_rule_sets",
            "ck_client_tax_rule_values_finite",
            ("rate", "threshold_amount"),
            "ck_client_tax_rule_values_nonnegative",
            ("rate >= 0", "threshold_amount >= 0"),
        ),
        (
            "client_income_needs_schedules",
            "ck_client_income_need_amount_finite",
            ("amount",),
            "ck_client_income_need_amount_positive",
            ("amount > 0",),
        ),
        (
            "liquidity_reserve_requirements",
            "ck_liquidity_reserve_amount_finite",
            ("required_amount",),
            "ck_liquidity_reserve_amount_positive",
            ("required_amount > 0",),
        ),
        (
            "planned_withdrawal_schedules",
            "ck_planned_withdrawal_amount_finite",
            ("amount",),
            "ck_planned_withdrawal_amount_positive",
            ("amount > 0",),
        ),
        (
            "model_portfolio_targets",
            "ck_model_portfolio_weights_finite",
            ("target_weight", "min_weight", "max_weight"),
            "ck_model_portfolio_weights_nonnegative",
            ("target_weight >= 0", "min_weight >= 0", "max_weight >= 0"),
        ),
    ],
)
def test_client_policy_numeric_models_enforce_finite_domain_policy(
    table_name: str,
    finite_constraint_name: str,
    finite_columns: tuple[str, ...],
    sign_constraint_name: str,
    sign_terms: tuple[str, ...],
) -> None:
    table = Base.metadata.tables[table_name]
    constraints = {
        constraint.name: constraint
        for constraint in table.constraints
        if constraint.name is not None
    }

    finite_sql = str(constraints[finite_constraint_name].sqltext)
    for column_name in finite_columns:
        assert f"CAST({column_name} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')" in finite_sql
    sign_sql = str(constraints[sign_constraint_name].sqltext)
    assert all(term in sign_sql for term in sign_terms)


@pytest.mark.parametrize(
    (
        "table_name",
        "finite_constraint_name",
        "finite_columns",
        "sign_constraint_name",
        "sign_term",
    ),
    [
        (
            "simulation_changes",
            "ck_simulation_change_values_finite",
            ("quantity", "price", "amount"),
            "ck_simulation_change_price_positive",
            "price > 0",
        ),
        (
            "position_history",
            "ck_position_history_values_finite",
            ("quantity", "cost_basis", "cost_basis_local"),
            None,
            None,
        ),
        (
            "daily_position_snapshots",
            "ck_daily_position_snapshot_values_finite",
            (
                "quantity",
                "cost_basis",
                "cost_basis_local",
                "market_price",
                "market_value",
                "market_value_local",
                "unrealized_gain_loss",
                "unrealized_gain_loss_local",
                "unrealized_price_gain_loss",
                "unrealized_fx_gain_loss",
            ),
            "ck_daily_position_snapshot_price_positive",
            "market_price > 0",
        ),
    ],
)
def test_position_state_numeric_models_enforce_finite_domain_policy(
    table_name: str,
    finite_constraint_name: str,
    finite_columns: tuple[str, ...],
    sign_constraint_name: str | None,
    sign_term: str | None,
) -> None:
    table = Base.metadata.tables[table_name]
    constraints = {
        constraint.name: constraint
        for constraint in table.constraints
        if constraint.name is not None
    }

    finite_sql = str(constraints[finite_constraint_name].sqltext)
    for column_name in finite_columns:
        assert f"CAST({column_name} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')" in finite_sql
    if sign_constraint_name is not None and sign_term is not None:
        assert sign_term in str(constraints[sign_constraint_name].sqltext)


def test_transaction_numeric_model_preserves_signed_economics_and_fences_special_values() -> None:
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in Transaction.__table__.constraints
        if constraint.name is not None and hasattr(constraint, "sqltext")
    }
    finite_families = {
        "ck_transactions_trade_values_finite": (
            "price",
            "gross_transaction_amount",
            "trade_fee",
            "gross_cost",
            "net_cost",
            "realized_gain_loss",
            "transaction_fx_rate",
            "net_cost_local",
            "realized_gain_loss_local",
        ),
        "ck_transactions_income_values_finite": (
            "withholding_tax_amount",
            "other_interest_deductions_amount",
            "net_interest_amount",
        ),
        "ck_transactions_fx_terms_finite": (
            "buy_amount",
            "sell_amount",
            "contract_rate",
        ),
        "ck_transactions_realized_values_finite": (
            "allocated_cost_basis_local",
            "allocated_cost_basis_base",
            "realized_capital_pnl_local",
            "realized_fx_pnl_local",
            "realized_total_pnl_local",
            "realized_capital_pnl_base",
            "realized_fx_pnl_base",
            "realized_total_pnl_base",
        ),
        "ck_transactions_synthetic_flow_values_finite": (
            "synthetic_flow_amount_local",
            "synthetic_flow_amount_base",
            "synthetic_flow_fx_rate_to_base",
            "synthetic_flow_price_used",
            "synthetic_flow_quantity_used",
        ),
    }

    for constraint_name, column_names in finite_families.items():
        for column_name in column_names:
            assert (
                f"CAST({column_name} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')"
                in constraints[constraint_name]
            )

    assert constraints["ck_transactions_trade_values_sign"] == (
        "price >= 0 AND gross_transaction_amount >= 0 AND trade_fee >= 0 "
        "AND transaction_fx_rate > 0"
    )
    assert constraints["ck_transactions_income_values_nonnegative"] == (
        "withholding_tax_amount >= 0 AND other_interest_deductions_amount >= 0 "
        "AND net_interest_amount >= 0"
    )
    assert constraints["ck_transactions_fx_terms_positive"] == (
        "buy_amount > 0 AND sell_amount > 0 AND contract_rate > 0"
    )
    assert constraints["ck_transactions_allocated_basis_nonnegative"] == (
        "allocated_cost_basis_local >= 0 AND allocated_cost_basis_base >= 0"
    )
    assert constraints["ck_transactions_synthetic_flow_values_sign"] == (
        "synthetic_flow_fx_rate_to_base > 0 AND synthetic_flow_price_used >= 0 "
        "AND synthetic_flow_quantity_used >= 0"
    )
    signed_columns = {
        "gross_cost",
        "net_cost",
        "realized_gain_loss",
        "net_cost_local",
        "realized_gain_loss_local",
        "realized_capital_pnl_local",
        "realized_fx_pnl_local",
        "realized_total_pnl_local",
        "realized_capital_pnl_base",
        "realized_fx_pnl_base",
        "realized_total_pnl_base",
        "synthetic_flow_amount_local",
        "synthetic_flow_amount_base",
    }
    sign_sql = " ".join(
        sql
        for name, sql in constraints.items()
        if name.endswith(("_sign", "_positive", "_nonnegative"))
    )
    assert all(f"{column_name} >=" not in sign_sql for column_name in signed_columns)
    assert all(f"{column_name} > " not in sign_sql for column_name in signed_columns)


def test_cashflow_numeric_model_preserves_signed_amount_and_fences_special_values() -> None:
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in Cashflow.__table__.constraints
        if constraint.name is not None and hasattr(constraint, "sqltext")
    }

    assert constraints["ck_cashflows_amount_finite"] == (
        "CAST(amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')"
    )
    assert all(
        "amount >" not in sql
        for name, sql in constraints.items()
        if name != "ck_cashflows_amount_finite"
    )


@pytest.mark.parametrize(
    ("table_name", "constraint_name", "column_names"),
    [
        (
            "position_timeseries",
            "ck_position_timeseries_values_finite",
            (
                "bod_market_value",
                "bod_cashflow_position",
                "eod_cashflow_position",
                "bod_cashflow_portfolio",
                "eod_cashflow_portfolio",
                "eod_market_value",
                "fees",
                "quantity",
                "cost",
            ),
        ),
        (
            "portfolio_timeseries",
            "ck_portfolio_timeseries_values_finite",
            (
                "bod_market_value",
                "bod_cashflow",
                "eod_cashflow",
                "eod_market_value",
                "fees",
            ),
        ),
    ],
)
def test_timeseries_numeric_models_fence_special_values_without_sign_narrowing(
    table_name: str,
    constraint_name: str,
    column_names: tuple[str, ...],
) -> None:
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in Base.metadata.tables[table_name].constraints
        if constraint.name is not None and hasattr(constraint, "sqltext")
    }

    for column_name in column_names:
        assert (
            f"CAST({column_name} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')"
            in constraints[constraint_name]
        )
    assert all(
        "> 0" not in sql and ">= 0" not in sql
        for name, sql in constraints.items()
        if name == constraint_name
    )


def test_reconciliation_tolerance_is_finite_and_nonnegative() -> None:
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in FinancialReconciliationRun.__table__.constraints
        if constraint.name is not None and hasattr(constraint, "sqltext")
    }

    assert constraints["ck_fin_recon_tolerance_finite"] == (
        "CAST(tolerance AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')"
    )
    assert constraints["ck_fin_recon_tolerance_nonnegative"] == "tolerance >= 0"


def test_model_portfolio_tables_declare_dpm_source_indexes():
    definition_indexes = {index.name: index for index in ModelPortfolioDefinition.__table__.indexes}
    target_indexes = {index.name: index for index in ModelPortfolioTarget.__table__.indexes}

    approved_definition = definition_indexes["ix_model_port_def_approved_eff_order"]
    active_target = target_indexes["ix_model_port_tgt_active_eff_order"]

    assert [str(expression) for expression in approved_definition.expressions] == [
        "model_portfolio_definitions.model_portfolio_id",
        "model_portfolio_definitions.effective_from DESC",
        "model_portfolio_definitions.effective_to",
        "model_portfolio_definitions.approved_at DESC",
        "model_portfolio_definitions.updated_at DESC",
    ]
    assert (
        str(approved_definition.dialect_options["postgresql"]["where"])
        == "approval_status = 'approved'"
    )
    assert [str(expression) for expression in active_target.expressions] == [
        "model_portfolio_targets.model_portfolio_id",
        "model_portfolio_targets.model_portfolio_version",
        "model_portfolio_targets.instrument_id",
        "model_portfolio_targets.effective_from DESC",
        "model_portfolio_targets.effective_to",
    ]
    assert (
        str(active_target.dialect_options["postgresql"]["where"])
        == MODEL_PORTFOLIO_TARGET_ACTIVE.sql
    )


def test_instrument_eligibility_declares_normalized_effective_index():
    indexes = {index.name: index for index in InstrumentEligibilityProfile.__table__.indexes}

    normalized_effective = indexes["ix_instr_elig_norm_sec_eff"]

    assert [str(expression) for expression in normalized_effective.expressions] == [
        "trim(instrument_eligibility_profiles.security_id)",
        "instrument_eligibility_profiles.effective_from DESC",
        "instrument_eligibility_profiles.effective_to",
        "instrument_eligibility_profiles.observed_at DESC NULLS LAST",
        "instrument_eligibility_profiles.eligibility_version DESC",
        "instrument_eligibility_profiles.updated_at DESC",
    ]


def test_client_source_data_tables_declare_active_source_indexes():
    expected_indexes = [
        (
            ClientRestrictionProfile,
            "ix_client_restr_active_port_client_eff",
            [
                "client_restriction_profiles.portfolio_id",
                "client_restriction_profiles.client_id",
                "client_restriction_profiles.restriction_scope",
                "client_restriction_profiles.restriction_code",
                "client_restriction_profiles.effective_from DESC",
                "client_restriction_profiles.effective_to",
                "client_restriction_profiles.observed_at DESC NULLS LAST",
                "client_restriction_profiles.restriction_version DESC",
                "client_restriction_profiles.updated_at DESC",
            ],
            CLIENT_RESTRICTION_ACTIVE.sql,
        ),
        (
            SustainabilityPreferenceProfile,
            "ix_sust_pref_active_port_client_eff",
            [
                "sustainability_preference_profiles.portfolio_id",
                "sustainability_preference_profiles.client_id",
                "sustainability_preference_profiles.preference_framework",
                "sustainability_preference_profiles.preference_code",
                "sustainability_preference_profiles.effective_from DESC",
                "sustainability_preference_profiles.effective_to",
                "sustainability_preference_profiles.observed_at DESC NULLS LAST",
                "sustainability_preference_profiles.preference_version DESC",
                "sustainability_preference_profiles.updated_at DESC",
            ],
            SUSTAINABILITY_PREFERENCE_ACTIVE.sql,
        ),
        (
            ClientTaxProfile,
            "ix_client_tax_profile_active_eff",
            [
                "client_tax_profiles.portfolio_id",
                "client_tax_profiles.client_id",
                "client_tax_profiles.tax_profile_id",
                "client_tax_profiles.effective_from DESC",
                "client_tax_profiles.effective_to",
                "client_tax_profiles.observed_at DESC NULLS LAST",
                "client_tax_profiles.profile_version DESC",
                "client_tax_profiles.updated_at DESC",
            ],
            CLIENT_TAX_PROFILE_ACTIVE.sql,
        ),
        (
            ClientTaxRuleSet,
            "ix_client_tax_rule_active_eff",
            [
                "client_tax_rule_sets.portfolio_id",
                "client_tax_rule_sets.client_id",
                "client_tax_rule_sets.rule_set_id",
                "client_tax_rule_sets.jurisdiction_code",
                "client_tax_rule_sets.rule_code",
                "client_tax_rule_sets.effective_from DESC",
                "client_tax_rule_sets.effective_to",
                "client_tax_rule_sets.observed_at DESC NULLS LAST",
                "client_tax_rule_sets.rule_version DESC",
                "client_tax_rule_sets.updated_at DESC",
            ],
            CLIENT_TAX_RULE_SET_ACTIVE.sql,
        ),
        (
            ClientIncomeNeedsSchedule,
            "ix_client_income_needs_active_eff",
            [
                "client_income_needs_schedules.portfolio_id",
                "client_income_needs_schedules.client_id",
                "client_income_needs_schedules.schedule_id",
                "client_income_needs_schedules.start_date DESC",
                "client_income_needs_schedules.end_date",
                "client_income_needs_schedules.observed_at DESC NULLS LAST",
                "client_income_needs_schedules.updated_at DESC",
            ],
            CLIENT_INCOME_NEEDS_ACTIVE.sql,
        ),
        (
            LiquidityReserveRequirement,
            "ix_liquidity_reserve_active_eff",
            [
                "liquidity_reserve_requirements.portfolio_id",
                "liquidity_reserve_requirements.client_id",
                "liquidity_reserve_requirements.reserve_requirement_id",
                "liquidity_reserve_requirements.effective_from DESC",
                "liquidity_reserve_requirements.effective_to",
                "liquidity_reserve_requirements.observed_at DESC NULLS LAST",
                "liquidity_reserve_requirements.requirement_version DESC",
                "liquidity_reserve_requirements.updated_at DESC",
            ],
            LIQUIDITY_RESERVE_ACTIVE.sql,
        ),
        (
            PlannedWithdrawalSchedule,
            "ix_planned_withdrawal_active_window",
            [
                "planned_withdrawal_schedules.portfolio_id",
                "planned_withdrawal_schedules.client_id",
                "planned_withdrawal_schedules.scheduled_date",
                "planned_withdrawal_schedules.withdrawal_schedule_id",
                "planned_withdrawal_schedules.observed_at DESC NULLS LAST",
                "planned_withdrawal_schedules.updated_at DESC",
            ],
            PLANNED_WITHDRAWAL_ACTIVE.sql,
        ),
    ]

    for model, index_name, expressions, where_clause in expected_indexes:
        indexes = {index.name: index for index in model.__table__.indexes}
        index = indexes[index_name]

        assert [str(expression) for expression in index.expressions] == expressions
        assert str(index.dialect_options["postgresql"]["where"]) == where_clause


def test_market_reference_definition_tables_declare_active_source_indexes():
    benchmark_indexes = {index.name: index for index in BenchmarkDefinition.__table__.indexes}
    index_indexes = {index.name: index for index in IndexDefinition.__table__.indexes}

    active_benchmark = benchmark_indexes["ix_benchmark_def_active_id_eff"]
    active_index = index_indexes["ix_index_def_active_id_eff"]

    assert [str(expression) for expression in active_benchmark.expressions] == [
        "benchmark_definitions.benchmark_id",
        "benchmark_definitions.effective_from DESC",
        "benchmark_definitions.effective_to",
    ]
    assert (
        str(active_benchmark.dialect_options["postgresql"]["where"])
        == BENCHMARK_DEFINITION_ACTIVE.sql
    )
    assert [str(expression) for expression in active_index.expressions] == [
        "index_definitions.index_id",
        "index_definitions.effective_from DESC",
        "index_definitions.effective_to",
    ]
    assert str(active_index.dialect_options["postgresql"]["where"]) == INDEX_DEFINITION_ACTIVE.sql


def test_benchmark_composition_declares_latest_effective_index():
    indexes = {index.name: index for index in BenchmarkCompositionSeries.__table__.indexes}

    latest_effective = indexes["ix_bench_comp_benchmark_index_eff"]

    assert [str(expression) for expression in latest_effective.expressions] == [
        "benchmark_composition_series.benchmark_id",
        "benchmark_composition_series.index_id",
        "benchmark_composition_series.composition_effective_from DESC",
        "benchmark_composition_series.composition_effective_to",
    ]


def test_transaction_declares_realized_tax_evidence_index():
    indexes = {index.name: index for index in Transaction.__table__.indexes}

    realized_tax_evidence = indexes["ix_txn_realized_tax_evidence_port_currency_date_txn"]

    assert [column.name for column in realized_tax_evidence.columns] == [
        "portfolio_id",
        "currency",
        "transaction_date",
        "transaction_id",
    ]
    assert (
        str(realized_tax_evidence.dialect_options["postgresql"]["where"])
        == "withholding_tax_amount IS NOT NULL OR other_interest_deductions_amount IS NOT NULL"
    )


def test_transaction_declares_projected_external_cash_index():
    indexes = {index.name: index for index in Transaction.__table__.indexes}

    projected_cash = indexes["ix_txn_projected_cash_external_port_settle_txn_date_id"]

    assert [column.name for column in projected_cash.columns] == [
        "portfolio_id",
        "settlement_date",
        "transaction_date",
        "id",
    ]
    assert (
        str(projected_cash.dialect_options["postgresql"]["where"])
        == "transaction_type IN ('DEPOSIT', 'WITHDRAWAL') AND settlement_date IS NOT NULL"
    )


def test_financial_reconciliation_finding_declares_control_query_indexes():
    indexes = {index.name: index for index in FinancialReconciliationFinding.__table__.indexes}

    run_severity_type_id = indexes["ix_financial_reconciliation_findings_run_severity_type_id"]
    run_severity_created = indexes["ix_financial_reconciliation_findings_run_severity_created_id"]

    assert [str(expression) for expression in run_severity_type_id.expressions] == [
        "financial_reconciliation_findings.run_id",
        "financial_reconciliation_findings.severity",
        "financial_reconciliation_findings.finding_type",
        "financial_reconciliation_findings.id ASC",
    ]
    assert [str(expression) for expression in run_severity_created.expressions] == [
        "financial_reconciliation_findings.run_id",
        "financial_reconciliation_findings.severity",
        "financial_reconciliation_findings.created_at DESC",
        "financial_reconciliation_findings.id DESC",
    ]


def test_financial_reconciliation_run_declares_support_query_indexes():
    indexes = {index.name: index for index in FinancialReconciliationRun.__table__.indexes}

    portfolio_status_started = indexes["ix_financial_reconciliation_runs_port_status_started_id"]
    portfolio_type_started = indexes["ix_financial_reconciliation_runs_port_type_started_id"]
    portfolio_correlation_started = indexes["ix_fin_recon_runs_port_corr_started_id"]
    portfolio_requested_started = indexes["ix_fin_recon_runs_port_req_by_started_id"]
    portfolio_date_epoch_started = indexes["ix_fin_recon_runs_port_date_epoch_started_id"]

    assert [str(expression) for expression in portfolio_status_started.expressions] == [
        "financial_reconciliation_runs.portfolio_id",
        "financial_reconciliation_runs.status",
        "financial_reconciliation_runs.started_at DESC",
        "financial_reconciliation_runs.id ASC",
    ]
    assert [str(expression) for expression in portfolio_type_started.expressions] == [
        "financial_reconciliation_runs.portfolio_id",
        "financial_reconciliation_runs.reconciliation_type",
        "financial_reconciliation_runs.started_at DESC",
        "financial_reconciliation_runs.id DESC",
    ]
    assert [str(expression) for expression in portfolio_correlation_started.expressions] == [
        "financial_reconciliation_runs.portfolio_id",
        "financial_reconciliation_runs.correlation_id",
        "financial_reconciliation_runs.started_at DESC",
        "financial_reconciliation_runs.id ASC",
    ]
    assert [str(expression) for expression in portfolio_requested_started.expressions] == [
        "financial_reconciliation_runs.portfolio_id",
        "financial_reconciliation_runs.requested_by",
        "financial_reconciliation_runs.started_at DESC",
        "financial_reconciliation_runs.id ASC",
    ]
    assert [str(expression) for expression in portfolio_date_epoch_started.expressions] == [
        "financial_reconciliation_runs.portfolio_id",
        "financial_reconciliation_runs.business_date",
        "financial_reconciliation_runs.epoch",
        "financial_reconciliation_runs.started_at DESC",
        "financial_reconciliation_runs.id DESC",
    ]


def test_portfolio_valuation_job_declares_operations_hot_path_indexes():
    indexes = {index.name: index for index in PortfolioValuationJob.__table__.indexes}
    columns = PortfolioValuationJob.__table__.columns
    constraint_names = {
        constraint.name for constraint in PortfolioValuationJob.__table__.constraints
    }

    portfolio_status_updated = indexes["ix_portfolio_valuation_jobs_portfolio_status_updated"]
    portfolio_status_date_updated = indexes[
        "ix_portfolio_valuation_jobs_portfolio_status_date_updated_id"
    ]
    claim_order_epoch = indexes["ix_portfolio_valuation_jobs_claim_order_epoch"]
    lineage_latest = indexes["ix_val_jobs_lineage_latest"]
    correlation_support = indexes["ix_val_jobs_port_corr_date_updated_id"]
    lease_expiry = indexes["ix_portfolio_valuation_jobs_processing_lease_recovery"]

    assert columns["valuation_lease_owner"].type.length == 128
    assert columns["valuation_claim_token"].type.length == 32
    assert columns["valuation_lease_expires_at"].type.timezone is True
    assert "ck_portfolio_valuation_jobs_lease_all_or_none" in constraint_names
    assert "ck_portfolio_valuation_jobs_lease_owner_nonblank" in constraint_names
    assert "ck_portfolio_valuation_jobs_lease_expiry_finite" in constraint_names
    assert "ck_portfolio_valuation_jobs_processing_lease_state" in constraint_names
    assert [column.name for column in lease_expiry.columns] == [
        "valuation_lease_expires_at",
        "id",
    ]
    assert lease_expiry.dialect_options["postgresql"]["where"] is not None

    assert [column.name for column in portfolio_status_updated.columns] == [
        "portfolio_id",
        "status",
        "updated_at",
    ]
    assert [column.name for column in portfolio_status_date_updated.columns] == [
        "portfolio_id",
        "status",
        "valuation_date",
        "updated_at",
        "id",
    ]
    assert [str(expression) for expression in claim_order_epoch.expressions] == [
        "portfolio_valuation_jobs.status",
        "portfolio_valuation_jobs.portfolio_id",
        "portfolio_valuation_jobs.security_id",
        "portfolio_valuation_jobs.valuation_date",
        "portfolio_valuation_jobs.epoch DESC",
        "portfolio_valuation_jobs.id",
    ]
    assert [str(expression) for expression in lineage_latest.expressions] == [
        "portfolio_valuation_jobs.portfolio_id",
        "trim(portfolio_valuation_jobs.security_id)",
        "portfolio_valuation_jobs.epoch",
        "portfolio_valuation_jobs.valuation_date DESC",
        "portfolio_valuation_jobs.id DESC",
    ]
    assert [column.name for column in correlation_support.columns] == [
        "portfolio_id",
        "correlation_id",
        "valuation_date",
        "updated_at",
        "id",
    ]
    assert (
        str(correlation_support.dialect_options["postgresql"]["where"])
        == "portfolio_valuation_jobs.correlation_id IS NOT NULL"
    )


def test_normalized_calculation_lookup_indexes_are_declared():
    index_specs = {
        Portfolio: {
            "ix_portfolios_norm_portfolio_id": ["trim(portfolios.portfolio_id)"],
        },
        PositionHistory: {
            "ix_pos_hist_norm_port_sec_epoch_date": [
                "trim(position_history.portfolio_id)",
                "trim(position_history.security_id)",
                "position_history.epoch",
                "position_history.position_date DESC",
                "position_history.id DESC",
            ],
            "ix_pos_hist_norm_port_sec_epoch_txn": [
                "trim(position_history.portfolio_id)",
                "trim(position_history.security_id)",
                "position_history.epoch",
                "trim(position_history.transaction_id)",
            ],
        },
        DailyPositionSnapshot: {
            "ix_daily_snap_norm_port_sec_date_epoch": [
                "trim(daily_position_snapshots.portfolio_id)",
                "trim(daily_position_snapshots.security_id)",
                "daily_position_snapshots.date DESC",
                "daily_position_snapshots.epoch DESC",
            ],
        },
        MarketPrice: {
            "ix_market_prices_norm_sec_price_date": [
                "trim(market_prices.security_id)",
                "market_prices.price_date DESC",
            ],
        },
        Instrument: {
            "ix_instruments_norm_security_id": [
                "trim(instruments.security_id)",
            ],
            "ix_instruments_norm_asset_cls_sec": [
                "upper(trim(instruments.asset_class))",
                "trim(instruments.security_id)",
            ],
        },
        Transaction: {
            "ix_txn_norm_port_sec_date_id": [
                "trim(transactions.portfolio_id)",
                "trim(transactions.security_id)",
                "transactions.transaction_date",
                "transactions.transaction_id",
            ],
            "ix_txn_norm_port_sec_date_qty_id": [
                "trim(transactions.portfolio_id)",
                "trim(transactions.security_id)",
                "transactions.transaction_date",
                "transactions.quantity DESC",
                "transactions.transaction_id",
            ],
        },
        Cashflow: {
            "ix_cashflows_norm_port_sec_date_epoch": [
                "trim(cashflows.portfolio_id)",
                "trim(cashflows.security_id)",
                "cashflows.cashflow_date",
                "cashflows.epoch DESC",
            ],
            "ix_cashflows_port_norm_sec_date_epoch": [
                "cashflows.portfolio_id",
                "trim(cashflows.security_id)",
                "cashflows.cashflow_date",
                "cashflows.epoch DESC",
            ],
            "ix_cashflows_port_txn_epoch_id": [
                "cashflows.portfolio_id",
                "cashflows.transaction_id",
                "cashflows.epoch DESC",
                "cashflows.id DESC",
            ],
        },
        PositionLotState: {
            "ix_position_lot_norm_port_sec": [
                "trim(position_lot_state.portfolio_id)",
                "trim(position_lot_state.security_id)",
            ],
            "ix_position_lot_port_norm_sec_acq_id": [
                "position_lot_state.portfolio_id",
                "trim(position_lot_state.security_id)",
                "position_lot_state.acquisition_date",
                "position_lot_state.id",
            ],
            "ix_position_lot_port_acq_lot_id": [
                "position_lot_state.portfolio_id",
                "position_lot_state.acquisition_date",
                "position_lot_state.lot_id",
            ],
        },
        AccruedIncomeOffsetState: {
            "ix_accrued_offset_port_norm_sec_id": [
                "accrued_income_offset_state.portfolio_id",
                "trim(accrued_income_offset_state.security_id)",
                "accrued_income_offset_state.id",
            ],
        },
        TransactionCost: {
            "ix_transaction_costs_transaction_id": [
                "transaction_costs.transaction_id",
            ],
            "ix_txn_costs_positive_txn_id": [
                "transaction_costs.transaction_id",
            ],
            "uq_transaction_costs_component_identity": [
                "transaction_costs.transaction_id",
                "lower(trim(transaction_costs.fee_type))",
                "upper(trim(transaction_costs.currency))",
            ],
        },
        PositionTimeseries: {
            "ix_pos_ts_norm_port_sec_date_epoch": [
                "trim(position_timeseries.portfolio_id)",
                "trim(position_timeseries.security_id)",
                "position_timeseries.date DESC",
                "position_timeseries.epoch DESC",
            ],
            "ix_pos_ts_port_date_norm_sec_epoch": [
                "position_timeseries.portfolio_id",
                "position_timeseries.date",
                "trim(position_timeseries.security_id)",
                "position_timeseries.epoch DESC",
            ],
            "ix_pos_ts_port_norm_sec_date_epoch": [
                "position_timeseries.portfolio_id",
                "trim(position_timeseries.security_id)",
                "position_timeseries.date DESC",
                "position_timeseries.epoch DESC",
            ],
        },
        PortfolioTimeseries: {
            "ix_port_ts_norm_port_date_epoch": [
                "trim(portfolio_timeseries.portfolio_id)",
                "portfolio_timeseries.date DESC",
                "portfolio_timeseries.epoch DESC",
            ],
        },
        PortfolioValuationJob: {
            "ix_val_jobs_norm_port_sec_date_epoch_status": [
                "trim(portfolio_valuation_jobs.portfolio_id)",
                "trim(portfolio_valuation_jobs.security_id)",
                "portfolio_valuation_jobs.valuation_date",
                "portfolio_valuation_jobs.epoch",
                "portfolio_valuation_jobs.status",
            ],
        },
    }

    for model, indexes in index_specs.items():
        declared_indexes = {index.name: index for index in model.__table__.indexes}
        for index_name, expected_expressions in indexes.items():
            assert index_name in declared_indexes
            actual_expressions = [
                str(expression) for expression in declared_indexes[index_name].expressions
            ]
            assert actual_expressions == expected_expressions

    transaction_cost_indexes = {index.name: index for index in TransactionCost.__table__.indexes}
    assert (
        str(
            transaction_cost_indexes["ix_txn_costs_positive_txn_id"].dialect_options["postgresql"][
                "where"
            ]
        )
        == "amount > 0"
    )
    assert transaction_cost_indexes["uq_transaction_costs_component_identity"].unique is True


def test_portfolio_aggregation_job_declares_operations_hot_path_indexes():
    indexes = {index.name: index for index in PortfolioAggregationJob.__table__.indexes}
    columns = PortfolioAggregationJob.__table__.columns
    constraint_names = {
        constraint.name for constraint in PortfolioAggregationJob.__table__.constraints
    }

    portfolio_status_updated = indexes["ix_portfolio_aggregation_jobs_portfolio_status_updated"]
    portfolio_status_date_updated = indexes[
        "ix_portfolio_aggregation_jobs_portfolio_status_date_updated_id"
    ]
    claim_order = indexes["ix_portfolio_aggregation_jobs_claim_order"]
    correlation_support = indexes["ix_agg_jobs_port_corr_date_updated_id"]
    lease_expiry = indexes["ix_portfolio_aggregation_jobs_status_lease_expiry"]

    assert columns["lease_owner"].type.length == 128
    assert columns["lease_token"].type.length == 64
    assert columns["lease_expires_at"].type.timezone is True
    assert columns["lease_owner"].nullable is True
    assert columns["lease_token"].nullable is True
    assert columns["lease_expires_at"].nullable is True
    assert "ck_portfolio_aggregation_jobs_lease_complete" in constraint_names
    assert columns["target_epoch"].nullable is False
    assert columns["source_revision"].nullable is False
    assert "ck_portfolio_aggregation_jobs_target_epoch_nonnegative" in constraint_names
    assert "ck_portfolio_aggregation_jobs_source_revision_positive" in constraint_names

    assert [column.name for column in portfolio_status_updated.columns] == [
        "portfolio_id",
        "status",
        "updated_at",
    ]
    assert [column.name for column in portfolio_status_date_updated.columns] == [
        "portfolio_id",
        "status",
        "aggregation_date",
        "updated_at",
        "id",
    ]
    assert [column.name for column in claim_order.columns] == [
        "status",
        "portfolio_id",
        "aggregation_date",
        "id",
    ]
    assert [column.name for column in correlation_support.columns] == [
        "portfolio_id",
        "correlation_id",
        "aggregation_date",
        "updated_at",
        "id",
    ]
    assert [column.name for column in lease_expiry.columns] == [
        "status",
        "lease_expires_at",
    ]
    assert (
        str(correlation_support.dialect_options["postgresql"]["where"])
        == "portfolio_aggregation_jobs.correlation_id IS NOT NULL"
    )


def test_api_query_hot_path_indexes_are_declared():
    index_specs = {
        PositionHistory: {
            "ix_pos_hist_port_norm_sec_date_id": [
                "position_history.portfolio_id",
                "trim(position_history.security_id)",
                "position_history.position_date DESC",
                "position_history.id DESC",
                "position_history.epoch",
            ],
            "ix_pos_hist_lineage_latest": [
                "position_history.portfolio_id",
                "trim(position_history.security_id)",
                "position_history.epoch",
                "position_history.position_date DESC",
            ],
        },
        DailyPositionSnapshot: {
            "ix_daily_snap_port_norm_sec_date_id": [
                "daily_position_snapshots.portfolio_id",
                "trim(daily_position_snapshots.security_id)",
                "daily_position_snapshots.date DESC",
                "daily_position_snapshots.id DESC",
                "daily_position_snapshots.epoch",
            ],
            "ix_daily_snap_port_date_status_norm_sec_epoch": [
                "daily_position_snapshots.portfolio_id",
                "daily_position_snapshots.date",
                "daily_position_snapshots.valuation_status",
                "trim(daily_position_snapshots.security_id)",
                "daily_position_snapshots.epoch",
            ],
            "ix_daily_snap_lineage_latest": [
                "daily_position_snapshots.portfolio_id",
                "trim(daily_position_snapshots.security_id)",
                "daily_position_snapshots.epoch",
                "daily_position_snapshots.date DESC",
            ],
        },
        Transaction: {
            "ix_txn_port_date_id": [
                "transactions.portfolio_id",
                "transactions.transaction_date DESC",
                "transactions.id DESC",
            ],
            "ix_txn_port_norm_sec_date_id": [
                "transactions.portfolio_id",
                "trim(transactions.security_id)",
                "transactions.transaction_date DESC",
                "transactions.id DESC",
            ],
            "ix_txn_port_norm_sec_type_date_id": [
                "transactions.portfolio_id",
                "trim(transactions.security_id)",
                "transactions.transaction_type",
                "transactions.transaction_date DESC",
                "transactions.id DESC",
            ],
            "ix_txn_port_norm_cash_instr_date_id": [
                "transactions.portfolio_id",
                "trim(transactions.settlement_cash_instrument_id)",
                "transactions.transaction_date DESC",
                "transactions.id DESC",
            ],
            "ix_txn_port_linked_group_date_id": [
                "transactions.portfolio_id",
                "transactions.linked_transaction_group_id",
                "transactions.transaction_date DESC",
                "transactions.id DESC",
            ],
            "ix_txn_port_settlement_date_id": [
                "transactions.portfolio_id",
                "transactions.settlement_date",
                "transactions.id",
            ],
        },
        CashAccountMaster: {
            "ix_cash_account_port_currency_id": [
                "cash_account_masters.portfolio_id",
                "cash_account_masters.account_currency",
                "cash_account_masters.cash_account_id",
            ],
        },
        InstrumentLookthroughComponent: {
            "ix_lookthrough_norm_parent_eff_comp": [
                "trim(instrument_lookthrough_components.parent_security_id)",
                "instrument_lookthrough_components.effective_from DESC",
                "instrument_lookthrough_components.effective_to",
                "trim(instrument_lookthrough_components.component_security_id)",
            ],
        },
        PositionState: {
            "ix_position_state_port_norm_sec_epoch": [
                "position_state.portfolio_id",
                "trim(position_state.security_id)",
                "position_state.epoch",
            ],
            "ix_position_state_updated_watermark_key": [
                "position_state.updated_at",
                "position_state.watermark_date",
                "position_state.portfolio_id",
                "position_state.security_id",
            ],
            "ix_position_state_status_updated_watermark_key": [
                "position_state.status",
                "position_state.updated_at",
                "position_state.watermark_date",
                "position_state.portfolio_id",
                "position_state.security_id",
            ],
        },
        PipelineStageState: {
            "ix_pipeline_stage_state_port_status_date_stage_epoch_updated_id": [
                "pipeline_stage_state.portfolio_id",
                "pipeline_stage_state.status",
                "pipeline_stage_state.business_date DESC",
                "pipeline_stage_state.stage_name",
                "pipeline_stage_state.epoch DESC",
                "pipeline_stage_state.updated_at DESC",
                "pipeline_stage_state.id ASC",
            ],
            "ix_pipeline_stage_state_port_stage_date_epoch_id": [
                "pipeline_stage_state.portfolio_id",
                "pipeline_stage_state.stage_name",
                "pipeline_stage_state.business_date DESC",
                "pipeline_stage_state.epoch DESC",
                "pipeline_stage_state.id DESC",
            ],
        },
    }

    for model, indexes in index_specs.items():
        declared_indexes = {index.name: index for index in model.__table__.indexes}
        for index_name, expected_expressions in indexes.items():
            assert index_name in declared_indexes
            actual_expressions = [
                str(expression) for expression in declared_indexes[index_name].expressions
            ]
            assert actual_expressions == expected_expressions
