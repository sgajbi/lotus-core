"""Retain canonical FX source revisions and sealed membership without legacy backfill.

Revision ID: c179b2c3d540
Revises: c178b2c3d539
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c179b2c3d540"
down_revision = "c178b2c3d539"
branch_labels = None
depends_on = None


def _scope_columns() -> list[sa.Column]:
    return [
        sa.Column(name, sa.String(128), nullable=False)
        for name in ("tenant_id", "provider_id", "source_id")
    ]


def _text_checks(prefix: str, columns: tuple[str, ...]) -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint(
            f"{column} <> '' AND {column} = btrim({column}) AND {column} !~ '[[:cntrl:]]'",
            name=f"ck_{prefix}_{column}",
        )
        for column in columns
    ]


def _digest_checks(prefix: str, columns: tuple[str, ...]) -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint(f"{column} ~ '^[0-9a-f]{{64}}$'", name=f"ck_{prefix}_{column}")
        for column in columns
    ]


def upgrade() -> None:
    # Legacy fx_rates, v1 broker records and pending ingestion jobs remain unchanged.
    # Deploy this schema and v2-aware consumers before enabling a canonical producer.
    op.create_table(
        "fx_rate_source_cuts",
        sa.Column("cut_id", sa.String(64), primary_key=True),
        *_scope_columns(),
        sa.Column("source_cut_reference", sa.String(128), nullable=False),
        sa.Column("source_cut_revision", sa.String(128), nullable=False),
        sa.Column("source_observed_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("members", postgresql.JSONB(), nullable=False),
        sa.Column("membership_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("admission_receipt", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "cut_id", "tenant_id", "provider_id", "source_id", name="uq_fx_cut_scope"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_id",
            "source_id",
            "source_cut_reference",
            "source_cut_revision",
            name="uq_fx_cut_source_version",
        ),
        sa.CheckConstraint("member_count BETWEEN 1 AND 512", name="ck_fx_cut_member_count"),
        sa.CheckConstraint(
            "jsonb_typeof(members) = 'array' AND jsonb_array_length(members) = member_count",
            name="ck_fx_cut_exact_members",
        ),
        sa.CheckConstraint(
            "isfinite(source_observed_cutoff) AND isfinite(accepted_at) "
            "AND source_observed_cutoff <= accepted_at",
            name="ck_fx_cut_time",
        ),
        *_digest_checks("fx_cut", ("cut_id", "membership_hash", "content_hash")),
        *_text_checks(
            "fx_cut",
            (
                "tenant_id",
                "provider_id",
                "source_id",
                "source_cut_reference",
                "source_cut_revision",
            ),
        ),
    )
    op.create_index(
        "ix_fx_cut_historical_scope",
        "fx_rate_source_cuts",
        ["tenant_id", "provider_id", "source_id", "accepted_at"],
    )
    _create_revisions()
    op.execute("""
        CREATE FUNCTION refuse_fx_source_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'FX_SOURCE_AUTHORITY_IMMUTABLE' USING ERRCODE = '23514';
        END; $$;
    """)
    op.execute("""
        CREATE FUNCTION guard_empty_fx_source_truncate() RETURNS trigger
        LANGUAGE plpgsql VOLATILE AS $$
        DECLARE has_history boolean;
        BEGIN
            IF current_setting('transaction_isolation') <> 'read committed' THEN
                RAISE EXCEPTION 'FX_SOURCE_TRUNCATE_ISOLATION_REFUSED' USING ERRCODE = '23514';
            END IF;
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I)',
                           TG_TABLE_SCHEMA, TG_TABLE_NAME) INTO has_history;
            IF has_history THEN
                RAISE EXCEPTION 'FX_SOURCE_TRUNCATE_WOULD_LOSE_AUTHORITY'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END; $$;
    """)
    for table in ("fx_rate_source_cuts", "fx_rate_source_revisions"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION refuse_fx_source_mutation()"
            )
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
                "FOR EACH STATEMENT EXECUTE FUNCTION guard_empty_fx_source_truncate()"
            )
        )
    _create_cut_member_fence()


def _create_revisions() -> None:
    op.create_table(
        "fx_rate_source_revisions",
        sa.Column("revision_id", sa.String(64), primary_key=True),
        *_scope_columns(),
        sa.Column("source_record_id", sa.String(128), nullable=False),
        sa.Column("source_revision", sa.String(128), nullable=False),
        sa.Column("from_currency", sa.String(3), nullable=False),
        sa.Column("to_currency", sa.String(3), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(18, 10), nullable=False),
        sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.Column("fixing_kind", sa.String(128), nullable=False),
        sa.Column("calendar_version", sa.String(128), nullable=False),
        sa.Column("predecessor_revision_id", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("admitted_cut_id", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_id",
            "source_id",
            "source_record_id",
            "source_revision",
            name="uq_fx_revision_source_version",
        ),
        sa.UniqueConstraint(
            "revision_id",
            "tenant_id",
            "provider_id",
            "source_id",
            "source_record_id",
            "from_currency",
            "to_currency",
            "rate_date",
            name="uq_fx_revision_chain_scope",
        ),
        sa.ForeignKeyConstraint(
            ["admitted_cut_id", "tenant_id", "provider_id", "source_id"],
            [
                "fx_rate_source_cuts.cut_id",
                "fx_rate_source_cuts.tenant_id",
                "fx_rate_source_cuts.provider_id",
                "fx_rate_source_cuts.source_id",
            ],
            name="fk_fx_revision_admission_scope",
        ),
        sa.ForeignKeyConstraint(
            [
                "predecessor_revision_id",
                "tenant_id",
                "provider_id",
                "source_id",
                "source_record_id",
                "from_currency",
                "to_currency",
                "rate_date",
            ],
            [
                f"fx_rate_source_revisions.{column}"
                for column in (
                    "revision_id",
                    "tenant_id",
                    "provider_id",
                    "source_id",
                    "source_record_id",
                    "from_currency",
                    "to_currency",
                    "rate_date",
                )
            ],
            name="fk_fx_revision_same_chain",
        ),
        sa.UniqueConstraint("predecessor_revision_id", name="uq_fx_revision_single_child"),
        sa.CheckConstraint(
            "predecessor_revision_id IS NULL OR predecessor_revision_id <> revision_id",
            name="ck_fx_revision_not_self",
        ),
        sa.CheckConstraint(
            "from_currency ~ '^[A-Z]{3}$' AND to_currency ~ '^[A-Z]{3}$' "
            "AND from_currency <> to_currency",
            name="ck_fx_revision_pair",
        ),
        sa.CheckConstraint("rate > 0", name="ck_fx_revision_positive_rate"),
        sa.CheckConstraint(
            "CAST(rate AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_fx_revision_finite_rate",
        ),
        sa.CheckConstraint(
            "isfinite(source_observed_at) AND isfinite(accepted_at) "
            "AND source_observed_at <= accepted_at",
            name="ck_fx_revision_time",
        ),
        *_digest_checks("fx_revision", ("revision_id", "content_hash")),
        *_text_checks(
            "fx_revision",
            (
                "tenant_id",
                "provider_id",
                "source_id",
                "source_record_id",
                "source_revision",
                "fixing_kind",
                "calendar_version",
            ),
        ),
    )
    op.create_index(
        "uq_fx_revision_single_root",
        "fx_rate_source_revisions",
        ["tenant_id", "provider_id", "source_id", "source_record_id"],
        unique=True,
        postgresql_where=sa.text("predecessor_revision_id IS NULL"),
    )


def _create_cut_member_fence() -> None:
    op.execute("""
        CREATE FUNCTION require_complete_fx_source_cut() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE matching_count integer; distinct_records integer;
        BEGIN
            SELECT count(DISTINCT r.revision_id), count(DISTINCT r.source_record_id)
            INTO matching_count, distinct_records
            FROM jsonb_array_elements(NEW.members) AS member
            JOIN fx_rate_source_revisions r ON r.revision_id = member->>'revision_id'
                AND r.content_hash = member->>'content_hash'
                AND r.tenant_id = NEW.tenant_id AND r.provider_id = NEW.provider_id
                AND r.source_id = NEW.source_id
                AND r.source_observed_at <= NEW.source_observed_cutoff;
            IF matching_count <> NEW.member_count OR distinct_records <> NEW.member_count THEN
                RAISE EXCEPTION 'FX_SOURCE_CUT_MEMBERS_NOT_RETAINED' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$;
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER trg_fx_source_cut_complete
        AFTER INSERT ON fx_rate_source_cuts DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION require_complete_fx_source_cut();
    """)
    op.execute("""
        CREATE FUNCTION require_fx_revision_admitted_membership() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM fx_rate_source_cuts c,
                              jsonb_array_elements(c.members) AS member
                WHERE c.cut_id = NEW.admitted_cut_id
                  AND c.tenant_id = NEW.tenant_id AND c.provider_id = NEW.provider_id
                  AND c.source_id = NEW.source_id AND c.accepted_at = NEW.accepted_at
                  AND NEW.source_observed_at <= c.source_observed_cutoff
                  AND member->>'revision_id' = NEW.revision_id
                  AND member->>'content_hash' = NEW.content_hash
            ) THEN
                RAISE EXCEPTION 'FX_SOURCE_REVISION_NOT_ADMITTED_MEMBER'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$;
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER trg_fx_source_revision_admitted
        AFTER INSERT ON fx_rate_source_revisions DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION require_fx_revision_admitted_membership();
    """)


def downgrade() -> None:
    # Never erase retained canonical authority to make an old deployment start.
    # A populated database requires forward fix or independently governed restore.
    if op.get_bind().scalar(sa.text("SHOW transaction_isolation")) != "read committed":
        raise RuntimeError("FX_SOURCE_DOWNGRADE_ISOLATION_REFUSED")
    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.execute("LOCK TABLE fx_rate_source_cuts, fx_rate_source_revisions IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM fx_rate_source_cuts)
               OR EXISTS (SELECT 1 FROM fx_rate_source_revisions) THEN
                RAISE EXCEPTION 'FX_SOURCE_DOWNGRADE_WOULD_LOSE_AUTHORITY';
            END IF;
        END; $$;
    """)
    op.drop_table("fx_rate_source_revisions")
    op.drop_table("fx_rate_source_cuts")
    op.execute("DROP FUNCTION require_complete_fx_source_cut()")
    op.execute("DROP FUNCTION require_fx_revision_admitted_membership()")
    op.execute("DROP FUNCTION refuse_fx_source_mutation()")
    op.execute("DROP FUNCTION guard_empty_fx_source_truncate()")
