from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from portfolio_common.runtime_providers import Clock, SystemClock
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.core_snapshot_dto import (
    CoreSnapshotFreshnessMetadata,
    CoreSnapshotGovernanceMetadata,
    CoreSnapshotMode,
    CoreSnapshotRequest,
    CoreSnapshotResponse,
    CoreSnapshotSections,
    CoreSnapshotSimulationMetadata,
    CoreSnapshotValuationContext,
)
from ..dtos.integration_dto import InstrumentEnrichmentRecord
from ..dtos.source_data_product_identity import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.fx_rate_repository import FxRateRepository
from ..repositories.instrument_repository import InstrumentRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.position_repository import PositionRepository
from ..repositories.price_repository import MarketPriceRepository
from ..repositories.simulation_repository import SimulationRepository
from .core_snapshot_baseline_metadata import baseline_freshness_metadata
from .core_snapshot_baseline_positions import baseline_position_entries
from .core_snapshot_calculations import (
    assign_baseline_weights,
    total_market_value_baseline,
    total_market_value_projected,
)
from .core_snapshot_errors import (
    CoreSnapshotBadRequestError as CoreSnapshotBadRequestError,
)
from .core_snapshot_errors import (
    CoreSnapshotConflictError as CoreSnapshotConflictError,
)
from .core_snapshot_errors import (
    CoreSnapshotNotFoundError as CoreSnapshotNotFoundError,
)
from .core_snapshot_errors import (
    CoreSnapshotUnavailableSectionError as CoreSnapshotUnavailableSectionError,
)
from .core_snapshot_governance import (
    CoreSnapshotGovernanceResolution,
    SnapshotGovernanceContext,
    resolve_core_snapshot_governance,
)
from .core_snapshot_identity import core_snapshot_request_fingerprint
from .core_snapshot_instrument_enrichment_reader import CoreSnapshotInstrumentEnrichmentReader
from .core_snapshot_market_data import get_fx_rate_or_raise
from .core_snapshot_projected_valuation import CoreSnapshotProjectedPositionResolver
from .core_snapshot_quality import snapshot_data_quality_status
from .core_snapshot_sections import build_core_snapshot_sections
from .core_snapshot_simulation_validation import CoreSnapshotSimulationSessionValidator


@dataclass(frozen=True)
class _CoreSnapshotCurrencyContext:
    portfolio_currency: str
    reporting_currency: str
    reporting_fx: Decimal


@dataclass(frozen=True)
class _CoreSnapshotProjection:
    positions: dict[str, dict[str, Any]] | None
    total_market_value: Decimal
    simulation_metadata: CoreSnapshotSimulationMetadata | None


@dataclass(frozen=True)
class _BaselinePositionRows:
    rows: list[Any]
    use_snapshot: bool


@dataclass(frozen=True)
class CoreSnapshotDependencies:
    position_repo: PositionRepository
    portfolio_repo: PortfolioRepository
    simulation_repo: SimulationRepository
    price_repo: MarketPriceRepository
    fx_repo: FxRateRepository
    instrument_repo: InstrumentRepository

    @classmethod
    def from_session(cls, db: AsyncSession) -> "CoreSnapshotDependencies":
        return cls(
            position_repo=PositionRepository(db),
            portfolio_repo=PortfolioRepository(db),
            simulation_repo=SimulationRepository(db),
            price_repo=MarketPriceRepository(db),
            fx_repo=FxRateRepository(db),
            instrument_repo=InstrumentRepository(db),
        )


