from datetime import UTC, date, datetime

import pytest
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.reconciliation_quality import UNKNOWN
from portfolio_common.reconstruction_identity import CURRENT_RESTATEMENT_VERSION
from src.services.query_service.app.dtos.analytics_input_dto import (
    PortfolioAnalyticsTimeseriesResponse,
    PositionAnalyticsTimeseriesResponse,
)
from src.services.query_service.app.dtos.core_snapshot_dto import CoreSnapshotResponse
from src.services.query_service.app.dtos.operations_dto import (
    LineageKeyListResponse,
    ReconciliationFindingListResponse,
    ReconciliationRunListResponse,
    ReprocessingJobListResponse,
    ReprocessingKeyListResponse,
)
from src.services.query_service.app.dtos.position_dto import PortfolioPositionsResponse
from src.services.query_service.app.dtos.reporting_dto import (
    ActivitySummaryResponse,
    CashBalancesResponse,
    HoldingsSnapshotResponse,
    IncomeSummaryResponse,
)
from src.services.query_service.app.dtos.source_data_product_identity import (
    source_data_product_runtime_metadata,
)
from src.services.query_service.app.dtos.transaction_dto import PaginatedTransactionResponse


@pytest.mark.parametrize(
    ("response_model", "product_name"),
    [
        (PortfolioAnalyticsTimeseriesResponse, "PortfolioTimeseriesInput"),
        (PositionAnalyticsTimeseriesResponse, "PositionTimeseriesInput"),
        (CoreSnapshotResponse, "PortfolioStateSnapshot"),
        (LineageKeyListResponse, "IngestionEvidenceBundle"),
        (ReprocessingJobListResponse, "IngestionEvidenceBundle"),
        (ReprocessingKeyListResponse, "IngestionEvidenceBundle"),
        (ReconciliationRunListResponse, "ReconciliationEvidenceBundle"),
        (ReconciliationFindingListResponse, "ReconciliationEvidenceBundle"),
        (PortfolioPositionsResponse, "HoldingsAsOf"),
        (CashBalancesResponse, "HoldingsAsOf"),
        (HoldingsSnapshotResponse, "HoldingsAsOf"),
        (PaginatedTransactionResponse, "TransactionLedgerWindow"),
        (IncomeSummaryResponse, "TransactionLedgerWindow"),
        (ActivitySummaryResponse, "TransactionLedgerWindow"),
    ],
)
def test_query_service_product_responses_declare_product_identity_defaults(
    response_model, product_name
) -> None:
    assert response_model.model_fields["product_name"].default == product_name
    assert response_model.model_fields["product_version"].default == "v1"


def test_source_data_product_runtime_metadata_defaults_to_truthful_supportability_fields() -> None:
    generated_at = datetime(2026, 4, 15, 1, 30, tzinfo=UTC)

    metadata = source_data_product_runtime_metadata(
        as_of_date=date(2026, 3, 26),
        generated_at=generated_at,
    )

    assert metadata == {
        "tenant_id": None,
        "generated_at": generated_at,
        "as_of_date": date(2026, 3, 26),
        "restatement_version": CURRENT_RESTATEMENT_VERSION,
        "reconciliation_status": UNKNOWN,
        "data_quality_status": UNKNOWN,
        "latest_evidence_timestamp": None,
        "source_batch_fingerprint": None,
        "snapshot_id": None,
        "policy_version": None,
        "correlation_id": None,
    }


def test_source_data_product_runtime_metadata_preserves_request_correlation_id() -> None:
    token = correlation_id_var.set("QRY-corr-1")
    try:
        metadata = source_data_product_runtime_metadata(
            as_of_date=date(2026, 3, 26),
            generated_at=datetime(2026, 4, 15, 1, 30, tzinfo=UTC),
        )
    finally:
        correlation_id_var.reset(token)

    assert metadata["correlation_id"] == "QRY-corr-1"
    assert metadata["data_quality_status"] == UNKNOWN


def test_source_data_product_runtime_metadata_accepts_truthful_runtime_lineage() -> None:
    latest_evidence_timestamp = datetime(2026, 4, 15, 1, 29, tzinfo=UTC)

    metadata = source_data_product_runtime_metadata(
        as_of_date=date(2026, 3, 26),
        generated_at=datetime(2026, 4, 15, 1, 30, tzinfo=UTC),
        tenant_id="tenant_sg_pb",
        latest_evidence_timestamp=latest_evidence_timestamp,
        source_batch_fingerprint="sbf_abc",
        snapshot_id="pss_abc",
        policy_version="tenant-default-v1",
    )

    assert metadata["tenant_id"] == "tenant_sg_pb"
    assert metadata["latest_evidence_timestamp"] == latest_evidence_timestamp
    assert metadata["source_batch_fingerprint"] == "sbf_abc"
    assert metadata["snapshot_id"] == "pss_abc"
    assert metadata["policy_version"] == "tenant-default-v1"
