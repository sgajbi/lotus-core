"""Assemble governed portfolio snapshots from source and simulation ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from portfolio_common.currency_codes import normalize_currency_code
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ...contracts.core_snapshot import (
    CoreSnapshotFreshnessMetadata,
    CoreSnapshotGovernanceMetadata,
    CoreSnapshotMode,
    CoreSnapshotRequest,
    CoreSnapshotResponse,
    CoreSnapshotSections,
    CoreSnapshotSimulationMetadata,
    CoreSnapshotValuationContext,
)
from ...contracts.instrument_enrichment import InstrumentEnrichmentRecord
from ...domain.core_snapshot import CoreSnapshotPositionSource
from ...ports.core_snapshot import CoreSnapshotSourceReader
from ...ports.simulation import SimulationStore
from .baseline_metadata import baseline_freshness_metadata
from .baseline_positions import baseline_position_entries
from .calculations import (
    assign_baseline_weights,
    total_market_value_baseline,
    total_market_value_projected,
)
from .errors import (
    CoreSnapshotBadRequestError as CoreSnapshotBadRequestError,
)
from .errors import (
    CoreSnapshotConflictError as CoreSnapshotConflictError,
)
from .errors import (
    CoreSnapshotNotFoundError as CoreSnapshotNotFoundError,
)
from .errors import (
    CoreSnapshotUnavailableSectionError as CoreSnapshotUnavailableSectionError,
)
from .governance import (
    CoreSnapshotGovernanceResolution,
    SnapshotGovernanceContext,
    resolve_core_snapshot_governance,
)
from .identity import core_snapshot_request_fingerprint
from .instrument_enrichment_reader import CoreSnapshotInstrumentEnrichmentReader
from .market_data import get_fx_rate_or_raise
from .projected_valuation import CoreSnapshotProjectedPositionResolver
from .quality import snapshot_data_quality_status
from .sections import build_core_snapshot_sections
from .simulation_validation import CoreSnapshotSimulationSessionValidator


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
    rows: list[CoreSnapshotPositionSource]
    use_snapshot: bool


@dataclass(frozen=True)
class CoreSnapshotDependencies:
    source_reader: CoreSnapshotSourceReader
    simulation_store: SimulationStore
    clock: Clock


class CoreSnapshotService:
    def __init__(
        self,
        dependencies: CoreSnapshotDependencies,
    ) -> None:
        self._source_reader = dependencies.source_reader
        self._simulation_store = dependencies.simulation_store
        self._clock = dependencies.clock
        self.simulation_session_validator = CoreSnapshotSimulationSessionValidator(
            simulation_store=self._simulation_store,
        )
        self.instrument_enrichment_reader = CoreSnapshotInstrumentEnrichmentReader(
            source_reader=self._source_reader,
        )
        self.projected_position_resolver = CoreSnapshotProjectedPositionResolver(
            simulation_store=self._simulation_store,
            source_reader=self._source_reader,
        )

    async def get_core_snapshot(
        self,
        portfolio_id: str,
        request: CoreSnapshotRequest,
        governance: SnapshotGovernanceContext | None = None,
    ) -> CoreSnapshotResponse:
        portfolio = await self._source_reader.get_portfolio(portfolio_id)
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
        as_of_date: date,
    ) -> _CoreSnapshotCurrencyContext:
        portfolio_currency = normalize_currency_code(str(portfolio_base_currency))
        reporting_currency = normalize_currency_code(
            str(requested_reporting_currency or portfolio_base_currency)
        )
        return _CoreSnapshotCurrencyContext(
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            reporting_fx=await get_fx_rate_or_raise(
                source_reader=self._source_reader,
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
        as_of_date: date,
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
        as_of_date: date,
    ) -> _BaselinePositionRows:
        rows = await self._source_reader.get_position_snapshot(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
        )
        if rows:
            return _BaselinePositionRows(rows=rows, use_snapshot=True)
        history_rows = await self._source_reader.get_position_history(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
        )
        return _BaselinePositionRows(rows=history_rows, use_snapshot=False)

    async def get_instrument_enrichment_bulk(
        self, security_ids: list[str]
    ) -> list[InstrumentEnrichmentRecord]:
        return await self.instrument_enrichment_reader.get_instrument_enrichment_bulk(security_ids)
