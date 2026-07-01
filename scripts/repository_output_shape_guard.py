"""Guard repository methods from exposing unregistered ORM row contracts."""

# ruff: noqa: E501

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATABASE_MODELS_PATH = (
    REPO_ROOT / "src" / "libs" / "portfolio-common" / "portfolio_common" / "database_models.py"
)

# Transitional register for public repository methods that still expose SQLAlchemy ORM rows.
# New repository outputs should return explicit domain/read records instead of adding entries here.
TRANSITIONAL_ORM_RETURN_EXCEPTIONS: dict[str, tuple[str, ...]] = {
    "src/services/calculators/cashflow_calculator_service/app/repositories/cashflow_repository.py:create_cashflow": (
        "Cashflow",
    ),
    "src/services/calculators/cashflow_calculator_service/app/repositories/cashflow_rules_repository.py:get_all_rules": (
        "CashflowRule",
    ),
    "src/services/calculators/cost_calculator_service/app/repository.py:create_or_update_transaction_event": (
        "Transaction",
    ),
    "src/services/calculators/cost_calculator_service/app/repository.py:get_bundle_a_group_transactions": (
        "Transaction",
    ),
    "src/services/calculators/cost_calculator_service/app/repository.py:get_fx_rate": ("FxRate",),
    "src/services/calculators/cost_calculator_service/app/repository.py:get_instrument": (
        "Instrument",
    ),
    "src/services/calculators/cost_calculator_service/app/repository.py:get_portfolio": (
        "Portfolio",
    ),
    "src/services/calculators/cost_calculator_service/app/repository.py:get_transaction_by_id": (
        "Transaction",
    ),
    "src/services/calculators/cost_calculator_service/app/repository.py:get_transaction_history": (
        "Transaction",
    ),
    "src/services/calculators/cost_calculator_service/app/repository.py:update_transaction_costs": (
        "Transaction",
    ),
    "src/services/calculators/position_calculator/app/repositories/position_repository.py:get_all_transactions_for_security": (
        "Transaction",
    ),
    "src/services/calculators/position_calculator/app/repositories/position_repository.py:get_last_position_before": (
        "PositionHistory",
    ),
    "src/services/calculators/position_calculator/app/repositories/position_repository.py:get_transaction_by_id": (
        "Transaction",
    ),
    "src/services/calculators/position_calculator/app/repositories/position_repository.py:get_transactions_on_or_after": (
        "Transaction",
    ),
    "src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py:create_run": (
        "FinancialReconciliationRun",
    ),
    "src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py:fetch_latest_fx_rate": (
        "FxRate",
    ),
    "src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py:fetch_portfolio_timeseries_rows": (
        "PortfolioTimeseries",
    ),
    "src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py:get_run": (
        "FinancialReconciliationRun",
    ),
    "src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py:get_run_by_dedupe_key": (
        "FinancialReconciliationRun",
    ),
    "src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py:list_findings": (
        "FinancialReconciliationFinding",
    ),
    "src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py:list_runs": (
        "FinancialReconciliationRun",
    ),
    "src/services/persistence_service/app/repositories/fx_rate_repository.py:upsert_fx_rate": (
        "FxRate",
    ),
    "src/services/persistence_service/app/repositories/instrument_repository.py:create_or_update_instrument": (
        "Instrument",
    ),
    "src/services/persistence_service/app/repositories/market_price_repository.py:create_market_price": (
        "MarketPrice",
    ),
    "src/services/persistence_service/app/repositories/portfolio_repository.py:create_or_update_portfolio": (
        "Portfolio",
    ),
    "src/services/persistence_service/app/repositories/transaction_db_repo.py:create_or_update_transaction": (
        "Transaction",
    ),
    "src/services/pipeline_orchestrator_service/app/repositories/pipeline_stage_repository.py:upsert_portfolio_control_stage_status": (
        "PipelineStageState",
    ),
    "src/services/pipeline_orchestrator_service/app/repositories/pipeline_stage_repository.py:upsert_stage_flags": (
        "PipelineStageState",
    ),
    "src/services/query_service/app/repositories/analytics_export_repository.py:create_job": (
        "AnalyticsExportJob",
    ),
    "src/services/query_service/app/repositories/analytics_export_repository.py:get_job": (
        "AnalyticsExportJob",
    ),
    "src/services/query_service/app/repositories/analytics_export_repository.py:get_latest_by_fingerprint": (
        "AnalyticsExportJob",
    ),
    "src/services/query_service/app/repositories/analytics_timeseries_repository.py:get_portfolio": (
        "Portfolio",
    ),
    "src/services/query_service/app/repositories/buy_state_repository.py:get_accrued_offsets": (
        "AccruedIncomeOffsetState",
    ),
    "src/services/query_service/app/repositories/buy_state_repository.py:get_buy_cash_linkage": (
        "Cashflow",
        "Transaction",
    ),
    "src/services/query_service/app/repositories/buy_state_repository.py:get_position_lots": (
        "PositionLotState",
    ),
    "src/services/query_service/app/repositories/cash_account_repository.py:list_cash_accounts": (
        "CashAccountMaster",
    ),
    "src/services/query_service/app/repositories/cashflow_repository.py:get_income_cashflows_for_position": (
        "Cashflow",
    ),
    "src/services/query_service/app/repositories/fx_rate_repository.py:get_fx_rates": ("FxRate",),
    "src/services/query_service/app/repositories/instrument_repository.py:get_by_security_ids": (
        "Instrument",
    ),
    "src/services/query_service/app/repositories/instrument_repository.py:get_instruments": (
        "Instrument",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_aggregation_jobs": (
        "PortfolioAggregationJob",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_analytics_export_jobs": (
        "AnalyticsExportJob",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_failed_outbox_events": (
        "OutboxEvent",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_latest_financial_reconciliation_control_stage": (
        "PipelineStageState",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_latest_reconciliation_run_for_portfolio_day": (
        "FinancialReconciliationRun",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_latest_valuation_job": (
        "PortfolioValuationJob",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_outbox_recovery_audits": (
        "OutboxRecoveryAudit",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_portfolio_control_stages": (
        "PipelineStageState",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_position_state": (
        "PositionState",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_reconciliation_findings": (
        "FinancialReconciliationFinding",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_reconciliation_run": (
        "FinancialReconciliationRun",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_reconciliation_runs": (
        "FinancialReconciliationRun",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_reprocessing_keys": (
        "PositionState",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:get_valuation_jobs": (
        "PortfolioValuationJob",
    ),
    "src/services/query_service/app/repositories/operations_repository.py:requeue_failed_outbox_event": (
        "OutboxEvent",
        "OutboxRecoveryAudit",
    ),
    "src/services/query_service/app/repositories/portfolio_repository.py:get_by_id": ("Portfolio",),
    "src/services/query_service/app/repositories/portfolio_repository.py:get_portfolios": (
        "Portfolio",
    ),
    "src/services/query_service/app/repositories/portfolio_repository.py:list_portfolio_manager_book_members": (
        "Portfolio",
    ),
    "src/services/query_service/app/repositories/price_repository.py:get_prices": ("MarketPrice",),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_benchmark_components": (
        "BenchmarkCompositionSeries",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_benchmark_components_for_benchmarks": (
        "BenchmarkCompositionSeries",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_benchmark_components_overlapping_window": (
        "BenchmarkCompositionSeries",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_benchmark_definitions": (
        "BenchmarkDefinition",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_benchmark_definitions_overlapping_window": (
        "BenchmarkDefinition",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_benchmark_return_points": (
        "BenchmarkReturnSeries",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_client_income_needs_schedules": (
        "ClientIncomeNeedsSchedule",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_client_restriction_profiles": (
        "ClientRestrictionProfile",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_client_tax_profiles": (
        "ClientTaxProfile",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_client_tax_rule_sets": (
        "ClientTaxRuleSet",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_dpm_portfolio_universe_candidates": (
        "PortfolioMandateBinding",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_index_definitions": (
        "IndexDefinition",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_index_price_points": (
        "IndexPriceSeries",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_index_price_series": (
        "IndexPriceSeries",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_index_return_points": (
        "IndexReturnSeries",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_index_return_series": (
        "IndexReturnSeries",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_instrument_eligibility_profiles": (
        "InstrumentEligibilityProfile",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_latest_fx_rates": (
        "FxRate",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_latest_market_prices": (
        "MarketPrice",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_liquidity_reserve_requirements": (
        "LiquidityReserveRequirement",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_model_portfolio_affected_mandates": (
        "PortfolioMandateBinding",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_model_portfolio_targets": (
        "ModelPortfolioTarget",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_planned_withdrawal_schedules": (
        "PlannedWithdrawalSchedule",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_risk_free_series": (
        "RiskFreeSeries",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_sustainability_preference_profiles": (
        "SustainabilityPreferenceProfile",
    ),
    "src/services/query_service/app/repositories/reference_data_repository.py:list_taxonomy": (
        "ClassificationTaxonomy",
    ),
    "src/services/query_service/app/repositories/reporting_repository.py:get_portfolio_by_id": (
        "Portfolio",
    ),
    "src/services/query_service/app/repositories/reporting_repository.py:list_cash_account_masters": (
        "CashAccountMaster",
    ),
    "src/services/query_service/app/repositories/reporting_repository.py:list_portfolios": (
        "Portfolio",
    ),
    "src/services/query_service/app/repositories/sell_state_repository.py:get_sell_cash_linkage": (
        "Cashflow",
        "Transaction",
    ),
    "src/services/query_service/app/repositories/sell_state_repository.py:get_sell_disposals": (
        "Transaction",
    ),
    "src/services/query_service/app/repositories/simulation_repository.py:add_changes": (
        "SimulationChange",
        "SimulationSession",
    ),
    "src/services/query_service/app/repositories/simulation_repository.py:close_session": (
        "SimulationSession",
    ),
    "src/services/query_service/app/repositories/simulation_repository.py:create_session": (
        "SimulationSession",
    ),
    "src/services/query_service/app/repositories/simulation_repository.py:get_changes": (
        "SimulationChange",
    ),
    "src/services/query_service/app/repositories/simulation_repository.py:get_session": (
        "SimulationSession",
    ),
    "src/services/query_service/app/repositories/transaction_repository.py:get_transactions": (
        "Transaction",
    ),
    "src/services/query_service/app/repositories/transaction_repository.py:list_realized_tax_evidence_transactions": (
        "Transaction",
    ),
    "src/services/query_service/app/repositories/transaction_repository.py:list_transaction_cost_evidence": (
        "Transaction",
    ),
    "src/services/timeseries_generator_service/app/repositories/timeseries_repository.py:get_position_timeseries": (
        "PositionTimeseries",
    ),
    "src/services/timeseries_generator_service/app/repositories/timeseries_repository.py:get_position_timeseries_for_dates": (
        "PositionTimeseries",
    ),
    "src/services/valuation_orchestrator_service/app/repositories/valuation_repository.py:claim_instrument_reprocessing_triggers": (
        "InstrumentReprocessingState",
    ),
}


