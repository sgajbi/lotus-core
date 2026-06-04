from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import Depends
from portfolio_common.db import get_async_db_session
from portfolio_common.reconciliation_quality import COMPLETE, PARTIAL, UNKNOWN
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.core_snapshot_dto import (
    CoreSnapshotDeltaRecord,
    CoreSnapshotFreshnessMetadata,
    CoreSnapshotGovernanceMetadata,
    CoreSnapshotInstrumentEnrichmentRecord,
    CoreSnapshotMode,
    CoreSnapshotPolicyProvenance,
    CoreSnapshotPortfolioTotals,
    CoreSnapshotPositionRecord,
    CoreSnapshotRequest,
    CoreSnapshotResponse,
    CoreSnapshotSection,
    CoreSnapshotSections,
    CoreSnapshotSimulationMetadata,
    CoreSnapshotValuationContext,
)
from ..dtos.integration_dto import InstrumentEnrichmentRecord
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.fx_rate_repository import FxRateRepository
from ..repositories.identifier_normalization import normalize_security_id
from ..repositories.instrument_repository import InstrumentRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.position_repository import PositionRepository
from ..repositories.price_repository import MarketPriceRepository
from ..repositories.simulation_repository import SimulationRepository
from .control_code_normalization import normalize_control_code
from .decimal_amounts import decimal_or_none, decimal_or_zero
from .position_flow_effects import transaction_quantity_effect_decimal
from .request_fingerprint import request_fingerprint

CASH_ASSET_CLASS = "CASH"


class CoreSnapshotBadRequestError(ValueError):
    pass


class CoreSnapshotNotFoundError(ValueError):
    pass


class CoreSnapshotConflictError(ValueError):
    pass


class CoreSnapshotUnavailableSectionError(ValueError):
    pass


def _is_cash_asset_class(value: Any) -> bool:
    return normalize_control_code(value) == CASH_ASSET_CLASS


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


