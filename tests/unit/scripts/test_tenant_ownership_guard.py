from pathlib import Path

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import registry

from scripts.quality.tenant_ownership_guard import (
    CRITICAL_TENANT_BOUNDARIES,
    TENANT_SCOPED_INGESTION_JOB_METHODS,
    _is_blocking,
    find_critical_tenant_boundary_findings,
    find_orm_tenant_findings,
    find_synthetic_default_findings,
)


def _write_idempotency_replay_reader(
    root: Path,
    *,
    tenant_parameter: str = "tenant_id",
) -> None:
    source = (
        root
        / "src"
        / "services"
        / "ingestion_service"
        / "app"
        / "infrastructure"
        / "ingestion_idempotency_replay_reader.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "class SqlAlchemyIngestionIdempotencyReplayReader:\n"
        f"    async def find_matching_job(self, *, {tenant_parameter}): ...\n",
        encoding="utf-8",
    )


def _write_portfolio_tenant_reader(
    root: Path,
    *,
    tenant_parameter: str = "tenant_id",
) -> None:
    source = (
        root
        / "src"
        / "services"
        / "ingestion_service"
        / "app"
        / "repositories"
        / "portfolio_tenant_repository.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "class SqlAlchemyPortfolioTenantReader:\n"
        f"    async def resolve_ownership(self, *, {tenant_parameter}): ...\n",
        encoding="utf-8",
    )


def _write_core_snapshot_reader(
    root: Path,
    *,
    tenant_parameter: str = "tenant_id",
) -> None:
    source = (
        root
        / "src"
        / "services"
        / "query_control_plane_service"
        / "app"
        / "infrastructure"
        / "core_snapshot_sources.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "class SqlAlchemyCoreSnapshotSourceReader:\n"
        f"    async def get_portfolio(self, *, {tenant_parameter}): ...\n",
        encoding="utf-8",
    )


def _write_position_repository(
    root: Path,
    *,
    tenant_parameter: str = "tenant_id",
) -> None:
    source = (
        root
        / "src"
        / "services"
        / "query_service"
        / "app"
        / "repositories"
        / "position_repository.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "class PositionRepository:\n"
        f"    async def portfolio_exists(self, *, {tenant_parameter}): ...\n",
        encoding="utf-8",
    )


def _write_position_service(
    root: Path,
    *,
    tenant_parameter: str = "tenant_context",
) -> None:
    source = (
        root / "src" / "services" / "query_service" / "app" / "services" / "position_service.py"
    )
    source.parent.mkdir(parents=True)
    methods = "\n".join(
        f"    async def {name}(self, *, {tenant_parameter}): ..."
        for name in (
            "get_position_history",
            "get_portfolio_positions",
            "get_portfolio_maturity_summary",
        )
    )
    source.write_text(f"class PositionService:\n{methods}\n", encoding="utf-8")


