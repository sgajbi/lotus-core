import pytest

from src.services.ingestion_service.app.adapter_mode import (
    ADAPTER_MODE_DISABLED_CODE,
    PORTFOLIO_BUNDLE_ADAPTER_CAPABILITY,
    UPLOAD_ADAPTER_CAPABILITY,
    AdapterModeDisabledError,
    ensure_portfolio_bundle_adapter_enabled,
    ensure_upload_adapter_enabled,
    portfolio_bundle_adapter_enabled,
    upload_adapter_enabled,
)
from src.services.ingestion_service.app.settings import (
    IngestionAdapterModeSettings,
    IngestionServiceSettings,
)


def _settings(
    *,
    portfolio_bundle_enabled: bool,
    upload_apis_enabled: bool,
) -> IngestionServiceSettings:
    return IngestionServiceSettings(
        adapter_mode=IngestionAdapterModeSettings(
            portfolio_bundle_enabled=portfolio_bundle_enabled,
            upload_apis_enabled=upload_apis_enabled,
            upload_max_bytes=1024,
            upload_max_rows=100,
            upload_max_columns=50,
            upload_max_cell_length=1024,
        ),
        ops_auth=None,  # type: ignore[arg-type]
        rate_limit=None,  # type: ignore[arg-type]
        runtime_policy=None,  # type: ignore[arg-type]
    )


def test_adapter_mode_policy_reads_supplied_settings() -> None:
    settings = _settings(
        portfolio_bundle_enabled=True,
        upload_apis_enabled=False,
    )

    assert portfolio_bundle_adapter_enabled(settings) is True
    assert upload_adapter_enabled(settings) is False


def test_portfolio_bundle_adapter_mode_raises_framework_neutral_error() -> None:
    settings = _settings(
        portfolio_bundle_enabled=False,
        upload_apis_enabled=True,
    )

    with pytest.raises(AdapterModeDisabledError) as exc_info:
        ensure_portfolio_bundle_adapter_enabled(settings)

    assert exc_info.value.detail == {
        "code": ADAPTER_MODE_DISABLED_CODE,
        "capability": PORTFOLIO_BUNDLE_ADAPTER_CAPABILITY,
        "message": (
            "Portfolio bundle adapter mode is disabled. "
            "Use canonical ingestion endpoints (/ingest/portfolios, /ingest/transactions, "
            "/ingest/instruments, /ingest/market-prices, /ingest/fx-rates, "
            "/ingest/business-dates)."
        ),
    }


def test_upload_adapter_mode_raises_framework_neutral_error() -> None:
    settings = _settings(
        portfolio_bundle_enabled=True,
        upload_apis_enabled=False,
    )

    with pytest.raises(AdapterModeDisabledError) as exc_info:
        ensure_upload_adapter_enabled(settings)

    assert exc_info.value.detail == {
        "code": ADAPTER_MODE_DISABLED_CODE,
        "capability": UPLOAD_ADAPTER_CAPABILITY,
        "message": (
            "Bulk upload adapter mode is disabled. "
            "Use canonical ingestion endpoints for production upstream integration."
        ),
    }
