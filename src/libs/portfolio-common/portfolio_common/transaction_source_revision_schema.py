"""Nonnumeric contract for immutable transaction source revisions.

Persistence locks retained source and verifies complete receipt authority.
The fact and notification share the consumer-owned UOW; predecessor links,
not wall-clock timestamps, select the source head. No economic row is replayed.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)


class TransactionSourceRevisionColumns:
    root_raw_sha256 = Column(String(64), nullable=False)
    predecessor_revision_id = Column(String(128), nullable=True)
    expected_head_id = Column(String(128), nullable=False)
    expected_head_sha256 = Column(String(64), nullable=False)
    command_id = Column(String(128), nullable=False)
    operation_id = Column(String(128), nullable=False)
    canonical_request_sha256 = Column(String(64), nullable=False)
    attestation_sha256 = Column(String(64), nullable=False)
    original_output_sha256 = Column(String(64), nullable=False)
    revision_sha256 = Column(String(64), nullable=False)
    original_local_present = Column(Boolean, nullable=False)
    original_base_present = Column(Boolean, nullable=False)
    qualification_receipt = Column(JSON, nullable=False)
    authorization_claims = Column(JSON, nullable=False)
    reason = Column(String(512), nullable=False)
    correlation_id = Column(String(128), nullable=False)
    trace_id = Column(String(128), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def transaction_source_revision_table_args() -> tuple:
    return (
        ForeignKeyConstraint(
            ["transaction_id", "portfolio_id"],
            ["transactions.transaction_id", "transactions.portfolio_id"],
            name="fk_source_revision_transaction_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "operation_id"],
            ["ingestion_jobs.tenant_id", "ingestion_jobs.job_id"],
            name="fk_source_revision_operation_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.portfolio_id"],
            name="fk_source_revision_portfolio_owner",
        ),
        UniqueConstraint("tenant_id", "command_id", name="uq_source_revision_command"),
        UniqueConstraint("tenant_id", "operation_id", name="uq_source_revision_operation"),
        UniqueConstraint(
            "revision_id",
            "tenant_id",
            "transaction_id",
            "root_raw_event_id",
            "revision_sha256",
            name="uq_source_revision_chain_identity",
        ),
        ForeignKeyConstraint(
            [
                "predecessor_revision_id",
                "tenant_id",
                "transaction_id",
                "root_raw_event_id",
                "expected_head_sha256",
            ],
            [
                "transaction_source_revisions.revision_id",
                "transaction_source_revisions.tenant_id",
                "transaction_source_revisions.transaction_id",
                "transaction_source_revisions.root_raw_event_id",
                "transaction_source_revisions.revision_sha256",
            ],
            name="fk_source_revision_same_chain_predecessor",
        ),
        UniqueConstraint("predecessor_revision_id", name="uq_source_revision_child"),
        Index(
            "uq_source_revision_initial",
            "tenant_id",
            "transaction_id",
            unique=True,
            postgresql_where=text("predecessor_revision_id IS NULL"),
        ),
        CheckConstraint(
            "predecessor_revision_id IS NULL OR predecessor_revision_id <> revision_id",
            name="ck_source_revision_not_self",
        ),
        CheckConstraint(
            "expected_head_id = coalesce(predecessor_revision_id, root_raw_event_id::text)",
            name="ck_source_revision_expected_head",
        ),
        CheckConstraint(
            "predecessor_revision_id IS NOT NULL OR expected_head_sha256 = root_raw_sha256",
            name="ck_source_revision_root_head_hash",
        ),
        CheckConstraint(
            "NOT original_local_present OR NOT original_base_present",
            name="ck_source_revision_original_incomplete",
        ),
        CheckConstraint(
            "(original_local_present OR source_local = 0) AND "
            "(original_base_present OR source_base = 0)",
            name="ck_source_revision_missing_confirmation_zero",
        ),
        *(
            CheckConstraint(f"{column} ~ '^[0-9a-f]{{64}}$'", name=f"ck_source_revision_{column}")
            for column in (
                "root_raw_sha256",
                "expected_head_sha256",
                "canonical_request_sha256",
                "attestation_sha256",
                "original_output_sha256",
                "revision_sha256",
            )
        ),
        *(
            CheckConstraint(
                f"length(btrim({column})) > 0", name=f"ck_source_revision_{column}_nonblank"
            )
            for column in (
                "revision_id",
                "command_id",
                "operation_id",
                "reason",
                "correlation_id",
                "trace_id",
            )
        ),
    )
