"""Materialize replayable cashflow source cuts at the durable write boundary.

Revision ID: c169b2c3d530
Revises: c168b2c3d52f
Create Date: 2026-09-13

Cashflow summary and projection reads must not re-hash an unbounded portfolio
history.  This projection is maintained in the same PostgreSQL transaction as
the authoritative cashflow/transaction mutation.  The refresh function locks
the portfolio root before reading source facts so a late writer cannot overwrite
a cut produced by a newer committed writer.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c169b2c3d530"
down_revision: str | Sequence[str] | None = "c168b2c3d52f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "portfolio_cashflow_source_cuts"
_QUEUE_TABLE = "portfolio_cashflow_source_cut_refresh_queue"
_REFRESH = "refresh_portfolio_cashflow_source_cut"
_STAGE = "stage_portfolio_cashflow_source_cut_refresh"
_FLUSH = "flush_deferred_portfolio_cashflow_source_cuts"
_CASHFLOW_TRIGGER_PREFIX = "trg_cashflows_refresh_portfolio_source_cut"
_TRANSACTION_TRIGGER_PREFIX = "trg_transactions_refresh_portfolio_source_cut"
_PORTFOLIO_TRIGGER = "trg_portfolios_refresh_cashflow_source_cut"


def upgrade() -> None:
    """Create and backfill the transactionally maintained cashflow-cut projection."""

    op.create_table(
        _TABLE,
        sa.Column("portfolio_id", sa.String(), primary_key=True, nullable=False),
        sa.Column("portfolio_base_currency", sa.String(length=3), nullable=False),
        sa.Column("cashflow_revision_count", sa.BigInteger(), nullable=False),
        sa.Column("cashflow_revision_digest", sa.String(length=64), nullable=False),
        sa.Column("settlement_revision_count", sa.BigInteger(), nullable=False),
        sa.Column("settlement_revision_digest", sa.String(length=64), nullable=False),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.portfolio_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        _QUEUE_TABLE,
        sa.Column("transaction_id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("portfolio_id", sa.String(), primary_key=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.portfolio_id"],
            ondelete="CASCADE",
        ),
    )
    op.execute(sa.text(_refresh_function_sql()))
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_STAGE}(target_portfolio_id text)
            RETURNS void
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF current_setting('lotus.cashflow_source_cut_deferred', true) = 'on' THEN
                    INSERT INTO {_QUEUE_TABLE} (transaction_id, portfolio_id)
                    VALUES (txid_current(), target_portfolio_id)
                    ON CONFLICT DO NOTHING;
                    RETURN;
                END IF;
                PERFORM {_REFRESH}(target_portfolio_id);
            END;
            $$;

            CREATE FUNCTION {_FLUSH}()
            RETURNS void
            LANGUAGE plpgsql
            AS $$
            DECLARE
                queued_portfolio record;
            BEGIN
                -- One transaction-processing unit of work can rebuild many
                -- cashflows.  Refresh each affected root once, in a stable
                -- order, immediately before that unit commits.
                FOR queued_portfolio IN
                    SELECT portfolio_id
                    FROM {_QUEUE_TABLE}
                    WHERE transaction_id = txid_current()
                    ORDER BY portfolio_id
                LOOP
                    PERFORM {_REFRESH}(queued_portfolio.portfolio_id);
                END LOOP;
                DELETE FROM {_QUEUE_TABLE}
                WHERE transaction_id = txid_current();
            END;
            $$;

            CREATE FUNCTION refresh_portfolio_cashflow_source_cut_trigger()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    PERFORM {_STAGE}(portfolio_id)
                    FROM (SELECT DISTINCT portfolio_id FROM new_rows) AS affected
                    ORDER BY portfolio_id;
                    RETURN NULL;
                END IF;

                IF TG_OP = 'DELETE' THEN
                    PERFORM {_STAGE}(portfolio_id)
                    FROM (SELECT DISTINCT portfolio_id FROM old_rows) AS affected
                    ORDER BY portfolio_id;
                    RETURN NULL;
                END IF;

                IF TG_TABLE_NAME = 'cashflows' THEN
                    PERFORM {_STAGE}(portfolio_id)
                    FROM (
                        SELECT DISTINCT new_rows.portfolio_id
                        FROM new_rows
                        JOIN old_rows USING (id)
                        WHERE (
                            new_rows.portfolio_id, new_rows.transaction_id, new_rows.epoch,
                            new_rows.cashflow_date, new_rows.amount, new_rows.currency,
                            new_rows.classification, new_rows.timing, new_rows.is_position_flow,
                            new_rows.is_portfolio_flow
                        ) IS DISTINCT FROM (
                            old_rows.portfolio_id, old_rows.transaction_id, old_rows.epoch,
                            old_rows.cashflow_date, old_rows.amount, old_rows.currency,
                            old_rows.classification, old_rows.timing, old_rows.is_position_flow,
                            old_rows.is_portfolio_flow
                        )
                        UNION
                        SELECT DISTINCT old_rows.portfolio_id
                        FROM new_rows
                        JOIN old_rows USING (id)
                        WHERE new_rows.portfolio_id IS DISTINCT FROM old_rows.portfolio_id
                    ) AS affected
                    ORDER BY portfolio_id;
                ELSE
                    PERFORM {_STAGE}(portfolio_id)
                    FROM (
                        SELECT DISTINCT new_rows.portfolio_id
                        FROM new_rows
                        JOIN old_rows USING (id)
                        WHERE (
                            new_rows.portfolio_id, new_rows.transaction_id,
                            new_rows.transaction_type,
                            new_rows.transaction_date, new_rows.settlement_date,
                            new_rows.gross_transaction_amount, new_rows.currency
                        ) IS DISTINCT FROM (
                            old_rows.portfolio_id, old_rows.transaction_id,
                            old_rows.transaction_type,
                            old_rows.transaction_date, old_rows.settlement_date,
                            old_rows.gross_transaction_amount, old_rows.currency
                        )
                        UNION
                        SELECT DISTINCT old_rows.portfolio_id
                        FROM new_rows
                        JOIN old_rows USING (id)
                        WHERE new_rows.portfolio_id IS DISTINCT FROM old_rows.portfolio_id
                    ) AS affected
                    ORDER BY portfolio_id;
                END IF;

                -- A deferred transaction-processing unit of work must not
                -- take the shared cut-row lock for timestamp chronology on
                -- every source statement.  Stage every updated root (not
                -- only economic changes) and let its single durable flush
                -- publish both the logical cut and timestamp-only chronology.
                IF current_setting('lotus.cashflow_source_cut_deferred', true) = 'on' THEN
                    PERFORM {_STAGE}(portfolio_id)
                    FROM (
                        SELECT DISTINCT portfolio_id FROM new_rows
                        UNION
                        SELECT DISTINCT portfolio_id FROM old_rows
                    ) AS affected
                    ORDER BY portfolio_id;
                    RETURN NULL;
                END IF;

                -- A timestamp-only update is chronology only when it belongs
                -- to this cut.  Maintenance on an unrelated transaction, or
                -- a superseded cashflow revision, must not recast an unchanged
                -- product proof envelope.
                IF TG_TABLE_NAME = 'transactions' THEN
                    UPDATE {_TABLE} AS cut
                    SET materialized_at = source.latest_at
                    FROM (
                        SELECT portfolio_id, max(updated_at) AS latest_at
                        FROM new_rows
                        WHERE transaction_type IN ('DEPOSIT', 'WITHDRAWAL')
                        GROUP BY portfolio_id
                    ) AS source
                    WHERE cut.portfolio_id = source.portfolio_id
                      AND source.latest_at > cut.materialized_at;
                ELSE
                    UPDATE {_TABLE} AS cut
                    SET materialized_at = source.latest_at
                    FROM (
                        SELECT updated.portfolio_id, max(updated.updated_at) AS latest_at
                        FROM new_rows AS updated
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM cashflows AS newer
                            WHERE newer.portfolio_id = updated.portfolio_id
                              AND newer.transaction_id = updated.transaction_id
                              AND (newer.epoch, newer.id) > (updated.epoch, updated.id)
                        )
                        GROUP BY updated.portfolio_id
                    ) AS source
                    WHERE cut.portfolio_id = source.portfolio_id
                      AND source.latest_at > cut.materialized_at;
                END IF;
                RETURN NULL;
            END;
            $$;

            CREATE TRIGGER {_CASHFLOW_TRIGGER_PREFIX}_insert
            AFTER INSERT ON cashflows
            REFERENCING NEW TABLE AS new_rows
            FOR EACH STATEMENT EXECUTE FUNCTION refresh_portfolio_cashflow_source_cut_trigger();

            CREATE TRIGGER {_CASHFLOW_TRIGGER_PREFIX}_update
            AFTER UPDATE ON cashflows
            REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
            FOR EACH STATEMENT EXECUTE FUNCTION refresh_portfolio_cashflow_source_cut_trigger();

            CREATE TRIGGER {_CASHFLOW_TRIGGER_PREFIX}_delete
            AFTER DELETE ON cashflows
            REFERENCING OLD TABLE AS old_rows
            FOR EACH STATEMENT EXECUTE FUNCTION refresh_portfolio_cashflow_source_cut_trigger();

            CREATE TRIGGER {_TRANSACTION_TRIGGER_PREFIX}_insert
            AFTER INSERT ON transactions
            REFERENCING NEW TABLE AS new_rows
            FOR EACH STATEMENT EXECUTE FUNCTION refresh_portfolio_cashflow_source_cut_trigger();

            CREATE TRIGGER {_TRANSACTION_TRIGGER_PREFIX}_update
            AFTER UPDATE ON transactions
            REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
            FOR EACH STATEMENT EXECUTE FUNCTION refresh_portfolio_cashflow_source_cut_trigger();

            CREATE TRIGGER {_TRANSACTION_TRIGGER_PREFIX}_delete
            AFTER DELETE ON transactions
            REFERENCING OLD TABLE AS old_rows
            FOR EACH STATEMENT EXECUTE FUNCTION refresh_portfolio_cashflow_source_cut_trigger();

            CREATE FUNCTION refresh_portfolio_cashflow_source_cut_portfolio_trigger()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                PERFORM {_REFRESH}(NEW.portfolio_id);
                RETURN NEW;
            END;
            $$;

            CREATE TRIGGER {_PORTFOLIO_TRIGGER}
            AFTER INSERT OR UPDATE OF base_currency, updated_at ON portfolios
            FOR EACH ROW EXECUTE FUNCTION refresh_portfolio_cashflow_source_cut_portfolio_trigger();

            SELECT {_REFRESH}(portfolio_id)
            FROM portfolios
            ORDER BY portfolio_id;
            """
        )
    )


