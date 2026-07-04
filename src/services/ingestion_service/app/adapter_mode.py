from .settings import IngestionServiceSettings, get_ingestion_service_settings

ADAPTER_MODE_DISABLED_CODE = "LOTUS_CORE_ADAPTER_MODE_DISABLED"
PORTFOLIO_BUNDLE_ADAPTER_CAPABILITY = "lotus_core.ingestion.portfolio_bundle_adapter"
UPLOAD_ADAPTER_CAPABILITY = "lotus_core.ingestion.bulk_upload_adapter"


class AdapterModeDisabledError(RuntimeError):
    def __init__(self, *, capability: str, message: str) -> None:
        super().__init__(message)
        self.code = ADAPTER_MODE_DISABLED_CODE
        self.capability = capability
        self.message = message

    @property
    def detail(self) -> dict[str, str]:
        return {
            "code": self.code,
            "capability": self.capability,
            "message": self.message,
        }


def _settings_or_current(
    settings: IngestionServiceSettings | None = None,
) -> IngestionServiceSettings:
    return settings if settings is not None else get_ingestion_service_settings()


def portfolio_bundle_adapter_enabled(
    settings: IngestionServiceSettings | None = None,
) -> bool:
    return _settings_or_current(settings).adapter_mode.portfolio_bundle_enabled


def upload_adapter_enabled(settings: IngestionServiceSettings | None = None) -> bool:
    return _settings_or_current(settings).adapter_mode.upload_apis_enabled


def ensure_portfolio_bundle_adapter_enabled(
    settings: IngestionServiceSettings | None = None,
) -> None:
    if portfolio_bundle_adapter_enabled(settings):
        return
    raise AdapterModeDisabledError(
        capability=PORTFOLIO_BUNDLE_ADAPTER_CAPABILITY,
        message=(
            "Portfolio bundle adapter mode is disabled. "
            "Use canonical ingestion endpoints (/ingest/portfolios, /ingest/transactions, "
            "/ingest/instruments, /ingest/market-prices, /ingest/fx-rates, "
            "/ingest/business-dates)."
        ),
    )


def ensure_upload_adapter_enabled(
    settings: IngestionServiceSettings | None = None,
) -> None:
    if upload_adapter_enabled(settings):
        return
    raise AdapterModeDisabledError(
        capability=UPLOAD_ADAPTER_CAPABILITY,
        message=(
            "Bulk upload adapter mode is disabled. "
            "Use canonical ingestion endpoints for production upstream integration."
        ),
    )
