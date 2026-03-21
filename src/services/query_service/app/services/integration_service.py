import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.integration_dto import EffectiveIntegrationPolicyResponse, PolicyProvenanceMetadata
from ..dtos.reference_integration_dto import (
    BenchmarkAssignmentResponse,
    BenchmarkCatalogResponse,
    BenchmarkCompositionWindowRequest,
    BenchmarkCompositionWindowResponse,
    BenchmarkDefinitionResponse,
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
    BenchmarkReturnSeriesRequest,
    BenchmarkReturnSeriesResponse,
    ClassificationTaxonomyEntry,
    ClassificationTaxonomyResponse,
    ComponentSeriesResponse,
    CoverageResponse,
    IndexCatalogResponse,
    IndexDefinitionResponse,
    IndexPriceSeriesPoint,
    IndexPriceSeriesResponse,
    IndexReturnSeriesPoint,
    IndexReturnSeriesResponse,
    IndexSeriesRequest,
    IntegrationWindow,
    ReferencePageMetadata,
    RiskFreeSeriesPoint,
    RiskFreeSeriesRequest,
    RiskFreeSeriesResponse,
    SeriesPoint,
)
from ..repositories.reference_data_repository import ReferenceDataRepository
from ..settings import load_query_service_settings

logger = logging.getLogger(__name__)

_CONSUMER_CANONICAL_MAP: dict[str, str] = {
    "LOTUS-MANAGE": "lotus-manage",
    "LOTUS-GATEWAY": "lotus-gateway",
    "UI": "UI",
}


@dataclass
class PolicyContext:
    policy_version: str
    policy_source: str
    matched_rule_id: str
    strict_mode: bool
    allowed_sections: list[str] | None
    warnings: list[str]


class IntegrationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._reference_repository = ReferenceDataRepository(db)
        self._page_token_secret = load_query_service_settings().page_token_secret

    @staticmethod
    def _as_decimal(value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def _canonical_consumer_system(value: str | None) -> str:
        raw = (value or "UNKNOWN").strip()
        if not raw:
            return "unknown"
        key = raw.upper()
        return _CONSUMER_CANONICAL_MAP.get(key, raw.lower())

    @staticmethod
    def _request_fingerprint(payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.md5(serialized.encode("utf-8")).hexdigest()  # nosec B324

    def _encode_page_token(self, payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(
            self._page_token_secret.encode("utf-8"),
            serialized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        envelope = {"p": payload, "s": signature}
        return base64.urlsafe_b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")

    def _decode_page_token(self, token: str | None) -> dict[str, Any]:
        if not token:
            return {}
        try:
            decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
            envelope = json.loads(decoded)
            payload = envelope["p"]
            signature = envelope["s"]
            serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            expected = hmac.new(
                self._page_token_secret.encode("utf-8"),
                serialized.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("Invalid page token signature.")
            if not isinstance(payload, dict):
                raise ValueError("Malformed page token payload.")
            return payload
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Malformed page token.") from exc

    @staticmethod
    def _load_policy() -> dict[str, Any]:
        raw = load_query_service_settings().integration_snapshot_policy_json
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON; using defaults.")
            return {}
        if not isinstance(decoded, dict):
            return {}
        return decoded

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        return default

    @staticmethod
    def _normalize_sections(raw: Any) -> list[str] | None:
        if not isinstance(raw, list):
            return None
        normalized: list[str] = []
        for item in raw:
            if isinstance(item, str):
                value = item.strip().upper()
                if value:
                    normalized.append(value)
        return normalized

    @staticmethod
    def _resolve_consumer_sections(
        consumers: dict[str, Any] | None,
        consumer_system: str,
    ) -> tuple[list[str] | None, str | None]:
        if not isinstance(consumers, dict):
            return None, None
        canonical = IntegrationService._canonical_consumer_system(consumer_system)
        for key, value in consumers.items():
            if IntegrationService._canonical_consumer_system(str(key)) == canonical:
                return IntegrationService._normalize_sections(value), str(key)
        return None, None

    def _resolve_policy_context(self, tenant_id: str, consumer_system: str) -> PolicyContext:
        policy = self._load_policy()

        strict_mode = self._coerce_bool(policy.get("strict_mode"), default=False)
        policy_source = "default"
        matched_rule_id = "default"
        warnings: list[str] = []

        allowed_sections, matched_consumer_key = self._resolve_consumer_sections(
            policy.get("consumers"),
            consumer_system,
        )
        if allowed_sections is not None:
            policy_source = "global"
            matched_rule_id = f"global.consumers.{matched_consumer_key}"

        tenants = policy.get("tenants")
        tenant_policy_raw = tenants.get(tenant_id) if isinstance(tenants, dict) else None
        if isinstance(tenant_policy_raw, dict):
            strict_mode = self._coerce_bool(
                tenant_policy_raw.get("strict_mode"), default=strict_mode
            )
            tenant_consumers = tenant_policy_raw.get("consumers")
            tenant_allowed, tenant_match_key = self._resolve_consumer_sections(
                tenant_consumers if isinstance(tenant_consumers, dict) else None,
                consumer_system,
            )
            if tenant_allowed is None:
                tenant_allowed = self._normalize_sections(tenant_policy_raw.get("default_sections"))
            if tenant_allowed is not None:
                allowed_sections = tenant_allowed
                policy_source = "tenant"
                if tenant_match_key is not None:
                    matched_rule_id = f"tenant.{tenant_id}.consumers.{tenant_match_key}"
                else:
                    matched_rule_id = f"tenant.{tenant_id}.default_sections"
            if "strict_mode" in tenant_policy_raw and matched_rule_id == "default":
                policy_source = "tenant"
                matched_rule_id = f"tenant.{tenant_id}.strict_mode"

        if allowed_sections is None:
            warnings.append("NO_ALLOWED_SECTION_RESTRICTION")

        return PolicyContext(
            policy_version=load_query_service_settings().lotus_core_policy_version,
            policy_source=policy_source,
            matched_rule_id=matched_rule_id,
            strict_mode=strict_mode,
            allowed_sections=allowed_sections,
            warnings=warnings,
        )

    def get_effective_policy(
        self,
        consumer_system: str,
        tenant_id: str,
        include_sections: list[str] | None,
    ) -> EffectiveIntegrationPolicyResponse:
        normalized_consumer = self._canonical_consumer_system(consumer_system)
        policy_context = self._resolve_policy_context(
            tenant_id=tenant_id,
            consumer_system=normalized_consumer,
        )

        if include_sections:
            requested = [section.upper() for section in include_sections]
            if policy_context.allowed_sections is None:
                allowed_sections = requested
            else:
                allowed_set = set(policy_context.allowed_sections)
                allowed_sections = [section for section in requested if section in allowed_set]
        elif policy_context.allowed_sections is not None:
            allowed_sections = policy_context.allowed_sections
        else:
            allowed_sections = []

        return EffectiveIntegrationPolicyResponse(
            consumer_system=normalized_consumer,
            tenant_id=tenant_id,
            generated_at=datetime.now(UTC),
            policy_provenance=PolicyProvenanceMetadata(
                policy_version=policy_context.policy_version,
                policy_source=policy_context.policy_source,
                matched_rule_id=policy_context.matched_rule_id,
                strict_mode=policy_context.strict_mode,
            ),
            allowed_sections=allowed_sections,
            warnings=policy_context.warnings,
        )

    async def resolve_benchmark_assignment(
        self, portfolio_id: str, as_of_date: date
    ) -> BenchmarkAssignmentResponse | None:
        row = await self._reference_repository.resolve_benchmark_assignment(
            portfolio_id,
            as_of_date,
        )
        if row is None:
            return None
        return BenchmarkAssignmentResponse(
            portfolio_id=row.portfolio_id,
            benchmark_id=row.benchmark_id,
            as_of_date=as_of_date,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            assignment_source=row.assignment_source,
            assignment_status=row.assignment_status,
            policy_pack_id=row.policy_pack_id,
            source_system=row.source_system,
            assignment_recorded_at=row.assignment_recorded_at,
            assignment_version=int(row.assignment_version),
        )

    async def get_benchmark_definition(
        self, benchmark_id: str, as_of_date: date
    ) -> BenchmarkDefinitionResponse | None:
        row = await self._reference_repository.get_benchmark_definition(benchmark_id, as_of_date)
        if row is None:
            return None
        components = await self._reference_repository.list_benchmark_components(
            benchmark_id,
            as_of_date,
        )
        return BenchmarkDefinitionResponse(
            benchmark_id=row.benchmark_id,
            benchmark_name=row.benchmark_name,
            benchmark_type=row.benchmark_type,
            benchmark_currency=row.benchmark_currency,
            return_convention=row.return_convention,
            benchmark_status=row.benchmark_status,
            benchmark_family=row.benchmark_family,
            benchmark_provider=row.benchmark_provider,
            rebalance_frequency=row.rebalance_frequency,
            classification_set_id=row.classification_set_id,
            classification_labels=dict(row.classification_labels or {}),
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            quality_status=row.quality_status,
            source_timestamp=row.source_timestamp,
            source_vendor=row.source_vendor,
            source_record_id=row.source_record_id,
            components=[
                {
                    "index_id": component.index_id,
                    "composition_weight": self._as_decimal(component.composition_weight),
                    "composition_effective_from": component.composition_effective_from,
                    "composition_effective_to": component.composition_effective_to,
                    "rebalance_event_id": component.rebalance_event_id,
                }
                for component in components
            ],
        )

    async def get_benchmark_composition_window(
        self,
        benchmark_id: str,
        request: BenchmarkCompositionWindowRequest,
    ) -> BenchmarkCompositionWindowResponse | None:
        definitions = (
            await self._reference_repository.list_benchmark_definitions_overlapping_window(
                benchmark_id=benchmark_id,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            )
        )
        if not definitions:
            return None

        benchmark_currencies = {row.benchmark_currency for row in definitions}
        if len(benchmark_currencies) != 1:
            raise ValueError(
                "Benchmark definition currency changed within requested composition window."
            )

        components = await self._reference_repository.list_benchmark_components_overlapping_window(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )

        return BenchmarkCompositionWindowResponse(
            benchmark_id=benchmark_id,
            benchmark_currency=next(iter(benchmark_currencies)),
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            segments=[
                {
                    "index_id": component.index_id,
                    "composition_weight": self._as_decimal(component.composition_weight),
                    "composition_effective_from": component.composition_effective_from,
                    "composition_effective_to": component.composition_effective_to,
                    "rebalance_event_id": component.rebalance_event_id,
                }
                for component in components
            ],
            lineage={
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core-query-service",
                "generated_by": "integration.benchmark_composition_window",
            },
        )

    async def list_benchmark_catalog(
        self,
        as_of_date: date,
        benchmark_type: str | None,
        benchmark_currency: str | None,
        benchmark_status: str | None,
    ) -> BenchmarkCatalogResponse:
        rows = await self._reference_repository.list_benchmark_definitions(
            as_of_date=as_of_date,
            benchmark_type=benchmark_type,
            benchmark_currency=benchmark_currency,
            benchmark_status=benchmark_status,
        )
        components_by_benchmark = (
            await self._reference_repository.list_benchmark_components_for_benchmarks(
                benchmark_ids=[row.benchmark_id for row in rows],
                as_of_date=as_of_date,
            )
        )
        records: list[BenchmarkDefinitionResponse] = []
        for row in rows:
            components = components_by_benchmark.get(row.benchmark_id, [])
            records.append(
                BenchmarkDefinitionResponse(
                    benchmark_id=row.benchmark_id,
                    benchmark_name=row.benchmark_name,
                    benchmark_type=row.benchmark_type,
                    benchmark_currency=row.benchmark_currency,
                    return_convention=row.return_convention,
                    benchmark_status=row.benchmark_status,
                    benchmark_family=row.benchmark_family,
                    benchmark_provider=row.benchmark_provider,
                    rebalance_frequency=row.rebalance_frequency,
                    classification_set_id=row.classification_set_id,
                    classification_labels=dict(row.classification_labels or {}),
                    effective_from=row.effective_from,
                    effective_to=row.effective_to,
                    quality_status=row.quality_status,
                    source_timestamp=row.source_timestamp,
                    source_vendor=row.source_vendor,
                    source_record_id=row.source_record_id,
                    components=[
                        {
                            "index_id": component.index_id,
                            "composition_weight": self._as_decimal(component.composition_weight),
                            "composition_effective_from": component.composition_effective_from,
                            "composition_effective_to": component.composition_effective_to,
                            "rebalance_event_id": component.rebalance_event_id,
                        }
                        for component in components
                    ],
                )
            )
        return BenchmarkCatalogResponse(as_of_date=as_of_date, records=records)

    async def list_index_catalog(
        self,
        as_of_date: date,
        index_currency: str | None,
        index_type: str | None,
        index_status: str | None,
    ) -> IndexCatalogResponse:
        rows = await self._reference_repository.list_index_definitions(
            as_of_date=as_of_date,
            index_currency=index_currency,
            index_type=index_type,
            index_status=index_status,
        )
        return IndexCatalogResponse(
            as_of_date=as_of_date,
            records=[
                IndexDefinitionResponse(
                    index_id=row.index_id,
                    index_name=row.index_name,
                    index_currency=row.index_currency,
                    index_type=row.index_type,
                    index_status=row.index_status,
                    index_provider=row.index_provider,
                    index_market=row.index_market,
                    classification_set_id=row.classification_set_id,
                    classification_labels=dict(row.classification_labels or {}),
                    effective_from=row.effective_from,
                    effective_to=row.effective_to,
                    quality_status=row.quality_status,
                    source_timestamp=row.source_timestamp,
                    source_vendor=row.source_vendor,
                    source_record_id=row.source_record_id,
                )
                for row in rows
            ],
        )

    async def get_benchmark_market_series(
        self,
        benchmark_id: str,
        request: BenchmarkMarketSeriesRequest,
    ) -> BenchmarkMarketSeriesResponse:
        requested_fields = set(request.series_fields)
        definition = await self._reference_repository.get_benchmark_definition(
            benchmark_id, request.as_of_date
        )
        benchmark_currency = (
            definition.benchmark_currency if definition else (request.target_currency or "UNKNOWN")
        )
        components = await self._reference_repository.list_benchmark_components_overlapping_window(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        index_ids = sorted({component.index_id for component in components})
        index_prices = await self._reference_repository.list_index_price_points(
            index_ids=index_ids,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        index_returns = await self._reference_repository.list_index_return_points(
            index_ids=index_ids,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        benchmark_returns = await self._reference_repository.list_benchmark_return_points(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        request_scope_fingerprint = self._request_fingerprint(
            {
                "benchmark_id": benchmark_id,
                "as_of_date": request.as_of_date.isoformat(),
                "window": {
                    "start_date": request.window.start_date.isoformat(),
                    "end_date": request.window.end_date.isoformat(),
                },
                "frequency": request.frequency,
                "target_currency": request.target_currency,
                "series_fields": sorted(request.series_fields),
            }
        )
        page = getattr(request, "page", None)
        page_size = getattr(page, "page_size", 250)
        page_token = getattr(page, "page_token", None)
        cursor = self._decode_page_token(page_token)
        token_scope = cursor.get("scope_fingerprint")
        if token_scope and token_scope != request_scope_fingerprint:
            raise ValueError("Benchmark market series page token does not match request scope.")
        cursor_index_id = cursor.get("last_index_id")

        fx_rates: dict[date, Decimal] = {}
        fx_context_source_currency: str | None = None
        fx_context_target_currency: str | None = None
        normalization_status = "native_component_series_only"
        if request.target_currency:
            fx_context_source_currency = benchmark_currency
            fx_context_target_currency = request.target_currency
            if benchmark_currency != request.target_currency and "fx_rate" in requested_fields:
                fx_rates = await self._reference_repository.get_fx_rates(
                    from_currency=benchmark_currency,
                    to_currency=request.target_currency,
                    start_date=request.window.start_date,
                    end_date=request.window.end_date,
                )
                if fx_rates:
                    normalization_status = (
                        "native_component_series_with_benchmark_to_target_fx_context"
                    )
                else:
                    normalization_status = (
                        "native_component_series_with_missing_benchmark_to_target_fx_context"
                    )
            elif benchmark_currency == request.target_currency:
                normalization_status = (
                    "native_component_series_with_identity_benchmark_to_target_fx_context"
                )
            else:
                normalization_status = "native_component_series_without_fx_context_request"

        prices_by_index_date = {(row.index_id, row.series_date): row for row in index_prices}
        returns_by_index_date = {(row.index_id, row.series_date): row for row in index_returns}
        benchmark_return_by_date = {row.series_date: row for row in benchmark_returns}
        component_segments_by_index: dict[str, list[Any]] = {}
        for row in components:
            component_segments_by_index.setdefault(row.index_id, []).append(row)

        all_dates = sorted(
            {row.series_date for row in index_prices + index_returns + benchmark_returns}
        )
        component_series_all: list[ComponentSeriesResponse] = []
        for index_id in sorted(index_ids):
            points: list[SeriesPoint] = []
            for current_date in all_dates:
                price_row = prices_by_index_date.get((index_id, current_date))
                return_row = returns_by_index_date.get((index_id, current_date))
                benchmark_return_row = benchmark_return_by_date.get(current_date)
                component_weight = None
                for segment in component_segments_by_index.get(index_id, []):
                    if (
                        segment.composition_effective_from <= current_date
                        and (
                            segment.composition_effective_to is None
                            or segment.composition_effective_to >= current_date
                        )
                    ):
                        component_weight = self._as_decimal(segment.composition_weight)
                        break
                quality_status = (
                    (price_row and price_row.quality_status)
                    or (return_row and return_row.quality_status)
                    or (benchmark_return_row and benchmark_return_row.quality_status)
                )
                points.append(
                    SeriesPoint(
                        series_date=current_date,
                        series_currency=(
                            (price_row and price_row.series_currency)
                            or (return_row and return_row.series_currency)
                            or (
                                benchmark_return_row
                                and benchmark_return_row.series_currency
                            )
                        ),
                        index_price=(
                            self._as_decimal(price_row.index_price)
                            if price_row and "index_price" in requested_fields
                            else None
                        ),
                        index_return=(
                            self._as_decimal(return_row.index_return)
                            if return_row and "index_return" in requested_fields
                            else None
                        ),
                        benchmark_return=(
                            self._as_decimal(benchmark_return_row.benchmark_return)
                            if benchmark_return_row and "benchmark_return" in requested_fields
                            else None
                        ),
                        component_weight=(
                            component_weight if "component_weight" in requested_fields else None
                        ),
                        fx_rate=(
                            fx_rates.get(current_date) if "fx_rate" in requested_fields else None
                        ),
                        quality_status=quality_status,
                    )
                )
            component_series_all.append(ComponentSeriesResponse(index_id=index_id, points=points))

        if cursor_index_id:
            component_series_all = [
                series for series in component_series_all if series.index_id > cursor_index_id
            ]

        has_more = len(component_series_all) > page_size
        component_series = component_series_all[:page_size]
        next_page_token: str | None = None
        if has_more and component_series:
            next_page_token = self._encode_page_token(
                {
                    "scope_fingerprint": request_scope_fingerprint,
                    "last_index_id": component_series[-1].index_id,
                }
            )

        quality_status_summary: dict[str, int] = {}
        for component in component_series:
            for point in component.points:
                if point.quality_status:
                    quality_status_summary[point.quality_status] = (
                        quality_status_summary.get(point.quality_status, 0) + 1
                    )

        return BenchmarkMarketSeriesResponse(
            benchmark_id=benchmark_id,
            as_of_date=request.as_of_date,
            benchmark_currency=benchmark_currency,
            target_currency=request.target_currency,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            component_series=component_series,
            quality_status_summary=quality_status_summary,
            fx_context_source_currency=fx_context_source_currency,
            fx_context_target_currency=fx_context_target_currency,
            normalization_policy="native_component_series_downstream_normalization_required",
            normalization_status=normalization_status,
            request_fingerprint=request_scope_fingerprint,
            page=ReferencePageMetadata(
                page_size=page_size,
                sort_key="index_id:asc",
                returned_component_count=len(component_series),
                request_scope_fingerprint=request_scope_fingerprint,
                next_page_token=next_page_token,
            ),
            lineage={
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core-query-service",
                "generated_by": "integration.market_series",
            },
        )

    async def get_index_price_series(
        self, index_id: str, request: IndexSeriesRequest
    ) -> IndexPriceSeriesResponse:
        rows = await self._reference_repository.list_index_price_series(
            index_id=index_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return IndexPriceSeriesResponse(
            index_id=index_id,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            points=[
                IndexPriceSeriesPoint(
                    series_date=row.series_date,
                    index_price=self._as_decimal(row.index_price),
                    series_currency=row.series_currency,
                    value_convention=row.value_convention,
                    quality_status=row.quality_status,
                )
                for row in rows
            ],
            lineage={
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core-query-service",
                "generated_by": "integration.index_price_series",
            },
        )

    async def get_index_return_series(
        self, index_id: str, request: IndexSeriesRequest
    ) -> IndexReturnSeriesResponse:
        rows = await self._reference_repository.list_index_return_series(
            index_id=index_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return IndexReturnSeriesResponse(
            index_id=index_id,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            points=[
                IndexReturnSeriesPoint(
                    series_date=row.series_date,
                    index_return=self._as_decimal(row.index_return),
                    return_period=row.return_period,
                    return_convention=row.return_convention,
                    series_currency=row.series_currency,
                    quality_status=row.quality_status,
                )
                for row in rows
            ],
            lineage={
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core-query-service",
                "generated_by": "integration.index_return_series",
            },
        )

    async def get_benchmark_return_series(
        self, benchmark_id: str, request: BenchmarkReturnSeriesRequest
    ) -> BenchmarkReturnSeriesResponse:
        rows = await self._reference_repository.list_benchmark_return_points(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return BenchmarkReturnSeriesResponse(
            benchmark_id=benchmark_id,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            points=[
                {
                    "series_date": row.series_date,
                    "benchmark_return": self._as_decimal(row.benchmark_return),
                    "return_period": row.return_period,
                    "return_convention": row.return_convention,
                    "series_currency": row.series_currency,
                    "quality_status": row.quality_status,
                }
                for row in rows
            ],
            lineage={
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core-query-service",
                "generated_by": "integration.benchmark_return_series",
            },
        )

    async def get_risk_free_series(self, request: RiskFreeSeriesRequest) -> RiskFreeSeriesResponse:
        rows = await self._reference_repository.list_risk_free_series(
            currency=request.currency,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return RiskFreeSeriesResponse(
            currency=request.currency.upper(),
            series_mode=request.series_mode,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            points=[
                RiskFreeSeriesPoint(
                    series_date=row.series_date,
                    value=self._as_decimal(row.value),
                    value_convention=row.value_convention,
                    day_count_convention=row.day_count_convention,
                    compounding_convention=row.compounding_convention,
                    series_currency=row.series_currency,
                    quality_status=row.quality_status,
                )
                for row in rows
            ],
            lineage={
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core-query-service",
                "generated_by": "integration.risk_free_series",
            },
        )

    async def get_benchmark_coverage(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        coverage = await self._reference_repository.get_benchmark_coverage(
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
        )
        return self._to_coverage_response(coverage, start_date, end_date)

    async def get_risk_free_coverage(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        coverage = await self._reference_repository.get_risk_free_coverage(
            currency=currency,
            start_date=start_date,
            end_date=end_date,
        )
        return self._to_coverage_response(coverage, start_date, end_date)

    async def get_classification_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> ClassificationTaxonomyResponse:
        rows = await self._reference_repository.list_taxonomy(
            as_of_date=as_of_date,
            taxonomy_scope=taxonomy_scope,
        )
        return ClassificationTaxonomyResponse(
            as_of_date=as_of_date,
            records=[
                ClassificationTaxonomyEntry(
                    classification_set_id=row.classification_set_id,
                    taxonomy_scope=row.taxonomy_scope,
                    dimension_name=row.dimension_name,
                    dimension_value=row.dimension_value,
                    dimension_description=row.dimension_description,
                    effective_from=row.effective_from,
                    effective_to=row.effective_to,
                    quality_status=row.quality_status,
                )
                for row in rows
            ],
        )

    @staticmethod
    def _to_coverage_response(
        coverage: dict[str, Any],
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        expected_dates: set[date] = set()
        cursor = start_date
        while cursor <= end_date:
            expected_dates.add(cursor)
            cursor = cursor + timedelta(days=1)

        observed_start = coverage.get("observed_start_date")
        observed_end = coverage.get("observed_end_date")
        observed_dates = {
            value
            for value in coverage.get("observed_dates", [])
            if isinstance(value, date)
        }
        if not observed_dates and observed_start and observed_end:
            observed_cursor = observed_start
            while observed_cursor <= observed_end:
                observed_dates.add(observed_cursor)
                observed_cursor = observed_cursor + timedelta(days=1)

        missing_dates = sorted(expected_dates - observed_dates)
        return CoverageResponse(
            observed_start_date=observed_start,
            observed_end_date=observed_end,
            expected_start_date=start_date,
            expected_end_date=end_date,
            total_points=int(coverage.get("total_points", 0)),
            missing_dates_count=len(missing_dates),
            missing_dates_sample=missing_dates[:10],
            quality_status_distribution=dict(coverage.get("quality_status_counts", {})),
        )