def _write_transaction_and_tax_lot_boundaries(root: Path) -> None:
    sources = {
        (
            "src/services/ingestion_service/app/infrastructure/"
            "transaction_reprocessing_target_reader.py",
            "SqlAlchemyTransactionReprocessingTargetReader",
            ("read_targets",),
            "tenant_id",
        ),
        (
            "src/services/ingestion_service/app/application/"
            "resolve_transaction_reprocessing_targets.py",
            "ResolveTransactionReprocessingTargets",
            ("execute",),
            "tenant_id",
        ),
        (
            "src/services/query_service/app/repositories/transaction_repository.py",
            "TransactionRepository",
            ("portfolio_exists",),
            "tenant_id",
        ),
        (
            "src/services/query_service/app/services/transaction_service.py",
            "TransactionService",
            ("get_transactions", "get_transaction_record", "get_realized_tax_summary"),
            "tenant_context",
        ),
        (
            "src/services/query_service/app/repositories/reporting_repository.py",
            "ReportingRepository",
            ("get_portfolio_by_id", "list_portfolios"),
            "tenant_id",
        ),
        (
            "src/services/query_service/app/services/cash_balance_service.py",
            "CashBalanceService",
            ("get_cash_balances",),
            "tenant_context",
        ),
        (
            "src/services/query_service/app/services/liquidity_ladder_service.py",
            "PortfolioLiquidityLadderService",
            ("get_liquidity_ladder",),
            "tenant_context",
        ),
        (
            "src/services/query_service/app/services/reporting_service.py",
            "ReportingService",
            (
                "get_assets_under_management",
                "get_asset_allocation",
                "get_portfolio_summary",
                "get_bulk_portfolio_summary",
            ),
            "tenant_context",
        ),
        (
            "src/services/query_service/app/repositories/buy_state_repository.py",
            "BuyStateRepository",
            ("portfolio_exists",),
            "tenant_id",
        ),
        (
            "src/services/query_service/app/services/buy_state_service.py",
            "BuyStateService",
            ("get_position_lots", "get_accrued_offsets", "get_buy_cash_linkage"),
            "tenant_context",
        ),
        (
            "src/services/query_service/app/repositories/sell_state_repository.py",
            "SellStateRepository",
            ("portfolio_exists",),
            "tenant_id",
        ),
        (
            "src/services/query_service/app/services/sell_state_service.py",
            "SellStateService",
            ("get_sell_disposals", "get_sell_cash_linkage"),
            "tenant_context",
        ),
        (
            "src/services/query_service/app/repositories/lot_disposal_repository.py",
            "LotDisposalRepository",
            ("portfolio_exists",),
            "tenant_id",
        ),
        (
            "src/services/query_service/app/services/lot_disposal_service.py",
            "LotDisposalService",
            ("get_latest_receipt",),
            "tenant_context",
        ),
        (
            "src/services/query_service/app/repositories/lot_basis_transfer_repository.py",
            "LotBasisTransferRepository",
            ("portfolio_exists",),
            "tenant_id",
        ),
        (
            "src/services/query_service/app/services/lot_basis_transfer_service.py",
            "LotBasisTransferService",
            ("get_latest_receipt",),
            "tenant_context",
        ),
        (
            "src/services/query_service/app/repositories/cash_account_repository.py",
            "CashAccountRepository",
            ("portfolio_exists",),
            "tenant_id",
        ),
        (
            "src/services/query_service/app/services/cash_account_service.py",
            "CashAccountService",
            ("get_cash_accounts",),
            "tenant_context",
        ),
        (
            "src/services/query_service/app/repositories/cashflow_repository.py",
            "CashflowRepository",
            ("get_portfolio_currency",),
            "tenant_id",
        ),
        (
            "src/services/query_service/app/services/cashflow_projection_service.py",
            "CashflowProjectionService",
            ("get_cashflow_projection",),
            "tenant_context",
        ),
        (
            "src/services/query_service/app/services/cash_movement_service.py",
            "CashMovementService",
            ("get_cash_movement_summary",),
            "tenant_context",
        ),
        (
            "src/services/query_control_plane_service/app/infrastructure/"
            "dpm_portfolio_state_sources.py",
            "SqlAlchemyDpmPortfolioStateReader",
            ("portfolio_exists",),
            "tenant_id",
        ),
        (
            "src/services/query_control_plane_service/app/application/"
            "dpm_source_readiness/portfolio_tax_lots.py",
            "PortfolioTaxLotService",
            ("resolve",),
            "tenant_context",
        ),
        (
            "src/services/query_control_plane_service/app/application/"
            "dpm_source_readiness/readiness.py",
            "DpmSourceReadinessService",
            ("get_portfolio_tax_lot_window", "get_source_readiness", "resolve"),
            "tenant_context",
        ),
        (
            "src/services/query_control_plane_service/app/infrastructure/"
            "portfolio_manager_book_sources.py",
            "SqlAlchemyPortfolioManagerBookReader",
            ("list_members",),
            "tenant_id",
        ),
        (
            "src/services/query_control_plane_service/app/application/portfolio_manager_book.py",
            "PortfolioManagerBookService",
            ("resolve_membership",),
            "tenant_context",
        ),
        (
            "src/services/query_control_plane_service/app/infrastructure/"
            "transaction_economics_sources.py",
            "SqlAlchemyTransactionEconomicsReader",
            ("portfolio_exists", "get_portfolio_base_currency"),
            "tenant_id",
        ),
        (
            "src/services/query_control_plane_service/app/application/"
            "transaction_economics/service.py",
            "TransactionEconomicsService",
            ("get_transaction_cost_curve", "get_performance_component_economics"),
            "tenant_context",
        ),
        (
            "src/services/query_control_plane_service/app/infrastructure/"
            "analytics_timeseries_repository.py",
            "AnalyticsTimeseriesRepository",
            ("get_portfolio",),
            "tenant_id",
        ),
        (
            "src/services/query_control_plane_service/app/application/analytics/"
            "analytics_timeseries_service.py",
            "AnalyticsTimeseriesService",
            ("__init__",),
            "tenant_context",
        ),
        (
            "src/services/query_control_plane_service/app/infrastructure/"
            "analytics_export_repository.py",
            "AnalyticsExportRepository",
            (
                "create_job",
                "get_job",
                "get_latest_by_fingerprint",
                "mark_running",
                "mark_completed",
                "mark_failed",
            ),
            "tenant_id",
        ),
        (
            "src/services/query_control_plane_service/app/infrastructure/operations/repository.py",
            "OperationsRepository",
            (
                "portfolio_exists_for_tenant",
                "get_analytics_export_jobs_count",
                "get_analytics_export_jobs",
            ),
            "tenant_id",
        ),
        (
            "src/services/query_control_plane_service/app/application/operations/service.py",
            "OperationsService",
            ("get_analytics_export_jobs",),
            "tenant_id",
        ),
        (
            "src/services/query_control_plane_service/app/infrastructure/simulation_store.py",
            "SqlAlchemySimulationStore",
            (
                "stage_session",
                "get_session",
                "stage_session_close",
                "stage_changes",
                "stage_change_delete",
                "get_changes",
            ),
            "tenant_id",
        ),
        (
            "src/services/query_control_plane_service/app/infrastructure/simulation_store.py",
            "SqlAlchemySimulationBaselineReader",
            ("portfolio_exists", "get_current_positions"),
            "tenant_id",
        ),
        (
            "src/services/query_control_plane_service/app/application/simulation.py",
            "SimulationService",
            (
                "create_session",
                "get_session",
                "close_session",
                "add_changes",
                "delete_change",
                "get_projected_positions",
                "get_projected_summary",
            ),
            "tenant_context",
        ),
    }
    for relative_path, class_name, method_names, tenant_parameter in sources:
        source = root / relative_path
        source.parent.mkdir(parents=True, exist_ok=True)
        methods = "\n".join(
            f"    async def {name}(self, *, {tenant_parameter}): ..." for name in method_names
        )
        source.write_text(f"class {class_name}:\n{methods}\n", encoding="utf-8")
    simulation_source = (
        root / "src/services/query_control_plane_service/app/infrastructure/simulation_store.py"
    )
    simulation_source.write_text(
        "class SqlAlchemySimulationStore:\n"
        + "\n".join(
            f"    async def {name}(self, *, tenant_id): ..."
            for name in (
                "stage_session",
                "get_session",
                "stage_session_close",
                "stage_changes",
                "stage_change_delete",
                "get_changes",
            )
        )
        + "\n\nclass SqlAlchemySimulationBaselineReader:\n"
        + "\n".join(
            f"    async def {name}(self, *, tenant_id): ..."
            for name in ("portfolio_exists", "get_current_positions")
        )
        + "\n",
        encoding="utf-8",
    )


