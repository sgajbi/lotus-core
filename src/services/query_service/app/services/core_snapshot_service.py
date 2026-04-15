from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import md5
from typing import Any

from fastapi import Depends
from portfolio_common.db import get_async_db_session
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
from ..repositories.fx_rate_repository import FxRateRepository
from ..repositories.instrument_repository import InstrumentRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.position_repository import PositionRepository
from ..repositories.price_repository import MarketPriceRepository
from ..repositories.simulation_repository import SimulationRepository
from .position_flow_effects import transaction_quantity_effect_decimal


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
        return md5(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    async def get_core_snapshot(
        self,
        portfolio_id: str,
        request: CoreSnapshotRequest,
        governance: SnapshotGovernanceContext | None = None,
    ) -> CoreSnapshotResponse:
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise CoreSnapshotNotFoundError(f"Portfolio {portfolio_id} not found")

        reporting_currency = request.reporting_currency or portfolio.base_currency
        reporting_fx = await self._get_fx_rate_or_raise(
            from_currency=portfolio.base_currency,
            to_currency=reporting_currency,
            as_of_date=request.as_of_date,
        )

        baseline_positions, freshness_meta = await self._resolve_baseline_positions(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            reporting_fx=reporting_fx,
            include_cash=request.options.include_cash_positions,
            include_zero=request.options.include_zero_quantity_positions,
        )

        sections_payload = CoreSnapshotSections()
        simulation_metadata: CoreSnapshotSimulationMetadata | None = None

        if CoreSnapshotSection.POSITIONS_BASELINE in request.sections:
            sections_payload.positions_baseline = [
                item["position_record"] for item in baseline_positions.values()
            ]

        projected_positions: dict[str, dict[str, Any]] | None = None
        projected_total = Decimal(0)
        baseline_total = self._total_market_value_baseline(baseline_positions)

        if request.snapshot_mode == CoreSnapshotMode.SIMULATION:
            session_opts = request.simulation
            assert session_opts is not None
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

            simulation_metadata = CoreSnapshotSimulationMetadata(
                session_id=session.session_id,
                version=session.version,
                baseline_as_of_date=request.as_of_date,
            )
            projected_positions = await self._resolve_projected_positions(
                session_id=session.session_id,
                as_of_date=request.as_of_date,
                portfolio_base_currency=portfolio.base_currency,
                reporting_currency=reporting_currency,
                baseline_positions=baseline_positions,
                include_zero=request.options.include_zero_quantity_positions,
                include_cash=request.options.include_cash_positions,
            )
            projected_total = self._total_market_value_projected(projected_positions)
        else:
            if (
                CoreSnapshotSection.POSITIONS_PROJECTED in request.sections
                or CoreSnapshotSection.POSITIONS_DELTA in request.sections
            ):
                raise CoreSnapshotBadRequestError(
                    "Projected and delta sections require snapshot_mode=SIMULATION"
                )

        if CoreSnapshotSection.POSITIONS_PROJECTED in request.sections:
            if projected_positions is None:
                raise CoreSnapshotUnavailableSectionError("positions_projected unavailable")
            self._assign_projected_weights(projected_positions, projected_total)
            sections_payload.positions_projected = [
                item["position_record"] for item in projected_positions.values()
            ]

        if CoreSnapshotSection.POSITIONS_DELTA in request.sections:
            if projected_positions is None:
                raise CoreSnapshotUnavailableSectionError("positions_delta unavailable")
            sections_payload.positions_delta = self._build_delta_section(
                baseline_positions=baseline_positions,
                projected_positions=projected_positions,
                baseline_total=baseline_total,
                projected_total=projected_total,
            )

        if CoreSnapshotSection.PORTFOLIO_TOTALS in request.sections:
            sections_payload.portfolio_totals = CoreSnapshotPortfolioTotals(
                baseline_total_market_value_base=baseline_total,
                projected_total_market_value_base=(
                    projected_total if projected_positions is not None else None
                ),
                delta_total_market_value_base=(
                    projected_total - baseline_total if projected_positions is not None else None
                ),
            )

        if CoreSnapshotSection.INSTRUMENT_ENRICHMENT in request.sections:
            sections_payload.instrument_enrichment = [
                CoreSnapshotInstrumentEnrichmentRecord(
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
                for item in baseline_positions.values()
            ]

        requested_sections = (
            governance.requested_sections if governance is not None else list(request.sections)
        )
        applied_sections = (
            governance.applied_sections if governance is not None else list(request.sections)
        )
        dropped_sections = governance.dropped_sections if governance is not None else []
        policy_provenance = CoreSnapshotPolicyProvenance(
            policy_version=(
                governance.policy_version
                if governance is not None
                else "snapshot.policy.inline.default"
            ),
            policy_source=(
                governance.policy_source if governance is not None else "snapshot.inline.default"
            ),
            matched_rule_id=(
                governance.matched_rule_id if governance is not None else "snapshot.default"
            ),
            strict_mode=governance.strict_mode if governance is not None else False,
        )
        warnings = governance.warnings if governance is not None else []
        request_fingerprint = self._request_fingerprint(
            {
                "portfolio_id": portfolio_id,
                "request": request.model_dump(mode="json"),
                "governance": {
                    "consumer_system": (
                        governance.consumer_system
                        if governance is not None
                        else request.consumer_system
                    ),
                    "tenant_id": (
                        governance.tenant_id if governance is not None else request.tenant_id
                    ),
                    "requested_sections": [section.value for section in requested_sections],
                    "applied_sections": [section.value for section in applied_sections],
                    "dropped_sections": [section.value for section in dropped_sections],
                    "policy_version": policy_provenance.policy_version,
                    "policy_source": policy_provenance.policy_source,
                    "matched_rule_id": policy_provenance.matched_rule_id,
                    "strict_mode": policy_provenance.strict_mode,
                    "warnings": warnings,
                },
            }
        )

        generated_at = datetime.now(UTC)
        resolved_tenant_id = governance.tenant_id if governance is not None else request.tenant_id

        return CoreSnapshotResponse(
            portfolio_id=portfolio_id,
            snapshot_mode=request.snapshot_mode,
            contract_version="rfc_081_v1",
            request_fingerprint=request_fingerprint,
            freshness=freshness_meta,
            governance=CoreSnapshotGovernanceMetadata(
                consumer_system=(
                    governance.consumer_system
                    if governance is not None
                    else request.consumer_system
                ),
                tenant_id=governance.tenant_id if governance is not None else request.tenant_id,
                requested_sections=requested_sections,
                applied_sections=applied_sections,
                dropped_sections=dropped_sections,
                policy_provenance=policy_provenance,
                warnings=warnings,
            ),
            valuation_context=CoreSnapshotValuationContext(
                portfolio_currency=portfolio.base_currency,
                reporting_currency=reporting_currency,
                position_basis=request.options.position_basis,
                weight_basis=request.options.weight_basis,
            ),
            simulation=simulation_metadata,
            sections=sections_payload,
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                generated_at=generated_at,
                tenant_id=resolved_tenant_id,
                policy_version=policy_provenance.policy_version,
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
        rows = await self.position_repo.get_latest_positions_by_portfolio_as_of_date(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
        )
        use_snapshot = True
        if not rows:
            rows = await self.position_repo.get_latest_position_history_by_portfolio_as_of_date(
                portfolio_id=portfolio_id,
                as_of_date=as_of_date,
            )
            use_snapshot = False

        baseline: dict[str, dict[str, Any]] = {}
        for row, instrument, _state in rows:
            quantity = Decimal(str(row.quantity))
            if not include_zero and quantity == Decimal(0):
                continue
            if (
                not include_cash
                and instrument
                and str(instrument.asset_class or "").upper() == "CASH"
            ):
                continue

            if use_snapshot:
                market_value_base_raw = (
                    Decimal(str(row.market_value)) if row.market_value is not None else None
                )
                market_value_local = (
                    Decimal(str(row.market_value_local))
                    if row.market_value_local is not None
                    else None
                )
            else:
                market_value_base_raw = (
                    Decimal(str(row.cost_basis)) if row.cost_basis is not None else None
                )
                market_value_local = (
                    Decimal(str(row.cost_basis_local)) if row.cost_basis_local is not None else None
                )

            market_value_base = (
                market_value_base_raw * reporting_fx if market_value_base_raw is not None else None
            )

            baseline[row.security_id] = {
                "security_id": row.security_id,
                "quantity": quantity,
                "market_value_base": market_value_base,
                "market_value_local": market_value_local,
                "currency": instrument.currency if instrument else None,
                "instrument_name": instrument.name if instrument else row.security_id,
                "asset_class": instrument.asset_class if instrument else None,
                "sector": instrument.sector if instrument else None,
                "country_of_risk": instrument.country_of_risk if instrument else None,
                "isin": instrument.isin if instrument else None,
                "issuer_id": instrument.issuer_id if instrument else None,
                "issuer_name": instrument.issuer_name if instrument else None,
                "ultimate_parent_issuer_id": (
                    instrument.ultimate_parent_issuer_id if instrument else None
                ),
                "ultimate_parent_issuer_name": (
                    instrument.ultimate_parent_issuer_name if instrument else None
                ),
                "liquidity_tier": instrument.liquidity_tier if instrument else None,
            }

        total_base = self._total_market_value_baseline(baseline)
        self._assign_baseline_weights(baseline, total_base)
        source = "position_state" if use_snapshot else "position_history"
        freshness = CoreSnapshotFreshnessMetadata(
            freshness_status=("CURRENT_SNAPSHOT" if use_snapshot else "HISTORICAL_FALLBACK"),
            baseline_source=source,
            snapshot_timestamp=None,
            snapshot_epoch=None,
            fallback_reason=(None if use_snapshot else "NO_CURRENT_POSITION_STATE_ROWS"),
        )
        return dict(sorted(baseline.items(), key=lambda item: item[0])), freshness

    async def _resolve_projected_positions(
        self,
        session_id: str,
        as_of_date,
        portfolio_base_currency: str,
        reporting_currency: str,
        baseline_positions: dict[str, dict[str, Any]],
        include_zero: bool,
        include_cash: bool,
    ) -> dict[str, dict[str, Any]]:
        projected: dict[str, dict[str, Any]] = {
            key: dict(value) for key, value in baseline_positions.items()
        }
        for value in projected.values():
            value["baseline_quantity"] = value["quantity"]

        changes = await self.simulation_repo.get_changes(session_id)
        changed_security_ids = {change.security_id for change in changes}
        missing_security_ids = [sid for sid in changed_security_ids if sid not in projected]
        if missing_security_ids:
            instruments = await self.instrument_repo.get_by_security_ids(missing_security_ids)
            instrument_map = {item.security_id: item for item in instruments}
            for security_id in missing_security_ids:
                instrument = instrument_map.get(security_id)
                if instrument is None:
                    raise CoreSnapshotUnavailableSectionError(
                        f"positions_projected unavailable: missing instrument {security_id}"
                    )
                projected[security_id] = {
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

        for change in changes:
            entry = projected[change.security_id]
            delta = self._change_quantity_effect(change)
            entry["quantity"] = entry["quantity"] + delta

        for security_id, entry in projected.items():
            if not include_cash and str(entry.get("asset_class") or "").upper() == "CASH":
                continue
            if not include_zero and entry["quantity"] == Decimal(0):
                continue
            baseline_qty = entry["baseline_quantity"]
            if baseline_qty > 0 and entry.get("market_value_base") is not None:
                unit_base = entry["market_value_base"] / baseline_qty
                entry["market_value_base"] = unit_base * entry["quantity"]
                if entry.get("market_value_local") is not None:
                    unit_local = entry["market_value_local"] / baseline_qty
                    entry["market_value_local"] = unit_local * entry["quantity"]
                continue

            quantity = entry["quantity"]
            if quantity <= 0:
                entry["market_value_base"] = Decimal(0)
                entry["market_value_local"] = Decimal(0)
                continue

            prices = await self.price_repo.get_prices(
                security_id=security_id,
                end_date=as_of_date,
            )
            if not prices:
                raise CoreSnapshotUnavailableSectionError(
                    f"positions_projected unavailable: missing market price for {security_id}"
                )
            latest_price = prices[-1]
            local_value = Decimal(str(latest_price.price)) * quantity
            market_currency = latest_price.currency
            fx_to_portfolio = await self._get_fx_rate_or_raise(
                from_currency=market_currency,
                to_currency=portfolio_base_currency,
                as_of_date=as_of_date,
            )
            portfolio_value = local_value * fx_to_portfolio
            fx_to_reporting = await self._get_fx_rate_or_raise(
                from_currency=portfolio_base_currency,
                to_currency=reporting_currency,
                as_of_date=as_of_date,
            )
            entry["market_value_local"] = local_value
            entry["market_value_base"] = portfolio_value * fx_to_reporting

        filtered: dict[str, dict[str, Any]] = {}
        for key, value in projected.items():
            if not include_cash and str(value.get("asset_class") or "").upper() == "CASH":
                continue
            if not include_zero and value["quantity"] == Decimal(0):
                continue
            filtered[key] = value

        return dict(sorted(filtered.items(), key=lambda item: item[0]))

    @staticmethod
    def _change_quantity_effect(change) -> Decimal:
        effect = transaction_quantity_effect_decimal(
            transaction_type=getattr(change, "transaction_type", None),
            quantity=getattr(change, "quantity", None),
            amount=getattr(change, "amount", None),
        )
        return Decimal(str(effect))

    async def get_instrument_enrichment_bulk(
        self, security_ids: list[str]
    ) -> list[InstrumentEnrichmentRecord]:
        requested_ids = [value.strip() for value in security_ids if value and value.strip()]
        if not requested_ids:
            raise CoreSnapshotBadRequestError("security_ids must contain at least one value")

        instruments = await self.instrument_repo.get_by_security_ids(requested_ids)
        by_security_id = {item.security_id: item for item in instruments}

        records: list[InstrumentEnrichmentRecord] = []
        for security_id in requested_ids:
            instrument = by_security_id.get(security_id)
            records.append(
                InstrumentEnrichmentRecord(
                    security_id=security_id,
                    issuer_id=(instrument.issuer_id if instrument else None),
                    issuer_name=(instrument.issuer_name if instrument else None),
                    ultimate_parent_issuer_id=(
                        instrument.ultimate_parent_issuer_id if instrument else None
                    ),
                    ultimate_parent_issuer_name=(
                        instrument.ultimate_parent_issuer_name if instrument else None
                    ),
                    liquidity_tier=(instrument.liquidity_tier if instrument else None),
                )
            )
        return records

    async def _get_fx_rate_or_raise(
        self, from_currency: str, to_currency: str, as_of_date
    ) -> Decimal:
        if from_currency == to_currency:
            return Decimal(1)
        rates = await self.fx_repo.get_fx_rates(
            from_currency=from_currency,
            to_currency=to_currency,
            end_date=as_of_date,
        )
        if not rates:
            pair = f"{from_currency}/{to_currency}"
            raise CoreSnapshotUnavailableSectionError(
                f"missing FX rate {pair} on or before {as_of_date.isoformat()}"
            )
        return Decimal(str(rates[-1].rate))

    @staticmethod
    def _total_market_value_baseline(items: dict[str, dict[str, Any]]) -> Decimal:
        total = Decimal(0)
        for item in items.values():
            market_value = item.get("market_value_base")
            if market_value is not None:
                total += Decimal(str(market_value))
        return total

    @staticmethod
    def _total_market_value_projected(items: dict[str, dict[str, Any]]) -> Decimal:
        total = Decimal(0)
        for item in items.values():
            total += Decimal(str(item.get("market_value_base") or Decimal(0)))
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
