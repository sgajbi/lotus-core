from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLATFORM_REPO = REPO_ROOT.parent / "lotus-platform"
CONTRACT_RELATIVE_PATH = Path("context/contracts/canonical-front-office-demo-data-contract.json")
INVARIANTS_RELATIVE_PATH = Path("context/contracts/canonical-front-office-demo-data-invariants.json")


@dataclass(frozen=True)
class FrontOfficeSeedContract:
    portfolio_id: str
    benchmark_id: str
    canonical_as_of_date: str
    benchmark_start_date: str
    seed_start_date: str
    projected_horizon_end_date: str
    min_positions: int
    min_valued_positions: int
    min_transactions: int
    min_cash_accounts: int
    min_allocation_views: int
    min_projected_cashflow_points: int
    min_performance_contribution_rows: int
    min_risk_ready_metrics: int
    min_risk_rolling_windows: int
    min_risk_attribution_contributors: int


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_platform_repo_root() -> Path | None:
    configured_root = os.getenv("LOTUS_PLATFORM_REPO")
    if configured_root:
        path = Path(configured_root).expanduser().resolve()
        if path.exists():
            return path

    if DEFAULT_PLATFORM_REPO.exists():
        return DEFAULT_PLATFORM_REPO.resolve()
    return None


def _load_platform_contract_artifacts() -> tuple[dict[str, Any], dict[str, Any]] | None:
    platform_root = _resolve_platform_repo_root()
    if platform_root is None:
        return None

    contract_path = platform_root / CONTRACT_RELATIVE_PATH
    invariants_path = platform_root / INVARIANTS_RELATIVE_PATH
    if not contract_path.exists() or not invariants_path.exists():
        return None

    return _load_json(contract_path), _load_json(invariants_path)


def _build_fallback_contract() -> FrontOfficeSeedContract:
    return FrontOfficeSeedContract(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        benchmark_id="BMK_PB_GLOBAL_BALANCED_60_40",
        canonical_as_of_date="2026-04-10",
        benchmark_start_date="2025-01-06",
        seed_start_date="2025-03-31",
        projected_horizon_end_date="2026-05-10",
        min_positions=10,
        min_valued_positions=10,
        min_transactions=30,
        min_cash_accounts=2,
        min_allocation_views=4,
        min_projected_cashflow_points=1,
        min_performance_contribution_rows=4,
        min_risk_ready_metrics=6,
        min_risk_rolling_windows=4,
        min_risk_attribution_contributors=7,
    )


def _to_seed_contract(
    contract_payload: dict[str, Any],
    invariant_payload: dict[str, Any],
) -> FrontOfficeSeedContract:
    portfolio = contract_payload["portfolio"]
    benchmark = contract_payload["benchmark"]
    date_policy = contract_payload["date_policy"]
    thresholds = invariant_payload["minimum_thresholds"]

    return FrontOfficeSeedContract(
        portfolio_id=portfolio["portfolio_id"],
        benchmark_id=benchmark["benchmark_code"],
        canonical_as_of_date=date_policy["canonical_as_of_date"],
        benchmark_start_date=date_policy["warmup_start_date"],
        seed_start_date=date_policy["seed_start_date"],
        projected_horizon_end_date=date_policy["projected_horizon_end_date"],
        min_positions=int(thresholds.get("positions", 10)),
        min_valued_positions=int(thresholds.get("valued_positions", 10)),
        min_transactions=int(thresholds["transactions"]),
        min_cash_accounts=int(thresholds["cash_accounts"]),
        min_allocation_views=int(thresholds["allocation_views"]),
        min_projected_cashflow_points=int(thresholds["projected_cashflow_points"]),
        min_performance_contribution_rows=int(thresholds["performance_contribution_rows"]),
        min_risk_ready_metrics=int(thresholds["risk_ready_metrics"]),
        min_risk_rolling_windows=int(thresholds["risk_rolling_windows"]),
        min_risk_attribution_contributors=int(thresholds["risk_attribution_contributors"]),
    )


def load_front_office_seed_contract() -> FrontOfficeSeedContract:
    payloads = _load_platform_contract_artifacts()
    if payloads is None:
        return _build_fallback_contract()
    contract_payload, invariant_payload = payloads
    return _to_seed_contract(contract_payload, invariant_payload)
