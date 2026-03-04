from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET_FILES = [
    ROOT / "src/services/ingestion_service/app/ops_controls.py",
    ROOT / "src/services/ingestion_service/app/services/ingestion_job_service.py",
]


def main() -> int:
    violations: list[str] = []
    for path in TARGET_FILES:
        content = path.read_text(encoding="utf-8")
        if "os.getenv(" in content:
            violations.append(str(path.relative_to(ROOT)))

    if violations:
        print("Configuration access guard failed. Direct os.getenv usage is not allowed in:")
        for item in violations:
            print(f"- {item}")
        print(
            "Move env parsing to src/services/ingestion_service/app/settings.py and consume typed settings."
        )
        return 1

    print("Configuration access guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