def _write_valid_additional_boundaries(root: Path) -> None:
    _write_idempotency_replay_reader(root)
    _write_portfolio_tenant_reader(root)
    _write_core_snapshot_reader(root)
    _write_position_repository(root)
    _write_position_service(root)
    _write_transaction_and_tax_lot_boundaries(root)


def test_orm_report_lists_only_tables_without_tenant_ownership() -> None:
    mapper_registry = registry()
    base = mapper_registry.generate_base()

    class TenantOwned(base):
        __tablename__ = "tenant_owned"
        id = Column(Integer, primary_key=True)
        tenant_id = Column(String, nullable=False)

    class MissingTenant(base):
        __tablename__ = "missing_tenant"
        id = Column(Integer, primary_key=True)

    findings = find_orm_tenant_findings(base)

    assert [finding.detail for finding in findings] == ["missing_tenant (MissingTenant)"]


def test_synthetic_default_scan_covers_all_tenant_default_shapes(tmp_path: Path) -> None:
    source = tmp_path / "src" / "app" / "tenant_defaults.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "tenant_id: str = 'default'\n"
        "payload = {'tenant_id': 'default'}\n"
        "scope = build(tenant_id='default')\n"
        "header = headers.get('X-Tenant-Id', 'default')\n"
        "def positional(tenant_id='default'): ...\n"
        "def keyword_only(*, tenant_id='default'): ...\n"
        "def routed(tenant_id: str = Query('default')): ...\n"
        "tenant_id = Field(default='default')\n"
        "tenant_id = env.get('TENANT_ID', 'default')\n",
        encoding="utf-8",
    )

    findings = find_synthetic_default_findings(tmp_path)

    assert len(findings) == 9
    assert {finding.rule for finding in findings} == {"synthetic-default-tenant"}


