import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from portfolio_common.market_reference_quality import (
    BLOCKING_QUALITY_STATUSES,
    PARTIAL_QUALITY_STATUSES,
    STALE_QUALITY_STATUSES,
    MarketReferenceCoverageSignal,
    classify_market_reference_coverage,
)
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
    CioModelChangeAffectedCohortRequest,
    CioModelChangeAffectedCohortResponse,
    CioModelChangeAffectedCohortSupportability,
    CioModelChangeAffectedMandate,
    ClassificationTaxonomyEntry,
    ClassificationTaxonomyResponse,
    ClientRestrictionProfileEntry,
    ClientRestrictionProfileRequest,
    ClientRestrictionProfileResponse,
    ClientRestrictionProfileSupportability,
    ComponentSeriesResponse,
    CoverageResponse,
    DiscretionaryMandateBindingRequest,
    DiscretionaryMandateBindingResponse,
    DiscretionaryMandateBindingSupportability,
    DpmSourceFamilyReadiness,
    DpmSourceFamilyState,
    DpmSourceReadinessRequest,
    DpmSourceReadinessResponse,
    DpmSourceReadinessSupportability,
    IndexCatalogResponse,
    IndexDefinitionResponse,
    IndexPriceSeriesPoint,
    IndexPriceSeriesResponse,
    IndexReturnSeriesPoint,
    IndexReturnSeriesResponse,
    IndexSeriesRequest,
    InstrumentEligibilityBulkRequest,
    InstrumentEligibilityBulkResponse,
    InstrumentEligibilityRecord,
    InstrumentEligibilitySupportability,
    IntegrationWindow,
    MarketDataCoverageRequest,
    MarketDataCoverageSupportability,
    MarketDataCoverageWindowResponse,
    MarketDataFxCoverageRecord,
    MarketDataPriceCoverageRecord,
    ModelPortfolioSupportability,
    ModelPortfolioTargetRequest,
    ModelPortfolioTargetResponse,
    ModelPortfolioTargetRow,
    PortfolioManagerBookMember,
    PortfolioManagerBookMembershipRequest,
    PortfolioManagerBookMembershipResponse,
    PortfolioManagerBookMembershipSupportability,
    PortfolioTaxLotRecord,
    PortfolioTaxLotWindowRequest,
    PortfolioTaxLotWindowResponse,
    PortfolioTaxLotWindowSupportability,
    RebalanceBandContext,
    ReferencePageMetadata,
    RiskFreeSeriesPoint,
    RiskFreeSeriesRequest,
    RiskFreeSeriesResponse,
    SeriesPoint,
    SustainabilityPreferenceProfileEntry,
    SustainabilityPreferenceProfileRequest,
    SustainabilityPreferenceProfileResponse,
    SustainabilityPreferenceProfileSupportability,
    TransactionCostCurvePoint,
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
    TransactionCostCurveSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.buy_state_repository import BuyStateRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.reference_data_repository import ReferenceDataRepository
