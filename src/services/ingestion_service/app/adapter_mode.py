from fastapi import HTTPException, status
from .settings import get_ingestion_service_settings


def portfolio_bundle_adapter_enabled() -> bool:
    return get_ingestion_service_settings().adapter_mode.portfolio_bundle_enabled


def upload_adapter_enabled() -> bool:
    return get_ingestion_service_settings().adapter_mode.upload_apis_enabled


def require_portfolio_bundle_adapter_enabled() -> None:
    if portfolio_bundle_adapter_enabled():
        return
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "LOTUS_CORE_ADAPTER_MODE_DISABLED",
            "capability": "lotus_core.ingestion.portfolio_bundle_adapter",
            "message": (
                "Portfolio bundle adapter mode is disabled. "
                "Use canonical ingestion endpoints (/ingest/portfolios, /ingest/transactions, "
                "/ingest/instruments, /ingest/market-prices, /ingest/fx-rates, /ingest/business-dates)."
            ),
        },
    )


def require_upload_adapter_enabled() -> None:
    if upload_adapter_enabled():
        return
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "LOTUS_CORE_ADAPTER_MODE_DISABLED",
            "capability": "lotus_core.ingestion.bulk_upload_adapter",
            "message": (
                "Bulk upload adapter mode is disabled. "
                "Use canonical ingestion endpoints for production upstream integration."
            ),
        },
    )