def test_report_mode_banks_orm_debt_while_default_enforcement_blocks_new_fallbacks() -> None:
    mapper_registry = registry()
    base = mapper_registry.generate_base()

    class MissingTenant(base):
        __tablename__ = "missing_tenant"
        id = Column(Integer, primary_key=True)

    finding = find_orm_tenant_findings(base)[0]

    assert _is_blocking(finding, "report") is False
    assert _is_blocking(finding, "enforce-defaults") is False
    assert _is_blocking(finding, "enforce-critical") is False
    assert _is_blocking(finding, "enforce") is True


def test_critical_tenant_boundary_scan_requires_keyword_only_tenant_scope(
    tmp_path: Path,
) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "ingestion_service"
        / "app"
        / "services"
        / "ingestion_job_service.py"
    )
    source.parent.mkdir(parents=True)
    required_methods = "\n".join(
        f"    async def {name}(self, *, tenant_id): ..."
        for name in TENANT_SCOPED_INGESTION_JOB_METHODS - {"get_job"}
    )
    source.write_text(
        "class IngestionJobService:\n"
        "    async def get_job(self, job_id, *, tenant_id=None): ...\n"
        f"{required_methods}\n",
        encoding="utf-8",
    )
    _write_valid_additional_boundaries(tmp_path)

    findings = find_critical_tenant_boundary_findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule == "optional-critical-tenant-boundary"
    assert "get_job" in findings[0].detail
    assert _is_blocking(findings[0], "enforce-defaults") is False
    assert _is_blocking(findings[0], "enforce-critical") is True


