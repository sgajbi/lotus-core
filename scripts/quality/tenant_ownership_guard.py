"""Measure tenant ownership coverage and prohibit synthetic production tenants."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
GuardMode = Literal["report", "enforce-defaults", "enforce-critical", "enforce"]

INGESTION_JOB_SERVICE_PATH = Path(
    "src/services/ingestion_service/app/services/ingestion_job_service.py"
)
TENANT_SCOPED_INGESTION_JOB_METHODS = frozenset(
    {
        "get_job",
        "get_job_record_status",
        "get_job_replay_context",
        "get_unique_replayable_job_by_correlation_id",
        "list_jobs",
        "mark_failed",
        "mark_queued",
        "mark_retried_and_queued",
    }
)
CRITICAL_TENANT_BOUNDARIES = (
    (
        INGESTION_JOB_SERVICE_PATH,
        "IngestionJobService",
        TENANT_SCOPED_INGESTION_JOB_METHODS,
        "tenant_id",
    ),
    (
        Path(
            "src/services/ingestion_service/app/infrastructure/"
            "ingestion_idempotency_replay_reader.py"
        ),
        "SqlAlchemyIngestionIdempotencyReplayReader",
        frozenset({"find_matching_job"}),
        "tenant_id",
    ),
    (
        Path("src/services/ingestion_service/app/repositories/portfolio_tenant_repository.py"),
        "SqlAlchemyPortfolioTenantReader",
        frozenset({"resolve_ownership"}),
        "tenant_id",
    ),
    (
        Path(
            "src/services/ingestion_service/app/infrastructure/"
            "transaction_reprocessing_target_reader.py"
        ),
        "SqlAlchemyTransactionReprocessingTargetReader",
        frozenset({"read_targets"}),
        "tenant_id",
    ),
    (
        Path(
            "src/services/ingestion_service/app/application/"
            "resolve_transaction_reprocessing_targets.py"
        ),
        "ResolveTransactionReprocessingTargets",
        frozenset({"execute"}),
        "tenant_id",
    ),
    (
        Path(
            "src/services/query_control_plane_service/app/infrastructure/core_snapshot_sources.py"
        ),
        "SqlAlchemyCoreSnapshotSourceReader",
        frozenset({"get_portfolio"}),
        "tenant_id",
    ),
    (
        Path("src/services/query_service/app/repositories/position_repository.py"),
        "PositionRepository",
        frozenset({"portfolio_exists"}),
        "tenant_id",
    ),
    (
        Path("src/services/query_service/app/services/position_service.py"),
        "PositionService",
        frozenset(
            {
                "get_position_history",
                "get_portfolio_positions",
                "get_portfolio_maturity_summary",
            }
        ),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/repositories/transaction_repository.py"),
        "TransactionRepository",
        frozenset({"portfolio_exists"}),
        "tenant_id",
    ),
    (
        Path("src/services/query_service/app/services/transaction_service.py"),
        "TransactionService",
        frozenset(
            {
                "get_transactions",
                "get_transaction_record",
                "get_realized_tax_summary",
            }
        ),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/repositories/reporting_repository.py"),
        "ReportingRepository",
        frozenset({"get_portfolio_by_id", "list_portfolios"}),
        "tenant_id",
    ),
    (
        Path("src/services/query_service/app/services/cash_balance_service.py"),
        "CashBalanceService",
        frozenset({"get_cash_balances"}),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/services/liquidity_ladder_service.py"),
        "PortfolioLiquidityLadderService",
        frozenset({"get_liquidity_ladder"}),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/services/reporting_service.py"),
        "ReportingService",
        frozenset(
            {
                "get_assets_under_management",
                "get_asset_allocation",
                "get_portfolio_summary",
                "get_bulk_portfolio_summary",
            }
        ),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/repositories/buy_state_repository.py"),
        "BuyStateRepository",
        frozenset({"portfolio_exists"}),
        "tenant_id",
    ),
    (
        Path("src/services/query_service/app/services/buy_state_service.py"),
        "BuyStateService",
        frozenset({"get_position_lots", "get_accrued_offsets", "get_buy_cash_linkage"}),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/repositories/sell_state_repository.py"),
        "SellStateRepository",
        frozenset({"portfolio_exists"}),
        "tenant_id",
    ),
    (
        Path("src/services/query_service/app/services/sell_state_service.py"),
        "SellStateService",
        frozenset({"get_sell_disposals", "get_sell_cash_linkage"}),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/repositories/lot_disposal_repository.py"),
        "LotDisposalRepository",
        frozenset({"portfolio_exists"}),
        "tenant_id",
    ),
    (
        Path("src/services/query_service/app/services/lot_disposal_service.py"),
        "LotDisposalService",
        frozenset({"get_latest_receipt"}),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/repositories/lot_basis_transfer_repository.py"),
        "LotBasisTransferRepository",
        frozenset({"portfolio_exists"}),
        "tenant_id",
    ),
    (
        Path("src/services/query_service/app/services/lot_basis_transfer_service.py"),
        "LotBasisTransferService",
        frozenset({"get_latest_receipt"}),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/repositories/cash_account_repository.py"),
        "CashAccountRepository",
        frozenset({"portfolio_exists"}),
        "tenant_id",
    ),
    (
        Path("src/services/query_service/app/services/cash_account_service.py"),
        "CashAccountService",
        frozenset({"get_cash_accounts"}),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/repositories/cashflow_repository.py"),
        "CashflowRepository",
        frozenset({"get_portfolio_currency"}),
        "tenant_id",
    ),
    (
        Path("src/services/query_service/app/services/cashflow_projection_service.py"),
        "CashflowProjectionService",
        frozenset({"get_cashflow_projection"}),
        "tenant_context",
    ),
    (
        Path("src/services/query_service/app/services/cash_movement_service.py"),
        "CashMovementService",
        frozenset({"get_cash_movement_summary"}),
        "tenant_context",
    ),
    (
        Path(
            "src/services/query_control_plane_service/app/infrastructure/"
            "dpm_portfolio_state_sources.py"
        ),
        "SqlAlchemyDpmPortfolioStateReader",
        frozenset({"portfolio_exists"}),
        "tenant_id",
    ),
    (
        Path(
            "src/services/query_control_plane_service/app/application/"
            "dpm_source_readiness/portfolio_tax_lots.py"
        ),
        "PortfolioTaxLotService",
        frozenset({"resolve"}),
        "tenant_context",
    ),
    (
        Path(
            "src/services/query_control_plane_service/app/application/"
            "dpm_source_readiness/readiness.py"
        ),
        "DpmSourceReadinessService",
        frozenset({"get_portfolio_tax_lot_window", "get_source_readiness", "resolve"}),
        "tenant_context",
    ),
)


@dataclass(frozen=True, slots=True)
class TenantOwnershipFinding:
    path: str
    line: int | None
    rule: str
    detail: str

    def as_text(self) -> str:
        location = f"{self.path}:{self.line}" if self.line is not None else self.path
        return f"{location}: {self.rule}: {self.detail}"


def find_orm_tenant_findings(base: Any) -> list[TenantOwnershipFinding]:
    """Return every mapped table that is not yet explicitly tenant-owned."""

    findings: list[TenantOwnershipFinding] = []
    mappers = sorted(base.registry.mappers, key=lambda mapper: mapper.local_table.name)
    for mapper in mappers:
        table = mapper.local_table
        if "tenant_id" not in table.c:
            findings.append(
                TenantOwnershipFinding(
                    path="src/libs/portfolio-common/portfolio_common/database_models.py",
                    line=None,
                    rule="missing-tenant-column",
                    detail=f"{table.name} ({mapper.class_.__name__})",
                )
            )
    return findings


def find_synthetic_default_findings(root: Path) -> list[TenantOwnershipFinding]:
    """Find production tenant defaults that silently fabricate ownership."""

    findings: list[TenantOwnershipFinding] = []
    source_root = root / "src"
    for path in sorted(source_root.rglob("*.py")):
        if "build" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if _is_synthetic_tenant_default(node):
                findings.append(
                    TenantOwnershipFinding(
                        path=path.relative_to(root).as_posix(),
                        line=node.lineno,
                        rule="synthetic-default-tenant",
                        detail="production tenant ownership cannot use the literal 'default'",
                    )
                )
    return findings


def find_critical_tenant_boundary_findings(root: Path) -> list[TenantOwnershipFinding]:
    """Require fail-closed tenant scope on critical application and persistence boundaries."""

    findings: list[TenantOwnershipFinding] = []
    for (
        relative_path,
        owner_name,
        required_methods,
        required_parameter,
    ) in CRITICAL_TENANT_BOUNDARIES:
        path = root / relative_path
        if not path.is_file():
            findings.append(
                TenantOwnershipFinding(
                    path=relative_path.as_posix(),
                    line=None,
                    rule="missing-critical-tenant-boundary",
                    detail=f"{owner_name} source file is missing",
                )
            )
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        owner = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == owner_name
            ),
            None,
        )
        methods = (
            {
                node.name: node
                for node in owner.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if owner is not None
            else {}
        )
        for method_name in sorted(required_methods):
            method = methods.get(method_name)
            if method is None:
                findings.append(
                    TenantOwnershipFinding(
                        path=relative_path.as_posix(),
                        line=owner.lineno if owner is not None else None,
                        rule="missing-critical-tenant-boundary",
                        detail=f"{owner_name}.{method_name} is missing",
                    )
                )
                continue
            tenant_parameters = [
                (argument, default)
                for argument, default in zip(method.args.kwonlyargs, method.args.kw_defaults)
                if argument.arg == required_parameter
            ]
            if not tenant_parameters or tenant_parameters[0][1] is not None:
                findings.append(
                    TenantOwnershipFinding(
                        path=relative_path.as_posix(),
                        line=method.lineno,
                        rule="optional-critical-tenant-boundary",
                        detail=(
                            f"{owner_name}.{method_name} must require keyword-only "
                            f"{required_parameter}"
                        ),
                    )
                )
    return findings


def _is_synthetic_tenant_default(node: ast.AST) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return _has_defaulted_tenant_parameter(node.args)
    if isinstance(node, ast.keyword):
        return node.arg == "tenant_id" and _is_default_literal(node.value)
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        value = node.value
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return any("tenant_id" in _target_names(item) for item in targets) and (
            _is_default_literal(value) or _call_contains_default_literal(value)
        )
    if isinstance(node, ast.Dict):
        return any(
            _is_tenant_id_literal(key) and _is_default_literal(value)
            for key, value in zip(node.keys, node.values)
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return (
            node.func.attr == "get"
            and len(node.args) >= 2
            and _is_tenant_header_literal(node.args[0])
            and _is_default_literal(node.args[1])
        )
    return False


def _has_defaulted_tenant_parameter(arguments: ast.arguments) -> bool:
    positional = [*arguments.posonlyargs, *arguments.args]
    defaulted_positional = zip(positional[-len(arguments.defaults) :], arguments.defaults)
    if any(
        argument.arg == "tenant_id" and _is_synthetic_default_expression(default)
        for argument, default in defaulted_positional
    ):
        return True
    return any(
        argument.arg == "tenant_id" and _is_synthetic_default_expression(default)
        for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults)
    )


def _call_contains_default_literal(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    return any(_is_default_literal(argument) for argument in node.args) or any(
        _is_default_literal(keyword.value) for keyword in node.keywords
    )


def _is_synthetic_default_expression(node: ast.AST | None) -> bool:
    return _is_default_literal(node) or _call_contains_default_literal(node)


def _target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return {name for child in node.elts for name in _target_names(child)}
    return set()


def _is_default_literal(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value == "default"


def _is_tenant_id_literal(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value == "tenant_id"


def _is_tenant_header_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and str(node.value).lower() == "x-tenant-id"


def evaluate_tenant_ownership(root: Path = REPO_ROOT) -> list[TenantOwnershipFinding]:
    from portfolio_common.database_models import Base

    return [
        *find_orm_tenant_findings(Base),
        *find_synthetic_default_findings(root),
        *find_critical_tenant_boundary_findings(root),
    ]


def _is_blocking(finding: TenantOwnershipFinding, mode: GuardMode) -> bool:
    if mode == "report":
        return False
    if mode == "enforce-defaults":
        return finding.rule == "synthetic-default-tenant"
    if mode == "enforce-critical":
        return finding.rule in {
            "synthetic-default-tenant",
            "missing-critical-tenant-boundary",
            "optional-critical-tenant-boundary",
        }
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure source-owned tenant coverage and reject synthetic defaults."
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--mode",
        choices=("report", "enforce-defaults", "enforce-critical", "enforce"),
        default="report",
    )
    args = parser.parse_args()

    findings = evaluate_tenant_ownership(args.root.resolve())
    for finding in findings:
        print(f"  - {finding.as_text()}")
    blocking = [finding for finding in findings if _is_blocking(finding, args.mode)]
    print(
        "Tenant ownership guard: "
        f"{len(findings)} finding(s), {len(blocking)} blocking in {args.mode} mode."
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
