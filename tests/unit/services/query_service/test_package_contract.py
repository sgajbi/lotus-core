from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SERVICE_ROOT = REPO_ROOT / "src" / "services" / "query_service"
DOCKERFILE = SERVICE_ROOT / "Dockerfile"


def test_query_service_wheel_keeps_app_package(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(tmp_path),
            str(SERVICE_ROOT),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel_path = next(tmp_path.glob("query_service-*.whl"))
    with zipfile.ZipFile(wheel_path) as wheel:
        names = set(wheel.namelist())

    assert "app/__init__.py" in names
    assert "app/main.py" in names
    assert "app/routers/transactions.py" in names


def test_query_service_dockerfile_targets_packaged_app_module() -> None:
    dockerfile_text = DOCKERFILE.read_text(encoding="utf-8")
    assert 'CMD ["uvicorn", "app.main:app"' in dockerfile_text
