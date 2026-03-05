"""Single source of truth for CI/local test suite composition."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _discover_integration_lite() -> list[str]:
    query_integration_root = Path("tests/integration/services/query_service")
    router_like = sorted(query_integration_root.glob("test_*router*.py"))
    explicit = [query_integration_root / "test_main_app.py"]
    combined = [*router_like, *explicit]
    return [str(path).replace("\\", "/") for path in sorted(set(combined))]


SUITES: dict[str, list[str]] = {
    "unit": ["tests/unit"],
    "unit-db": [
        "tests/unit/libs/portfolio-common/test_position_state_repository.py",
        "tests/unit/services/calculators/position_valuation_calculator/repositories/test_unit_valuation_repo.py",
    ],
    "integration-lite": _discover_integration_lite(),
    "ops-contract": [
        "tests/integration/services/ingestion_service/test_ingestion_routers.py",
    ],
    "e2e-smoke": [
        "tests/e2e/test_query_service_observability.py",
        "tests/e2e/test_complex_portfolio_lifecycle.py",
    ],
    "transaction-buy-contract": [
        "tests/unit/transaction_specs/test_buy_slice0_characterization.py",
        "tests/unit/libs/portfolio_common/test_buy_validation.py",
        "tests/unit/libs/portfolio_common/test_transaction_metadata_contract.py",
        "tests/unit/services/ingestion_service/test_transaction_model.py",
        "tests/unit/libs/financial-calculator-engine/unit/test_cost_calculator.py",
        "tests/unit/libs/financial-calculator-engine/unit/test_transaction_processor.py",
        "tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py",
        "tests/unit/services/query_service/repositories/test_buy_state_repository.py",
        "tests/unit/services/query_service/services/test_buy_state_service.py",
        "tests/integration/services/calculators/cost_calculator_service/test_int_cost_repository_lot_offset.py",
        "tests/integration/services/query_service/test_buy_state_router.py",
    ],
    "transaction-sell-contract": [
        "tests/unit/transaction_specs/test_sell_slice0_characterization.py",
        "tests/unit/libs/portfolio_common/test_sell_validation.py",
        "tests/unit/libs/portfolio_common/test_sell_linkage.py",
        "tests/unit/libs/financial-calculator-engine/unit/test_cost_calculator.py",
        "tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py",
        "tests/unit/services/query_service/repositories/test_sell_state_repository.py",
        "tests/unit/services/query_service/services/test_sell_state_service.py",
        "tests/integration/services/query_service/test_sell_state_router.py",
    ],
    "transaction-dividend-contract": [
        "tests/unit/transaction_specs/test_dividend_slice0_characterization.py",
        "tests/unit/libs/portfolio_common/test_dividend_validation.py",
        "tests/unit/libs/portfolio_common/test_dividend_linkage.py",
        "tests/unit/libs/portfolio_common/test_cash_entry_mode.py",
        "tests/unit/libs/portfolio_common/test_transaction_metadata_contract.py",
        "tests/unit/libs/financial-calculator-engine/unit/test_cost_calculator.py",
        "tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py",
        "tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py",
        "tests/unit/services/ingestion_service/test_transaction_model.py",
        "tests/unit/services/query_service/services/test_transaction_service.py",
        "tests/integration/services/query_service/test_transactions_router.py",
        "tests/integration/services/persistence_service/repositories/test_repositories.py",
    ],
    "transaction-interest-contract": [
        "tests/unit/transaction_specs/test_interest_slice0_characterization.py",
        "tests/unit/libs/portfolio_common/test_interest_validation.py",
        "tests/unit/libs/portfolio_common/test_interest_linkage.py",
        "tests/unit/libs/portfolio_common/test_transaction_metadata_contract.py",
        "tests/unit/libs/financial-calculator-engine/unit/test_cost_calculator.py",
        "tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py",
        "tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py",
        "tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py",
        "tests/unit/services/ingestion_service/test_transaction_model.py",
        "tests/unit/services/query_service/services/test_transaction_service.py",
        "tests/integration/services/query_service/test_transactions_router.py",
        "tests/integration/services/persistence_service/repositories/test_repositories.py",
    ],
    "transaction-portfolio-flow-bundle-contract": [
        "tests/unit/libs/portfolio_common/test_portfolio_flow_guardrails.py",
        "tests/unit/services/calculators/portfolio_flow_bundle/test_portfolio_flow_bundle_slice0_characterization.py",
        "tests/unit/services/calculators/portfolio_flow_bundle/test_portfolio_flow_bundle_slice2_classification.py",
        "tests/unit/services/calculators/position_calculator/core/test_position_logic.py",
        "tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py",
        "tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py",
        "tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py",
        "tests/unit/services/query_service/services/test_position_flow_effects.py",
        "tests/unit/services/query_service/services/test_core_snapshot_service.py",
        "tests/unit/services/query_service/services/test_simulation_service.py",
    ],
}

# Backward-compatible aliases for previous suite names.
SUITES["buy-rfc"] = SUITES["transaction-buy-contract"]
SUITES["sell-rfc"] = SUITES["transaction-sell-contract"]
SUITES["dividend-rfc"] = SUITES["transaction-dividend-contract"]
SUITES["interest-rfc"] = SUITES["transaction-interest-contract"]
SUITES["portfolio-flow-bundle-rfc"] = SUITES["transaction-portfolio-flow-bundle-contract"]

SOURCE = "src/services/query_service/app"
SUITE_PYTEST_ARGS: dict[str, list[str]] = {
    "unit": ["-m", "not integration_db"],
}

SUITE_ENV_PROFILE: dict[str, str] = {
    "unit": "unit",
    "unit-db": "unit",
    "integration-lite": "integration",
    "ops-contract": "integration",
    "transaction-buy-contract": "integration",
    "transaction-sell-contract": "integration",
    "transaction-dividend-contract": "integration",
    "transaction-interest-contract": "integration",
    "transaction-portfolio-flow-bundle-contract": "integration",
    "buy-rfc": "integration",
    "sell-rfc": "integration",
    "dividend-rfc": "integration",
    "interest-rfc": "integration",
    "portfolio-flow-bundle-rfc": "integration",
    "e2e-smoke": "e2e",
}

PROFILE_ENV_DEFAULTS: dict[str, dict[str, str]] = {
    "unit": {
        "LOTUS_ZOOKEEPER_PORT": "2181",
        "LOTUS_KAFKA_EXTERNAL_PORT": "9092",
        "LOTUS_KAFKA_INTERNAL_PORT": "9093",
        "LOTUS_POSTGRES_HOST_PORT": "55432",
        "LOTUS_INGESTION_HOST_PORT": "8200",
        "LOTUS_QUERY_HOST_PORT": "8201",
        "LOTUS_PERSISTENCE_HOST_PORT": "8080",
        "LOTUS_POSITION_CALCULATOR_HOST_PORT": "8081",
        "LOTUS_CASHFLOW_CALCULATOR_HOST_PORT": "8082",
        "LOTUS_COST_CALCULATOR_HOST_PORT": "8083",
        "LOTUS_POSITION_VALUATION_HOST_PORT": "8084",
        "LOTUS_TIMESERIES_GENERATOR_HOST_PORT": "8085",
    },
    "integration": {
        "LOTUS_ZOOKEEPER_PORT": "2281",
        "LOTUS_KAFKA_EXTERNAL_PORT": "9192",
        "LOTUS_KAFKA_INTERNAL_PORT": "9193",
        "LOTUS_POSTGRES_HOST_PORT": "56432",
        "LOTUS_INGESTION_HOST_PORT": "8300",
        "LOTUS_QUERY_HOST_PORT": "8301",
        "LOTUS_PERSISTENCE_HOST_PORT": "8180",
        "LOTUS_POSITION_CALCULATOR_HOST_PORT": "8181",
        "LOTUS_CASHFLOW_CALCULATOR_HOST_PORT": "8182",
        "LOTUS_COST_CALCULATOR_HOST_PORT": "8183",
        "LOTUS_POSITION_VALUATION_HOST_PORT": "8184",
        "LOTUS_TIMESERIES_GENERATOR_HOST_PORT": "8185",
    },
    "e2e": {
        "LOTUS_ZOOKEEPER_PORT": "2381",
        "LOTUS_KAFKA_EXTERNAL_PORT": "9292",
        "LOTUS_KAFKA_INTERNAL_PORT": "9293",
        "LOTUS_POSTGRES_HOST_PORT": "57432",
        "LOTUS_INGESTION_HOST_PORT": "8400",
        "LOTUS_QUERY_HOST_PORT": "8401",
        "LOTUS_PERSISTENCE_HOST_PORT": "8280",
        "LOTUS_POSITION_CALCULATOR_HOST_PORT": "8281",
        "LOTUS_CASHFLOW_CALCULATOR_HOST_PORT": "8282",
        "LOTUS_COST_CALCULATOR_HOST_PORT": "8283",
        "LOTUS_POSITION_VALUATION_HOST_PORT": "8284",
        "LOTUS_TIMESERIES_GENERATOR_HOST_PORT": "8285",
    },
}


def get_suite(name: str) -> list[str]:
    try:
        return SUITES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown suite: {name}") from exc


def validate_suite_paths(name: str) -> None:
    missing = [
        path for path in get_suite(name) if not path.startswith("-") and not Path(path).exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"Suite '{name}' has missing test paths:\n"
            + "\n".join(f" - {path}" for path in missing)
        )


def run_suite(
    name: str,
    *,
    quiet: bool = False,
    with_coverage: bool = False,
    coverage_file: str | None = None,
) -> int:
    validate_suite_paths(name)

    cmd = [sys.executable, "-m", "pytest", *get_suite(name), *SUITE_PYTEST_ARGS.get(name, [])]
    if quiet:
        cmd.append("-q")
    if with_coverage:
        cmd.extend([f"--cov={SOURCE}", "--cov-report="])

    env = os.environ.copy()
    env_profile = SUITE_ENV_PROFILE.get(name, "unit")
    env.setdefault("LOTUS_TEST_ENV_PROFILE", env_profile)
    for key, value in PROFILE_ENV_DEFAULTS[env_profile].items():
        env.setdefault(key, value)
    env.setdefault(
        "COMPOSE_PROJECT_NAME",
        f"lotus-{env_profile}-{name}".replace("_", "-"),
    )
    if coverage_file:
        env["COVERAGE_FILE"] = coverage_file

    return subprocess.run(cmd, check=False, env=env).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or inspect CI test suite definitions.")
    parser.add_argument(
        "--suite",
        choices=sorted(SUITES.keys()),
        required=True,
        help="Suite name to run or inspect.",
    )
    parser.add_argument(
        "--print-args",
        action="store_true",
        help="Print pytest args for the suite and exit.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Run pytest with -q.",
    )
    parser.add_argument(
        "--with-coverage",
        action="store_true",
        help="Add --cov and --cov-report= to pytest invocation.",
    )
    parser.add_argument(
        "--coverage-file",
        default=None,
        help="Set COVERAGE_FILE while running the suite.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate suite paths and exit.",
    )
    args = parser.parse_args()

    validate_suite_paths(args.suite)

    if args.print_args:
        print(" ".join(get_suite(args.suite)))
        return 0

    if args.validate_only:
        print(f"Suite '{args.suite}' is valid ({len(get_suite(args.suite))} entries).")
        return 0

    return run_suite(
        args.suite,
        quiet=args.quiet,
        with_coverage=args.with_coverage,
        coverage_file=args.coverage_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
