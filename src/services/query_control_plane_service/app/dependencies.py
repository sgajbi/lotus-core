from fastapi import Depends
from portfolio_common.db import get_async_db_session
from portfolio_common.page_tokens import PageTokenCodec
from portfolio_common.runtime_providers import SystemClock, UuidIdGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from .application.analytics.analytics_timeseries_service import (
    AnalyticsRuntimePolicy,
    AnalyticsTimeseriesService,
)
from .application.benchmark_assignment import BenchmarkAssignmentService
from .application.benchmark_catalog import BenchmarkCatalogService
from .application.benchmark_composition import BenchmarkCompositionService
from .application.benchmark_definition import BenchmarkDefinitionService
from .application.benchmark_market_series.service import BenchmarkMarketSeriesService
from .application.benchmark_return_series import BenchmarkReturnSeriesService
from .application.classification_taxonomy import ClassificationTaxonomyService
from .application.client_liquidity_evidence import ClientLiquidityEvidenceService
from .application.client_restriction_profile import ClientRestrictionProfileService
from .application.client_tax_profile import ClientTaxProfileService
from .application.client_tax_rule_set import ClientTaxRuleSetService
from .application.core_snapshot.service import (
    CoreSnapshotDependencies,
    CoreSnapshotService,
)
from .application.dpm_portfolio_population import DpmPortfolioPopulationService
from .application.dpm_source_readiness.discretionary_mandate_binding import (
    DiscretionaryMandateBindingService,
)
from .application.dpm_source_readiness.instrument_eligibility import (
    InstrumentEligibilityService,
)
from .application.dpm_source_readiness.market_data_coverage import MarketDataCoverageService
from .application.dpm_source_readiness.model_portfolio_targets import ModelPortfolioTargetService
from .application.dpm_source_readiness.portfolio_tax_lots import PortfolioTaxLotService
from .application.dpm_source_readiness.readiness import DpmSourceReadinessService
from .application.external_hedge_posture import ExternalHedgePostureService
from .application.index_catalog import IndexCatalogService
from .application.index_series import IndexSeriesService
from .application.integration_policy import (
    IntegrationPolicyConfiguration,
    IntegrationPolicyService,
)
from .application.operations.service import OperationsService
from .application.portfolio_manager_book import PortfolioManagerBookService
from .application.portfolio_party_roles import PortfolioPartyRoleAssignmentService
from .application.reference_coverage import ReferenceCoverageService
from .application.risk_free_series import RiskFreeSeriesService
from .application.simulation import SimulationService
from .application.sustainability_preference_profile import SustainabilityPreferenceProfileService
from .application.transaction_economics.service import TransactionEconomicsService
from .infrastructure.analytics_export_repository import AnalyticsExportRepository
from .infrastructure.analytics_timeseries_repository import AnalyticsTimeseriesRepository
from .infrastructure.analytics_unit_of_work import SqlAlchemyAnalyticsUnitOfWork
from .infrastructure.benchmark_assignment_sources import (
    SqlAlchemyBenchmarkAssignmentReader,
)
from .infrastructure.benchmark_definition_sources import (
    SqlAlchemyBenchmarkDefinitionReader,
)
from .infrastructure.benchmark_return_series_sources import (
    SqlAlchemyBenchmarkReturnSeriesReader,
)
from .infrastructure.classification_taxonomy_sources import (
    SqlAlchemyClassificationTaxonomyReader,
)
from .infrastructure.client_liquidity_evidence_sources import (
    SqlAlchemyClientLiquidityEvidenceReader,
)
from .infrastructure.client_restriction_profile_sources import (
    SqlAlchemyClientRestrictionProfileSourceReader,
)
from .infrastructure.client_tax_profile_sources import SqlAlchemyClientTaxProfileSourceReader
from .infrastructure.client_tax_rule_set_sources import SqlAlchemyClientTaxRuleSetSourceReader
from .infrastructure.core_snapshot_sources import SqlAlchemyCoreSnapshotSourceReader
from .infrastructure.dpm_portfolio_population_sources import (
    SqlAlchemyDpmPortfolioPopulationReader,
)
from .infrastructure.dpm_portfolio_state_sources import SqlAlchemyDpmPortfolioStateReader
from .infrastructure.dpm_reference_data_sources import SqlAlchemyDpmReferenceDataReader
from .infrastructure.effective_mandate_sources import SqlAlchemyEffectiveMandateReader
from .infrastructure.index_definition_sources import SqlAlchemyIndexDefinitionReader
from .infrastructure.index_series_sources import SqlAlchemyIndexSeriesReader
from .infrastructure.market_fx_sources import SqlAlchemyMarketFxRateReader
from .infrastructure.operations.repository import OperationsRepository
from .infrastructure.portfolio_manager_book_sources import SqlAlchemyPortfolioManagerBookReader
from .infrastructure.portfolio_party_role_sources import SqlAlchemyPortfolioPartyRoleReader
from .infrastructure.risk_free_series_sources import SqlAlchemyRiskFreeSeriesReader
from .infrastructure.scoped_page_tokens import RouteScopedPageTokenCodec
from .infrastructure.simulation_store import (
    SqlAlchemySimulationBaselineReader,
    SqlAlchemySimulationStore,
)
from .infrastructure.simulation_unit_of_work import SqlAlchemySimulationUnitOfWork
from .infrastructure.sustainability_preference_profile_sources import (
    SqlAlchemySustainabilityPreferenceProfileSourceReader,
)
from .infrastructure.transaction_economics_sources import (
    SqlAlchemyTransactionEconomicsReader,
)
from .settings import load_query_control_plane_settings


