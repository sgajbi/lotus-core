from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    AnalyticsExportJob,
    CashAccountMaster,
    Cashflow,
    DailyPositionSnapshot,
    FinancialReconciliationFinding,
    InstrumentLookthroughComponent,
    MarketPrice,
    Portfolio,
    PortfolioAggregationJob,
    PortfolioTimeseries,
    PortfolioValuationJob,
    PositionHistory,
    PositionLotState,
    PositionState,
    PositionTimeseries,
    ReprocessingJob,
    Transaction,
    TransactionCost,
)


def test_reprocessing_job_declares_pending_reset_watermarks_uniqueness_index():
    indexes = {index.name: index for index in ReprocessingJob.__table__.indexes}

    uniqueness_index = indexes["uq_reprocessing_jobs_pending_reset_watermarks_security"]

    assert uniqueness_index.unique is True
    assert str(next(iter(uniqueness_index.expressions))) == "(payload->>'security_id')"
    assert (
        str(uniqueness_index.dialect_options["postgresql"]["where"])
        == "job_type = 'RESET_WATERMARKS' AND status = 'PENDING'"
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


def test_financial_reconciliation_finding_declares_control_query_indexes():
    indexes = {index.name: index for index in FinancialReconciliationFinding.__table__.indexes}

    run_severity_created = indexes["ix_financial_reconciliation_findings_run_severity_created_id"]

    assert [str(expression) for expression in run_severity_created.expressions] == [
        "financial_reconciliation_findings.run_id",
        "financial_reconciliation_findings.severity",
        "financial_reconciliation_findings.created_at DESC",
        "financial_reconciliation_findings.id DESC",
    ]


def test_portfolio_valuation_job_declares_operations_hot_path_indexes():
    indexes = {index.name: index for index in PortfolioValuationJob.__table__.indexes}

    portfolio_status_updated = indexes["ix_portfolio_valuation_jobs_portfolio_status_updated"]
    portfolio_status_date_updated = indexes[
        "ix_portfolio_valuation_jobs_portfolio_status_date_updated_id"
    ]
    claim_order_epoch = indexes["ix_portfolio_valuation_jobs_claim_order_epoch"]

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
        },
        DailyPositionSnapshot: {
            "ix_daily_snap_port_norm_sec_date_id": [
                "daily_position_snapshots.portfolio_id",
                "trim(daily_position_snapshots.security_id)",
                "daily_position_snapshots.date DESC",
                "daily_position_snapshots.id DESC",
                "daily_position_snapshots.epoch",
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
    }

    for model, indexes in index_specs.items():
        declared_indexes = {index.name: index for index in model.__table__.indexes}
        for index_name, expected_expressions in indexes.items():
            assert index_name in declared_indexes
            actual_expressions = [
                str(expression) for expression in declared_indexes[index_name].expressions
            ]
            assert actual_expressions == expected_expressions