def test_critical_tenant_boundary_scan_rejects_unscoped_idempotency_replay(
    tmp_path: Path,
) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "ingestion_service"
        / "app"
        / "services"
        / "ingestion_job_service.py"
    )
    source.parent.mkdir(parents=True)
    methods = "\n".join(
        f"    async def {name}(self, *, tenant_id): ..."
        for name in TENANT_SCOPED_INGESTION_JOB_METHODS
    )
    source.write_text(f"class IngestionJobService:\n{methods}\n", encoding="utf-8")
    _write_idempotency_replay_reader(tmp_path, tenant_parameter="tenant_id=None")
    _write_portfolio_tenant_reader(tmp_path)
    _write_core_snapshot_reader(tmp_path)
    _write_position_repository(tmp_path)
    _write_position_service(tmp_path)
    _write_transaction_and_tax_lot_boundaries(tmp_path)

    findings = find_critical_tenant_boundary_findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule == "optional-critical-tenant-boundary"
    assert "SqlAlchemyIngestionIdempotencyReplayReader.find_matching_job" in findings[0].detail
    assert _is_blocking(findings[0], "enforce-critical") is True


def test_critical_tenant_boundary_scan_rejects_unscoped_ownership_adapters(
    tmp_path: Path,
) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "ingestion_service"
        / "app"
        / "services"
        / "ingestion_job_service.py"
    )
    source.parent.mkdir(parents=True)
    methods = "\n".join(
        f"    async def {name}(self, *, tenant_id): ..."
        for name in TENANT_SCOPED_INGESTION_JOB_METHODS
    )
    source.write_text(f"class IngestionJobService:\n{methods}\n", encoding="utf-8")
    _write_idempotency_replay_reader(tmp_path)
    _write_portfolio_tenant_reader(tmp_path, tenant_parameter="tenant_id=None")
    _write_core_snapshot_reader(tmp_path, tenant_parameter="tenant_id=None")
    _write_position_repository(tmp_path)
    _write_position_service(tmp_path)
    _write_transaction_and_tax_lot_boundaries(tmp_path)

    findings = find_critical_tenant_boundary_findings(tmp_path)

    assert len(findings) == 2
    assert {finding.detail for finding in findings} == {
        "SqlAlchemyPortfolioTenantReader.resolve_ownership must require keyword-only tenant_id",
        "SqlAlchemyCoreSnapshotSourceReader.get_portfolio must require keyword-only tenant_id",
    }
    assert all(_is_blocking(finding, "enforce-critical") for finding in findings)


def test_critical_tenant_boundary_scan_rejects_unscoped_reprocessing_target_reader(
    tmp_path: Path,
) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "ingestion_service"
        / "app"
        / "infrastructure"
        / "transaction_reprocessing_target_reader.py"
    )
    _write_valid_additional_boundaries(tmp_path)
    source.write_text(
        "class SqlAlchemyTransactionReprocessingTargetReader:\n"
        "    async def read_targets(self, transaction_ids): ...\n",
        encoding="utf-8",
    )
    job_service = (
        tmp_path
        / "src"
        / "services"
        / "ingestion_service"
        / "app"
        / "services"
        / "ingestion_job_service.py"
    )
    job_service.parent.mkdir(parents=True)
    methods = "\n".join(
        f"    async def {name}(self, *, tenant_id): ..."
        for name in TENANT_SCOPED_INGESTION_JOB_METHODS
    )
    job_service.write_text(f"class IngestionJobService:\n{methods}\n", encoding="utf-8")

    findings = find_critical_tenant_boundary_findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule == "optional-critical-tenant-boundary"
    assert "SqlAlchemyTransactionReprocessingTargetReader.read_targets" in findings[0].detail
    assert _is_blocking(findings[0], "enforce-critical") is True


def test_critical_tenant_boundary_scan_accepts_required_scope(tmp_path: Path) -> None:
    source = (
        tmp_path
        / "src"
        / "services"
        / "ingestion_service"
        / "app"
        / "services"
        / "ingestion_job_service.py"
    )
    source.parent.mkdir(parents=True)
    methods = "\n".join(
        f"    async def {name}(self, *, tenant_id): ..."
        for name in TENANT_SCOPED_INGESTION_JOB_METHODS
    )
    source.write_text(f"class IngestionJobService:\n{methods}\n", encoding="utf-8")
    _write_valid_additional_boundaries(tmp_path)

    assert find_critical_tenant_boundary_findings(tmp_path) == []