from ..repositories.transaction_repository import TransactionRepository
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
        self._buy_state_repository = BuyStateRepository(db)
        self._portfolio_repository = PortfolioRepository(db)
        self._transaction_repository = TransactionRepository(db)
        self._page_token_secret = load_query_service_settings().page_token_secret

    @staticmethod
    def _as_decimal(value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    @staticmethod
    def _runtime_metadata(
        as_of_date: date,
        *,
        data_quality_status: str | None = None,
        latest_evidence_timestamp: datetime | None = None,
    ) -> dict[str, object]:
        return source_data_product_runtime_metadata(
            as_of_date=as_of_date,
            data_quality_status=data_quality_status or "UNKNOWN",
            latest_evidence_timestamp=latest_evidence_timestamp,
        )

    @staticmethod
    def _runtime_metadata_for_existing_as_of_date(
        as_of_date: date,
        *,
        data_quality_status: str | None = None,
        latest_evidence_timestamp: datetime | None = None,
    ) -> dict[str, object]:
        metadata = source_data_product_runtime_metadata(
            as_of_date=as_of_date,
            data_quality_status=data_quality_status or "UNKNOWN",
            latest_evidence_timestamp=latest_evidence_timestamp,
        )
        metadata.pop("as_of_date")
        return metadata

    @staticmethod
    def _latest_reference_evidence_timestamp(*row_groups: list[Any]) -> datetime | None:
        timestamps: list[datetime] = []
        for rows in row_groups:
            for row in rows:
                for field_name in (
                    "observed_at",
                    "source_timestamp",
                    "assignment_recorded_at",
                    "updated_at",
                    "created_at",
                ):
                    value = getattr(row, field_name, None)
                    if isinstance(value, datetime):
                        timestamps.append(value)
        return max(timestamps) if timestamps else None

    @staticmethod
    def _market_reference_data_quality_status(rows: list[Any], required_count: int) -> str:
        if required_count <= 0:
            return "UNKNOWN"
        quality_statuses = [
            str(status).strip().upper()
            for row in rows
            if (status := getattr(row, "quality_status", None)) is not None
        ]
        if not quality_statuses:
            return "UNKNOWN"
        return classify_market_reference_coverage(
            MarketReferenceCoverageSignal(
                required_count=required_count,
                observed_count=len(quality_statuses),
                stale_count=sum(
                    1 for status in quality_statuses if status in STALE_QUALITY_STATUSES
                ),
                estimated_count=sum(
                    1 for status in quality_statuses if status in PARTIAL_QUALITY_STATUSES
                ),
                blocking_count=sum(
                    1 for status in quality_statuses if status in BLOCKING_QUALITY_STATUSES
                ),
            )
        )

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

    @staticmethod
    def _series_request_fingerprint(
        series_key: str,
        identifier_key: str,
        identifier_value: str,
        request: Any,
        extras: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "series_key": series_key,
            identifier_key: identifier_value,
            "as_of_date": request.as_of_date.isoformat(),
            "window": {
                "start_date": request.window.start_date.isoformat(),
                "end_date": request.window.end_date.isoformat(),
            },
            "frequency": request.frequency,
        }
        if extras:
            payload.update(extras)
        return IntegrationService._request_fingerprint(payload)

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
            **self._runtime_metadata_for_existing_as_of_date(
                as_of_date,
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp([row]),
            ),
        )

    async def resolve_model_portfolio_targets(
        self,
        model_portfolio_id: str,
        request: ModelPortfolioTargetRequest,
    ) -> ModelPortfolioTargetResponse | None:
        definition = await self._reference_repository.resolve_model_portfolio_definition(
            model_portfolio_id=model_portfolio_id,
            as_of_date=request.as_of_date,
        )
        if definition is None:
            return None

        targets = await self._reference_repository.list_model_portfolio_targets(
            model_portfolio_id=model_portfolio_id,
            model_portfolio_version=definition.model_portfolio_version,
            as_of_date=request.as_of_date,
            include_inactive_targets=request.include_inactive_targets,
        )
        target_rows = [
            ModelPortfolioTargetRow(
                instrument_id=row.instrument_id,
                target_weight=self._as_decimal(row.target_weight),
                min_weight=(
                    self._as_decimal(row.min_weight) if row.min_weight is not None else None
                ),
                max_weight=(
                    self._as_decimal(row.max_weight) if row.max_weight is not None else None
                ),
                target_status=row.target_status,
                quality_status=row.quality_status,
                source_record_id=row.source_record_id,
            )
            for row in targets
        ]
        total_weight = sum((row.target_weight for row in target_rows), Decimal("0"))
        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "MODEL_TARGETS_READY"
        if not target_rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "MODEL_TARGETS_EMPTY"
        elif total_weight != Decimal("1.0000000000"):
            supportability_state = "DEGRADED"
            supportability_reason = "MODEL_TARGET_WEIGHTS_NOT_ONE"

        latest_evidence_timestamp = self._latest_reference_evidence_timestamp(
            [definition],
            targets,
        )
        return ModelPortfolioTargetResponse(
            model_portfolio_id=definition.model_portfolio_id,
            model_portfolio_version=definition.model_portfolio_version,
            display_name=definition.display_name,
            base_currency=definition.base_currency,
            risk_profile=definition.risk_profile,
            mandate_type=definition.mandate_type,
            rebalance_frequency=definition.rebalance_frequency,
            approval_status=definition.approval_status,
            approved_at=definition.approved_at,
            effective_from=definition.effective_from,
            effective_to=definition.effective_to,
            targets=target_rows,
            supportability=ModelPortfolioSupportability(
                state=supportability_state,
                reason=supportability_reason,
                target_count=len(target_rows),
                total_target_weight=total_weight,
            ),
            lineage={
                "source_system": definition.source_system or "unknown",
                "source_record_id": definition.source_record_id or "unknown",
                "contract_version": "rfc_087_v1",
            },
            **self._runtime_metadata(
                request.as_of_date,
                data_quality_status=self._market_reference_data_quality_status(
                    targets,
                    required_count=len(target_rows),
                ),
                latest_evidence_timestamp=latest_evidence_timestamp,
            ),
        )

    async def resolve_portfolio_manager_book_membership(
        self,
        portfolio_manager_id: str,
        request: PortfolioManagerBookMembershipRequest,
    ) -> PortfolioManagerBookMembershipResponse:
        portfolio_types = [
            portfolio_type.strip().upper()
            for portfolio_type in request.portfolio_types
            if portfolio_type.strip()
        ]
        rows = await self._portfolio_repository.list_portfolio_manager_book_members(
            portfolio_manager_id=portfolio_manager_id,
            as_of_date=request.as_of_date,
            booking_center_code=request.booking_center_code,
            portfolio_types=portfolio_types,
            include_inactive=request.include_inactive,
        )
        members = [
            PortfolioManagerBookMember(
                portfolio_id=row.portfolio_id,
                client_id=row.client_id,
                booking_center_code=row.booking_center_code,
                portfolio_type=row.portfolio_type,
                status=row.status,
                open_date=row.open_date,
                close_date=row.close_date,
                base_currency=row.base_currency,
                source_record_id=f"portfolio:{row.portfolio_id}",
            )
            for row in rows
        ]
        filters_applied = ["portfolio_manager_id", "as_of_date"]
        if request.booking_center_code:
            filters_applied.append("booking_center_code")
        if portfolio_types:
            filters_applied.append("portfolio_types")
        if not request.include_inactive:
            filters_applied.extend(["active_lifecycle_window", "active_status"])

        supportability_state: Literal["READY", "INCOMPLETE"] = "READY"
        supportability_reason = "PM_BOOK_MEMBERSHIP_READY"
        if not members:
            supportability_state = "INCOMPLETE"
            supportability_reason = "PM_BOOK_MEMBERSHIP_EMPTY"

        snapshot_id = self._request_fingerprint(
            {
                "product_name": "PortfolioManagerBookMembership",
                "portfolio_manager_id": portfolio_manager_id,
                "as_of_date": request.as_of_date.isoformat(),
                "booking_center_code": request.booking_center_code,
                "portfolio_types": portfolio_types,
                "include_inactive": request.include_inactive,
                "portfolio_ids": [member.portfolio_id for member in members],
            }
        )
        latest_evidence_timestamp = self._latest_reference_evidence_timestamp(rows)

        return PortfolioManagerBookMembershipResponse(
            portfolio_manager_id=portfolio_manager_id,
            booking_center_code=request.booking_center_code,
            members=members,
            supportability=PortfolioManagerBookMembershipSupportability(
                state=supportability_state,
                reason=supportability_reason,
                returned_portfolio_count=len(members),
                filters_applied=filters_applied,
            ),
            lineage={
                "source_system": "lotus-core",
                "source_table": "portfolios",
                "source_field": "advisor_id",
                "contract_version": "rfc_041_pm_book_membership_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                data_quality_status="ACCEPTED" if members else "MISSING",
                latest_evidence_timestamp=latest_evidence_timestamp,
                snapshot_id=f"pm_book_membership:{snapshot_id}",
            ),
        )

    async def resolve_cio_model_change_affected_cohort(
        self,
        model_portfolio_id: str,
        request: CioModelChangeAffectedCohortRequest,
    ) -> CioModelChangeAffectedCohortResponse | None:
        definition = await self._reference_repository.resolve_model_portfolio_definition(
            model_portfolio_id=model_portfolio_id,
            as_of_date=request.as_of_date,
        )
        if definition is None:
            return None

        rows = await self._reference_repository.list_model_portfolio_affected_mandates(
            model_portfolio_id=model_portfolio_id,
            as_of_date=request.as_of_date,
            booking_center_code=request.booking_center_code,
            include_inactive_mandates=request.include_inactive_mandates,
        )
        affected_mandates = [
            CioModelChangeAffectedMandate(
                portfolio_id=row.portfolio_id,
                mandate_id=row.mandate_id,
                client_id=row.client_id,
                booking_center_code=row.booking_center_code,
                jurisdiction_code=row.jurisdiction_code,
                discretionary_authority_status=row.discretionary_authority_status,
                model_portfolio_id=row.model_portfolio_id,
                policy_pack_id=row.policy_pack_id,
                risk_profile=row.risk_profile,
                effective_from=row.effective_from,
                effective_to=row.effective_to,
                binding_version=int(row.binding_version),
                source_record_id=row.source_record_id,
            )
            for row in rows
        ]
        filters_applied = ["model_portfolio_id", "as_of_date"]
        if request.booking_center_code:
            filters_applied.append("booking_center_code")
        if not request.include_inactive_mandates:
            filters_applied.append("active_discretionary_authority")

        supportability_state: Literal["READY", "INCOMPLETE"] = "READY"
        supportability_reason = "CIO_MODEL_CHANGE_COHORT_READY"
        if not affected_mandates:
            supportability_state = "INCOMPLETE"
            supportability_reason = "CIO_MODEL_CHANGE_COHORT_EMPTY"

        snapshot_fingerprint = self._request_fingerprint(
            {
                "product_name": "CioModelChangeAffectedCohort",
                "model_portfolio_id": model_portfolio_id,
                "model_portfolio_version": definition.model_portfolio_version,
                "as_of_date": request.as_of_date.isoformat(),
                "booking_center_code": request.booking_center_code,
                "include_inactive_mandates": request.include_inactive_mandates,
                "mandate_ids": [mandate.mandate_id for mandate in affected_mandates],
                "portfolio_ids": [mandate.portfolio_id for mandate in affected_mandates],
            }
        )
        event_id = (
            "cio_model_change:"
            f"{model_portfolio_id}:"
            f"{definition.model_portfolio_version}:"
            f"{request.as_of_date.isoformat()}:{snapshot_fingerprint}"
        )
        latest_evidence_timestamp = self._latest_reference_evidence_timestamp(
            [definition],
            rows,
        )

        return CioModelChangeAffectedCohortResponse(
            model_portfolio_id=definition.model_portfolio_id,
            model_portfolio_version=definition.model_portfolio_version,
            model_change_event_id=event_id,
            approval_state=definition.approval_status,
            approved_at=definition.approved_at,
            effective_from=definition.effective_from,
            effective_to=definition.effective_to,
            affected_mandates=affected_mandates,
            supportability=CioModelChangeAffectedCohortSupportability(
                state=supportability_state,
                reason=supportability_reason,
                returned_mandate_count=len(affected_mandates),
                filters_applied=filters_applied,
            ),
            lineage={
                "source_system": definition.source_system or "lotus-core",
                "model_definition_source_record_id": definition.source_record_id or "unknown",
                "mandate_binding_table": "portfolio_mandate_bindings",
                "contract_version": "rfc_041_cio_model_change_cohort_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status="ACCEPTED" if affected_mandates else "MISSING",
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=snapshot_fingerprint,
                snapshot_id=f"cio_model_change_cohort:{snapshot_fingerprint}",
            ),
        )

    async def resolve_discretionary_mandate_binding(
        self,
        portfolio_id: str,
        request: DiscretionaryMandateBindingRequest,
    ) -> DiscretionaryMandateBindingResponse | None:
        row = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
            booking_center_code=request.booking_center_code,
        )
        if row is None:
            return None

        missing_data_families: list[str] = []
        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "MANDATE_BINDING_READY"
        if str(row.discretionary_authority_status).lower() != "active":
            supportability_state = "INCOMPLETE"
            supportability_reason = "DISCRETIONARY_AUTHORITY_NOT_ACTIVE"
            missing_data_families.append("active_discretionary_authority")
        if request.include_policy_pack and not row.policy_pack_id:
            supportability_state = "INCOMPLETE"
            supportability_reason = "MANDATE_POLICY_PACK_MISSING"
            missing_data_families.append("policy_pack")
        mandate_objective = getattr(row, "mandate_objective", None)
        review_cadence = getattr(row, "review_cadence", None)
        last_review_date = getattr(row, "last_review_date", None)
        next_review_due_date = getattr(row, "next_review_due_date", None)
        if not mandate_objective:
            if supportability_state == "READY":
                supportability_state = "INCOMPLETE"
                supportability_reason = "MANDATE_OBJECTIVE_MISSING"
            missing_data_families.append("mandate_objective")
        if not review_cadence or last_review_date is None or next_review_due_date is None:
            if supportability_state == "READY":
                supportability_state = "INCOMPLETE"
                supportability_reason = "MANDATE_REVIEW_SCHEDULE_MISSING"
            missing_data_families.append("mandate_review_schedule")
        elif next_review_due_date < request.as_of_date and supportability_state == "READY":
            supportability_state = "DEGRADED"
            supportability_reason = "MANDATE_REVIEW_OVERDUE"

        bands = dict(row.rebalance_bands or {})
        default_band = self._as_decimal(bands.get("default_band", "0"))
        cash_reserve_raw = bands.get("cash_reserve_weight")

        return DiscretionaryMandateBindingResponse(
            portfolio_id=row.portfolio_id,
            mandate_id=row.mandate_id,
            client_id=row.client_id,
            mandate_type=row.mandate_type,
            discretionary_authority_status=row.discretionary_authority_status,
            booking_center_code=row.booking_center_code,
            jurisdiction_code=row.jurisdiction_code,
            model_portfolio_id=row.model_portfolio_id,
            policy_pack_id=row.policy_pack_id if request.include_policy_pack else None,
            mandate_objective=mandate_objective,
            risk_profile=row.risk_profile,
            investment_horizon=row.investment_horizon,
            review_cadence=review_cadence,
            last_review_date=last_review_date,
            next_review_due_date=next_review_due_date,
            leverage_allowed=bool(row.leverage_allowed),
            tax_awareness_allowed=bool(row.tax_awareness_allowed),
            settlement_awareness_required=bool(row.settlement_awareness_required),
            rebalance_frequency=row.rebalance_frequency,
            rebalance_bands=RebalanceBandContext(
                default_band=default_band,
                cash_reserve_weight=(
                    self._as_decimal(cash_reserve_raw) if cash_reserve_raw is not None else None
                ),
            ),
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            binding_version=int(row.binding_version),
            supportability=DiscretionaryMandateBindingSupportability(
                state=supportability_state,
                reason=supportability_reason,
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": row.source_system or "unknown",
                "source_record_id": row.source_record_id or "unknown",
                "contract_version": "rfc_087_v1",
            },
            **self._runtime_metadata(
                request.as_of_date,
                data_quality_status=str(row.quality_status).upper(),
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp([row]),
            ),
        )

    async def get_client_restriction_profile(
        self,
        portfolio_id: str,
        request: ClientRestrictionProfileRequest,
    ) -> ClientRestrictionProfileResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        rows = await self._reference_repository.list_client_restriction_profiles(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_restrictions=request.include_inactive_restrictions,
        )
        entries = [
            ClientRestrictionProfileEntry(
                restriction_scope=row.restriction_scope,
                restriction_code=row.restriction_code,
                restriction_status=row.restriction_status,
                restriction_source=row.restriction_source,
                applies_to_buy=bool(row.applies_to_buy),
                applies_to_sell=bool(row.applies_to_sell),
                instrument_ids=self._string_list(row.instrument_ids),
                asset_classes=self._string_list(row.asset_classes),
                issuer_ids=self._string_list(row.issuer_ids),
                country_codes=self._string_list(row.country_codes),
                effective_from=row.effective_from,
                effective_to=row.effective_to,
                restriction_version=int(row.restriction_version),
                source_record_id=row.source_record_id,
            )
            for row in rows
        ]
        supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "CLIENT_RESTRICTION_PROFILE_READY"
        missing_data_families: list[str] = []
        if not rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "CLIENT_RESTRICTION_PROFILE_EMPTY"
            missing_data_families.append("client_restrictions")

        latest_evidence_timestamp = self._latest_reference_evidence_timestamp([binding], rows)
        return ClientRestrictionProfileResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            restrictions=entries,
            supportability=ClientRestrictionProfileSupportability(
                state=supportability_state,
                reason=supportability_reason,
                restriction_count=len(entries),
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "client_restriction_profiles,portfolio_mandate_bindings",
                "contract_version": "rfc_040_client_restriction_profile_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if rows else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=self._request_fingerprint(
                    {
                        "product": "ClientRestrictionProfile",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "row_count": len(rows),
                    }
                ),
                snapshot_id=(
                    "client_restriction_profile:"
                    + self._request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                        }
                    )
                ),
            ),
        )

    async def get_sustainability_preference_profile(
        self,
        portfolio_id: str,
        request: SustainabilityPreferenceProfileRequest,
    ) -> SustainabilityPreferenceProfileResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        rows = await self._reference_repository.list_sustainability_preference_profiles(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_preferences=request.include_inactive_preferences,
        )
        entries = [
            SustainabilityPreferenceProfileEntry(
                preference_framework=row.preference_framework,
                preference_code=row.preference_code,
                preference_status=row.preference_status,
                preference_source=row.preference_source,
                minimum_allocation=(
                    self._as_decimal(row.minimum_allocation)
                    if row.minimum_allocation is not None
                    else None
                ),
                maximum_allocation=(
                    self._as_decimal(row.maximum_allocation)
                    if row.maximum_allocation is not None
                    else None
                ),
                applies_to_asset_classes=self._string_list(row.applies_to_asset_classes),
                exclusion_codes=self._string_list(row.exclusion_codes),
                positive_tilt_codes=self._string_list(row.positive_tilt_codes),
                effective_from=row.effective_from,
                effective_to=row.effective_to,
                preference_version=int(row.preference_version),
                source_record_id=row.source_record_id,
            )
            for row in rows
        ]
        supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "SUSTAINABILITY_PREFERENCE_PROFILE_READY"
        missing_data_families: list[str] = []
        if not rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "SUSTAINABILITY_PREFERENCE_PROFILE_EMPTY"
            missing_data_families.append("sustainability_preferences")

        latest_evidence_timestamp = self._latest_reference_evidence_timestamp([binding], rows)
        return SustainabilityPreferenceProfileResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            preferences=entries,
            supportability=SustainabilityPreferenceProfileSupportability(
                state=supportability_state,
                reason=supportability_reason,
                preference_count=len(entries),
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "sustainability_preference_profiles,portfolio_mandate_bindings",
                "contract_version": "rfc_040_sustainability_preference_profile_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if rows else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=self._request_fingerprint(
                    {
                        "product": "SustainabilityPreferenceProfile",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "row_count": len(rows),
                    }
                ),
                snapshot_id=(
                    "sustainability_preference_profile:"
                    + self._request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                        }
                    )
                ),
            ),
        )

    async def resolve_instrument_eligibility_bulk(
        self,
        request: InstrumentEligibilityBulkRequest,
    ) -> InstrumentEligibilityBulkResponse:
        rows = await self._reference_repository.list_instrument_eligibility_profiles(
            security_ids=request.security_ids,
            as_of_date=request.as_of_date,
        )
        rows_by_security_id = {row.security_id: row for row in rows}

        records: list[InstrumentEligibilityRecord] = []
        missing_security_ids: list[str] = []
        for security_id in request.security_ids:
            row = rows_by_security_id.get(security_id)
            if row is None:
                missing_security_ids.append(security_id)
                records.append(
                    InstrumentEligibilityRecord(
                        security_id=security_id,
                        found=False,
                        eligibility_status="UNKNOWN",
                        product_shelf_status="UNKNOWN",
                        buy_allowed=False,
                        sell_allowed=False,
                        restriction_reason_codes=["ELIGIBILITY_PROFILE_MISSING"],
                        settlement_days=None,
                        settlement_calendar_id=None,
                        liquidity_tier=None,
                        issuer_id=None,
                        issuer_name=None,
                        ultimate_parent_issuer_id=None,
                        ultimate_parent_issuer_name=None,
                        asset_class=None,
                        country_of_risk=None,
                        effective_from=None,
                        effective_to=None,
                        quality_status="MISSING",
                        source_record_id=None,
                    )
                )
                continue
            records.append(
                InstrumentEligibilityRecord(
                    security_id=row.security_id,
                    found=True,
                    eligibility_status=str(row.eligibility_status).upper(),
                    product_shelf_status=str(row.product_shelf_status).upper(),
                    buy_allowed=bool(row.buy_allowed),
                    sell_allowed=bool(row.sell_allowed),
                    restriction_reason_codes=list(row.restriction_reason_codes or []),
                    settlement_days=int(row.settlement_days),
                    settlement_calendar_id=row.settlement_calendar_id,
                    liquidity_tier=row.liquidity_tier,
                    issuer_id=row.issuer_id,
                    issuer_name=row.issuer_name,
                    ultimate_parent_issuer_id=row.ultimate_parent_issuer_id,
                    ultimate_parent_issuer_name=row.ultimate_parent_issuer_name,
                    asset_class=row.asset_class,
                    country_of_risk=row.country_of_risk,
                    effective_from=row.effective_from,
                    effective_to=row.effective_to,
                    quality_status=str(row.quality_status).upper(),
                    source_record_id=row.source_record_id,
                )
            )

        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "INSTRUMENT_ELIGIBILITY_READY"
        if missing_security_ids:
            supportability_state = "INCOMPLETE"
            supportability_reason = "INSTRUMENT_ELIGIBILITY_MISSING"

        return InstrumentEligibilityBulkResponse(
            records=records,
            supportability=InstrumentEligibilitySupportability(
                state=supportability_state,
                reason=supportability_reason,
                requested_count=len(request.security_ids),
                resolved_count=len(request.security_ids) - len(missing_security_ids),
                missing_security_ids=missing_security_ids,
            ),
            lineage={
                "source_system": "instrument_eligibility",
                "contract_version": "rfc_087_v1",
            },
            **self._runtime_metadata(
                request.as_of_date,
                data_quality_status=self._market_reference_data_quality_status(
                    rows,
                    required_count=len(request.security_ids),
                ),
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp(rows),
            ),
        )

    async def get_portfolio_tax_lot_window(
        self,
        *,
        portfolio_id: str,
        request: PortfolioTaxLotWindowRequest,
    ) -> PortfolioTaxLotWindowResponse:
        if not await self._buy_state_repository.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")

        request_scope_fingerprint = self._request_fingerprint(
            {
                "portfolio_id": portfolio_id,
                "as_of_date": request.as_of_date.isoformat(),
                "security_ids": sorted(request.security_ids or []),
                "lot_status_filter": request.lot_status_filter,
                "include_closed_lots": request.include_closed_lots,
                "tenant_id": request.tenant_id,
            }
        )
        cursor = self._decode_page_token(request.page.page_token)
        token_scope = cursor.get("scope_fingerprint")
        if token_scope and token_scope != request_scope_fingerprint:
            raise ValueError("Portfolio tax-lot page token does not match request scope.")

        after_sort_key: tuple[date, str] | None = None
        if cursor.get("last_acquisition_date") and cursor.get("last_lot_id"):
            after_sort_key = (
                date.fromisoformat(str(cursor["last_acquisition_date"])),
                str(cursor["last_lot_id"]),
            )

        rows = await self._buy_state_repository.list_portfolio_tax_lots(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            security_ids=request.security_ids,
            include_closed_lots=request.include_closed_lots,
            lot_status_filter=request.lot_status_filter,
            after_sort_key=after_sort_key,
            limit=request.page.page_size + 1,
        )
        has_more = len(rows) > request.page.page_size
        page_rows = rows[: request.page.page_size]

        lots: list[PortfolioTaxLotRecord] = []
        for lot, local_currency in page_rows:
            open_quantity = self._as_decimal(lot.open_quantity)
            lots.append(
                PortfolioTaxLotRecord(
                    portfolio_id=lot.portfolio_id,
                    security_id=lot.security_id,
                    instrument_id=lot.instrument_id,
                    lot_id=lot.lot_id,
                    open_quantity=open_quantity,
                    original_quantity=self._as_decimal(lot.original_quantity),
                    acquisition_date=lot.acquisition_date,
                    cost_basis_base=self._as_decimal(lot.lot_cost_base),
                    cost_basis_local=self._as_decimal(lot.lot_cost_local),
                    local_currency=local_currency,
                    tax_lot_status="OPEN" if open_quantity > Decimal("0") else "CLOSED",
                    source_transaction_id=lot.source_transaction_id,
                    source_lineage={
                        "source_system": lot.source_system or "position_lot_state",
                        "source_transaction_id": lot.source_transaction_id,
                        "calculation_policy_id": lot.calculation_policy_id or "UNKNOWN",
                        "calculation_policy_version": lot.calculation_policy_version or "UNKNOWN",
                    },
                )
            )

        next_page_token: str | None = None
        if has_more and lots:
            last_lot = lots[-1]
            next_page_token = self._encode_page_token(
                {
                    "scope_fingerprint": request_scope_fingerprint,
                    "last_acquisition_date": last_lot.acquisition_date.isoformat(),
                    "last_lot_id": last_lot.lot_id,
                }
            )

        requested_security_ids = set(request.security_ids or [])
        returned_security_ids = {lot.security_id for lot in lots}
        missing_security_ids = (
            [] if has_more else sorted(requested_security_ids - returned_security_ids)
        )
        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "TAX_LOTS_READY"
        if not lots and not request.security_ids:
            supportability_state = "UNAVAILABLE"
            supportability_reason = "TAX_LOTS_EMPTY"
        elif has_more:
            supportability_state = "DEGRADED"
            supportability_reason = "TAX_LOTS_PAGE_PARTIAL"
        elif request.security_ids and missing_security_ids:
            supportability_state = "INCOMPLETE"
            supportability_reason = "TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES"

        return PortfolioTaxLotWindowResponse(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            lots=lots,
            page=ReferencePageMetadata(
                page_size=request.page.page_size,
                sort_key="acquisition_date:asc,lot_id:asc",
                returned_component_count=len(lots),
                request_scope_fingerprint=request_scope_fingerprint,
                next_page_token=next_page_token,
            ),
            supportability=PortfolioTaxLotWindowSupportability(
                state=supportability_state,
                reason=supportability_reason,
                requested_security_count=(
                    len(request.security_ids) if request.security_ids is not None else None
                ),
                returned_lot_count=len(lots),
                missing_security_ids=missing_security_ids,
            ),
            lineage={
                "source_system": "position_lot_state",
                "contract_version": "rfc_087_v1",
            },
            **self._runtime_metadata_for_existing_as_of_date(
                request.as_of_date,
                data_quality_status=(
                    "COMPLETE"
                    if supportability_state == "READY"
                    else "MISSING"
                    if supportability_state == "UNAVAILABLE"
                    else "PARTIAL"
                ),
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp(
                    [lot for lot, _ in page_rows]
                ),
            ),
        )

    @staticmethod
    def _transaction_fee_amount(transaction: Any) -> Decimal:
        costs = list(getattr(transaction, "costs", None) or [])
        if costs:
            return sum(
                (IntegrationService._as_decimal(getattr(cost, "amount", Decimal("0"))))
                for cost in costs
            )
        trade_fee = getattr(transaction, "trade_fee", None)
        if trade_fee is None:
            return Decimal("0")
        return IntegrationService._as_decimal(trade_fee)

    @staticmethod
    def _transaction_cost_curve_key(transaction: Any) -> tuple[str, str, str]:
        return (
            str(transaction.security_id),
            str(transaction.transaction_type).upper(),
            str(transaction.currency).upper(),
        )

    @classmethod
    def _has_observed_transaction_cost_evidence(cls, transaction: Any) -> bool:
        fee_amount = cls._transaction_fee_amount(transaction)
        notional = abs(cls._as_decimal(transaction.gross_transaction_amount))
        return fee_amount > 0 and notional > 0

    @classmethod
    def _build_transaction_cost_curve_point(
        cls,
        *,
        portfolio_id: str,
        key: tuple[str, str, str],
        rows: list[Any],
    ) -> TransactionCostCurvePoint | None:
        security_id, transaction_type, currency = key
        total_cost = sum(cls._transaction_fee_amount(row) for row in rows)
        total_notional = sum(abs(cls._as_decimal(row.gross_transaction_amount)) for row in rows)
        if total_cost <= 0 or total_notional <= 0:
            return None

        cost_bps_values = [
            (cls._transaction_fee_amount(row) / abs(cls._as_decimal(row.gross_transaction_amount)))
            * Decimal("10000")
            for row in rows
            if abs(cls._as_decimal(row.gross_transaction_amount)) > 0
        ]
        if not cost_bps_values:
            return None

        observed_dates = [row.transaction_date.date() for row in rows]
        return TransactionCostCurvePoint(
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_type=transaction_type,
            currency=currency,
            observation_count=len(rows),
            total_notional=total_notional,
            total_cost=total_cost,
            average_cost_bps=(total_cost / total_notional * Decimal("10000")).quantize(
                Decimal("0.0001")
            ),
            min_cost_bps=min(cost_bps_values).quantize(Decimal("0.0001")),
            max_cost_bps=max(cost_bps_values).quantize(Decimal("0.0001")),
            first_observed_date=min(observed_dates),
            last_observed_date=max(observed_dates),
            sample_transaction_ids=[
                str(row.transaction_id)
                for row in sorted(rows, key=lambda row: row.transaction_id)[:5]
            ],
            source_lineage={
                "source_system": "transactions",
                "source_table": "transactions,transaction_costs",
                "contract_version": "rfc_040_wtbd_007_v1",
            },
        )

    async def get_transaction_cost_curve(
        self,
        *,
        portfolio_id: str,
        request: TransactionCostCurveRequest,
    ) -> TransactionCostCurveResponse:
        if not await self._transaction_repository.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")

        request_scope_fingerprint = self._request_fingerprint(
            {
                "portfolio_id": portfolio_id,
                "as_of_date": request.as_of_date.isoformat(),
                "window": {
                    "start_date": request.window.start_date.isoformat(),
                    "end_date": request.window.end_date.isoformat(),
                },
                "security_ids": sorted(request.security_ids or []),
                "transaction_types": sorted(request.transaction_types or []),
                "min_observation_count": request.min_observation_count,
                "tenant_id": request.tenant_id,
            }
        )
        cursor = self._decode_page_token(request.page.page_token)
        token_scope = cursor.get("scope_fingerprint")
        if token_scope and token_scope != request_scope_fingerprint:
            raise ValueError("Transaction cost curve page token does not match request scope.")
        after_key = tuple(cursor.get("last_curve_key") or ())

        transactions = await self._transaction_repository.list_transaction_cost_evidence(
            portfolio_id=portfolio_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
            as_of_date=request.as_of_date,
            security_ids=request.security_ids,
            transaction_types=request.transaction_types,
        )

        grouped: dict[tuple[str, str, str], list[Any]] = {}
        for transaction in transactions:
            if not self._has_observed_transaction_cost_evidence(transaction):
                continue
            grouped.setdefault(self._transaction_cost_curve_key(transaction), []).append(
                transaction
            )

        all_points: list[TransactionCostCurvePoint] = []
        for key in sorted(grouped):
            rows = grouped[key]
            if len(rows) < request.min_observation_count:
                continue
            point = self._build_transaction_cost_curve_point(
                portfolio_id=portfolio_id,
                key=key,
                rows=rows,
            )
            if point is not None:
                all_points.append(point)

        paged_candidates = [
            point
            for point in all_points
            if not after_key
            or (point.security_id, point.transaction_type, point.currency) > after_key
        ]
        has_more = len(paged_candidates) > request.page.page_size
        curve_points = paged_candidates[: request.page.page_size]
        next_page_token: str | None = None
        if has_more and curve_points:
            last_point = curve_points[-1]
            next_page_token = self._encode_page_token(
                {
                    "scope_fingerprint": request_scope_fingerprint,
                    "last_curve_key": [
                        last_point.security_id,
                        last_point.transaction_type,
                        last_point.currency,
                    ],
                }
            )

        requested_security_ids = set(request.security_ids or [])
        returned_security_ids = {point.security_id for point in all_points}
        missing_security_ids = sorted(requested_security_ids - returned_security_ids)

        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "TRANSACTION_COST_CURVE_READY"
        if not all_points:
            supportability_state = "UNAVAILABLE"
            supportability_reason = "TRANSACTION_COST_EVIDENCE_NOT_FOUND"
        elif missing_security_ids:
            supportability_state = "INCOMPLETE"
            supportability_reason = "TRANSACTION_COST_EVIDENCE_MISSING_FOR_SECURITIES"
        elif has_more:
            supportability_state = "DEGRADED"
            supportability_reason = "TRANSACTION_COST_CURVE_PAGE_PARTIAL"

        return TransactionCostCurveResponse(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            window=request.window,
            curve_points=curve_points,
            page=ReferencePageMetadata(
                page_size=request.page.page_size,
                sort_key="security_id:asc,transaction_type:asc,currency:asc",
                returned_component_count=len(curve_points),
                request_scope_fingerprint=request_scope_fingerprint,
                next_page_token=next_page_token,
            ),
            supportability=TransactionCostCurveSupportability(
                state=supportability_state,
                reason=supportability_reason,
                requested_security_count=(
                    len(request.security_ids) if request.security_ids is not None else None
                ),
                returned_curve_point_count=len(curve_points),
                missing_security_ids=missing_security_ids,
            ),
            lineage={
                "source_system": "transactions",
                "contract_version": "rfc_040_wtbd_007_v1",
            },
            **self._runtime_metadata_for_existing_as_of_date(
                request.as_of_date,
                data_quality_status="COMPLETE" if supportability_state == "READY" else "PARTIAL",
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp(transactions),
            ),
        )

    async def get_market_data_coverage(
        self,
        request: MarketDataCoverageRequest,
    ) -> MarketDataCoverageWindowResponse:
        price_rows = await self._reference_repository.list_latest_market_prices(
            security_ids=request.instrument_ids,
            as_of_date=request.as_of_date,
        )
        fx_pairs = [(pair.from_currency, pair.to_currency) for pair in request.currency_pairs]
        fx_rows = await self._reference_repository.list_latest_fx_rates(
            currency_pairs=fx_pairs,
            as_of_date=request.as_of_date,
        )

        price_by_instrument = {row.security_id: row for row in price_rows}
        fx_by_pair = {(row.from_currency, row.to_currency): row for row in fx_rows}

        price_coverage: list[MarketDataPriceCoverageRecord] = []
        missing_instrument_ids: list[str] = []
        stale_instrument_ids: list[str] = []
        for instrument_id in request.instrument_ids:
            row = price_by_instrument.get(instrument_id)
            if row is None:
                missing_instrument_ids.append(instrument_id)
                price_coverage.append(
                    MarketDataPriceCoverageRecord(
                        instrument_id=instrument_id,
                        found=False,
                        quality_status="MISSING",
                    )
                )
                continue

            age_days = (request.as_of_date - row.price_date).days
            quality_status: Literal["READY", "STALE", "MISSING"] = (
                "STALE" if age_days > request.max_staleness_days else "READY"
            )
            if quality_status == "STALE":
                stale_instrument_ids.append(instrument_id)
            price_coverage.append(
                MarketDataPriceCoverageRecord(
                    instrument_id=instrument_id,
                    found=True,
                    price_date=row.price_date,
                    price=self._as_decimal(row.price),
                    currency=row.currency,
                    age_days=age_days,
                    quality_status=quality_status,
                )
            )

        fx_coverage: list[MarketDataFxCoverageRecord] = []
        missing_currency_pairs: list[str] = []
        stale_currency_pairs: list[str] = []
        for pair in request.currency_pairs:
            pair_key = (pair.from_currency, pair.to_currency)
            pair_label = f"{pair.from_currency}/{pair.to_currency}"
            row = fx_by_pair.get(pair_key)
            if row is None:
                missing_currency_pairs.append(pair_label)
                fx_coverage.append(
                    MarketDataFxCoverageRecord(
                        from_currency=pair.from_currency,
                        to_currency=pair.to_currency,
                        found=False,
                        quality_status="MISSING",
                    )
                )
                continue

            age_days = (request.as_of_date - row.rate_date).days
            quality_status = "STALE" if age_days > request.max_staleness_days else "READY"
            if quality_status == "STALE":
                stale_currency_pairs.append(pair_label)
            fx_coverage.append(
                MarketDataFxCoverageRecord(
                    from_currency=pair.from_currency,
                    to_currency=pair.to_currency,
                    found=True,
                    rate_date=row.rate_date,
                    rate=self._as_decimal(row.rate),
                    age_days=age_days,
                    quality_status=quality_status,
                )
            )

        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "MARKET_DATA_READY"
        if missing_instrument_ids or missing_currency_pairs:
            supportability_state = "INCOMPLETE"
            supportability_reason = "MARKET_DATA_MISSING"
        elif stale_instrument_ids or stale_currency_pairs:
            supportability_state = "DEGRADED"
            supportability_reason = "MARKET_DATA_STALE"

        return MarketDataCoverageWindowResponse(
            as_of_date=request.as_of_date,
            valuation_currency=request.valuation_currency,
            price_coverage=price_coverage,
            fx_coverage=fx_coverage,
            supportability=MarketDataCoverageSupportability(
                state=supportability_state,
                reason=supportability_reason,
                requested_price_count=len(request.instrument_ids),
                resolved_price_count=sum(1 for record in price_coverage if record.found),
                requested_fx_count=len(request.currency_pairs),
                resolved_fx_count=sum(1 for record in fx_coverage if record.found),
                missing_instrument_ids=missing_instrument_ids,
                stale_instrument_ids=stale_instrument_ids,
                missing_currency_pairs=missing_currency_pairs,
                stale_currency_pairs=stale_currency_pairs,
            ),
            lineage={
                "source_system": "market_prices+fx_rates",
                "contract_version": "rfc_087_v1",
            },
            **self._runtime_metadata_for_existing_as_of_date(
                request.as_of_date,
                data_quality_status=("COMPLETE" if supportability_state == "READY" else "PARTIAL"),
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp(
                    price_rows,
                    fx_rows,
                ),
            ),
        )

    async def get_dpm_source_readiness(
        self,
        *,
        portfolio_id: str,
        request: DpmSourceReadinessRequest,
    ) -> DpmSourceReadinessResponse:
        families: list[DpmSourceFamilyReadiness] = []
        resolved_mandate_id: str | None = request.mandate_id
        resolved_model_portfolio_id: str | None = request.model_portfolio_id

        mandate_response: DiscretionaryMandateBindingResponse | None = None
        try:
            mandate_response = await self.resolve_discretionary_mandate_binding(
                portfolio_id,
                DiscretionaryMandateBindingRequest(
                    as_of_date=request.as_of_date,
                    tenant_id=request.tenant_id,
                    mandate_id=request.mandate_id,
                    include_policy_pack=True,
                ),
            )
        except (LookupError, ValueError):
            mandate_response = None
        if mandate_response is None:
            families.append(
                DpmSourceFamilyReadiness(
                    family="mandate",
                    product_name="DiscretionaryMandateBinding",
                    state="UNAVAILABLE",
                    reason="MANDATE_BINDING_UNAVAILABLE",
                    missing_items=["mandate_binding"],
                )
            )
        else:
            resolved_mandate_id = mandate_response.mandate_id
            resolved_model_portfolio_id = (
                resolved_model_portfolio_id or mandate_response.model_portfolio_id
            )
            families.append(
                DpmSourceFamilyReadiness(
                    family="mandate",
                    product_name="DiscretionaryMandateBinding",
                    state=mandate_response.supportability.state,
                    reason=mandate_response.supportability.reason,
                    missing_items=mandate_response.supportability.missing_data_families,
                    evidence_count=1,
                )
            )

        target_instrument_ids: list[str] = []
        if resolved_model_portfolio_id is None:
            families.append(
                DpmSourceFamilyReadiness(
                    family="model_targets",
                    product_name="DpmModelPortfolioTarget",
                    state="UNAVAILABLE",
                    reason="MODEL_PORTFOLIO_ID_UNAVAILABLE",
                    missing_items=["model_portfolio_id"],
                )
            )
        else:
            try:
                model_response = await self.resolve_model_portfolio_targets(
                    resolved_model_portfolio_id,
                    ModelPortfolioTargetRequest(
                        as_of_date=request.as_of_date,
                        include_inactive_targets=False,
                        tenant_id=request.tenant_id,
                    ),
                )
            except (LookupError, ValueError):
                model_response = None
            if model_response is None:
                families.append(
                    DpmSourceFamilyReadiness(
                        family="model_targets",
                        product_name="DpmModelPortfolioTarget",
                        state="UNAVAILABLE",
                        reason="MODEL_TARGETS_UNAVAILABLE",
                        missing_items=[resolved_model_portfolio_id],
                    )
                )
            else:
                target_instrument_ids = [target.instrument_id for target in model_response.targets]
                families.append(
                    DpmSourceFamilyReadiness(
                        family="model_targets",
                        product_name="DpmModelPortfolioTarget",
                        state=model_response.supportability.state,
                        reason=model_response.supportability.reason,
                        evidence_count=model_response.supportability.target_count,
                    )
                )

        evaluated_instrument_ids = sorted({*request.instrument_ids, *target_instrument_ids})
        if evaluated_instrument_ids:
            try:
                eligibility = await self.resolve_instrument_eligibility_bulk(
                    InstrumentEligibilityBulkRequest(
                        as_of_date=request.as_of_date,
                        security_ids=evaluated_instrument_ids,
                        tenant_id=request.tenant_id,
                        include_restricted_rationale=False,
                    )
                )
                families.append(
                    DpmSourceFamilyReadiness(
                        family="eligibility",
                        product_name="InstrumentEligibilityProfile",
                        state=eligibility.supportability.state,
                        reason=eligibility.supportability.reason,
                        missing_items=eligibility.supportability.missing_security_ids,
                        evidence_count=eligibility.supportability.resolved_count,
                    )
                )
            except (LookupError, ValueError):
                families.append(
                    DpmSourceFamilyReadiness(
                        family="eligibility",
                        product_name="InstrumentEligibilityProfile",
                        state="UNAVAILABLE",
                        reason="INSTRUMENT_ELIGIBILITY_UNAVAILABLE",
                        missing_items=evaluated_instrument_ids[:10],
                    )
                )
        else:
            families.append(
                DpmSourceFamilyReadiness(
                    family="eligibility",
                    product_name="InstrumentEligibilityProfile",
                    state="UNAVAILABLE",
                    reason="DPM_INSTRUMENT_UNIVERSE_EMPTY",
                    missing_items=["instrument_ids"],
                )
            )

        try:
            tax_lots = await self.get_portfolio_tax_lot_window(
                portfolio_id=portfolio_id,
                request=PortfolioTaxLotWindowRequest(
                    as_of_date=request.as_of_date,
                    security_ids=evaluated_instrument_ids or None,
                    tenant_id=request.tenant_id,
                ),
            )
            families.append(
                DpmSourceFamilyReadiness(
                    family="tax_lots",
                    product_name="PortfolioTaxLotWindow",
                    state=tax_lots.supportability.state,
                    reason=tax_lots.supportability.reason,
                    missing_items=tax_lots.supportability.missing_security_ids,
                    evidence_count=tax_lots.supportability.returned_lot_count,
                )
            )
        except (LookupError, ValueError):
            families.append(
                DpmSourceFamilyReadiness(
                    family="tax_lots",
                    product_name="PortfolioTaxLotWindow",
                    state="UNAVAILABLE",
                    reason="PORTFOLIO_TAX_LOTS_UNAVAILABLE",
                    missing_items=[portfolio_id],
                )
            )

        try:
            market_data = await self.get_market_data_coverage(
                MarketDataCoverageRequest(
                    as_of_date=request.as_of_date,
                    instrument_ids=evaluated_instrument_ids,
                    currency_pairs=request.currency_pairs,
                    valuation_currency=request.valuation_currency,
                    max_staleness_days=request.max_staleness_days,
                    tenant_id=request.tenant_id,
                )
            )
            families.append(
                DpmSourceFamilyReadiness(
                    family="market_data",
                    product_name="MarketDataCoverageWindow",
                    state=market_data.supportability.state,
                    reason=market_data.supportability.reason,
                    missing_items=[
                        *market_data.supportability.missing_instrument_ids,
                        *market_data.supportability.missing_currency_pairs,
                    ],
                    stale_items=[
                        *market_data.supportability.stale_instrument_ids,
                        *market_data.supportability.stale_currency_pairs,
                    ],
                    evidence_count=(
                        market_data.supportability.resolved_price_count
                        + market_data.supportability.resolved_fx_count
                    ),
                )
            )
        except (LookupError, ValueError):
            families.append(
                DpmSourceFamilyReadiness(
                    family="market_data",
                    product_name="MarketDataCoverageWindow",
                    state="UNAVAILABLE",
                    reason="MARKET_DATA_COVERAGE_UNAVAILABLE",
                    missing_items=["market_data_coverage"],
                )
            )

        supportability = self._dpm_source_readiness_supportability(families)
        return DpmSourceReadinessResponse(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=resolved_mandate_id,
            model_portfolio_id=resolved_model_portfolio_id,
            evaluated_instrument_ids=evaluated_instrument_ids,
            families=families,
            supportability=supportability,
            lineage={
                "source_system": "lotus-core",
                "contract_version": "rfc_087_v1",
                "readiness_scope": "dpm_source_family",
            },
            **self._runtime_metadata_for_existing_as_of_date(
                request.as_of_date,
                data_quality_status=("COMPLETE" if supportability.state == "READY" else "PARTIAL"),
                latest_evidence_timestamp=None,
            ),
        )

    @staticmethod
    def _dpm_source_readiness_supportability(
        families: list[DpmSourceFamilyReadiness],
    ) -> DpmSourceReadinessSupportability:
        counts: dict[DpmSourceFamilyState, int] = {
            "READY": 0,
            "DEGRADED": 0,
            "INCOMPLETE": 0,
            "UNAVAILABLE": 0,
        }
        for family in families:
            counts[family.state] += 1
        if counts["UNAVAILABLE"]:
            state: DpmSourceFamilyState = "UNAVAILABLE"
            reason = "DPM_SOURCE_READINESS_UNAVAILABLE"
        elif counts["INCOMPLETE"]:
            state = "INCOMPLETE"
            reason = "DPM_SOURCE_READINESS_INCOMPLETE"
        elif counts["DEGRADED"]:
            state = "DEGRADED"
            reason = "DPM_SOURCE_READINESS_DEGRADED"
        else:
            state = "READY"
            reason = "DPM_SOURCE_READINESS_READY"
        return DpmSourceReadinessSupportability(
            state=state,
            reason=reason,
            ready_family_count=counts["READY"],
            degraded_family_count=counts["DEGRADED"],
            incomplete_family_count=counts["INCOMPLETE"],
            unavailable_family_count=counts["UNAVAILABLE"],
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

        evidence_rows = definitions + components
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
            **self._runtime_metadata(
                request.window.end_date,
                data_quality_status=self._market_reference_data_quality_status(
                    evidence_rows,
                    required_count=len(evidence_rows),
                ),
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp(evidence_rows),
            ),
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
        index_ids: list[str],
        index_currency: str | None,
        index_type: str | None,
        index_status: str | None,
    ) -> IndexCatalogResponse:
        rows = await self._reference_repository.list_index_definitions(
            as_of_date=as_of_date,
            index_ids=index_ids,
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
                    if segment.composition_effective_from <= current_date and (
                        segment.composition_effective_to is None
                        or segment.composition_effective_to >= current_date
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
                            or (benchmark_return_row and benchmark_return_row.series_currency)
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
        returned_index_ids = {series.index_id for series in component_series}
        returned_index_prices = [row for row in index_prices if row.index_id in returned_index_ids]
        returned_index_returns = [
            row for row in index_returns if row.index_id in returned_index_ids
        ]
        returned_components = [row for row in components if row.index_id in returned_index_ids]
        returned_evidence_rows = (
            returned_components + returned_index_prices + returned_index_returns + benchmark_returns
        )
        total_evidence_rows = components + index_prices + index_returns + benchmark_returns
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
            component_metadata_policy=(
                "targeted_index_catalog_lookup_required_for_component_metadata"
            ),
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
            **self._runtime_metadata_for_existing_as_of_date(
                request.as_of_date,
                data_quality_status=self._market_reference_data_quality_status(
                    returned_evidence_rows,
                    required_count=(
                        len(total_evidence_rows) if has_more else len(returned_evidence_rows)
                    ),
                ),
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp(
                    returned_evidence_rows
                ),
            ),
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
            **self._runtime_metadata(
                getattr(request, "as_of_date", request.window.end_date),
                data_quality_status=self._market_reference_data_quality_status(
                    rows,
                    required_count=len(rows),
                ),
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp(rows),
            ),
        )

    async def get_index_return_series(
        self, index_id: str, request: IndexSeriesRequest
    ) -> IndexReturnSeriesResponse:
        request_fingerprint = self._series_request_fingerprint(
            series_key="index_return_series",
            identifier_key="index_id",
            identifier_value=index_id,
            request=request,
        )
        rows = await self._reference_repository.list_index_return_series(
            index_id=index_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return IndexReturnSeriesResponse(
            index_id=index_id,
            as_of_date=request.as_of_date,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            request_fingerprint=request_fingerprint,
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
            **self._runtime_metadata_for_existing_as_of_date(
                request.as_of_date,
                data_quality_status=self._market_reference_data_quality_status(
                    rows,
                    required_count=len(rows),
                ),
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp(rows),
            ),
        )

    async def get_benchmark_return_series(
        self, benchmark_id: str, request: BenchmarkReturnSeriesRequest
    ) -> BenchmarkReturnSeriesResponse:
        request_fingerprint = self._series_request_fingerprint(
            series_key="benchmark_return_series",
            identifier_key="benchmark_id",
            identifier_value=benchmark_id,
            request=request,
        )
        rows = await self._reference_repository.list_benchmark_return_points(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return BenchmarkReturnSeriesResponse(
            benchmark_id=benchmark_id,
            as_of_date=request.as_of_date,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            request_fingerprint=request_fingerprint,
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
        request_fingerprint = self._series_request_fingerprint(
            series_key="risk_free_series",
            identifier_key="currency",
            identifier_value=request.currency.upper(),
            request=request,
            extras={"series_mode": request.series_mode},
        )
        rows = await self._reference_repository.list_risk_free_series(
            currency=request.currency,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return RiskFreeSeriesResponse(
            currency=request.currency.upper(),
            as_of_date=request.as_of_date,
            series_mode=request.series_mode,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            request_fingerprint=request_fingerprint,
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
            **self._runtime_metadata_for_existing_as_of_date(
                request.as_of_date,
                data_quality_status=self._market_reference_data_quality_status(
                    rows,
                    required_count=len(rows),
                ),
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp(rows),
            ),
        )

    async def get_benchmark_coverage(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        request_fingerprint = self._request_fingerprint(
            {
                "coverage_key": "benchmark_coverage",
                "benchmark_id": benchmark_id,
                "window": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            }
        )
        coverage = await self._reference_repository.get_benchmark_coverage(
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
        )
        return self._to_coverage_response(
            coverage,
            start_date,
            end_date,
            request_fingerprint=request_fingerprint,
        )

    async def get_risk_free_coverage(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        request_fingerprint = self._request_fingerprint(
            {
                "coverage_key": "risk_free_coverage",
                "currency": currency.upper(),
                "window": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            }
        )
        coverage = await self._reference_repository.get_risk_free_coverage(
            currency=currency,
            start_date=start_date,
            end_date=end_date,
        )
        return self._to_coverage_response(
            coverage,
            start_date,
            end_date,
            request_fingerprint=request_fingerprint,
        )

    async def get_classification_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> ClassificationTaxonomyResponse:
        request_fingerprint = self._request_fingerprint(
            {
                "taxonomy_key": "classification_taxonomy",
                "as_of_date": as_of_date.isoformat(),
                "taxonomy_scope": taxonomy_scope,
            }
        )
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
            request_fingerprint=request_fingerprint,
            **self._runtime_metadata_for_existing_as_of_date(
                as_of_date,
                data_quality_status=self._market_reference_data_quality_status(
                    rows,
                    required_count=len(rows),
                ),
                latest_evidence_timestamp=self._latest_reference_evidence_timestamp(rows),
            ),
        )

    @staticmethod
    def _to_coverage_response(
        coverage: dict[str, Any],
        start_date: date,
        end_date: date,
        request_fingerprint: str,
    ) -> CoverageResponse:
        expected_dates: set[date] = set()
        cursor = start_date
        while cursor <= end_date:
            expected_dates.add(cursor)
            cursor = cursor + timedelta(days=1)

        observed_start = coverage.get("observed_start_date")
        observed_end = coverage.get("observed_end_date")
        observed_dates = {
            value for value in coverage.get("observed_dates", []) if isinstance(value, date)
        }
        if not observed_dates and observed_start and observed_end:
            observed_cursor = observed_start
            while observed_cursor <= observed_end:
                observed_dates.add(observed_cursor)
                observed_cursor = observed_cursor + timedelta(days=1)

        missing_dates = sorted(expected_dates - observed_dates)
        quality_counts = dict(coverage.get("quality_status_counts", {}))
        normalized_quality_counts = {
            str(status).strip().upper(): int(count)
            for status, count in quality_counts.items()
            if count
        }
        data_quality_status = classify_market_reference_coverage(
            MarketReferenceCoverageSignal(
                required_count=len(expected_dates),
                observed_count=len(observed_dates),
                stale_count=sum(
                    count
                    for status, count in normalized_quality_counts.items()
                    if status in STALE_QUALITY_STATUSES
                ),
                estimated_count=sum(
                    count
                    for status, count in normalized_quality_counts.items()
                    if status in PARTIAL_QUALITY_STATUSES
                ),
                blocking_count=sum(
                    count
                    for status, count in normalized_quality_counts.items()
                    if status in BLOCKING_QUALITY_STATUSES
                ),
            )
        )
        return CoverageResponse(
            request_fingerprint=request_fingerprint,
            observed_start_date=observed_start,
            observed_end_date=observed_end,
            expected_start_date=start_date,
            expected_end_date=end_date,
            total_points=int(coverage.get("total_points", 0)),
            missing_dates_count=len(missing_dates),
            missing_dates_sample=missing_dates[:10],
            quality_status_distribution=quality_counts,
            **IntegrationService._runtime_metadata(
                end_date,
                data_quality_status=data_quality_status,
                latest_evidence_timestamp=coverage.get("latest_evidence_timestamp"),
            ),
        )
