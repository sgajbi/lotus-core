from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Files intentionally permitted to access os.getenv directly.
# All other source files under src/ will fail if they introduce direct env reads.
ALLOWED_OS_GETENV_PATHS = {
    Path("src/libs/portfolio-common/portfolio_common/config.py"),
    Path("src/libs/portfolio-common/portfolio_common/db.py"),
    Path("src/libs/portfolio-common/portfolio_common/logging_utils.py"),
    Path("src/services/calculators/position_valuation_calculator/app/core/reprocessing_worker.py"),
    Path("src/services/calculators/position_valuation_calculator/app/core/valuation_scheduler.py"),
    Path("src/services/ingestion_service/app/settings.py"),
    Path("src/services/query_service/app/enterprise_readiness.py"),
    Path("src/services/query_service/app/services/analytics_timeseries_service.py"),
    Path("src/services/query_service/app/services/capabilities_service.py"),
    Path("src/services/query_service/app/services/integration_service.py"),
}


def main() -> int:
    violations: list[str] = []
    for path in ROOT.glob("src/**/*.py"):
        content = path.read_text(encoding="utf-8")
        if "os.getenv(" not in content:
            continue
        relative = path.relative_to(ROOT)
        if relative not in ALLOWED_OS_GETENV_PATHS:
            violations.append(str(relative))

    if violations:
        print(
            "Configuration access guard failed. Direct os.getenv usage is not allowed in:"
        )
        for item in sorted(violations):
            print(f"- {item}")
        print(
            "Move env parsing into approved typed settings/config modules "
            "and consume structured settings from service code."
        )
        return 1

    print("Configuration access guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