def get_analytics_timeseries_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> AnalyticsTimeseriesService:
    settings = load_query_control_plane_settings()
    return AnalyticsTimeseriesService(
        reader=AnalyticsTimeseriesRepository(db),
        export_store=AnalyticsExportRepository(db),
        unit_of_work=SqlAlchemyAnalyticsUnitOfWork(db),
        policy=AnalyticsRuntimePolicy(
            page_token_secret=settings.page_token_secret,
            page_token_key_id=settings.page_token_key_id,
            page_token_previous_keys=settings.page_token_previous_keys,
            page_token_ttl_seconds=settings.page_token_ttl_seconds,
            export_stale_timeout_minutes=settings.analytics_export_stale_timeout_minutes,
            export_execution_timeout_seconds=settings.analytics_export_execution_timeout_seconds,
        ),
    )


def get_core_snapshot_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CoreSnapshotService:
    return CoreSnapshotService(
        dependencies=CoreSnapshotDependencies(
            source_reader=SqlAlchemyCoreSnapshotSourceReader(db),
            simulation_store=SqlAlchemySimulationStore(db),
            clock=SystemClock(),
        )
    )


def get_benchmark_assignment_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> BenchmarkAssignmentService:
    """Compose the QCP-owned benchmark assignment use case."""

    return BenchmarkAssignmentService(
        reader=SqlAlchemyBenchmarkAssignmentReader(db),
        clock=SystemClock().utc_now,
    )


def get_benchmark_definition_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> BenchmarkDefinitionService:
    """Compose the QCP-owned benchmark definition use case."""

    return BenchmarkDefinitionService(
        reader=SqlAlchemyBenchmarkDefinitionReader(db),
        clock=SystemClock().utc_now,
    )


def get_benchmark_composition_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> BenchmarkCompositionService:
    """Compose the QCP-owned benchmark composition-window use case."""

    return BenchmarkCompositionService(
        reader=SqlAlchemyBenchmarkDefinitionReader(db),
        clock=SystemClock().utc_now,
    )


def get_benchmark_catalog_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> BenchmarkCatalogService:
    """Compose the QCP-owned benchmark catalog use case."""

    return BenchmarkCatalogService(
        reader=SqlAlchemyBenchmarkDefinitionReader(db),
        clock=SystemClock().utc_now,
    )


def get_benchmark_return_series_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> BenchmarkReturnSeriesService:
    """Compose the QCP-owned benchmark return series use case."""

    return BenchmarkReturnSeriesService(
        reader=SqlAlchemyBenchmarkReturnSeriesReader(db),
        clock=SystemClock().utc_now,
    )


