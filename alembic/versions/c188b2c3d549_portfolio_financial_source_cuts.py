"""Frozen neutral source custody, acquired captures and fenced work. No economic backfill.

Revision ID: c188b2c3d549
Revises: c187b2c3d548
"""

import sqlalchemy as sa

from alembic import op

revision = "c188b2c3d549"
down_revision = "c187b2c3d548"
branch_labels = None
depends_on = None

# Migration-local frozen PostgreSQL DDL; mutable application models never execute here.
CREATE_DDL = (
    """
    CREATE TABLE portfolio_financial_source_captures ( tenant_id VARCHAR(128) NOT NULL, capture_id
    VARCHAR(64) NOT NULL, source_product VARCHAR(64) NOT NULL, product_version VARCHAR(32) NOT
    NULL, selector_hash VARCHAR(64) NOT NULL, typed_content_hash VARCHAR(64) NOT NULL, raw_hash
    VARCHAR(64) NOT NULL, byte_count BIGINT NOT NULL, segment_count BIGINT NOT NULL, serializer_id
    VARCHAR(128) NOT NULL, mime_type VARCHAR(128) NOT NULL, source_context JSON NOT NULL,
    original_supplier_digest VARCHAR(64), original_supplier_reference VARCHAR(128), PRIMARY KEY
    (tenant_id, capture_id), CHECK (capture_id ~ '^[0-9a-f]{64}$' AND selector_hash ~
    '^[0-9a-f]{64}$' AND typed_content_hash ~ '^[0-9a-f]{64}$' AND raw_hash ~ '^[0-9a-f]{64}$'),
    CHECK (byte_count >= 0 AND segment_count > 0), CHECK
    (jsonb_typeof(source_context::jsonb)='object'), CHECK ((original_supplier_digest IS NULL) =
    (original_supplier_reference IS NULL)), CHECK (original_supplier_digest IS NULL OR
    original_supplier_digest ~ '^[0-9a-f]{64}$') )
    """,
    """
    CREATE INDEX ix_financial_capture_exact_source ON portfolio_financial_source_captures
    (tenant_id, source_product, selector_hash, raw_hash)
    """,
    """
    CREATE TABLE portfolio_financial_source_cut_chunks ( chunk_index BIGINT NOT NULL, typed_hash
    VARCHAR(64) NOT NULL, raw_hash VARCHAR(64) NOT NULL, raw_bytes BYTEA NOT NULL, row_count
    BIGINT NOT NULL, received_at TIMESTAMP WITH TIME ZONE NOT NULL, receipt_job_id VARCHAR NOT
    NULL, tenant_id VARCHAR(128) NOT NULL, product_name VARCHAR(64) NOT NULL, source_system
    VARCHAR(128) NOT NULL, registry_scope_id VARCHAR(128) NOT NULL, source_cut_id VARCHAR(128) NOT
    NULL, revision BIGINT NOT NULL, PRIMARY KEY (chunk_index, tenant_id, product_name,
    source_system, registry_scope_id, source_cut_id, revision), FOREIGN KEY(tenant_id,
    receipt_job_id) REFERENCES ingestion_jobs (tenant_id, job_id), CHECK (product_name IN
    ('PortfolioHistoricalRegistry','PortfolioFinancialSourceCut')), CHECK (revision > 0 AND
    chunk_index >= 0 AND row_count BETWEEN 0 AND 500), CHECK (octet_length(raw_bytes) BETWEEN 1
    AND 1048576), CHECK (typed_hash ~ '^[0-9a-f]{64}$' AND raw_hash ~ '^[0-9a-f]{64}$'), CHECK
    (isfinite(received_at)) )
    """,
    """
    CREATE TABLE portfolio_financial_source_cut_manifests ( content_hash VARCHAR(64) NOT NULL,
    raw_hash VARCHAR(64) NOT NULL, raw_bytes BYTEA NOT NULL, declaration JSON NOT NULL, row_count
    BIGINT NOT NULL, chunk_count BIGINT NOT NULL, received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    receipt_job_id VARCHAR NOT NULL, tenant_id VARCHAR(128) NOT NULL, product_name VARCHAR(64) NOT
    NULL, source_system VARCHAR(128) NOT NULL, registry_scope_id VARCHAR(128) NOT NULL,
    source_cut_id VARCHAR(128) NOT NULL, revision BIGINT NOT NULL, PRIMARY KEY (tenant_id,
    product_name, source_system, registry_scope_id, source_cut_id, revision), UNIQUE (tenant_id,
    product_name, source_system, registry_scope_id, source_cut_id, revision, content_hash),
    FOREIGN KEY(tenant_id, receipt_job_id) REFERENCES ingestion_jobs (tenant_id, job_id), CHECK
    (product_name IN ('PortfolioHistoricalRegistry','PortfolioFinancialSourceCut')), CHECK
    (revision > 0 AND row_count >= 0 AND chunk_count >= 0), CHECK (content_hash ~ '^[0-9a-f]{64}$'
    AND isfinite(received_at)), CHECK (jsonb_typeof(declaration::jsonb) = 'object'), CHECK
    (raw_hash ~ '^[0-9a-f]{64}$' AND octet_length(raw_bytes) BETWEEN 1 AND 1048576) )
    """,
    """
    CREATE INDEX ix_financial_manifest_exact_root ON portfolio_financial_source_cut_manifests
    (tenant_id, product_name, content_hash)
    """,
    """
    CREATE TABLE portfolio_financial_source_capture_segments ( tenant_id VARCHAR(128) NOT NULL,
    capture_id VARCHAR(64) NOT NULL, segment_index BIGINT NOT NULL, raw_bytes BYTEA NOT NULL,
    PRIMARY KEY (tenant_id, capture_id, segment_index), FOREIGN KEY(tenant_id, capture_id)
    REFERENCES portfolio_financial_source_captures (tenant_id, capture_id), CHECK (segment_index
    >= 0 AND octet_length(raw_bytes) <= 524288) )
    """,
    """
    CREATE TABLE portfolio_financial_source_cut_inputs ( portfolio_id VARCHAR COLLATE "C" NOT
    NULL, chunk_index BIGINT NOT NULL, content_hash VARCHAR(64) NOT NULL, declaration JSON NOT
    NULL, tenant_id VARCHAR(128) NOT NULL, product_name VARCHAR(64) NOT NULL, source_system
    VARCHAR(128) NOT NULL, registry_scope_id VARCHAR(128) NOT NULL, source_cut_id VARCHAR(128) NOT
    NULL, revision BIGINT NOT NULL, PRIMARY KEY (portfolio_id, tenant_id, product_name,
    source_system, registry_scope_id, source_cut_id, revision), FOREIGN KEY(tenant_id,
    product_name, source_system, registry_scope_id, source_cut_id, revision, chunk_index)
    REFERENCES portfolio_financial_source_cut_chunks (tenant_id, product_name, source_system,
    registry_scope_id, source_cut_id, revision, chunk_index), FOREIGN KEY(tenant_id, portfolio_id)
    REFERENCES portfolios (tenant_id, portfolio_id), CHECK (product_name =
    'PortfolioFinancialSourceCut'), CHECK (content_hash ~ '^[0-9a-f]{64}$' AND
    jsonb_typeof(declaration::jsonb)='object') )
    """,
    """
    CREATE INDEX ix_financial_cut_portfolio_revision ON portfolio_financial_source_cut_inputs
    (tenant_id, portfolio_id, source_system, revision)
    """,
    """
    CREATE TABLE portfolio_historical_registry_members ( provider_namespace VARCHAR(128) COLLATE
    "C" NOT NULL, source_member_id VARCHAR(128) COLLATE "C" NOT NULL, chunk_index BIGINT NOT NULL,
    core_portfolio_id VARCHAR, member_revision BIGINT NOT NULL, content_hash VARCHAR(64) NOT NULL,
    declaration JSON NOT NULL, tenant_id VARCHAR(128) NOT NULL, product_name VARCHAR(64) NOT NULL,
    source_system VARCHAR(128) NOT NULL, registry_scope_id VARCHAR(128) NOT NULL, source_cut_id
    VARCHAR(128) NOT NULL, revision BIGINT NOT NULL, PRIMARY KEY (provider_namespace,
    source_member_id, tenant_id, product_name, source_system, registry_scope_id, source_cut_id,
    revision), FOREIGN KEY(tenant_id, product_name, source_system, registry_scope_id,
    source_cut_id, revision, chunk_index) REFERENCES portfolio_financial_source_cut_chunks
    (tenant_id, product_name, source_system, registry_scope_id, source_cut_id, revision,
    chunk_index), FOREIGN KEY(tenant_id, core_portfolio_id) REFERENCES portfolios (tenant_id,
    portfolio_id), CHECK (product_name = 'PortfolioHistoricalRegistry' AND member_revision > 0),
    CHECK (content_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(declaration::jsonb)='object') )
    """,
    """
    CREATE INDEX ix_registry_member_core_portfolio ON portfolio_historical_registry_members
    (tenant_id, core_portfolio_id, registry_scope_id, revision)
    """,
    """
    CREATE TABLE portfolio_financial_source_cut_heads ( tenant_id VARCHAR(128) NOT NULL,
    product_name VARCHAR(64) NOT NULL, source_system VARCHAR(128) NOT NULL, registry_scope_id
    VARCHAR(128) NOT NULL, source_cut_id VARCHAR(128) NOT NULL, revision BIGINT NOT NULL,
    content_hash VARCHAR(64) NOT NULL, PRIMARY KEY (tenant_id, product_name, source_system,
    registry_scope_id, source_cut_id), FOREIGN KEY(tenant_id, product_name, source_system,
    registry_scope_id, source_cut_id, revision, content_hash) REFERENCES
    portfolio_financial_source_cut_manifests (tenant_id, product_name, source_system,
    registry_scope_id, source_cut_id, revision, content_hash), CHECK (product_name IN
    ('PortfolioHistoricalRegistry','PortfolioFinancialSourceCut')) )
    """,
    """
    CREATE TABLE portfolio_financial_source_cut_work ( work_id VARCHAR(36) NOT NULL,
    partition_index BIGINT DEFAULT '0' NOT NULL, tenant_id VARCHAR(128) NOT NULL, product_name
    VARCHAR(64) NOT NULL, source_system VARCHAR(128) NOT NULL, registry_scope_id VARCHAR(128) NOT
    NULL, source_cut_id VARCHAR(128) NOT NULL, revision BIGINT NOT NULL, content_hash VARCHAR(64)
    NOT NULL, receipt_job_id VARCHAR NOT NULL, status VARCHAR(16) DEFAULT 'PENDING' NOT NULL,
    lease_token VARCHAR(36), lease_expires_at TIMESTAMP WITH TIME ZONE, checkpoint JSON NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, attempts BIGINT
    DEFAULT '0' NOT NULL, last_error_code VARCHAR(64), PRIMARY KEY (work_id), UNIQUE (tenant_id,
    product_name, source_system, registry_scope_id, source_cut_id, revision, partition_index),
    FOREIGN KEY(tenant_id, product_name, source_system, registry_scope_id, source_cut_id,
    revision, content_hash) REFERENCES portfolio_financial_source_cut_manifests (tenant_id,
    product_name, source_system, registry_scope_id, source_cut_id, revision, content_hash),
    FOREIGN KEY(tenant_id, receipt_job_id) REFERENCES ingestion_jobs (tenant_id, job_id), CHECK
    (status IN ('PENDING','CLAIMED','COMPLETED','FAILED') AND attempts >= 0), CHECK
    (partition_index >= 0), CHECK ((status = 'CLAIMED' AND lease_token IS NOT NULL AND
    lease_expires_at IS NOT NULL) OR (status <> 'CLAIMED' AND lease_token IS NULL AND
    lease_expires_at IS NULL)), CHECK (jsonb_typeof(checkpoint::jsonb)='object' AND
    isfinite(available_at)) )
    """,
    """
    CREATE INDEX ix_financial_source_work_claim ON portfolio_financial_source_cut_work (status,
    available_at, tenant_id, work_id)
    """,
    """
    CREATE TABLE portfolio_financial_source_capture_links ( portfolio_id VARCHAR COLLATE "C" NOT
    NULL, role VARCHAR(32) NOT NULL, page_index BIGINT NOT NULL, capture_id VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL, product_name VARCHAR(64) NOT NULL, source_system VARCHAR(128)
    NOT NULL, registry_scope_id VARCHAR(128) NOT NULL, source_cut_id VARCHAR(128) NOT NULL,
    revision BIGINT NOT NULL, PRIMARY KEY (portfolio_id, role, page_index, tenant_id,
    product_name, source_system, registry_scope_id, source_cut_id, revision), FOREIGN
    KEY(tenant_id, product_name, source_system, registry_scope_id, source_cut_id, revision,
    portfolio_id) REFERENCES portfolio_financial_source_cut_inputs (tenant_id, product_name,
    source_system, registry_scope_id, source_cut_id, revision, portfolio_id), FOREIGN
    KEY(tenant_id, capture_id) REFERENCES portfolio_financial_source_captures (tenant_id,
    capture_id), CHECK (page_index >= 0 AND role IN
    ('PRIOR_ASSETS','MONTH_END_ASSETS','CASH','READINESS','FLOWS')) )
    """,
)

