from __future__ import annotations

from datetime import timedelta

import pytest

from src.services.ingestion_service.app.application.reference_data_ingestion_registry import (
    REFERENCE_DATA_INGESTION_REGISTRY,
)
from src.services.ingestion_service.app.domain.ingestion_evidence_policy import (
    INGESTION_EVIDENCE_POLICY_REGISTRY,
    DurablePayloadRepresentation,
    IngestionEvidencePolicy,
    IngestionEvidencePolicyRegistry,
    LineageFieldPosture,
    PayloadClassification,
)


def test_every_reference_family_has_one_explicit_lineage_and_payload_policy() -> None:
    commands = REFERENCE_DATA_INGESTION_REGISTRY.all_commands()
    versioned_endpoints = {
        "/ingest/benchmark-assignments",
        "/ingest/instrument-valuation-policy-assignments",
        "/ingest/authoritative-market-price-source-facts",
        "/ingest/portfolio-party-role-assignments",
    }

    assert len(commands) == 25
    for command in commands:
        policy = INGESTION_EVIDENCE_POLICY_REGISTRY.require(
            command.endpoint,
            entity_type=command.entity_type,
        )
        assert policy.source_lineage is not None
        assert policy.durable_representation is DurablePayloadRepresentation.FINGERPRINT_ONLY
        assert policy.replay_eligible is False
        assert policy.replay_ttl is None
        assert policy.source_lineage.source_batch_id is LineageFieldPosture.NOT_APPLICABLE
        if command.endpoint not in versioned_endpoints:
            assert policy.source_lineage.source_version is LineageFieldPosture.NOT_APPLICABLE
        assert set(policy.source_lineage.__dataclass_fields__) == {
            "source_system",
            "source_record_id",
            "observed_at",
            "quality_status",
            "source_batch_id",
            "source_version",
        }


def test_registry_covers_every_job_creating_endpoint_family() -> None:
    reference_endpoints = {
        command.endpoint for command in REFERENCE_DATA_INGESTION_REGISTRY.all_commands()
    }
    generic_job_endpoints = {
        "/ingest/portfolios",
        "/ingest/instruments",
        "/ingest/market-prices",
        "/ingest/fx-rates",
        "/ingest/transactions",
        "/ingest/business-dates",
        "/ingest/portfolio-bundle",
        "/reprocess/transactions",
        "/ingest/fixed-income-book-cost-authorities",
        "/ingest/corporate-action-manifests",
    }

    assert {
        policy.endpoint for policy in INGESTION_EVIDENCE_POLICY_REGISTRY.all_policies()
    } == reference_endpoints | generic_job_endpoints


def test_sensitive_payload_families_are_fingerprint_only() -> None:
    for endpoint in (
        "/ingest/transactions",
        "/ingest/portfolios",
        "/ingest/portfolio-bundle",
        "/reprocess/transactions",
        "/ingest/client-tax-profiles",
        "/ingest/client-restriction-profiles",
        "/ingest/planned-withdrawal-schedules",
    ):
        policy = INGESTION_EVIDENCE_POLICY_REGISTRY.require(endpoint)
        assert policy.classification is PayloadClassification.RESTRICTED
        assert policy.durable_representation is DurablePayloadRepresentation.FINGERPRINT_ONLY
        assert policy.replay_eligible is False
        assert policy.replay_ttl is None


def test_only_source_safe_internal_families_authorize_payload_replay() -> None:
    replay_policies = {
        policy.endpoint: policy.partial_replay_eligible
        for policy in INGESTION_EVIDENCE_POLICY_REGISTRY.all_policies()
        if policy.replay_eligible
    }

    assert replay_policies == {
        "/ingest/instruments": True,
        "/ingest/market-prices": False,
        "/ingest/fx-rates": False,
        "/ingest/business-dates": True,
    }
    assert {
        policy.replay_ttl
        for policy in INGESTION_EVIDENCE_POLICY_REGISTRY.all_policies()
        if policy.replay_eligible
    } == {timedelta(hours=24)}


def test_strong_authority_families_declare_exact_source_identity_and_version_posture() -> None:
    for endpoint in (
        "/ingest/instrument-valuation-policy-assignments",
        "/ingest/authoritative-market-price-source-facts",
    ):
        lineage = INGESTION_EVIDENCE_POLICY_REGISTRY.require(endpoint).source_lineage
        assert lineage is not None
        assert lineage.source_system is LineageFieldPosture.REQUIRED
        assert lineage.source_record_id is LineageFieldPosture.REQUIRED
        assert lineage.observed_at is LineageFieldPosture.REQUIRED
        assert lineage.quality_status is LineageFieldPosture.NOT_APPLICABLE
        assert lineage.source_version is LineageFieldPosture.REQUIRED
        assert lineage.source_batch_id is LineageFieldPosture.NOT_APPLICABLE