def get_benchmark_market_series_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> BenchmarkMarketSeriesService:
    """Compose the QCP-owned benchmark component market-series use case."""

    settings = load_query_control_plane_settings()
    return BenchmarkMarketSeriesService(
        benchmark_reader=SqlAlchemyBenchmarkDefinitionReader(db),
        index_series_reader=SqlAlchemyIndexSeriesReader(db),
        benchmark_return_reader=SqlAlchemyBenchmarkReturnSeriesReader(db),
        fx_rate_reader=SqlAlchemyMarketFxRateReader(db),
        page_tokens=RouteScopedPageTokenCodec(
            codec=PageTokenCodec(
                secret=settings.page_token_secret,
                active_kid=settings.page_token_key_id,
                previous_secrets=settings.page_token_previous_keys,
                ttl_seconds=settings.page_token_ttl_seconds,
            ),
            route="integration.benchmark_market_series",
        ),
        clock=SystemClock().utc_now,
    )


def get_index_catalog_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> IndexCatalogService:
    """Compose the QCP-owned index catalog use case."""

    return IndexCatalogService(
        reader=SqlAlchemyIndexDefinitionReader(db),
        clock=SystemClock().utc_now,
    )


def get_index_series_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> IndexSeriesService:
    """Compose the QCP-owned index series window use case."""

    return IndexSeriesService(
        reader=SqlAlchemyIndexSeriesReader(db),
        clock=SystemClock().utc_now,
    )


def get_risk_free_series_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> RiskFreeSeriesService:
    """Compose the QCP-owned risk-free series use case."""

    return RiskFreeSeriesService(
        reader=SqlAlchemyRiskFreeSeriesReader(db),
        clock=SystemClock().utc_now,
    )


def get_reference_coverage_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ReferenceCoverageService:
    """Compose QCP-owned benchmark and risk-free coverage diagnostics."""

    return ReferenceCoverageService(
        benchmark_reader=SqlAlchemyBenchmarkDefinitionReader(db),
        index_series_reader=SqlAlchemyIndexSeriesReader(db),
        benchmark_return_reader=SqlAlchemyBenchmarkReturnSeriesReader(db),
        risk_free_reader=SqlAlchemyRiskFreeSeriesReader(db),
        clock=SystemClock().utc_now,
    )


def get_external_hedge_posture_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ExternalHedgePostureService:
    return ExternalHedgePostureService(
        mandate_reader=SqlAlchemyEffectiveMandateReader(db),
        clock=SystemClock(),
    )


def get_dpm_portfolio_population_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> DpmPortfolioPopulationService:
    settings = load_query_control_plane_settings()
    return DpmPortfolioPopulationService(
        reader=SqlAlchemyDpmPortfolioPopulationReader(db),
        page_tokens=PageTokenCodec(
            secret=settings.page_token_secret,
            active_kid=settings.page_token_key_id,
            previous_secrets=settings.page_token_previous_keys,
            ttl_seconds=settings.page_token_ttl_seconds,
        ),
        clock=SystemClock(),
    )


def get_dpm_source_readiness_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> DpmSourceReadinessService:
    """Compose the QCP-owned DPM source-readiness capability graph."""

    settings = load_query_control_plane_settings()
    clock = SystemClock()
    reference_reader = SqlAlchemyDpmReferenceDataReader(db)
    portfolio_reader = SqlAlchemyDpmPortfolioStateReader(db)
    page_tokens = PageTokenCodec(
        secret=settings.page_token_secret,
        active_kid=settings.page_token_key_id,
        previous_secrets=settings.page_token_previous_keys,
        ttl_seconds=settings.page_token_ttl_seconds,
    )
    return DpmSourceReadinessService(
        mandates=DiscretionaryMandateBindingService(
            reader=reference_reader,
            clock=clock.utc_now,
        ),
        model_targets=ModelPortfolioTargetService(
            reader=reference_reader,
            clock=clock.utc_now,
        ),
        eligibility=InstrumentEligibilityService(
            reader=reference_reader,
            clock=clock.utc_now,
        ),
        tax_lots=PortfolioTaxLotService(
            reader=portfolio_reader,
            page_tokens=page_tokens,
            clock=clock.utc_now,
        ),
        market_data=MarketDataCoverageService(
            reader=reference_reader,
            clock=clock.utc_now,
        ),
        clock=clock.utc_now,
    )


