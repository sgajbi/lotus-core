"""Shared assertions for E2E API contract checks."""

from __future__ import annotations

from typing import Any


def assert_legacy_endpoint_status(
    response: Any,
    *,
    target_service: str | None = None,
    target_endpoint: str | None = None,
) -> None:
    """
    Assert a legacy endpoint is disabled and returns migration guidance.

    Accepts either 404 (not found) or 410 (gone) so tests remain stable while
    legacy endpoints are being decommissioned behind routing/proxy layers.
    """

    assert response.status_code in (404, 410), (
        f"Expected disabled legacy endpoint (404/410), got {response.status_code}: "
        f"{getattr(response, 'text', '')}"
    )

    if target_service is None and target_endpoint is None:
        return

    body_text = ""
    try:
        body = response.json()
        body_text = str(body).lower()
    except Exception:
        body_text = str(getattr(response, "text", "")).lower()

    if target_service:
        assert target_service.lower() in body_text
    if target_endpoint:
        assert target_endpoint.lower() in body_text
