"""Assemble governed portfolio snapshots from source and simulation ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, cast

from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.reconciliation_quality import (
    COMPLETE,
    PARTIAL,
    STALE,
    reconciliation_bound_data_quality_status,
)
from portfolio_common.reconstruction_identity import (
    CURRENT_RESTATEMENT_VERSION,
    ProductReconstructionScope,
    build_reconstruction_scope_evidence,
)
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
    CoreSnapshotValuationSupportability,
)
from ...contracts.instrument_enrichment import InstrumentEnrichmentRecord
from ...domain.core_snapshot import CoreSnapshotPositionSource
from ...ports.core_snapshot import CoreSnapshotSourceReader
from ...ports.simulation import SimulationStore
from .baseline_metadata import baseline_freshness_metadata
from .baseline_positions import baseline_position_entries
from .calculations import (
    CORE_SNAPSHOT_INTERMEDIATE_PRECISION,
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
from .market_data import MarketDataObservation, ResolvedFxRate, get_fx_rate_or_raise
from .projected_valuation import CoreSnapshotProjectedPositionResolver
from .quality import snapshot_data_quality_status
from .reconciliation import (
    CoreSnapshotReconciliationEvidence,
    core_snapshot_reconciliation_evidence,
    core_snapshot_reconciliation_scopes,
    core_snapshot_source_content_hash,
)
from .sections import build_core_snapshot_sections
from .simulation_validation import CoreSnapshotSimulationSessionValidator
from .source_provenance import resolve_core_snapshot_source_provenance


@dataclass(frozen=True)
class _CoreSnapshotCurrencyContext:
    portfolio_currency: str
    reporting_currency: str
    reporting_fx: ResolvedFxRate


@dataclass(frozen=True)
class _CoreSnapshotProjection:
    positions: dict[str, dict[str, Any]] | None
    total_market_value: Decimal
    simulation_metadata: CoreSnapshotSimulationMetadata | None
    market_data_observations: tuple[MarketDataObservation, ...]


@dataclass(frozen=True)
class _BaselinePositionRows:
    rows: list[CoreSnapshotPositionSource]
    use_snapshot: bool


@dataclass(frozen=True)
class _CoreSnapshotBaseline:
    positions: dict[str, dict[str, Any]]
    freshness: CoreSnapshotFreshnessMetadata
    reconciliation: CoreSnapshotReconciliationEvidence
    source_content_hash: str
    source_rows: tuple[CoreSnapshotPositionSource, ...]
    use_snapshot: bool


@dataclass(frozen=True)
class CoreSnapshotDependencies:
    source_reader: CoreSnapshotSourceReader
    simulation_store: SimulationStore
    clock: Clock


CORE_SNAPSHOT_ALGORITHM_ID = "PORTFOLIO_STATE_SNAPSHOT"
CORE_SNAPSHOT_ALGORITHM_VERSION = 1


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

        baseline = await self._resolve_baseline_positions(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            reporting_fx=currency_context.reporting_fx.value,
            include_cash=request.options.include_cash_positions,
            include_zero=request.options.include_zero_quantity_positions,
        )

        baseline_total = total_market_value_baseline(baseline.positions)
        projection = await self._snapshot_projection(
            portfolio_id=portfolio_id,
            request=request,
            portfolio_currency=currency_context.portfolio_currency,
            reporting_fx=currency_context.reporting_fx.value,
            baseline_positions=baseline.positions,
        )
        projected_positions = projection.positions
        sections_payload = build_core_snapshot_sections(
            requested_sections=request.sections,
            baseline_positions=baseline.positions,
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
            baseline=baseline,
            governance=governance_resolution,
            simulation_metadata=projection.simulation_metadata,
            projected_market_data=projection.market_data_observations,
            sections=sections_payload,
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
            return _CoreSnapshotProjection(None, Decimal(0), None, ())

        session = await self.simulation_session_validator.validated_session(
            portfolio_id=portfolio_id,
            request=request,
        )
        resolution = await self.projected_position_resolver.resolve_projected_positions(
            session_id=session.session_id,
            as_of_date=request.as_of_date,
            portfolio_base_currency=portfolio_currency,
            portfolio_to_reporting_fx=reporting_fx,
            baseline_positions=baseline_positions,
            include_zero=request.options.include_zero_quantity_positions,
            include_cash=request.options.include_cash_positions,
        )
        return _CoreSnapshotProjection(
            positions=resolution.positions,
            total_market_value=total_market_value_projected(resolution.positions),
            simulation_metadata=CoreSnapshotSimulationMetadata(
                session_id=session.session_id,
                version=session.version,
                baseline_as_of_date=request.as_of_date,
            ),
            market_data_observations=resolution.market_data_observations,
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
        baseline: _CoreSnapshotBaseline,
        governance: CoreSnapshotGovernanceResolution,
        simulation_metadata: CoreSnapshotSimulationMetadata | None,
        projected_market_data: tuple[MarketDataObservation, ...],
        sections: CoreSnapshotSections,
    ) -> CoreSnapshotResponse:
        generated_at = self._clock.utc_now()
        request_fingerprint_value = core_snapshot_request_fingerprint(
            portfolio_id=portfolio_id,
            request=request,
            governance=governance,
        )
        source_data_quality_status = snapshot_data_quality_status(
            freshness=baseline.freshness,
            baseline_count=len(baseline.positions),
        )
        data_quality_status = reconciliation_bound_data_quality_status(
            source_data_quality_status=source_data_quality_status,
            reconciliation_status=baseline.reconciliation.status,
        )
        provenance = resolve_core_snapshot_source_provenance(
            portfolio_id=portfolio_id,
            requested_as_of_date=request.as_of_date,
            position_rows=baseline.source_rows,
            use_snapshot=baseline.use_snapshot,
            reporting_fx=currency_context.reporting_fx,
            projected_market_data=projected_market_data,
        )
        source_evidence_current = (
            baseline.reconciliation.status == COMPLETE
            and data_quality_status in {COMPLETE, PARTIAL}
            and baseline.reconciliation.latest_evidence_timestamp is not None
            and provenance.supportability is CoreSnapshotValuationSupportability.READY
        )
        calculation_lineage = build_calculation_lineage(
            algorithm_id=CORE_SNAPSHOT_ALGORITHM_ID,
            algorithm_version=CORE_SNAPSHOT_ALGORITHM_VERSION,
            intermediate_precision=CORE_SNAPSHOT_INTERMEDIATE_PRECISION,
            input_payload={
                "portfolio_id": portfolio_id,
                "tenant_id": governance.tenant_id,
                "as_of_date": request.as_of_date,
                "snapshot_mode": request.snapshot_mode,
                "restatement_version": CURRENT_RESTATEMENT_VERSION,
                "request_fingerprint": request_fingerprint_value,
                "source_content_hash": baseline.source_content_hash,
                "source_provenance": provenance.source_provenance.model_dump(mode="python"),
                "reconciliation_scope_content_hash": (baseline.reconciliation.scope_content_hash),
                "reconciliation_control_content_hash": (
                    baseline.reconciliation.control_content_hash
                ),
                "freshness": baseline.freshness.model_dump(mode="python"),
                "governance_policy": governance.policy_provenance.model_dump(mode="python"),
                "valuation_context": {
                    "portfolio_currency": currency_context.portfolio_currency,
                    "reporting_currency": currency_context.reporting_currency,
                    "position_basis": request.options.position_basis,
                    "weight_basis": request.options.weight_basis,
                    "effective_as_of_date": provenance.effective_as_of_date,
                    "supportability": provenance.supportability,
                    "reason_code": provenance.reason_code,
                },
                "simulation": (
                    simulation_metadata.model_dump(mode="python")
                    if simulation_metadata is not None
                    else None
                ),
            },
            output_payload={
                "sections": sections.model_dump(mode="python"),
                "reconciliation_status": baseline.reconciliation.status,
                "data_quality_status": data_quality_status,
                "source_evidence_current": source_evidence_current,
            },
        )
        content_hash = stable_content_hash(
            {
                "product_name": "PortfolioStateSnapshot",
                "product_version": "v1",
                "portfolio_id": portfolio_id,
                "as_of_date": request.as_of_date,
                "snapshot_mode": request.snapshot_mode.value,
                "restatement_version": CURRENT_RESTATEMENT_VERSION,
                "request_fingerprint": request_fingerprint_value,
                "source_content_hash": baseline.source_content_hash,
                "source_provenance": provenance.source_provenance.model_dump(mode="json"),
                "freshness": baseline.freshness.model_dump(mode="json"),
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
                    "effective_as_of_date": (
                        provenance.effective_as_of_date.isoformat()
                        if provenance.effective_as_of_date is not None
                        else None
                    ),
                    "supportability": provenance.supportability.value,
                    "reason_code": provenance.reason_code.value,
                },
                "simulation": (
                    simulation_metadata.model_dump(mode="json")
                    if simulation_metadata is not None
                    else None
                ),
                "sections": sections.model_dump(mode="json"),
                "reconciliation_status": baseline.reconciliation.status,
                "reconciliation_scope_content_hash": (baseline.reconciliation.scope_content_hash),
                "reconciliation_control_content_hash": (
                    baseline.reconciliation.control_content_hash
                ),
                "calculation_lineage": calculation_lineage.lineage_payload(),
            }
        )
        source_ref = (
            "lotus-core://source/PortfolioStateSnapshot/"
            f"{portfolio_id}/{request.as_of_date.isoformat()}"
        )
        reconstruction_evidence = build_reconstruction_scope_evidence(
            ProductReconstructionScope(
                product="PortfolioStateSnapshot",
                portfolio_id=portfolio_id,
                as_of_date=request.as_of_date,
                source_data_products=(
                    "PortfolioStateSnapshot",
                    "HoldingsAsOf",
                    "ReconciliationEvidenceBundle",
                ),
                restatement_version=CURRENT_RESTATEMENT_VERSION,
                policy_version=governance.policy_provenance.policy_version,
                qualifiers=(
                    ("request_fingerprint", request_fingerprint_value),
                    ("snapshot_mode", request.snapshot_mode.value),
                    ("reporting_currency", currency_context.reporting_currency),
                ),
                material_evidence=(
                    ("source_content_hash", baseline.source_content_hash),
                    (
                        "reconciliation_scope_content_hash",
                        baseline.reconciliation.scope_content_hash,
                    ),
                    (
                        "reconciliation_control_content_hash",
                        baseline.reconciliation.control_content_hash,
                    ),
                    (
                        "calculation_output_content_hash",
                        calculation_lineage.output_content_hash,
                    ),
                    ("response_content_hash", content_hash),
                ),
            )
        )
        return CoreSnapshotResponse(
            portfolio_id=portfolio_id,
            snapshot_mode=request.snapshot_mode,
            contract_version="rfc_081_v1",
            request_fingerprint=request_fingerprint_value,
            freshness=baseline.freshness,
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
                effective_as_of_date=provenance.effective_as_of_date,
                supportability=provenance.supportability,
                reason_code=provenance.reason_code,
            ),
            source_provenance=provenance.source_provenance,
            simulation=simulation_metadata,
            calculation_lineage=calculation_lineage.lineage_payload(),
            sections=sections,
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=generated_at,
                tenant_id=governance.tenant_id,
                reconciliation_status=baseline.reconciliation.status,
                data_quality_status=data_quality_status,
                latest_evidence_timestamp=(baseline.reconciliation.latest_evidence_timestamp),
                snapshot_id=(
                    f"portfolio_state_snapshot:{calculation_lineage.output_content_hash[:24]}"
                ),
                policy_version=governance.policy_provenance.policy_version,
                content_hash=content_hash,
                source_refs=[source_ref],
                lineage={
                    "source_owner": "lotus-core",
                    "source_product": "PortfolioStateSnapshot",
                    "request_fingerprint": request_fingerprint_value,
                    "source_content_hash": baseline.source_content_hash,
                    "portfolio_source_id": provenance.source_provenance.portfolio.source_id,
                    "portfolio_source_hash": provenance.source_provenance.portfolio.source_hash,
                    "portfolio_effective_as_of_date": (
                        provenance.source_provenance.portfolio.as_of.isoformat()
                        if provenance.source_provenance.portfolio.as_of is not None
                        else "UNAVAILABLE"
                    ),
                    "market_data_source_id": provenance.source_provenance.market_data.source_id,
                    "market_data_source_hash": provenance.source_provenance.market_data.source_hash,
                    "market_data_effective_as_of_date": (
                        provenance.source_provenance.market_data.as_of.isoformat()
                        if provenance.source_provenance.market_data.as_of is not None
                        else "UNAVAILABLE"
                    ),
                    "valuation_supportability": provenance.supportability.value,
                    "valuation_reason_code": provenance.reason_code.value,
                    "reconciliation_scope_content_hash": (
                        baseline.reconciliation.scope_content_hash
                    ),
                    "reconciliation_control_content_hash": (
                        baseline.reconciliation.control_content_hash
                    ),
                    "input_content_hash": calculation_lineage.input_content_hash,
                    "calculation_content_hash": calculation_lineage.calculation_content_hash,
                    "output_content_hash": calculation_lineage.output_content_hash,
                    "algorithm_id": calculation_lineage.algorithm_id,
                    "algorithm_version": str(calculation_lineage.algorithm_version),
                    **reconstruction_evidence.lineage(),
                },
                source_evidence_current=source_evidence_current,
                freshness_status=(
                    "CURRENT"
                    if source_evidence_current
                    else "STALE"
                    if (
                        baseline.reconciliation.status == STALE
                        or provenance.source_provenance.portfolio.freshness_status == "STALE"
                        or provenance.source_provenance.market_data.freshness_status == "STALE"
                    )
                    else "UNAVAILABLE"
                ),
            ),
        )

    async def _resolve_baseline_positions(
        self,
        portfolio_id: str,
        as_of_date: date,
        reporting_fx: Decimal,
        include_cash: bool,
        include_zero: bool,
    ) -> _CoreSnapshotBaseline:
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
        scopes = core_snapshot_reconciliation_scopes(baseline_rows.rows)
        controls = await self._source_reader.get_financial_reconciliation_controls(
            portfolio_id=portfolio_id,
            scopes=scopes.items,
        )
        return _CoreSnapshotBaseline(
            positions=baseline,
            freshness=baseline_freshness_metadata(
                rows=baseline_rows.rows,
                use_snapshot=baseline_rows.use_snapshot,
                has_baseline=bool(baseline),
            ),
            reconciliation=core_snapshot_reconciliation_evidence(
                scopes=scopes,
                controls=controls,
            ),
            source_content_hash=core_snapshot_source_content_hash(baseline_rows.rows),
            source_rows=tuple(baseline_rows.rows),
            use_snapshot=baseline_rows.use_snapshot,
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
        return cast(
            list[InstrumentEnrichmentRecord],
            await self.instrument_enrichment_reader.get_instrument_enrichment_bulk(security_ids),
        )