class CoreSnapshotService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.position_repo = PositionRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.simulation_repo = SimulationRepository(db)
        self.price_repo = MarketPriceRepository(db)
        self.fx_repo = FxRateRepository(db)
        self.instrument_repo = InstrumentRepository(db)

    @staticmethod
    def _request_fingerprint(payload: dict[str, Any]) -> str:
        return request_fingerprint(payload)

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
        if (
            freshness_status == "CURRENT_SNAPSHOT"
            and freshness.snapshot_timestamp is not None
            and freshness.snapshot_epoch is not None
        ):
            return COMPLETE
        return PARTIAL

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

        baseline_total = self._total_market_value_baseline(baseline_positions)
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
            total_market_value=self._total_market_value_projected(projected_positions),
            simulation_metadata=CoreSnapshotSimulationMetadata(
                session_id=session.session_id,
                version=session.version,
                baseline_as_of_date=request.as_of_date,
            ),
        )

    async def _validated_simulation_session(self, portfolio_id: str, request: CoreSnapshotRequest):
        session_opts = request.simulation
        if session_opts is None:
            raise CoreSnapshotBadRequestError(
                "simulation options are required when snapshot_mode=SIMULATION"
            )
        session = await self.simulation_repo.get_session(session_opts.session_id)
        if session is None:
            raise CoreSnapshotNotFoundError(
                f"Simulation session {session_opts.session_id} not found"
            )
        if session.portfolio_id != portfolio_id:
            raise CoreSnapshotConflictError(
                "Simulation session does not belong to requested portfolio"
            )
        if (
            session_opts.expected_version is not None
            and session.version != session_opts.expected_version
        ):
            raise CoreSnapshotConflictError("Simulation expected_version mismatch")
        return session

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
        self._assign_projected_weights(projected_positions, projected_total)
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
        sections_payload.positions_delta = self._build_delta_section(
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
        generated_at = datetime.now(UTC)
        return CoreSnapshotResponse(
            portfolio_id=portfolio_id,
            snapshot_mode=request.snapshot_mode,
            contract_version="rfc_081_v1",
            request_fingerprint=self._core_snapshot_request_fingerprint(
                portfolio_id=portfolio_id,
                request=request,
                governance=governance,
            ),
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
                "request": request.model_dump(mode="json"),
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
        baseline: dict[str, dict[str, Any]] = {}
        for row, instrument, _state in baseline_rows.rows:
            entry = self._baseline_position_entry(
                row=row,
                instrument=instrument,
                use_snapshot=baseline_rows.use_snapshot,
                reporting_fx=reporting_fx,
                include_cash=include_cash,
                include_zero=include_zero,
            )
            if entry is None:
                continue
            baseline[entry["security_id"]] = entry

        total_base = self._total_market_value_baseline(baseline)
        self._assign_baseline_weights(baseline, total_base)
        return dict(sorted(baseline.items(), key=lambda item: item[0])), self._baseline_freshness(
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

    def _baseline_position_entry(
        self,
        *,
        row: Any,
        instrument: Any,
        use_snapshot: bool,
        reporting_fx: Decimal,
        include_cash: bool,
        include_zero: bool,
    ) -> dict[str, Any] | None:
        quantity = decimal_or_zero(row.quantity)
        if self._skip_baseline_position(
            quantity=quantity,
            instrument=instrument,
            include_cash=include_cash,
            include_zero=include_zero,
        ):
            return None
        security_id = normalize_security_id(row.security_id)
        if not security_id:
            return None
        market_value_base, market_value_local = self._baseline_market_values(
            row=row,
            use_snapshot=use_snapshot,
            reporting_fx=reporting_fx,
        )
        return self._baseline_position_payload(
            security_id=security_id,
            quantity=quantity,
            market_value_base=market_value_base,
            market_value_local=market_value_local,
            instrument=instrument,
        )

    @staticmethod
    def _skip_baseline_position(
        *,
        quantity: Decimal,
        instrument: Any,
        include_cash: bool,
        include_zero: bool,
    ) -> bool:
        if not include_zero and quantity == Decimal(0):
            return True
        return (
            not include_cash
            and instrument is not None
            and _is_cash_asset_class(instrument.asset_class)
        )

    @staticmethod
    def _baseline_market_values(
        *,
        row: Any,
        use_snapshot: bool,
        reporting_fx: Decimal,
    ) -> tuple[Decimal | None, Decimal | None]:
        if use_snapshot:
            market_value_base_raw = decimal_or_none(row.market_value)
            market_value_local = decimal_or_none(row.market_value_local)
        else:
            market_value_base_raw = decimal_or_none(row.cost_basis)
            market_value_local = decimal_or_none(row.cost_basis_local)
        market_value_base = (
            market_value_base_raw * reporting_fx if market_value_base_raw is not None else None
        )
        return market_value_base, market_value_local

    @staticmethod
    def _baseline_position_payload(
        *,
        security_id: str,
        quantity: Decimal,
        market_value_base: Decimal | None,
        market_value_local: Decimal | None,
        instrument: Any,
    ) -> dict[str, Any]:
        payload = {
            "security_id": security_id,
            "quantity": quantity,
            "market_value_base": market_value_base,
            "market_value_local": market_value_local,
        }
        if instrument is None:
            payload.update(CoreSnapshotService._missing_instrument_payload(security_id))
        else:
            payload.update(CoreSnapshotService._baseline_instrument_payload(instrument))
        return payload

    @staticmethod
    def _missing_instrument_payload(security_id: str) -> dict[str, Any]:
        return {
            "currency": None,
            "instrument_name": security_id,
            "asset_class": None,
            "sector": None,
            "country_of_risk": None,
            "isin": None,
            "issuer_id": None,
            "issuer_name": None,
            "ultimate_parent_issuer_id": None,
            "ultimate_parent_issuer_name": None,
            "liquidity_tier": None,
        }

    @staticmethod
    def _baseline_instrument_payload(instrument: Any) -> dict[str, Any]:
        return {
            "currency": instrument.currency,
            "instrument_name": instrument.name,
            "asset_class": instrument.asset_class,
            "sector": instrument.sector,
            "country_of_risk": instrument.country_of_risk,
            "isin": instrument.isin,
            "issuer_id": instrument.issuer_id,
            "issuer_name": instrument.issuer_name,
            "ultimate_parent_issuer_id": instrument.ultimate_parent_issuer_id,
            "ultimate_parent_issuer_name": instrument.ultimate_parent_issuer_name,
            "liquidity_tier": instrument.liquidity_tier,
        }

    def _baseline_freshness(
        self,
        *,
        rows: list[Any],
        use_snapshot: bool,
        has_baseline: bool,
    ) -> CoreSnapshotFreshnessMetadata:
        if not use_snapshot:
            return CoreSnapshotFreshnessMetadata(
                freshness_status="HISTORICAL_FALLBACK",
                baseline_source="position_history",
                snapshot_timestamp=None,
                snapshot_epoch=None,
                fallback_reason="NO_CURRENT_POSITION_STATE_ROWS",
            )
        return CoreSnapshotFreshnessMetadata(
            freshness_status="CURRENT_SNAPSHOT",
            baseline_source="position_state",
            snapshot_timestamp=self._latest_snapshot_timestamp(rows),
            snapshot_epoch=self._baseline_snapshot_epoch(rows=rows, has_baseline=has_baseline),
            fallback_reason=None,
        )

    def _baseline_snapshot_epoch(
        self,
        *,
        rows: list[Any],
        has_baseline: bool,
    ) -> int | None:
        if not has_baseline:
            return None
        return self._single_resolved_epoch(rows)

    @staticmethod
    def _latest_snapshot_timestamp(rows: list[Any]) -> datetime | None:
        timestamps: list[datetime] = []
        for row, _instrument, state in rows:
            for candidate in (
                getattr(row, "updated_at", None),
                getattr(row, "created_at", None),
                getattr(state, "updated_at", None),
                getattr(state, "created_at", None),
            ):
                if isinstance(candidate, datetime):
                    timestamps.append(candidate)
        return max(timestamps) if timestamps else None

    @staticmethod
    def _single_resolved_epoch(rows: list[Any]) -> int | None:
        epochs = {
            int(state.epoch)
            for _row, _instrument, state in rows
            if getattr(state, "epoch", None) is not None
        }
        return next(iter(epochs)) if len(epochs) == 1 else None

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
        projected: dict[str, dict[str, Any]] = {
            key: self._baseline_projected_position(value)
            for key, value in baseline_positions.items()
        }

        normalized_changes = await self._normalized_simulation_changes(session_id)
        await self._seed_missing_projected_instruments(projected, normalized_changes)
        self._apply_projected_position_changes(projected, normalized_changes)
        await self._value_projected_positions(
            projected=projected,
            as_of_date=as_of_date,
            portfolio_base_currency=portfolio_base_currency,
            portfolio_to_reporting_fx=portfolio_to_reporting_fx,
            include_cash=include_cash,
            include_zero=include_zero,
        )
        filtered = self._filtered_projected_positions(
            projected,
            include_cash=include_cash,
            include_zero=include_zero,
        )

        return dict(sorted(filtered.items(), key=lambda item: item[0]))

    @staticmethod
    def _baseline_projected_position(value: dict[str, Any]) -> dict[str, Any]:
        projected_value = dict(value)
        projected_value["baseline_quantity"] = projected_value["quantity"]
        return projected_value

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
        missing_security_ids = self._missing_projected_security_ids(projected, normalized_changes)
        if not missing_security_ids:
            return
        instrument_map = await self._projected_instrument_map(missing_security_ids)
        for security_id in missing_security_ids:
            projected[security_id] = self._new_projected_position(
                security_id,
                self._required_projected_instrument(security_id, instrument_map),
            )

    @staticmethod
    def _missing_projected_security_ids(
        projected: dict[str, dict[str, Any]],
        normalized_changes: list[tuple[str, Any]],
    ) -> list[str]:
        changed_security_ids = {security_id for security_id, _change in normalized_changes}
        return [sid for sid in changed_security_ids if sid not in projected]

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

    @staticmethod
    def _new_projected_position(security_id: str, instrument: Any) -> dict[str, Any]:
        return {
            "security_id": security_id,
            "quantity": Decimal(0),
            "baseline_quantity": Decimal(0),
            "market_value_base": Decimal(0),
            "market_value_local": Decimal(0),
            "currency": instrument.currency,
            "instrument_name": instrument.name,
            "asset_class": instrument.asset_class,
            "sector": instrument.sector,
            "country_of_risk": instrument.country_of_risk,
            "isin": instrument.isin,
            "issuer_id": instrument.issuer_id,
            "issuer_name": instrument.issuer_name,
            "ultimate_parent_issuer_id": instrument.ultimate_parent_issuer_id,
            "ultimate_parent_issuer_name": instrument.ultimate_parent_issuer_name,
            "liquidity_tier": instrument.liquidity_tier,
        }

    def _apply_projected_position_changes(
        self,
        projected: dict[str, dict[str, Any]],
        normalized_changes: list[tuple[str, Any]],
    ) -> None:
        for security_id, change in normalized_changes:
            entry = projected[security_id]
            entry["quantity"] = entry["quantity"] + self._change_quantity_effect(change)

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
        price_required = self._apply_baseline_projected_values(
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

    def _apply_baseline_projected_values(
        self,
        projected: dict[str, dict[str, Any]],
        *,
        include_cash: bool,
        include_zero: bool,
    ) -> dict[str, tuple[dict[str, Any], Decimal]]:
        price_required: dict[str, tuple[dict[str, Any], Decimal]] = {}
        for security_id, entry in projected.items():
            if self._skip_projected_position(
                entry, include_cash=include_cash, include_zero=include_zero
            ):
                continue
            if self._apply_baseline_projected_value(entry):
                continue
            quantity = entry["quantity"]
            if quantity <= 0:
                entry["market_value_base"] = Decimal(0)
                entry["market_value_local"] = Decimal(0)
                continue
            price_required[security_id] = (entry, quantity)
        return price_required

    @staticmethod
    def _apply_baseline_projected_value(entry: dict[str, Any]) -> bool:
        baseline_qty = entry["baseline_quantity"]
        if baseline_qty <= 0 or entry.get("market_value_base") is None:
            return False
        unit_base = entry["market_value_base"] / baseline_qty
        entry["market_value_base"] = unit_base * entry["quantity"]
        if entry.get("market_value_local") is not None:
            unit_local = entry["market_value_local"] / baseline_qty
            entry["market_value_local"] = unit_local * entry["quantity"]
        return True

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

    def _filtered_projected_positions(
        self,
        projected: dict[str, dict[str, Any]],
        *,
        include_cash: bool,
        include_zero: bool,
    ) -> dict[str, dict[str, Any]]:
        return {
            key: value
            for key, value in projected.items()
            if not self._skip_projected_position(
                value,
                include_cash=include_cash,
                include_zero=include_zero,
            )
        }

    @staticmethod
    def _skip_projected_position(
        entry: dict[str, Any],
        *,
        include_cash: bool,
        include_zero: bool,
    ) -> bool:
        if not include_cash and _is_cash_asset_class(entry.get("asset_class")):
            return True
        return not include_zero and entry["quantity"] == Decimal(0)

    @staticmethod
    def _change_quantity_effect(change) -> Decimal:
        effect = transaction_quantity_effect_decimal(
            transaction_type=getattr(change, "transaction_type", None),
            quantity=getattr(change, "quantity", None),
            amount=getattr(change, "amount", None),
        )
        return effect

    async def get_instrument_enrichment_bulk(
        self, security_ids: list[str]
    ) -> list[InstrumentEnrichmentRecord]:
        requested_ids = self._requested_instrument_security_ids(security_ids)
        by_security_id = await self._instrument_enrichment_map(requested_ids)
        return [
            self._instrument_enrichment_record(
                security_id=security_id,
                instrument=by_security_id.get(security_id),
            )
            for security_id in requested_ids
        ]

    @staticmethod
    def _requested_instrument_security_ids(security_ids: list[str]) -> list[str]:
        requested_ids = [value.strip() for value in security_ids if value and value.strip()]
        if not requested_ids:
            raise CoreSnapshotBadRequestError("security_ids must contain at least one identifier")
        return requested_ids

    async def _instrument_enrichment_map(self, security_ids: list[str]) -> dict[str, Any]:
        instruments = await self.instrument_repo.get_by_security_ids(security_ids)
        return {
            security_id: item
            for item in instruments
            if (security_id := normalize_security_id(item.security_id))
        }

    @staticmethod
    def _instrument_enrichment_record(
        *,
        security_id: str,
        instrument: Any,
    ) -> InstrumentEnrichmentRecord:
        if instrument is None:
            return InstrumentEnrichmentRecord(security_id=security_id)
        return InstrumentEnrichmentRecord(
            security_id=security_id,
            issuer_id=instrument.issuer_id,
            issuer_name=instrument.issuer_name,
            ultimate_parent_issuer_id=instrument.ultimate_parent_issuer_id,
            ultimate_parent_issuer_name=instrument.ultimate_parent_issuer_name,
            liquidity_tier=instrument.liquidity_tier,
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

    @staticmethod
    def _total_market_value_baseline(items: dict[str, dict[str, Any]]) -> Decimal:
        total = Decimal(0)
        for item in items.values():
            market_value = decimal_or_none(item.get("market_value_base"))
            if market_value is not None:
                total += market_value
        return total

    @staticmethod
    def _total_market_value_projected(items: dict[str, dict[str, Any]]) -> Decimal:
        total = Decimal(0)
        for item in items.values():
            total += decimal_or_zero(item.get("market_value_base"))
        return total

    @staticmethod
    def _assign_baseline_weights(items: dict[str, dict[str, Any]], total: Decimal) -> None:
        for item in items.values():
            if total > 0 and item["market_value_base"] is not None:
                weight = item["market_value_base"] / total
            else:
                weight = Decimal(0)
            item["position_record"] = CoreSnapshotPositionRecord(
                security_id=item["security_id"],
                quantity=item["quantity"],
                market_value_base=item["market_value_base"],
                market_value_local=item["market_value_local"],
                weight=weight,
                currency=item["currency"],
            )

    @staticmethod
    def _assign_projected_weights(items: dict[str, dict[str, Any]], total: Decimal) -> None:
        for item in items.values():
            weight = (item["market_value_base"] / total) if total > 0 else Decimal(0)
            item["position_record"] = CoreSnapshotPositionRecord(
                security_id=item["security_id"],
                quantity=item["quantity"],
                market_value_base=item["market_value_base"],
                market_value_local=item["market_value_local"],
                weight=weight,
                currency=item["currency"],
            )

    @staticmethod
    def _build_delta_section(
        baseline_positions: dict[str, dict[str, Any]],
        projected_positions: dict[str, dict[str, Any]],
        baseline_total: Decimal,
        projected_total: Decimal,
    ) -> list[CoreSnapshotDeltaRecord]:
        all_ids = sorted(set(baseline_positions.keys()) | set(projected_positions.keys()))
        rows: list[CoreSnapshotDeltaRecord] = []
        for security_id in all_ids:
            baseline = baseline_positions.get(security_id)
            projected = projected_positions.get(security_id)
            baseline_qty = baseline["quantity"] if baseline else Decimal(0)
            projected_qty = projected["quantity"] if projected else Decimal(0)
            baseline_mv = baseline["market_value_base"] if baseline else Decimal(0)
            projected_mv = projected["market_value_base"] if projected else Decimal(0)
            baseline_weight = (
                (baseline_mv / baseline_total)
                if baseline_total > 0 and baseline is not None
                else Decimal(0)
            )
            projected_weight = (
                (projected_mv / projected_total)
                if projected_total > 0 and projected is not None
                else Decimal(0)
            )
            rows.append(
                CoreSnapshotDeltaRecord(
                    security_id=security_id,
                    baseline_quantity=baseline_qty,
                    projected_quantity=projected_qty,
                    delta_quantity=projected_qty - baseline_qty,
                    baseline_market_value_base=baseline_mv,
                    projected_market_value_base=projected_mv,
                    delta_market_value_base=projected_mv - baseline_mv,
                    delta_weight=projected_weight - baseline_weight,
                )
            )
        return rows


def get_core_snapshot_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CoreSnapshotService:
    return CoreSnapshotService(db)
