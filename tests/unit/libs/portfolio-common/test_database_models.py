from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    AnalyticsExportJob,
    Base,
    BenchmarkCompositionSeries,
    BenchmarkDefinition,
    CashAccountMaster,
    Cashflow,
    ClientIncomeNeedsSchedule,
    ClientRestrictionProfile,
    ClientTaxProfile,
    ClientTaxRuleSet,
    DailyPositionSnapshot,
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    IndexDefinition,
    Instrument,
    InstrumentEligibilityProfile,
    InstrumentLookthroughComponent,
    LiquidityReserveRequirement,
    MarketPrice,
    ModelPortfolioDefinition,
    ModelPortfolioTarget,
    PipelineStageState,
    PlannedWithdrawalSchedule,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioMandateBinding,
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


def test_database_identifier_names_fit_postgresql_limit():
    names: list[str] = []
    for table in Base.metadata.tables.values():
        names.extend(index.name for index in table.indexes if index.name)
        names.extend(constraint.name for constraint in table.constraints if constraint.name)

    too_long = sorted(name for name in names if len(name) > 63)

    assert too_long == []


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
        str(dpm_source.dialect_options["postgresql"]["where"]) == "mandate_type = 'discretionary' "
        "AND discretionary_authority_status = 'active'"
    )


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
    assert str(active_target.dialect_options["postgresql"]["where"]) == "target_status = 'active'"


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
            "restriction_status = 'active'",
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
            "preference_status = 'active'",
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
            "profile_status = 'active'",
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
            "rule_status = 'active'",
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
            "need_status = 'active'",
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
            "reserve_status = 'active'",
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
            "withdrawal_status = 'active'",
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
        == "benchmark_status = 'active'"
    )
    assert [str(expression) for expression in active_index.expressions] == [
        "index_definitions.index_id",
        "index_definitions.effective_from DESC",
        "index_definitions.effective_to",
    ]
    assert str(active_index.dialect_options["postgresql"]["where"]) == "index_status = 'active'"


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


def test_portfolio_valuation_job_declares_operations_hot_path_indexes():
    indexes = {index.name: index for index in PortfolioValuationJob.__table__.indexes}

    portfolio_status_updated = indexes["ix_portfolio_valuation_jobs_portfolio_status_updated"]
    portfolio_status_date_updated = indexes[
        "ix_portfolio_valuation_jobs_portfolio_status_date_updated_id"
    ]
    claim_order_epoch = indexes["ix_portfolio_valuation_jobs_claim_order_epoch"]
    lineage_latest = indexes["ix_val_jobs_lineage_latest"]

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


def test_portfolio_aggregation_job_declares_operations_hot_path_indexes():
    indexes = {index.name: index for index in PortfolioAggregationJob.__table__.indexes}

    portfolio_status_updated = indexes["ix_portfolio_aggregation_jobs_portfolio_status_updated"]
    portfolio_status_date_updated = indexes[
        "ix_portfolio_aggregation_jobs_portfolio_status_date_updated_id"
    ]
    claim_order = indexes["ix_portfolio_aggregation_jobs_claim_order"]

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