TABLES = (
    "portfolio_financial_source_captures",
    "portfolio_financial_source_cut_chunks",
    "portfolio_financial_source_cut_manifests",
    "portfolio_financial_source_capture_segments",
    "portfolio_financial_source_cut_inputs",
    "portfolio_historical_registry_members",
    "portfolio_financial_source_cut_heads",
    "portfolio_financial_source_cut_work",
    "portfolio_financial_source_capture_links",
)
IMMUTABLE_TABLES = (
    "portfolio_financial_source_cut_manifests",
    "portfolio_financial_source_cut_chunks",
    "portfolio_historical_registry_members",
    "portfolio_financial_source_cut_inputs",
    "portfolio_financial_source_captures",
    "portfolio_financial_source_capture_segments",
    "portfolio_financial_source_capture_links",
)


def upgrade():
    for statement in CREATE_DDL:
        op.execute(sa.text(statement))
    for table in IMMUTABLE_TABLES:
        op.execute(
            sa.text(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION reject_portfolio_source_observation_mutation()"
            )
        )
    for table in TABLES:
        op.execute(
            sa.text(
                f"CREATE TRIGGER {table}_truncate_guard BEFORE TRUNCATE ON {table} "
                "FOR EACH STATEMENT EXECUTE FUNCTION "
                "guard_empty_portfolio_source_observation_truncate()"
            )
        )


def downgrade():
    # One transaction/lock set fences every row check and subsequent drop.
    op.execute(sa.text("LOCK TABLE " + ", ".join(sorted(TABLES)) + " IN ACCESS EXCLUSIVE MODE"))
    for table in TABLES:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("nonempty neutral source custody cannot be downgraded")
    # No CASCADE: an unknown dependent object refuses and rolls back the migration.
    for table in reversed(TABLES):
        op.drop_table(table)