def downgrade() -> None:
    """Remove the derived projection and its source-table maintenance hooks."""

    op.execute(
        sa.text(
            f"""
            DROP TRIGGER IF EXISTS {_PORTFOLIO_TRIGGER} ON portfolios;
            DROP FUNCTION IF EXISTS refresh_portfolio_cashflow_source_cut_portfolio_trigger();
            DROP TRIGGER IF EXISTS {_TRANSACTION_TRIGGER_PREFIX}_delete ON transactions;
            DROP TRIGGER IF EXISTS {_TRANSACTION_TRIGGER_PREFIX}_update ON transactions;
            DROP TRIGGER IF EXISTS {_TRANSACTION_TRIGGER_PREFIX}_insert ON transactions;
            DROP TRIGGER IF EXISTS {_TRANSACTION_TRIGGER_PREFIX} ON transactions;
            DROP TRIGGER IF EXISTS {_CASHFLOW_TRIGGER_PREFIX}_delete ON cashflows;
            DROP TRIGGER IF EXISTS {_CASHFLOW_TRIGGER_PREFIX}_update ON cashflows;
            DROP TRIGGER IF EXISTS {_CASHFLOW_TRIGGER_PREFIX}_insert ON cashflows;
            DROP TRIGGER IF EXISTS {_CASHFLOW_TRIGGER_PREFIX} ON cashflows;
            DROP FUNCTION IF EXISTS refresh_portfolio_cashflow_source_cut_trigger();
            DROP FUNCTION IF EXISTS {_FLUSH}();
            DROP FUNCTION IF EXISTS {_STAGE}(text);
            DROP FUNCTION IF EXISTS {_REFRESH}(text);
            """
        )
    )
    op.execute(sa.text(f"DROP TABLE IF EXISTS {_QUEUE_TABLE}"))
    op.drop_table(_TABLE)