def test_critical_tenant_boundaries_cover_portfolio_financial_reads() -> None:
    guarded_methods = {
        (class_name, method_name, tenant_parameter)
        for _, class_name, method_names, tenant_parameter in CRITICAL_TENANT_BOUNDARIES
        for method_name in method_names
    }

    assert {
        ("IngestionJobService", "get_consumer_dlq_event", "tenant_id"),
        (
            "IngestionJobService",
            "find_successful_replay_audit_by_fingerprint",
            "tenant_id",
        ),
        ("IngestionJobService", "get_replay_audit", "tenant_id"),
        ("IngestionJobService", "list_consumer_dlq_events", "tenant_id"),
        (
            "IngestionJobService",
            "list_consumer_dlq_events_by_event_ids",
            "tenant_id",
        ),
        (
            "IngestionJobService",
            "list_consumer_dlq_events_by_job_id",
            "tenant_id",
        ),
        ("IngestionJobService", "list_replay_audits", "tenant_id"),
        ("SqlAlchemyPortfolioManagerBookReader", "list_members", "tenant_id"),
        ("PortfolioManagerBookService", "resolve_membership", "tenant_context"),
        ("ReportingRepository", "get_portfolio_by_id", "tenant_id"),
        ("ReportingRepository", "list_portfolios", "tenant_id"),
        ("CashBalanceService", "get_cash_balances", "tenant_context"),
        (
            "PortfolioLiquidityLadderService",
            "get_liquidity_ladder",
            "tenant_context",
        ),
        ("ReportingService", "get_assets_under_management", "tenant_context"),
        ("ReportingService", "get_asset_allocation", "tenant_context"),
        ("ReportingService", "get_portfolio_summary", "tenant_context"),
        ("ReportingService", "get_bulk_portfolio_summary", "tenant_context"),
        ("BuyStateRepository", "portfolio_exists", "tenant_id"),
        ("BuyStateService", "get_position_lots", "tenant_context"),
        ("BuyStateService", "get_accrued_offsets", "tenant_context"),
        ("BuyStateService", "get_buy_cash_linkage", "tenant_context"),
        ("SellStateRepository", "portfolio_exists", "tenant_id"),
        ("SellStateService", "get_sell_disposals", "tenant_context"),
        ("SellStateService", "get_sell_cash_linkage", "tenant_context"),
        ("LotDisposalRepository", "portfolio_exists", "tenant_id"),
        ("LotDisposalService", "get_latest_receipt", "tenant_context"),
        ("LotBasisTransferRepository", "portfolio_exists", "tenant_id"),
        ("LotBasisTransferService", "get_latest_receipt", "tenant_context"),
        ("CashAccountRepository", "portfolio_exists", "tenant_id"),
        ("CashAccountService", "get_cash_accounts", "tenant_context"),
        ("CashflowRepository", "get_portfolio_currency", "tenant_id"),
        ("CashflowProjectionService", "get_cashflow_projection", "tenant_context"),
        ("CashMovementService", "get_cash_movement_summary", "tenant_context"),
        ("SqlAlchemyTransactionEconomicsReader", "portfolio_exists", "tenant_id"),
        (
            "SqlAlchemyTransactionEconomicsReader",
            "get_portfolio_base_currency",
            "tenant_id",
        ),
        (
            "TransactionEconomicsService",
            "get_transaction_cost_curve",
            "tenant_context",
        ),
        (
            "TransactionEconomicsService",
            "get_performance_component_economics",
            "tenant_context",
        ),
        ("SqlAlchemySimulationStore", "get_session", "tenant_id"),
        ("SqlAlchemySimulationStore", "stage_change_delete", "tenant_id"),
        ("SqlAlchemySimulationBaselineReader", "get_current_positions", "tenant_id"),
        ("SimulationService", "get_projected_positions", "tenant_context"),
    } <= guarded_methods