@dataclass(frozen=True)
class RepositoryOrmReturn:
    identifier: str
    path: str
    function_name: str
    line: int
    orm_models: tuple[str, ...]


def _repository_source_files(source_roots: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for source_root in source_roots:
        for path in sorted(source_root.rglob("*.py")):
            path_text = path.as_posix()
            if "/build/" in path_text or "__pycache__" in path.parts:
                continue
            if (
                "/repositories/" in path_text
                or path.name == "repository.py"
                or path.name.endswith("_repository.py")
            ):
                files.append(path)
    return files


def _load_orm_model_names(database_models_path: Path = DATABASE_MODELS_PATH) -> set[str]:
    tree = ast.parse(
        database_models_path.read_text(encoding="utf-8"), filename=str(database_models_path)
    )
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


def _imported_database_model_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "portfolio_common.database_models":
            continue
        for alias in node.names:
            aliases[alias.asname or alias.name] = alias.name
    return aliases


def _annotation_names(annotation: ast.AST | None) -> set[str]:
    if annotation is None:
        return set()
    names: set[str] = set()
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _discover_orm_returns(
    *,
    repo_root: Path,
    source_roots: tuple[Path, ...],
    orm_model_names: set[str],
) -> dict[str, RepositoryOrmReturn]:
    observations: dict[str, RepositoryOrmReturn] = {}
    for path in _repository_source_files(source_roots):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases = _imported_database_model_aliases(tree)
        if not aliases:
            continue
        relative_path = path.relative_to(repo_root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name.startswith("_"):
                continue
            annotation_names = _annotation_names(node.returns)
            exposed_models = sorted(
                {aliases[name] for name in annotation_names if name in aliases}
                | {name for name in annotation_names if name in orm_model_names}
            )
            if not exposed_models:
                continue
            identifier = f"{relative_path}:{node.name}"
            observations[identifier] = RepositoryOrmReturn(
                identifier=identifier,
                path=relative_path,
                function_name=node.name,
                line=node.lineno,
                orm_models=tuple(exposed_models),
            )
    return observations


def evaluate_repository_output_shapes(
    *,
    repo_root: Path = REPO_ROOT,
    source_roots: tuple[Path, ...] | None = None,
    orm_model_names: set[str] | None = None,
    transitional_exceptions: dict[str, tuple[str, ...]] = TRANSITIONAL_ORM_RETURN_EXCEPTIONS,
) -> list[dict[str, object]]:
    roots = source_roots or (repo_root / "src" / "services",)
    model_names = orm_model_names or _load_orm_model_names()
    observations = _discover_orm_returns(
        repo_root=repo_root,
        source_roots=roots,
        orm_model_names=model_names,
    )
    findings: list[dict[str, object]] = []

    for identifier, observation in sorted(observations.items()):
        expected_models = transitional_exceptions.get(identifier)
        if expected_models is None:
            findings.append(
                {
                    "id": identifier,
                    "file": observation.path,
                    "line": observation.line,
                    "function": observation.function_name,
                    "orm_models": list(observation.orm_models),
                    "violation": (
                        "repository method exposes ORM return annotation without a "
                        "transitional exception; map to an explicit read/domain record"
                    ),
                }
            )
            continue
        if tuple(expected_models) != observation.orm_models:
            findings.append(
                {
                    "id": identifier,
                    "file": observation.path,
                    "line": observation.line,
                    "function": observation.function_name,
                    "orm_models": list(observation.orm_models),
                    "registered_models": list(expected_models),
                    "violation": "transitional exception model list is stale",
                }
            )

    for identifier, expected_models in sorted(transitional_exceptions.items()):
        if identifier not in observations:
            findings.append(
                {
                    "id": identifier,
                    "registered_models": list(expected_models),
                    "violation": (
                        "stale transitional exception; remove it after the repository output "
                        "was mapped to an explicit record"
                    ),
                }
            )

    return findings


def main() -> int:
    findings = evaluate_repository_output_shapes()
    if findings:
        print("Repository output-shape guard failed:")
        print(json.dumps(findings, indent=2))
        return 1
    print("Repository output-shape guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