def test_party_role_family_declares_required_observation_authority() -> None:
    lineage = INGESTION_EVIDENCE_POLICY_REGISTRY.require(
        "/ingest/portfolio-party-role-assignments"
    ).source_lineage

    assert lineage is not None
    assert lineage.source_system is LineageFieldPosture.REQUIRED
    assert lineage.source_record_id is LineageFieldPosture.REQUIRED
    assert lineage.observed_at is LineageFieldPosture.REQUIRED
    assert lineage.quality_status is LineageFieldPosture.OPTIONAL
    assert lineage.source_version is LineageFieldPosture.OPTIONAL
    assert lineage.source_batch_id is LineageFieldPosture.NOT_APPLICABLE


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        (
            "/ingest/benchmark-assignments",
            {
                "source_system": "optional",
                "source_record_id": "not_applicable",
                "observed_at": "not_applicable",
                "quality_status": "not_applicable",
                "source_batch_id": "not_applicable",
                "source_version": "optional",
            },
        ),
        (
            "/ingest/reference/cash-accounts",
            {
                "source_system": "optional",
                "source_record_id": "optional",
                "observed_at": "not_applicable",
                "quality_status": "not_applicable",
                "source_batch_id": "not_applicable",
                "source_version": "not_applicable",
            },
        ),
        (
            "/ingest/reference/instrument-lookthrough-components",
            {
                "source_system": "optional",
                "source_record_id": "optional",
                "observed_at": "not_applicable",
                "quality_status": "not_applicable",
                "source_batch_id": "not_applicable",
                "source_version": "not_applicable",
            },
        ),
    ],
)
def test_incomplete_families_declare_truthful_not_applicable_lineage(
    endpoint: str,
    expected: dict[str, str],
) -> None:
    lineage = INGESTION_EVIDENCE_POLICY_REGISTRY.require(endpoint).source_lineage

    assert lineage is not None
    assert {field: getattr(lineage, field).value for field in expected} == expected


def test_registry_fails_closed_for_unknown_endpoint_or_entity_mismatch() -> None:
    with pytest.raises(KeyError, match="Unclassified ingestion endpoint"):
        INGESTION_EVIDENCE_POLICY_REGISTRY.require("/ingest/unknown")

    with pytest.raises(ValueError, match="entity mismatch"):
        INGESTION_EVIDENCE_POLICY_REGISTRY.require(
            "/ingest/transactions",
            entity_type="portfolio",
        )


def test_policy_rejects_impossible_replay_posture() -> None:
    with pytest.raises(ValueError, match="Fingerprint-only evidence"):
        IngestionEvidencePolicy(
            endpoint="/ingest/impossible",
            entity_type="impossible",
            classification=PayloadClassification.INTERNAL,
            durable_representation=DurablePayloadRepresentation.FINGERPRINT_ONLY,
            replay_eligible=True,
            partial_replay_eligible=False,
            replay_ttl=None,
        )

    with pytest.raises(ValueError, match="Partial replay"):
        IngestionEvidencePolicy(
            endpoint="/ingest/impossible",
            entity_type="impossible",
            classification=PayloadClassification.INTERNAL,
            durable_representation=DurablePayloadRepresentation.SOURCE_SAFE_REPLAY,
            replay_eligible=False,
            partial_replay_eligible=True,
            replay_ttl=None,
        )

    with pytest.raises(ValueError, match="cannot declare a replay TTL"):
        IngestionEvidencePolicy(
            endpoint="/ingest/impossible",
            entity_type="impossible",
            classification=PayloadClassification.INTERNAL,
            durable_representation=DurablePayloadRepresentation.FINGERPRINT_ONLY,
            replay_eligible=False,
            partial_replay_eligible=False,
            replay_ttl=timedelta(hours=1),
        )


def test_registry_rejects_duplicate_endpoint() -> None:
    policy = INGESTION_EVIDENCE_POLICY_REGISTRY.require("/ingest/instruments")

    with pytest.raises(ValueError, match="endpoints must be unique"):
        IngestionEvidencePolicyRegistry((policy, policy))
