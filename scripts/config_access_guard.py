from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Files intentionally permitted to access os.getenv directly.
# All other source files under src/ will fail if they introduce direct env reads.
ALLOWED_OS_GETENV_PATHS = {
    Path("src/libs/portfolio-common/portfolio_common/config.py"),
    Path("src/libs/portfolio-common/portfolio_common/db.py"),
    Path("src/libs/portfolio-common/portfolio_common/logging_utils.py"),
    Path("src/libs/portfolio-common/portfolio_common/outbox_settings.py"),
    Path("src/services/valuation_orchestrator_service/app/settings.py"),
    Path("src/services/ingestion_service/app/settings.py"),
    Path("src/services/portfolio_aggregation_service/app/settings.py"),
    Path("src/services/query_service/app/settings.py"),
}

IGNORED_GENERATED_PATH_PARTS = (
    "/build/",
    "/dist/",
)


def _is_generated_artifact(path: Path) -> bool:
    normalized = f"/{path.as_posix().strip('/')}/"
    return any(path_part in normalized for path_part in IGNORED_GENERATED_PATH_PARTS)


def main() -> int:
    violations: list[str] = []
    for path in ROOT.glob("src/**/*.py"):
        if _is_generated_artifact(path.relative_to(ROOT)):
            continue
        content = path.read_text(encoding="utf-8")
        if "os.getenv(" not in content:
            continue
        relative = path.relative_to(ROOT)
        if relative not in ALLOWED_OS_GETENV_PATHS:
            violations.append(str(relative))

    if violations:
        print("Configuration access guard failed. Direct os.getenv usage is not allowed in:")
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