def _refresh_function_sql() -> str:
    """Build the canonical, fixed-width source projection refresh function."""

    return f"""
        CREATE FUNCTION {_REFRESH}(target_portfolio_id text)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
            -- Serialize refreshes after every writer has reached its durable
            -- source mutation.  A waiter takes a fresh READ COMMITTED statement
            -- snapshot after the prior writer commits, preventing stale overwrite.
            PERFORM 1 FROM portfolios
            WHERE portfolio_id = target_portfolio_id
            FOR NO KEY UPDATE;
            IF NOT FOUND THEN
                RETURN;
            END IF;

            WITH portfolio_facts AS (
                SELECT base_currency, updated_at
                FROM portfolios
                WHERE portfolio_id = target_portfolio_id
            ),
            ranked_cashflows AS (
                SELECT cashflow.*,
                       row_number() OVER (
                           PARTITION BY cashflow.transaction_id
                           ORDER BY cashflow.epoch DESC, cashflow.id DESC
                       ) AS selection_rank
                FROM cashflows AS cashflow
                WHERE cashflow.portfolio_id = target_portfolio_id
            ),
            selected_cashflows AS (
                SELECT * FROM ranked_cashflows WHERE selection_rank = 1
            ),
            cashflow_rows AS (
                SELECT encode(
                    sha256(convert_to(
                        jsonb_build_array(
                            transaction_id, epoch, cashflow_date,
                            amount, currency, classification, timing,
                            is_position_flow, is_portfolio_flow
                        )::text,
                        'UTF8'
                    )),
                    'hex'
                ) AS row_digest,
                transaction_id,
                epoch,
                id
                FROM selected_cashflows
            ),
            cashflow_evidence AS (
                       SELECT count(*) AS row_count,
                       encode(sha256(convert_to(
                           coalesce(
                               string_agg(
                                   row_digest,
                                   '' ORDER BY transaction_id COLLATE "C", epoch, id
                               ),
                               ''
                           ),
                           'UTF8'
                       )), 'hex') AS digest,
                       max(updated_at) AS latest_at
                FROM selected_cashflows
                LEFT JOIN cashflow_rows USING (transaction_id, epoch, id)
            ),
            settlement_rows AS (
                SELECT encode(
                    sha256(convert_to(
                        jsonb_build_array(
                            transaction_id, transaction_type,
                            timezone('UTC', transaction_date),
                            timezone('UTC', settlement_date),
                            gross_transaction_amount, currency
                        )::text,
                        'UTF8'
                    )),
                    'hex'
                ) AS row_digest,
                transaction_id,
                id,
                updated_at
                FROM transactions
                WHERE portfolio_id = target_portfolio_id
                  AND transaction_type IN ('DEPOSIT', 'WITHDRAWAL')
            ),
            settlement_evidence AS (
                SELECT count(*) AS row_count,
                       encode(sha256(convert_to(
                           coalesce(
                               string_agg(
                                   row_digest,
                                   '' ORDER BY transaction_id COLLATE "C", id
                               ),
                               ''
                           ),
                           'UTF8'
                       )), 'hex') AS digest,
                       max(updated_at) AS latest_at
                FROM settlement_rows
            ),
            materialization AS (
                SELECT max(observed_at) AS materialized_at
                FROM (
                    SELECT updated_at AS observed_at
                    FROM portfolio_facts
                    UNION ALL SELECT latest_at FROM cashflow_evidence
                    UNION ALL SELECT latest_at FROM settlement_evidence
                ) AS observed
            )
            INSERT INTO {_TABLE} (
                portfolio_id, portfolio_base_currency,
                cashflow_revision_count, cashflow_revision_digest,
                settlement_revision_count, settlement_revision_digest, materialized_at
            )
            SELECT target_portfolio_id,
                   portfolio_facts.base_currency,
                   cashflow_evidence.row_count,
                   cashflow_evidence.digest,
                   settlement_evidence.row_count,
                   settlement_evidence.digest,
                   materialization.materialized_at
            FROM cashflow_evidence
            CROSS JOIN settlement_evidence
            CROSS JOIN materialization
            CROSS JOIN portfolio_facts
            ON CONFLICT (portfolio_id) DO UPDATE
            SET portfolio_base_currency = EXCLUDED.portfolio_base_currency,
                cashflow_revision_count = EXCLUDED.cashflow_revision_count,
                cashflow_revision_digest = EXCLUDED.cashflow_revision_digest,
                settlement_revision_count = EXCLUDED.settlement_revision_count,
                settlement_revision_digest = EXCLUDED.settlement_revision_digest,
                materialized_at = CASE
                    -- A changed fixed-width projection is a new durable source
                    -- materialization.  Keep its chronology separate from the
                    -- identity digest and advance it even when an upstream
                    -- upsert did not advance a model-managed updated_at field.
                    WHEN (
                        {_TABLE}.portfolio_base_currency,
                        {_TABLE}.cashflow_revision_count,
                        {_TABLE}.cashflow_revision_digest,
                        {_TABLE}.settlement_revision_count,
                        {_TABLE}.settlement_revision_digest
                    ) IS DISTINCT FROM (
                        EXCLUDED.portfolio_base_currency,
                        EXCLUDED.cashflow_revision_count,
                        EXCLUDED.cashflow_revision_digest,
                        EXCLUDED.settlement_revision_count,
                        EXCLUDED.settlement_revision_digest
                    ) THEN GREATEST(
                        {_TABLE}.materialized_at + INTERVAL '1 microsecond',
                        CURRENT_TIMESTAMP
                    )
                    -- Timestamp-only source updates retain their chronology
                    -- without producing a new logical source-cut identity.
                    WHEN EXCLUDED.materialized_at > {_TABLE}.materialized_at
                        THEN EXCLUDED.materialized_at
                    ELSE {_TABLE}.materialized_at
                END;
        END;
        $$;
    """
