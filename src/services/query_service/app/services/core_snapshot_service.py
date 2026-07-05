from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fastapi import Depends
from portfolio_common.db import get_async_db_session
from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN
from portfolio_common.runtime_providers import Clock, SystemClock
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.core_snapshot import (
    CoreSnapshotIdentityCommand,
    CoreSnapshotOptionsCommand,
    CoreSnapshotSimulationCommand,
)
from ..dtos.core_snapshot_dto import (
    CoreSnapshotFreshnessMetadata,
    CoreSnapshotGovernanceMetadata,
    CoreSnapshotInstrumentEnrichmentRecord,
    CoreSnapshotMode,
    CoreSnapshotPolicyProvenance,
    CoreSnapshotPortfolioTotals,
    CoreSnapshotRequest,
    CoreSnapshotResponse,
    CoreSnapshotSection,
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
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.instrument_repository import InstrumentRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.position_repository import PositionRepository
from ..repositories.price_repository import MarketPriceRepository
from ..repositories.simulation_repository import SimulationRepository
from .core_snapshot_baseline_metadata import baseline_freshness_metadata
from .core_snapshot_baseline_positions import baseline_position_entries
from .core_snapshot_calculations import (
    assign_baseline_weights,
    assign_projected_weights,
    build_delta_section,
    total_market_value_baseline,
    total_market_value_projected,
)
from .core_snapshot_instrument_enrichment import (
    instrument_enrichment_records,
    requested_instrument_security_ids,
)
from .core_snapshot_projected_positions import (
    apply_baseline_projected_values,
    apply_projected_position_changes,
    baseline_projected_positions,
    filtered_projected_positions,
    missing_projected_security_ids,
    new_projected_position,
)
from .decimal_amounts import decimal_or_none
from .request_fingerprint import request_fingerprint


class CoreSnapshotBadRequestError(ValueError):
    pass


class CoreSnapshotNotFoundError(ValueError):
    pass


class CoreSnapshotConflictError(ValueError):
    pass


class CoreSnapshotUnavailableSectionError(ValueError):
    pass


@dataclass
class SnapshotGovernanceContext:
    consumer_system: str
    tenant_id: str
    requested_sections: list[CoreSnapshotSection]
    applied_sections: list[CoreSnapshotSection]
    dropped_sections: list[CoreSnapshotSection]
    policy_version: str
    policy_source: str
    matched_rule_id: str
    strict_mode: bool
    warnings: list[str]


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
class _CoreSnapshotGovernanceResolution:
    requested_sections: list[CoreSnapshotSection]
    applied_sections: list[CoreSnapshotSection]
    dropped_sections: list[CoreSnapshotSection]
    policy_provenance: CoreSnapshotPolicyProvenance
    warnings: list[str]
    consumer_system: str
    tenant_id: str


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

    @staticmethod
    def _request_fingerprint(payload: dict[str, Any]) -> str:
        return request_fingerprint(payload)

    @staticmethod
    def _identity_command_from_request(
        request: CoreSnapshotRequest,
    ) -> CoreSnapshotIdentityCommand:
        return CoreSnapshotIdentityCommand(
            as_of_date=request.as_of_date,
            snapshot_mode=request.snapshot_mode.value,
            reporting_currency=request.reporting_currency,
            consumer_system=request.consumer_system,
            tenant_id=request.tenant_id,
            sections=[section.value for section in request.sections],
            simulation=(
                CoreSnapshotSimulationCommand(
                    session_id=request.simulation.session_id,
                    expected_version=request.simulation.expected_version,
                )
                if request.simulation is not None
                else None
            ),
            options=CoreSnapshotOptionsCommand(
                include_zero_quantity_positions=(request.options.include_zero_quantity_positions),
                include_cash_positions=request.options.include_cash_positions,
                position_basis=request.options.position_basis.value,
                weight_basis=request.options.weight_basis.value,
            ),
        )

    @staticmethod
    def _normalize_freshness_status(status: str | None) -> str | None:
        if status is None:
            return None
        normalized_status = status.strip().upper()
        return normalized_status or None

    @staticmethod
    def _snapshot_data_quality_status(
        *,
        freshness: CoreSnapshotFreshnessMetadata,
        baseline_count: int,
    ) -> str:
        if baseline_count <= 0:
            return UNKNOWN
        freshness_status = CoreSnapshotService._normalize_freshness_status(
            freshness.freshness_status
        )
        if freshness_status == "HISTORICAL_FALLBACK":
            return PARTIAL
        if CoreSnapshotService._is_complete_current_snapshot(
            freshness=freshness,
            freshness_status=freshness_status,
        ):
            return COMPLETE
        return PARTIAL

    @staticmethod
    def _is_complete_current_snapshot(
        *,
        freshness: CoreSnapshotFreshnessMetadata,
        freshness_status: str | None,
    ) -> bool:
        return (
            freshness_status == "CURRENT_SNAPSHOT"
            and freshness.snapshot_timestamp is not None
            and freshness.snapshot_epoch is not None
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

        sections_payload = CoreSnapshotSections()

        if CoreSnapshotSection.POSITIONS_BASELINE in request.sections:
            sections_payload.positions_baseline = [
                item["position_record"] for item in baseline_positions.values()
            ]
        if CoreSnapshotSection.PORTFOLIO_STATE in request.sections:
            sections_payload.portfolio_state = [
                item["position_record"] for item in baseline_positions.values()
            ]

        baseline_total = total_market_value_baseline(baseline_positions)
        projection = await self._snapshot_projection(
            portfolio_id=portfolio_id,
            request=request,
            portfolio_currency=currency_context.portfolio_currency,
            reporting_fx=currency_context.reporting_fx,
            baseline_positions=baseline_positions,
        )
        projected_positions = projection.positions

        self._populate_requested_snapshot_sections(
            sections_payload=sections_payload,
            request=request,
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
            reporting_fx=await self._get_fx_rate_or_raise(
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
            self._validate_baseline_snapshot_sections(request.sections)
            return _CoreSnapshotProjection(None, Decimal(0), None)

        session = await self._validated_simulation_session(portfolio_id, request)
        projected_positions = await self._resolve_projected_positions(
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

    async def _validated_simulation_session(self, portfolio_id: str, request: CoreSnapshotRequest):
        session_opts = self._required_simulation_options(request)
        session = await self._required_simulation_session(session_opts.session_id)
        self._validate_simulation_portfolio(session=session, portfolio_id=portfolio_id)
        self._validate_simulation_version(
            session=session,
            expected_version=session_opts.expected_version,
        )
        return session

    @staticmethod
    def _required_simulation_options(request: CoreSnapshotRequest):
        session_opts = request.simulation
        if session_opts is None:
            raise CoreSnapshotBadRequestError(
                "simulation options are required when snapshot_mode=SIMULATION"
            )
        return session_opts

    async def _required_simulation_session(self, session_id: str):
        session = await self.simulation_repo.get_session(session_id)
        if session is None:
            raise CoreSnapshotNotFoundError(f"Simulation session {session_id} not found")
        return session

    @staticmethod
    def _validate_simulation_portfolio(*, session: Any, portfolio_id: str) -> None:
        if session.portfolio_id != portfolio_id:
            raise CoreSnapshotConflictError(
                "Simulation session does not belong to requested portfolio"
            )

    @staticmethod
    def _validate_simulation_version(*, session: Any, expected_version: int | None) -> None:
        if expected_version is not None and session.version != expected_version:
            raise CoreSnapshotConflictError("Simulation expected_version mismatch")

    @staticmethod
    def _validate_baseline_snapshot_sections(sections: list[CoreSnapshotSection]) -> None:
        if (
            CoreSnapshotSection.POSITIONS_PROJECTED in sections
            or CoreSnapshotSection.POSITIONS_DELTA in sections
        ):
            raise CoreSnapshotBadRequestError(
                "Projected and delta sections require snapshot_mode=SIMULATION"
            )

    def _populate_requested_snapshot_sections(
        self,
        *,
        sections_payload: CoreSnapshotSections,
        request: CoreSnapshotRequest,
        baseline_positions: dict[str, dict[str, Any]],
        projected_positions: dict[str, dict[str, Any]] | None,
        baseline_total: Decimal,
        projected_total: Decimal,
    ) -> None:
        self._populate_projected_positions_section(
            sections_payload=sections_payload,
            requested_sections=request.sections,
            projected_positions=projected_positions,
            projected_total=projected_total,
        )
        self._populate_delta_section(
            sections_payload=sections_payload,
            requested_sections=request.sections,
            baseline_positions=baseline_positions,
            projected_positions=projected_positions,
            baseline_total=baseline_total,
            projected_total=projected_total,
        )
        self._populate_portfolio_totals_section(
            sections_payload=sections_payload,
            requested_sections=request.sections,
            baseline_total=baseline_total,
            projected_positions=projected_positions,
            projected_total=projected_total,
        )
        self._populate_instrument_enrichment_section(
            sections_payload=sections_payload,
            requested_sections=request.sections,
            baseline_positions=baseline_positions,
        )

    def _populate_projected_positions_section(
        self,
        *,
        sections_payload: CoreSnapshotSections,
        requested_sections: list[CoreSnapshotSection],
        projected_positions: dict[str, dict[str, Any]] | None,
        projected_total: Decimal,
    ) -> None:
        if CoreSnapshotSection.POSITIONS_PROJECTED not in requested_sections:
            return
        if projected_positions is None:
            raise CoreSnapshotUnavailableSectionError("positions_projected unavailable")
        assign_projected_weights(projected_positions, projected_total)
        sections_payload.positions_projected = [
            item["position_record"] for item in projected_positions.values()
        ]

    def _populate_delta_section(
        self,
        *,
        sections_payload: CoreSnapshotSections,
        requested_sections: list[CoreSnapshotSection],
        baseline_positions: dict[str, dict[str, Any]],
        projected_positions: dict[str, dict[str, Any]] | None,
        baseline_total: Decimal,
        projected_total: Decimal,
    ) -> None:
        if CoreSnapshotSection.POSITIONS_DELTA not in requested_sections:
            return
        if projected_positions is None:
            raise CoreSnapshotUnavailableSectionError("positions_delta unavailable")
        sections_payload.positions_delta = build_delta_section(
            baseline_positions=baseline_positions,
            projected_positions=projected_positions,
            baseline_total=baseline_total,
            projected_total=projected_total,
        )

    @staticmethod
    def _populate_portfolio_totals_section(
        *,
        sections_payload: CoreSnapshotSections,
        requested_sections: list[CoreSnapshotSection],
        baseline_total: Decimal,
        projected_positions: dict[str, dict[str, Any]] | None,
        projected_total: Decimal,
    ) -> None:
        if CoreSnapshotSection.PORTFOLIO_TOTALS not in requested_sections:
            return
        sections_payload.portfolio_totals = CoreSnapshotPortfolioTotals(
            baseline_total_market_value_base=baseline_total,
            projected_total_market_value_base=(
                projected_total if projected_positions is not None else None
            ),
            delta_total_market_value_base=(
                projected_total - baseline_total if projected_positions is not None else None
            ),
        )

    def _populate_instrument_enrichment_section(
        self,
        *,
        sections_payload: CoreSnapshotSections,
        requested_sections: list[CoreSnapshotSection],
        baseline_positions: dict[str, dict[str, Any]],
    ) -> None:
        if CoreSnapshotSection.INSTRUMENT_ENRICHMENT not in requested_sections:
            return
        sections_payload.instrument_enrichment = [
            self._core_snapshot_instrument_enrichment(item) for item in baseline_positions.values()
        ]

    @staticmethod
    def _core_snapshot_instrument_enrichment(
        item: dict[str, Any],
    ) -> CoreSnapshotInstrumentEnrichmentRecord:
        return CoreSnapshotInstrumentEnrichmentRecord(
            security_id=item["security_id"],
            isin=item["isin"],
            asset_class=item["asset_class"],
            sector=item["sector"],
            country_of_risk=item["country_of_risk"],
            instrument_name=item["instrument_name"],
            issuer_id=item["issuer_id"],
            issuer_name=item["issuer_name"],
            ultimate_parent_issuer_id=item["ultimate_parent_issuer_id"],
            ultimate_parent_issuer_name=item["ultimate_parent_issuer_name"],
            liquidity_tier=item["liquidity_tier"],
        )

    @staticmethod
    def _snapshot_governance_resolution(
        *,
        request: CoreSnapshotRequest,
        governance: SnapshotGovernanceContext | None,
    ) -> _CoreSnapshotGovernanceResolution:
        if governance is not None:
            return _CoreSnapshotGovernanceResolution(
                requested_sections=governance.requested_sections,
                applied_sections=governance.applied_sections,
                dropped_sections=governance.dropped_sections,
                policy_provenance=CoreSnapshotPolicyProvenance(
                    policy_version=governance.policy_version,
                    policy_source=governance.policy_source,
                    matched_rule_id=governance.matched_rule_id,
                    strict_mode=governance.strict_mode,
                ),
                warnings=governance.warnings,
                consumer_system=governance.consumer_system,
                tenant_id=governance.tenant_id,
            )
        return _CoreSnapshotGovernanceResolution(
            requested_sections=list(request.sections),
            applied_sections=list(request.sections),
            dropped_sections=[],
            policy_provenance=CoreSnapshotPolicyProvenance(
                policy_version="snapshot.policy.inline.default",
                policy_source="snapshot.inline.default",
                matched_rule_id="snapshot.default",
                strict_mode=False,
            ),
            warnings=[],
            consumer_system=request.consumer_system,
            tenant_id=request.tenant_id,
        )

    def _build_core_snapshot_response(
        self,
        *,
        portfolio_id: str,
        request: CoreSnapshotRequest,
        currency_context: _CoreSnapshotCurrencyContext,
        freshness: CoreSnapshotFreshnessMetadata,
        governance: _CoreSnapshotGovernanceResolution,
        simulation_metadata: CoreSnapshotSimulationMetadata | None,
        sections: CoreSnapshotSections,
        baseline_count: int,
    ) -> CoreSnapshotResponse:
        generated_at = self._clock.utc_now()
        request_fingerprint_value = self._core_snapshot_request_fingerprint(
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
                data_quality_status=self._snapshot_data_quality_status(
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

    def _core_snapshot_request_fingerprint(
        self,
        *,
        portfolio_id: str,
        request: CoreSnapshotRequest,
        governance: _CoreSnapshotGovernanceResolution,
    ) -> str:
        return self._request_fingerprint(
            {
                "portfolio_id": portfolio_id,
                "request": self._identity_command_from_request(request).canonical_payload(),
                "governance": {
                    "consumer_system": governance.consumer_system,
                    "tenant_id": governance.tenant_id,
                    "requested_sections": [
                        section.value for section in governance.requested_sections
                    ],
                    "applied_sections": [section.value for section in governance.applied_sections],
                    "dropped_sections": [section.value for section in governance.dropped_sections],
                    "policy_version": governance.policy_provenance.policy_version,
                    "policy_source": governance.policy_provenance.policy_source,
                    "matched_rule_id": governance.policy_provenance.matched_rule_id,
                    "strict_mode": governance.policy_provenance.strict_mode,
                    "warnings": governance.warnings,
                },
            }
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

    async def _resolve_projected_positions(
        self,
        session_id: str,
        as_of_date,
        portfolio_base_currency: str,
        portfolio_to_reporting_fx: Decimal,
        baseline_positions: dict[str, dict[str, Any]],
        include_zero: bool,
        include_cash: bool,
    ) -> dict[str, dict[str, Any]]:
        projected = baseline_projected_positions(baseline_positions)

        normalized_changes = await self._normalized_simulation_changes(session_id)
        await self._seed_missing_projected_instruments(projected, normalized_changes)
        apply_projected_position_changes(projected, normalized_changes)
        await self._value_projected_positions(
            projected=projected,
            as_of_date=as_of_date,
            portfolio_base_currency=portfolio_base_currency,
            portfolio_to_reporting_fx=portfolio_to_reporting_fx,
            include_cash=include_cash,
            include_zero=include_zero,
        )
        filtered = filtered_projected_positions(
            projected,
            include_cash=include_cash,
            include_zero=include_zero,
        )

        return dict(sorted(filtered.items(), key=lambda item: item[0]))

    async def _normalized_simulation_changes(self, session_id: str) -> list[tuple[str, Any]]:
        changes = await self.simulation_repo.get_changes(session_id)
        return [self._normalized_simulation_change(change) for change in changes]

    @staticmethod
    def _normalized_simulation_change(change: Any) -> tuple[str, Any]:
        security_id = normalize_security_id(change.security_id)
        if not security_id:
            raise CoreSnapshotUnavailableSectionError(
                "positions_projected unavailable: simulation change missing security_id"
            )
        return security_id, change

    async def _seed_missing_projected_instruments(
        self,
        projected: dict[str, dict[str, Any]],
        normalized_changes: list[tuple[str, Any]],
    ) -> None:
        missing_security_ids = missing_projected_security_ids(projected, normalized_changes)
        if not missing_security_ids:
            return
        instrument_map = await self._projected_instrument_map(missing_security_ids)
        for security_id in missing_security_ids:
            projected[security_id] = new_projected_position(
                security_id,
                self._required_projected_instrument(security_id, instrument_map),
            )

    async def _projected_instrument_map(self, security_ids: list[str]) -> dict[str, Any]:
        instruments = await self.instrument_repo.get_by_security_ids(security_ids)
        return {
            security_id: item
            for item in instruments
            if (security_id := normalize_security_id(item.security_id))
        }

    @staticmethod
    def _required_projected_instrument(
        security_id: str,
        instrument_map: dict[str, Any],
    ) -> Any:
        instrument = instrument_map.get(security_id)
        if instrument is None:
            raise CoreSnapshotUnavailableSectionError(
                f"positions_projected unavailable: missing instrument {security_id}"
            )
        return instrument

    async def _value_projected_positions(
        self,
        *,
        projected: dict[str, dict[str, Any]],
        as_of_date,
        portfolio_base_currency: str,
        portfolio_to_reporting_fx: Decimal,
        include_cash: bool,
        include_zero: bool,
    ) -> None:
        price_required = apply_baseline_projected_values(
            projected,
            include_cash=include_cash,
            include_zero=include_zero,
        )
        if price_required:
            await self._apply_priced_projected_values(
                price_required=price_required,
                projected=projected,
                as_of_date=as_of_date,
                portfolio_base_currency=portfolio_base_currency,
                portfolio_to_reporting_fx=portfolio_to_reporting_fx,
            )

    async def _apply_priced_projected_values(
        self,
        *,
        price_required: dict[str, tuple[dict[str, Any], Decimal]],
        projected: dict[str, dict[str, Any]],
        as_of_date,
        portfolio_base_currency: str,
        portfolio_to_reporting_fx: Decimal,
    ) -> None:
        priced_values = await self._priced_projected_local_values(
            price_required=price_required,
            as_of_date=as_of_date,
        )
        market_to_portfolio_fx = await self._market_to_portfolio_fx_rates(
            market_currencies={
                market_currency for _value, market_currency in priced_values.values()
            },
            portfolio_base_currency=portfolio_base_currency,
            as_of_date=as_of_date,
        )
        for security_id, (local_value, market_currency) in priced_values.items():
            entry = projected[security_id]
            portfolio_value = local_value * market_to_portfolio_fx[market_currency]
            entry["market_value_local"] = local_value
            entry["market_value_base"] = portfolio_value * portfolio_to_reporting_fx

    async def _priced_projected_local_values(
        self,
        *,
        price_required: dict[str, tuple[dict[str, Any], Decimal]],
        as_of_date,
    ) -> dict[str, tuple[Decimal, str]]:
        priced_values: dict[str, tuple[Decimal, str]] = {}
        for security_id, _entry_and_quantity in price_required.items():
            priced_values[security_id] = await self._priced_projected_local_value(
                security_id=security_id,
                quantity=price_required[security_id][1],
                as_of_date=as_of_date,
            )
        return priced_values

    async def _priced_projected_local_value(
        self,
        *,
        security_id: str,
        quantity: Decimal,
        as_of_date,
    ) -> tuple[Decimal, str]:
        prices = await self.price_repo.get_prices(security_id=security_id, end_date=as_of_date)
        if not prices:
            raise CoreSnapshotUnavailableSectionError(
                f"positions_projected unavailable: missing market price for {security_id}"
            )
        latest_price = prices[-1]
        missing_price_message = (
            f"positions_projected unavailable: missing market price for {security_id}"
        )
        local_value = (
            self._required_decimal(
                latest_price.price,
                message=missing_price_message,
            )
            * quantity
        )
        return local_value, normalize_currency_code(str(latest_price.currency))

    async def _market_to_portfolio_fx_rates(
        self,
        *,
        market_currencies: set[str],
        portfolio_base_currency: str,
        as_of_date,
    ) -> dict[str, Decimal]:
        market_to_portfolio_fx = {}
        for market_currency in sorted(market_currencies):
            market_to_portfolio_fx[market_currency] = await self._get_fx_rate_or_raise(
                from_currency=market_currency,
                to_currency=portfolio_base_currency,
                as_of_date=as_of_date,
            )
        return market_to_portfolio_fx

    async def get_instrument_enrichment_bulk(
        self, security_ids: list[str]
    ) -> list[InstrumentEnrichmentRecord]:
        requested_ids = requested_instrument_security_ids(security_ids)
        if not requested_ids:
            raise CoreSnapshotBadRequestError("security_ids must contain at least one identifier")
        instruments = await self.instrument_repo.get_by_security_ids(requested_ids)
        return instrument_enrichment_records(
            requested_ids=requested_ids,
            instruments=instruments,
        )

    async def _get_fx_rate_or_raise(
        self, from_currency: str, to_currency: str, as_of_date
    ) -> Decimal:
        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        if normalized_from_currency == normalized_to_currency:
            return Decimal(1)
        rates = await self.fx_repo.get_fx_rates(
            from_currency=normalized_from_currency,
            to_currency=normalized_to_currency,
            end_date=as_of_date,
        )
        if not rates:
            pair = f"{normalized_from_currency}/{normalized_to_currency}"
            raise CoreSnapshotUnavailableSectionError(
                f"missing FX rate {pair} on or before {as_of_date.isoformat()}"
            )
        pair = f"{normalized_from_currency}/{normalized_to_currency}"
        return self._required_decimal(
            rates[-1].rate,
            message=f"missing FX rate {pair} on or before {as_of_date.isoformat()}",
        )

    @staticmethod
    def _required_decimal(value: Any, *, message: str) -> Decimal:
        resolved_value = decimal_or_none(value)
        if resolved_value is None:
            raise CoreSnapshotUnavailableSectionError(message)
        return resolved_value


def get_core_snapshot_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CoreSnapshotService:
    return CoreSnapshotService(db)