class CoreSnapshotService:
    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        clock: Clock | None = None,
        dependencies: CoreSnapshotDependencies | None = None,
    ):
        if dependencies is None:
            if db is None:
                raise ValueError("CoreSnapshotService requires db or dependencies")
            dependencies = CoreSnapshotDependencies.from_session(db)
        self.db = db
        self._clock = clock or SystemClock()
        self.position_repo = dependencies.position_repo
        self.portfolio_repo = dependencies.portfolio_repo
        self.simulation_repo = dependencies.simulation_repo
        self.price_repo = dependencies.price_repo
        self.fx_repo = dependencies.fx_repo
        self.instrument_repo = dependencies.instrument_repo
        self.simulation_session_validator = CoreSnapshotSimulationSessionValidator(
            simulation_repo=self.simulation_repo,
        )
        self.instrument_enrichment_reader = CoreSnapshotInstrumentEnrichmentReader(
            instrument_repo=self.instrument_repo,
        )
        self.projected_position_resolver = CoreSnapshotProjectedPositionResolver(
            simulation_repo=self.simulation_repo,
            instrument_repo=self.instrument_repo,
            price_repo=self.price_repo,
            fx_repo=self.fx_repo,
        )

    async def get_core_snapshot(
        self,
        portfolio_id: str,
        request: CoreSnapshotRequest,
        governance: SnapshotGovernanceContext | None = None,
    ) -> CoreSnapshotResponse:
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise CoreSnapshotNotFoundError(f"Portfolio {portfolio_id} not found")

        currency_context = await self._snapshot_currency_context(
            portfolio_base_currency=portfolio.base_currency,
            requested_reporting_currency=request.reporting_currency,
            as_of_date=request.as_of_date,
        )

        baseline_positions, freshness_meta = await self._resolve_baseline_positions(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            reporting_fx=currency_context.reporting_fx,
            include_cash=request.options.include_cash_positions,
            include_zero=request.options.include_zero_quantity_positions,
        )

        baseline_total = total_market_value_baseline(baseline_positions)
        projection = await self._snapshot_projection(
            portfolio_id=portfolio_id,
            request=request,
            portfolio_currency=currency_context.portfolio_currency,
            reporting_fx=currency_context.reporting_fx,
            baseline_positions=baseline_positions,
        )
        projected_positions = projection.positions
        sections_payload = build_core_snapshot_sections(
            requested_sections=request.sections,
            baseline_positions=baseline_positions,
            projected_positions=projected_positions,
            baseline_total=baseline_total,
            projected_total=projection.total_market_value,
        )
        governance_resolution = self._snapshot_governance_resolution(
            request=request,
            governance=governance,
        )
        return self._build_core_snapshot_response(
            portfolio_id=portfolio_id,
            request=request,
            currency_context=currency_context,
            freshness=freshness_meta,
            governance=governance_resolution,
            simulation_metadata=projection.simulation_metadata,
            sections=sections_payload,
            baseline_count=len(baseline_positions),
        )

    async def _snapshot_currency_context(
        self,
        *,
        portfolio_base_currency: str,
        requested_reporting_currency: str | None,
        as_of_date,
    ) -> _CoreSnapshotCurrencyContext:
        portfolio_currency = normalize_currency_code(str(portfolio_base_currency))
        reporting_currency = normalize_currency_code(
            str(requested_reporting_currency or portfolio_base_currency)
        )
        return _CoreSnapshotCurrencyContext(
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            reporting_fx=await get_fx_rate_or_raise(
                fx_repo=self.fx_repo,
                from_currency=portfolio_currency,
                to_currency=reporting_currency,
                as_of_date=as_of_date,
            ),
        )

    async def _snapshot_projection(
        self,
        *,
        portfolio_id: str,
        request: CoreSnapshotRequest,
        portfolio_currency: str,
        reporting_fx: Decimal,
        baseline_positions: dict[str, dict[str, Any]],
    ) -> _CoreSnapshotProjection:
        if request.snapshot_mode != CoreSnapshotMode.SIMULATION:
            self.simulation_session_validator.validate_baseline_snapshot_sections(request.sections)
            return _CoreSnapshotProjection(None, Decimal(0), None)

        session = await self.simulation_session_validator.validated_session(
            portfolio_id=portfolio_id,
            request=request,
        )
        projected_positions = await self.projected_position_resolver.resolve_projected_positions(
            session_id=session.session_id,
            as_of_date=request.as_of_date,
            portfolio_base_currency=portfolio_currency,
            portfolio_to_reporting_fx=reporting_fx,
            baseline_positions=baseline_positions,
            include_zero=request.options.include_zero_quantity_positions,
            include_cash=request.options.include_cash_positions,
        )
        return _CoreSnapshotProjection(
            positions=projected_positions,
            total_market_value=total_market_value_projected(projected_positions),
            simulation_metadata=CoreSnapshotSimulationMetadata(
                session_id=session.session_id,
                version=session.version,
                baseline_as_of_date=request.as_of_date,
            ),
        )

    @staticmethod
    def _snapshot_governance_resolution(
        *,
        request: CoreSnapshotRequest,
        governance: SnapshotGovernanceContext | None,
    ) -> CoreSnapshotGovernanceResolution:
        return resolve_core_snapshot_governance(
            request=request,
            governance=governance,
        )

    def _build_core_snapshot_response(
        self,
        *,
        portfolio_id: str,
        request: CoreSnapshotRequest,
        currency_context: _CoreSnapshotCurrencyContext,
        freshness: CoreSnapshotFreshnessMetadata,
        governance: CoreSnapshotGovernanceResolution,
        simulation_metadata: CoreSnapshotSimulationMetadata | None,
        sections: CoreSnapshotSections,
        baseline_count: int,
    ) -> CoreSnapshotResponse:
        generated_at = self._clock.utc_now()
        request_fingerprint_value = core_snapshot_request_fingerprint(
            portfolio_id=portfolio_id,
            request=request,
            governance=governance,
        )
        content_hash = stable_content_hash(
            {
                "product_name": "PortfolioStateSnapshot",
                "product_version": "v1",
                "portfolio_id": portfolio_id,
                "as_of_date": request.as_of_date,
                "snapshot_mode": request.snapshot_mode.value,
                "request_fingerprint": request_fingerprint_value,
                "freshness": freshness.model_dump(mode="json"),
                "governance": {
                    "consumer_system": governance.consumer_system,
                    "tenant_id": governance.tenant_id,
                    "requested_sections": [
                        section.value for section in governance.requested_sections
                    ],
                    "applied_sections": [section.value for section in governance.applied_sections],
                    "dropped_sections": [section.value for section in governance.dropped_sections],
                    "policy_provenance": governance.policy_provenance.model_dump(mode="json"),
                    "warnings": governance.warnings,
                },
                "valuation_context": {
                    "portfolio_currency": currency_context.portfolio_currency,
                    "reporting_currency": currency_context.reporting_currency,
                    "position_basis": request.options.position_basis.value,
                    "weight_basis": request.options.weight_basis.value,
                },
                "simulation": (
                    simulation_metadata.model_dump(mode="json")
                    if simulation_metadata is not None
                    else None
                ),
                "sections": sections.model_dump(mode="json"),
            }
        )
        source_ref = (
            "lotus-core://source/PortfolioStateSnapshot/"
            f"{portfolio_id}/{request.as_of_date.isoformat()}"
        )
        return CoreSnapshotResponse(
            portfolio_id=portfolio_id,
            snapshot_mode=request.snapshot_mode,
            contract_version="rfc_081_v1",
            request_fingerprint=request_fingerprint_value,
            freshness=freshness,
            governance=CoreSnapshotGovernanceMetadata(
                consumer_system=governance.consumer_system,
                tenant_id=governance.tenant_id,
                requested_sections=governance.requested_sections,
                applied_sections=governance.applied_sections,
                dropped_sections=governance.dropped_sections,
                policy_provenance=governance.policy_provenance,
                warnings=governance.warnings,
            ),
            valuation_context=CoreSnapshotValuationContext(
                portfolio_currency=currency_context.portfolio_currency,
                reporting_currency=currency_context.reporting_currency,
                position_basis=request.options.position_basis,
                weight_basis=request.options.weight_basis,
            ),
            simulation=simulation_metadata,
            sections=sections,
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=generated_at,
                tenant_id=governance.tenant_id,
                data_quality_status=snapshot_data_quality_status(
                    freshness=freshness,
                    baseline_count=baseline_count,
                ),
                latest_evidence_timestamp=freshness.snapshot_timestamp,
                policy_version=governance.policy_provenance.policy_version,
                content_hash=content_hash,
                source_refs=[source_ref],
                lineage={
                    "source_owner": "lotus-core",
                    "source_product": "PortfolioStateSnapshot",
                    "request_fingerprint": request_fingerprint_value,
                },
                use_content_hash_as_source_batch_fingerprint=True,
            ),
        )

    async def _resolve_baseline_positions(
        self,
        portfolio_id: str,
        as_of_date,
        reporting_fx: Decimal,
        include_cash: bool,
        include_zero: bool,
    ) -> tuple[dict[str, dict[str, Any]], CoreSnapshotFreshnessMetadata]:
        baseline_rows = await self._baseline_position_rows(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
        )
        baseline = baseline_position_entries(
            rows=baseline_rows.rows,
            use_snapshot=baseline_rows.use_snapshot,
            reporting_fx=reporting_fx,
            include_cash=include_cash,
            include_zero=include_zero,
        )
        total_base = total_market_value_baseline(baseline)
        assign_baseline_weights(baseline, total_base)
        return baseline, baseline_freshness_metadata(
            rows=baseline_rows.rows,
            use_snapshot=baseline_rows.use_snapshot,
            has_baseline=bool(baseline),
        )

    async def _baseline_position_rows(
        self,
        *,
        portfolio_id: str,
        as_of_date,
    ) -> _BaselinePositionRows:
        rows = await self.position_repo.get_latest_positions_by_portfolio_as_of_date(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
        )
        if rows:
            return _BaselinePositionRows(rows=rows, use_snapshot=True)
        history_rows = await self.position_repo.get_latest_position_history_by_portfolio_as_of_date(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
        )
        return _BaselinePositionRows(rows=history_rows, use_snapshot=False)

    async def get_instrument_enrichment_bulk(
        self, security_ids: list[str]
    ) -> list[InstrumentEnrichmentRecord]:
        return await self.instrument_enrichment_reader.get_instrument_enrichment_bulk(security_ids)
