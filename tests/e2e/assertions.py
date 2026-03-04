from decimal import Decimal
from typing import Any

import pytest
import requests


def as_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def assert_decimal_approx(value: Any, expected: float, rel: float = 1e-9, abs: float = 1e-6) -> None:
    assert float(as_decimal(value)) == pytest.approx(expected, rel=rel, abs=abs)


def assert_legacy_endpoint_status(
    response: requests.Response,
    *,
    target_service: str | None = None,
    target_endpoint: str | None = None,
) -> None:
    """
    Accepts either:
    - 404 when endpoint has been fully removed from lotus-core routing, or
    - 410 with structured migration detail when compatibility shim is still present.
    """
    assert response.status_code in {404, 410}
    if response.status_code == 410:
        detail = response.json()["detail"]
        assert detail["code"] == "LOTUS_CORE_LEGACY_ENDPOINT_REMOVED"
        if target_service is not None:
            assert detail["target_service"] == target_service
        if target_endpoint is not None:
            assert detail["target_endpoint"] == target_endpoint

