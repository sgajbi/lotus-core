"""Governed source-lineage and durable payload policy for ingestion jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

INGESTION_EVIDENCE_POLICY_VERSION = "ingestion-evidence-policy.v1"
RETENTION_AUTHORITY = "lotus-core#708"
SOURCE_SAFE_REPLAY_TTL = timedelta(hours=24)


class LineageFieldPosture(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    NOT_APPLICABLE = "not_applicable"


class PayloadClassification(StrEnum):
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class DurablePayloadRepresentation(StrEnum):
    SOURCE_SAFE_REPLAY = "source_safe_replay"
    FINGERPRINT_ONLY = "fingerprint_only"


@dataclass(frozen=True, slots=True)
class SourceLineagePolicy:
    source_system: LineageFieldPosture
    source_record_id: LineageFieldPosture
    observed_at: LineageFieldPosture
    quality_status: LineageFieldPosture
    source_batch_id: LineageFieldPosture
    source_version: LineageFieldPosture


@dataclass(frozen=True, slots=True)
class IngestionEvidencePolicy:
    endpoint: str
    entity_type: str
    classification: PayloadClassification
    durable_representation: DurablePayloadRepresentation
    replay_eligible: bool
    partial_replay_eligible: bool
    replay_ttl: timedelta | None
    source_lineage: SourceLineagePolicy | None = None
    policy_version: str = INGESTION_EVIDENCE_POLICY_VERSION
    retention_authority: str = RETENTION_AUTHORITY

    def __post_init__(self) -> None:
        if not self.endpoint.startswith("/"):
            raise ValueError("Ingestion evidence policy endpoint must be absolute.")
        if not self.entity_type.strip():
            raise ValueError("Ingestion evidence policy entity type is required.")
        if self.partial_replay_eligible and not self.replay_eligible:
            raise ValueError("Partial replay cannot be enabled when full replay is disabled.")
        if (
            self.durable_representation is DurablePayloadRepresentation.FINGERPRINT_ONLY
            and self.replay_eligible
        ):
            raise ValueError("Fingerprint-only evidence cannot authorize payload replay.")
        if self.replay_eligible and self.replay_ttl is None:
            raise ValueError("Replay-eligible evidence requires a technical expiry.")
        if not self.replay_eligible and self.replay_ttl is not None:
            raise ValueError("Replay-ineligible evidence cannot declare a replay TTL.")
        if self.replay_ttl is not None and self.replay_ttl <= timedelta(0):
            raise ValueError("Replay TTL must be positive.")


class IngestionEvidencePolicyRegistry:
    def __init__(self, policies: tuple[IngestionEvidencePolicy, ...]) -> None:
        self._by_endpoint = {policy.endpoint: policy for policy in policies}
        if len(self._by_endpoint) != len(policies):
            raise ValueError("Ingestion evidence policy endpoints must be unique.")
        identities = {(policy.endpoint, policy.entity_type) for policy in policies}
        if len(identities) != len(policies):
            raise ValueError("Ingestion evidence policy identities must be unique.")

    def require(self, endpoint: str, *, entity_type: str | None = None) -> IngestionEvidencePolicy:
        try:
            policy = self._by_endpoint[endpoint]
        except KeyError as exc:
            raise KeyError(f"Unclassified ingestion endpoint: {endpoint}") from exc
        if entity_type is not None and policy.entity_type != entity_type:
            raise ValueError(
                "Ingestion evidence policy entity mismatch: "
                f"endpoint={endpoint}, expected={policy.entity_type}, actual={entity_type}."
            )
        return policy

    def all_policies(self) -> tuple[IngestionEvidencePolicy, ...]:
        return tuple(self._by_endpoint.values())


_OPTIONAL_SOURCE_LINEAGE = SourceLineagePolicy(
    source_system=LineageFieldPosture.OPTIONAL,
    source_record_id=LineageFieldPosture.OPTIONAL,
    observed_at=LineageFieldPosture.OPTIONAL,
    quality_status=LineageFieldPosture.OPTIONAL,
    source_batch_id=LineageFieldPosture.OPTIONAL,
    source_version=LineageFieldPosture.OPTIONAL,
)

_REQUIRED_SOURCE_LINEAGE = SourceLineagePolicy(
    source_system=LineageFieldPosture.REQUIRED,
    source_record_id=LineageFieldPosture.REQUIRED,
    observed_at=LineageFieldPosture.REQUIRED,
    quality_status=LineageFieldPosture.REQUIRED,
    source_batch_id=LineageFieldPosture.OPTIONAL,
    source_version=LineageFieldPosture.REQUIRED,
)


def _fingerprint_policy(
    endpoint: str,
    entity_type: str,
    *,
    classification: PayloadClassification,
    source_lineage: SourceLineagePolicy | None = None,
) -> IngestionEvidencePolicy:
    return IngestionEvidencePolicy(
        endpoint=endpoint,
        entity_type=entity_type,
        classification=classification,
        durable_representation=DurablePayloadRepresentation.FINGERPRINT_ONLY,
        replay_eligible=False,
        partial_replay_eligible=False,
        replay_ttl=None,
        source_lineage=source_lineage,
    )


def _replay_policy(
    endpoint: str,
    entity_type: str,
    *,
    partial_replay_eligible: bool,
) -> IngestionEvidencePolicy:
    return IngestionEvidencePolicy(
        endpoint=endpoint,
        entity_type=entity_type,
        classification=PayloadClassification.INTERNAL,
        durable_representation=DurablePayloadRepresentation.SOURCE_SAFE_REPLAY,
        replay_eligible=True,
        partial_replay_eligible=partial_replay_eligible,
        replay_ttl=SOURCE_SAFE_REPLAY_TTL,
    )


_REFERENCE_FAMILIES: tuple[tuple[str, str, PayloadClassification], ...] = (
    ("/ingest/benchmark-assignments", "benchmark_assignment", PayloadClassification.CONFIDENTIAL),
    ("/ingest/model-portfolios", "model_portfolio", PayloadClassification.INTERNAL),
    ("/ingest/model-portfolio-targets", "model_portfolio_target", PayloadClassification.INTERNAL),
    (
        "/ingest/instrument-eligibility",
        "instrument_eligibility_profile",
        PayloadClassification.INTERNAL,
    ),
    (
        "/ingest/instrument-valuation-policy-assignments",
        "instrument_valuation_policy_assignment",
        PayloadClassification.INTERNAL,
    ),
    (
        "/ingest/authoritative-market-price-source-facts",
        "authoritative_market_price_source_fact",
        PayloadClassification.INTERNAL,
    ),
    ("/ingest/mandate-bindings", "mandate_binding", PayloadClassification.RESTRICTED),
    (
        "/ingest/portfolio-party-role-assignments",
        "portfolio_party_role_assignment",
        PayloadClassification.RESTRICTED,
    ),
    (
        "/ingest/client-restriction-profiles",
        "client_restriction_profile",
        PayloadClassification.RESTRICTED,
    ),
    (
        "/ingest/sustainability-preferences",
        "sustainability_preference_profile",
        PayloadClassification.RESTRICTED,
    ),
    ("/ingest/client-tax-profiles", "client_tax_profile", PayloadClassification.RESTRICTED),
    ("/ingest/client-tax-rule-sets", "client_tax_rule_set", PayloadClassification.RESTRICTED),
    (
        "/ingest/client-income-needs-schedules",
        "client_income_needs_schedule",
        PayloadClassification.RESTRICTED,
    ),
    (
        "/ingest/liquidity-reserve-requirements",
        "liquidity_reserve_requirement",
        PayloadClassification.RESTRICTED,
    ),
    (
        "/ingest/planned-withdrawal-schedules",
        "planned_withdrawal_schedule",
        PayloadClassification.RESTRICTED,
    ),
    ("/ingest/benchmark-definitions", "benchmark_definition", PayloadClassification.INTERNAL),
    (
        "/ingest/benchmark-compositions",
        "benchmark_composition",
        PayloadClassification.INTERNAL,
    ),
    ("/ingest/indices", "index_definition", PayloadClassification.INTERNAL),
    ("/ingest/index-price-series", "index_price_series", PayloadClassification.INTERNAL),
    ("/ingest/index-return-series", "index_return_series", PayloadClassification.INTERNAL),
    (
        "/ingest/benchmark-return-series",
        "benchmark_return_series",
        PayloadClassification.INTERNAL,
    ),
    ("/ingest/risk-free-series", "risk_free_series", PayloadClassification.INTERNAL),
    (
        "/ingest/reference/classification-taxonomy",
        "classification_taxonomy",
        PayloadClassification.INTERNAL,
    ),
    (
        "/ingest/reference/cash-accounts",
        "cash_account_master",
        PayloadClassification.RESTRICTED,
    ),
    (
        "/ingest/reference/instrument-lookthrough-components",
        "instrument_lookthrough_component",
        PayloadClassification.CONFIDENTIAL,
    ),
)

_STRONG_LINEAGE_ENDPOINTS = {
    "/ingest/instrument-valuation-policy-assignments",
    "/ingest/authoritative-market-price-source-facts",
}

_REFERENCE_POLICIES = tuple(
    _fingerprint_policy(
        endpoint,
        entity_type,
        classification=classification,
        source_lineage=(
            _REQUIRED_SOURCE_LINEAGE
            if endpoint in _STRONG_LINEAGE_ENDPOINTS
            else _OPTIONAL_SOURCE_LINEAGE
        ),
    )
    for endpoint, entity_type, classification in _REFERENCE_FAMILIES
)

INGESTION_EVIDENCE_POLICY_REGISTRY = IngestionEvidencePolicyRegistry(
    (
        _fingerprint_policy(
            "/ingest/portfolios", "portfolio", classification=PayloadClassification.RESTRICTED
        ),
        _replay_policy("/ingest/instruments", "instrument", partial_replay_eligible=True),
        _replay_policy("/ingest/market-prices", "market_price", partial_replay_eligible=False),
        _replay_policy("/ingest/fx-rates", "fx_rate", partial_replay_eligible=False),
        _fingerprint_policy(
            "/ingest/transactions", "transaction", classification=PayloadClassification.RESTRICTED
        ),
        _replay_policy("/ingest/business-dates", "business_date", partial_replay_eligible=True),
        _fingerprint_policy(
            "/ingest/portfolio-bundle",
            "portfolio_bundle",
            classification=PayloadClassification.RESTRICTED,
        ),
        _fingerprint_policy(
            "/reprocess/transactions",
            "reprocessing_request",
            classification=PayloadClassification.RESTRICTED,
        ),
        _fingerprint_policy(
            "/ingest/fixed-income-book-cost-authorities",
            "fixed_income_book_cost_authority",
            classification=PayloadClassification.RESTRICTED,
        ),
        _fingerprint_policy(
            "/ingest/corporate-action-manifests",
            "corporate_action_manifest",
            classification=PayloadClassification.CONFIDENTIAL,
        ),
        *_REFERENCE_POLICIES,
    )
)