def get_transaction_economics_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> TransactionEconomicsService:
    settings = load_query_control_plane_settings()
    return TransactionEconomicsService(
        reader=SqlAlchemyTransactionEconomicsReader(db),
        page_tokens=PageTokenCodec(
            secret=settings.page_token_secret,
            active_kid=settings.page_token_key_id,
            previous_secrets=settings.page_token_previous_keys,
            ttl_seconds=settings.page_token_ttl_seconds,
        ),
        clock=SystemClock(),
    )


def get_client_restriction_profile_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ClientRestrictionProfileService:
    return ClientRestrictionProfileService(
        mandate_reader=SqlAlchemyEffectiveMandateReader(db),
        reader=SqlAlchemyClientRestrictionProfileSourceReader(db),
        clock=SystemClock(),
    )


def get_client_liquidity_evidence_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ClientLiquidityEvidenceService:
    return ClientLiquidityEvidenceService(
        mandate_reader=SqlAlchemyEffectiveMandateReader(db),
        reader=SqlAlchemyClientLiquidityEvidenceReader(db),
        clock=SystemClock(),
    )


def get_client_tax_profile_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ClientTaxProfileService:
    return ClientTaxProfileService(
        mandate_reader=SqlAlchemyEffectiveMandateReader(db),
        reader=SqlAlchemyClientTaxProfileSourceReader(db),
        clock=SystemClock(),
    )


def get_client_tax_rule_set_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ClientTaxRuleSetService:
    return ClientTaxRuleSetService(
        mandate_reader=SqlAlchemyEffectiveMandateReader(db),
        reader=SqlAlchemyClientTaxRuleSetSourceReader(db),
        clock=SystemClock(),
    )


def get_integration_policy_service() -> IntegrationPolicyService:
    settings = load_query_control_plane_settings()
    return IntegrationPolicyService(
        configuration=IntegrationPolicyConfiguration(
            policy_version=settings.lotus_core_policy_version,
            policy_json=settings.integration_snapshot_policy_json,
        ),
        clock=SystemClock(),
    )


def get_portfolio_manager_book_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PortfolioManagerBookService:
    return PortfolioManagerBookService(
        reader=SqlAlchemyPortfolioManagerBookReader(db),
        clock=SystemClock(),
    )


def get_portfolio_party_role_assignment_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PortfolioPartyRoleAssignmentService:
    return PortfolioPartyRoleAssignmentService(
        reader=SqlAlchemyPortfolioPartyRoleReader(db),
        clock=SystemClock(),
    )


def get_classification_taxonomy_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ClassificationTaxonomyService:
    """Compose the QCP-owned classification taxonomy use case."""

    return ClassificationTaxonomyService(
        reader=SqlAlchemyClassificationTaxonomyReader(db),
        clock=SystemClock().utc_now,
    )


def get_advisory_simulation_id_generator() -> UuidIdGenerator:
    """Provide runtime identity generation at the advisory API composition boundary."""

    return UuidIdGenerator()


def get_operations_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> OperationsService:
    return OperationsService(OperationsRepository(db))


def get_simulation_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> SimulationService:
    return SimulationService(
        store=SqlAlchemySimulationStore(db),
        baseline_reader=SqlAlchemySimulationBaselineReader(db),
        unit_of_work=SqlAlchemySimulationUnitOfWork(db),
        clock=SystemClock(),
        id_generator=UuidIdGenerator(),
    )


def get_sustainability_preference_profile_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> SustainabilityPreferenceProfileService:
    return SustainabilityPreferenceProfileService(
        mandate_reader=SqlAlchemyEffectiveMandateReader(db),
        reader=SqlAlchemySustainabilityPreferenceProfileSourceReader(db),
        clock=SystemClock(),
    )
