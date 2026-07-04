import pytest
from fastapi import HTTPException

from src.services.ingestion_service.app import dependencies
from src.services.ingestion_service.app.adapter_mode import (
    ADAPTER_MODE_DISABLED_CODE,
    UPLOAD_ADAPTER_CAPABILITY,
    AdapterModeDisabledError,
)


def test_require_upload_adapter_enabled_maps_policy_error_to_http_410(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_disabled() -> None:
        raise AdapterModeDisabledError(
            capability=UPLOAD_ADAPTER_CAPABILITY,
            message="Bulk upload adapter mode is disabled.",
        )

    monkeypatch.setattr(dependencies, "ensure_upload_adapter_enabled", _raise_disabled)

    with pytest.raises(HTTPException) as exc_info:
        dependencies.require_upload_adapter_enabled()

    assert exc_info.value.status_code == 410
    assert exc_info.value.detail == {
        "code": ADAPTER_MODE_DISABLED_CODE,
        "capability": UPLOAD_ADAPTER_CAPABILITY,
        "message": "Bulk upload adapter mode is disabled.",
    }
