from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_allocation_calculator_imports_from_packaged_query_service_namespace():
    query_service_root = Path(__file__).resolve().parents[5] / "src" / "services" / "query_service"
    sys.path.insert(0, str(query_service_root))
    try:
        module = importlib.import_module("app.services.allocation_calculator")
    finally:
        sys.path.pop(0)

    assert hasattr(module, "calculate_allocation_views")
