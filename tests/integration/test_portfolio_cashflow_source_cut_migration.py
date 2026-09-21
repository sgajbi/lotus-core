"""PostgreSQL proof for transactionally maintained cashflow source cuts."""

from __future__ import annotations

import os
import runpy
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue
from threading import Barrier
from time import monotonic, sleep
from typing import Any

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.lifecycle]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c169b2c3d530_feat_add_portfolio_cashflow_source_cut.py"
)
PORTFOLIO_ID = "CASHFLOW-CUT-PORTFOLIO"
MOVED_PORTFOLIO_ID = "CASHFLOW-CUT-PORTFOLIO-MOVED"
CORRECTIVE_MIGRATION = MIGRATION.with_name(
    "c170b2c3d531_fix_streamline_cashflow_source_cut_refresh.py"
)


@pytest.fixture(autouse=True)
def restore_installed_refresh_function(db_engine):
    """Historical migration tests must not leak old SQL into later head tests."""
    with db_engine.connect() as connection:
        original = connection.scalar(
            text(
                "SELECT pg_get_functiondef("
                "'refresh_portfolio_cashflow_source_cut(text)'::regprocedure)"
            )
        )
    try:
        yield
    finally:
        with db_engine.begin() as connection:
            connection.execute(text(original))


def test_cashflow_refresh_corrective_migration_preserves_nonempty_cuts_and_rolls_back(
    db_engine,
    clean_db,
) -> None:
    """Execute Alembic version transitions, including nonempty downgrade and replay."""
    repository_head = ScriptDirectory.from_config(
        Config(str(MIGRATION.parents[2] / "alembic.ini"))
    ).get_current_head()
    assert repository_head is not None
    with db_engine.begin() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == repository_head
        _seed_legacy_source(connection)
        connection.execute(
            text("UPDATE portfolios SET base_currency = 'EUR' WHERE portfolio_id = :portfolio_id"),
            {"portfolio_id": PORTFOLIO_ID},
        )
        connection.execute(
            text("SELECT refresh_portfolio_cashflow_source_cut(:portfolio_id)"),
            {"portfolio_id": PORTFOLIO_ID},
        )
        golden = _cut(connection)
        assert golden[0] == golden[2] == 2
        assert golden[5] == "EUR"
        assert connection.scalar(text("SELECT sum(amount) FROM cashflows")) == 300
        original_function = connection.scalar(
            text(
                "SELECT pg_get_functiondef("
                "'refresh_portfolio_cashflow_source_cut(text)'::regprocedure)"
            )
        )
        assert "LEFT JOIN cashflow_rows USING" not in original_function
        original_oid = connection.scalar(
            text("SELECT 'refresh_portfolio_cashflow_source_cut(text)'::regprocedure::oid")
        )
        original_triggers = connection.execute(
            text("SELECT oid, tgname, tgtype FROM pg_trigger WHERE NOT tgisinternal ORDER BY oid")
        ).all()

    corrective: dict[str, Any] = runpy.run_path(str(CORRECTIVE_MIGRATION))
    with db_engine.connect() as connection:
        transaction = connection.begin()
        try:
            _bind_operations(corrective, connection)
            corrective["downgrade"]()
            assert "LEFT JOIN cashflow_rows USING" in connection.scalar(
                text(
                    "SELECT pg_get_functiondef("
                    "'refresh_portfolio_cashflow_source_cut(text)'::regprocedure)"
                )
            )
            assert _cut(connection) == golden
        finally:
            transaction.rollback()
        assert (
            connection.scalar(
                text(
                    "SELECT pg_get_functiondef("
                    "'refresh_portfolio_cashflow_source_cut(text)'::regprocedure)"
                )
            )
            == original_function
        )

    child_env = dict(os.environ)
    child_env["HOST_DATABASE_URL"] = db_engine.url.render_as_string(hide_password=False)
    try:
        for direction, target, version in (
            ("downgrade", "c169b2c3d530", "c169b2c3d530"),
            ("upgrade", "c170b2c3d531", "c170b2c3d531"),
            ("upgrade", "c170b2c3d531", "c170b2c3d531"),
        ):
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/development/repository_python.py",
                    "-m",
                    "alembic",
                    direction,
                    target,
                ],
                cwd=MIGRATION.parents[2],
                env=child_env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == 0, (
                f"alembic {direction} {target} exited {completed.returncode}"
            )
            for session_timezone in ("UTC", "Asia/Singapore", "America/New_York"):
                with db_engine.begin() as connection:
                    assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                        version
                    )
                    connection.execute(
                        text("SELECT set_config('TimeZone', :timezone, true)"),
                        {"timezone": session_timezone},
                    )
                    connection.execute(
                        text("SELECT refresh_portfolio_cashflow_source_cut(:portfolio_id)"),
                        {"portfolio_id": PORTFOLIO_ID},
                    )
                    assert _cut(connection) == golden
                    assert connection.scalar(text("SELECT sum(amount) FROM cashflows")) == 300
                    assert (
                        connection.scalar(
                            text(
                                "SELECT "
                                "'refresh_portfolio_cashflow_source_cut(text)'::regprocedure::oid"
                            )
                        )
                        == original_oid
                    )
                    assert (
                        connection.execute(
                            text(
                                "SELECT oid, tgname, tgtype FROM pg_trigger "
                                "WHERE NOT tgisinternal ORDER BY oid"
                            )
                        ).all()
                        == original_triggers
                    )
                    definition = connection.scalar(
                        text(
                            "SELECT pg_get_functiondef("
                            "'refresh_portfolio_cashflow_source_cut(text)'::regprocedure)"
                        )
                    )
                    assert ("LEFT JOIN cashflow_rows USING" in definition) == (
                        version == "c169b2c3d530"
                    )
    finally:
        # An assertion after downgrade must not strand the next suite on legacy SQL.
        restored = subprocess.run(
            [
                sys.executable,
                "scripts/development/repository_python.py",
                "-m",
                "alembic",
                "upgrade",
                repository_head,
            ],
            cwd=MIGRATION.parents[2],
            env=child_env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert restored.returncode == 0, (
            f"Alembic head restoration to {repository_head} exited {restored.returncode}"
        )

    # Historical backfill proof runs c169's function. Exercise the installed
    # corrective function's durable boundary and affected roots independently.
    _assert_late_writer_cannot_publish_a_stale_cut(db_engine)
    _assert_fk_insert_refresh_uses_a_key_share_compatible_lock(db_engine)
    with db_engine.begin() as connection:
        _seed_empty_portfolio(connection, portfolio_id=MOVED_PORTFOLIO_ID)
        connection.execute(
            text(
                "UPDATE cashflows SET portfolio_id = :moved_portfolio_id "
                "WHERE transaction_id = 'CUT-T2'"
            ),
            {"moved_portfolio_id": MOVED_PORTFOLIO_ID},
        )
        assert _cut(connection)[0] == 1
        assert _cut(connection, portfolio_id=MOVED_PORTFOLIO_ID)[0] == 1
        assert dict(
            connection.execute(
                text("SELECT portfolio_id, sum(amount) FROM cashflows GROUP BY portfolio_id")
            ).all()
        ) == {PORTFOLIO_ID: 102, MOVED_PORTFOLIO_ID: 202}
        connection.execute(text("DELETE FROM cashflows WHERE transaction_id = 'CUT-T2'"))
        assert _cut(connection, portfolio_id=MOVED_PORTFOLIO_ID)[0] == 0
        assert _cut(connection)[0] == 1
    _assert_overlapping_bulk_refreshes_complete_in_portfolio_order(db_engine)


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _cut(
    connection, *, portfolio_id: str = PORTFOLIO_ID
) -> tuple[int, str, int, str, datetime, str]:
    row = connection.execute(
        text(
            """
            SELECT cashflow_revision_count, cashflow_revision_digest,
                   settlement_revision_count, settlement_revision_digest,
                   materialized_at
            FROM portfolio_cashflow_source_cuts
            WHERE portfolio_id = :portfolio_id
            """
        ),
        {"portfolio_id": portfolio_id},
    ).one()
    currency = connection.scalar(
        text(
            "SELECT portfolio_base_currency FROM portfolio_cashflow_source_cuts "
            "WHERE portfolio_id = :portfolio_id"
        ),
        {"portfolio_id": portfolio_id},
    )
    return int(row[0]), str(row[1]), int(row[2]), str(row[3]), row[4], str(currency)


def _seed_legacy_source(connection) -> None:
    connection.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                risk_exposure, investment_time_horizon, portfolio_type,
                booking_center_code, client_id, is_leverage_allowed, status
            ) VALUES (
                :portfolio_id, 'tenant-cut', 'BOOK-CUT', 'USD', DATE '2026-01-01',
                'balanced', 'long_term', 'advisory', 'SG', 'CLIENT-CUT', FALSE, 'active'
            )
            """
        ),
        {"portfolio_id": PORTFOLIO_ID},
    )
    for transaction_id, amount in (("CUT-T1", "100"), ("CUT-T2", "200")):
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    transaction_id, portfolio_id, instrument_id, security_id,
                    transaction_type, quantity, price, gross_transaction_amount,
                    trade_currency, currency, transaction_date, settlement_date
                ) VALUES (
                    :transaction_id, :portfolio_id, :transaction_id, :transaction_id,
                    'DEPOSIT', 1, 1, :amount, 'USD', 'USD',
                    TIMESTAMPTZ '2026-01-01 08:00:00+00',
                    TIMESTAMPTZ '2026-01-02 08:00:00+00'
                )
                """
            ),
            {
                "transaction_id": transaction_id,
                "portfolio_id": PORTFOLIO_ID,
                "amount": amount,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO cashflows (
                    transaction_id, portfolio_id, security_id, cashflow_date, epoch,
                    amount, currency, classification, timing, calculation_type,
                    is_position_flow, is_portfolio_flow
                ) VALUES (
                    :transaction_id, :portfolio_id, :transaction_id, DATE '2026-01-02', 0,
                    :amount, 'USD', 'CASHFLOW_IN', 'SETTLED', 'BOOKED', FALSE, TRUE
                )
                """
            ),
            {
                "transaction_id": transaction_id,
                "portfolio_id": PORTFOLIO_ID,
                "amount": amount,
            },
        )


def _seed_empty_portfolio(connection, *, portfolio_id: str) -> None:
    connection.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id, tenant_id, legal_book_id, base_currency, open_date,
                risk_exposure, investment_time_horizon, portfolio_type,
                booking_center_code, client_id, is_leverage_allowed, status
            ) VALUES (
                :portfolio_id, 'tenant-cut', 'BOOK-CUT', 'USD', DATE '2026-01-01',
                'balanced', 'long_term', 'advisory', 'SG', 'CLIENT-CUT-MOVED', FALSE, 'active'
            )
            """
        ),
        {"portfolio_id": portfolio_id},
    )


def _install_refresh_counter(connection) -> None:
    """Wrap the refresh once to prove PostgreSQL work, then restore it below."""
    connection.execute(text("CREATE TEMP TABLE source_cut_refresh_log (portfolio_id text)"))
    connection.execute(
        text(
            """
            ALTER FUNCTION refresh_portfolio_cashflow_source_cut(text)
            RENAME TO refresh_portfolio_cashflow_source_cut_implementation;
            CREATE FUNCTION refresh_portfolio_cashflow_source_cut(target_portfolio_id text)
            RETURNS void
            LANGUAGE plpgsql
            AS $$
            BEGIN
                INSERT INTO pg_temp.source_cut_refresh_log (portfolio_id)
                VALUES (target_portfolio_id);
                PERFORM refresh_portfolio_cashflow_source_cut_implementation(target_portfolio_id);
            END;
            $$;
            """
        )
    )
    # The trigger function may have cached the original target during the
    # preceding timestamp-only proof.  Re-plan it so the test counter observes
    # the actual flush calls, not just queue metadata.
    connection.execute(text("DISCARD PLANS"))


def _restore_refresh_function(connection) -> None:
    connection.execute(
        text(
            """
            DROP FUNCTION refresh_portfolio_cashflow_source_cut(text);
            ALTER FUNCTION refresh_portfolio_cashflow_source_cut_implementation(text)
            RENAME TO refresh_portfolio_cashflow_source_cut;
            """
        )
    )


def test_cashflow_source_cut_backfill_is_timestamp_stable_and_fences_late_writers(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        if "portfolio_cashflow_source_cuts" in inspect(connection).get_table_names():
            migration["downgrade"]()
        _seed_legacy_source(connection)
        migration["upgrade"]()

        backfilled = _cut(connection)
        timestamp_only_at = backfilled[4] + timedelta(microseconds=1)
        assert backfilled[:4][0] == 2
        assert backfilled[:4][2] == 2
        assert backfilled[5] == "USD"
        trigger_rows = connection.execute(
            text(
                """
                SELECT tgname, (tgtype & 1) = 0 AS is_statement_trigger
                FROM pg_trigger
                WHERE NOT tgisinternal
                  AND tgname LIKE 'trg_%_refresh_portfolio_source_cut_%'
                ORDER BY tgname
                """
            )
        ).all()
        assert [row.tgname for row in trigger_rows] == [
            "trg_cashflows_refresh_portfolio_source_cut_delete",
            "trg_cashflows_refresh_portfolio_source_cut_insert",
            "trg_cashflows_refresh_portfolio_source_cut_update",
            "trg_transactions_refresh_portfolio_source_cut_delete",
            "trg_transactions_refresh_portfolio_source_cut_insert",
            "trg_transactions_refresh_portfolio_source_cut_update",
        ]
        assert all(row.is_statement_trigger for row in trigger_rows)
        refresh_definition = connection.scalar(
            text(
                "SELECT pg_get_functiondef("
                "'refresh_portfolio_cashflow_source_cut(text)'::regprocedure)"
            )
        )
        assert refresh_definition.count('COLLATE "C"') == 2
        assert connection.scalar(
            text(
                'SELECT array_agg(identifier ORDER BY identifier COLLATE "C") '
                "FROM (VALUES ('z'), ('A'), ('é')) AS identifiers(identifier)"
            )
        ) == ["A", "z", "é"]

        for session_timezone in ("UTC", "Asia/Singapore", "America/New_York"):
            connection.execute(
                text("SELECT set_config('TimeZone', :session_timezone, false)"),
                {"session_timezone": session_timezone},
            )
            connection.execute(
                text("SELECT refresh_portfolio_cashflow_source_cut(:portfolio_id)"),
                {"portfolio_id": PORTFOLIO_ID},
            )
            assert _cut(connection)[:4] == backfilled[:4]

        connection.execute(
            text("UPDATE cashflows SET updated_at = :updated_at WHERE transaction_id = 'CUT-T1'"),
            {"updated_at": timestamp_only_at},
        )
        timestamp_only = _cut(connection)
        assert timestamp_only[:4] == backfilled[:4]
        assert timestamp_only[4] == timestamp_only_at

        failed_mutation = connection.begin_nested()
        connection.execute(
            text("UPDATE cashflows SET amount = 101 WHERE transaction_id = 'CUT-T1'")
        )
        failed_cut = _cut(connection)
        assert failed_cut[:2] != timestamp_only[:2]
        assert failed_cut[4] > timestamp_only[4]
        failed_mutation.rollback()
        assert _cut(connection) == timestamp_only

        # A base-currency revision changes the economic context used by both
        # query products even when no cashflow or settlement business fact does.
        connection.execute(
            text("UPDATE portfolios SET base_currency = 'EUR' WHERE portfolio_id = :portfolio_id"),
            {"portfolio_id": PORTFOLIO_ID},
        )
        currency_recast = _cut(connection)
        assert currency_recast[:4] == timestamp_only[:4]
        assert currency_recast[5] == "EUR"

        # A supported transaction-table maintenance write outside the source
        # cut must not recast chronology or either product proof envelope.
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    transaction_id, portfolio_id, instrument_id, security_id,
                    transaction_type, quantity, price, gross_transaction_amount,
                    trade_currency, currency, transaction_date, settlement_date
                ) VALUES (
                    'CUT-UNRELATED-BUY', :portfolio_id, 'CUT-UNRELATED-BUY',
                    'CUT-UNRELATED-BUY', 'BUY', 1, 1, 1, 'EUR', 'EUR',
                    TIMESTAMPTZ '2026-01-03 08:00:00+00',
                    TIMESTAMPTZ '2026-01-04 08:00:00+00'
                )
                """
            ),
            {"portfolio_id": PORTFOLIO_ID},
        )
        unrelated_before = _cut(connection)
        connection.execute(
            text(
                "UPDATE transactions SET updated_at = :updated_at "
                "WHERE transaction_id = 'CUT-UNRELATED-BUY'"
            ),
            {"updated_at": unrelated_before[4] + timedelta(microseconds=1)},
        )
        assert _cut(connection) == unrelated_before

        _seed_empty_portfolio(connection, portfolio_id=MOVED_PORTFOLIO_ID)
        assert _cut(connection, portfolio_id=MOVED_PORTFOLIO_ID)[0] == 0
        _install_refresh_counter(connection)
        try:
            connection.execute(text("TRUNCATE source_cut_refresh_log"))
            connection.execute(
                text("SELECT set_config('lotus.cashflow_source_cut_deferred', 'on', true)")
            )
            deferred_timestamp_at = currency_recast[4] + timedelta(microseconds=1)
            connection.execute(
                text(
                    "UPDATE cashflows SET updated_at = :updated_at WHERE transaction_id = 'CUT-T1'"
                ),
                {"updated_at": deferred_timestamp_at},
            )
            # Deferred timestamp-only writes must not take the shared cut row
            # lock or publish chronology before the owning UoW flushes.
            assert _cut(connection)[4] == currency_recast[4]
            # Two supported source-table update statements for one root do no
            # refresh work until the owning unit of work flushes once.
            connection.execute(
                text("UPDATE cashflows SET amount = 102 WHERE transaction_id = 'CUT-T1'")
            )
            connection.execute(
                text("UPDATE cashflows SET amount = 202 WHERE transaction_id = 'CUT-T2'")
            )
            assert connection.scalar(text("SELECT count(*) FROM source_cut_refresh_log")) == 0
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM portfolio_cashflow_source_cut_refresh_queue "
                        "WHERE portfolio_id = :portfolio_id"
                    ),
                    {"portfolio_id": PORTFOLIO_ID},
                )
                == 1
            )
            connection.execute(text("SELECT flush_deferred_portfolio_cashflow_source_cuts()"))
            assert connection.execute(
                text("SELECT portfolio_id FROM source_cut_refresh_log ORDER BY portfolio_id")
            ).scalars().all() == [PORTFOLIO_ID]
            assert _cut(connection)[4] >= deferred_timestamp_at

            connection.execute(text("TRUNCATE source_cut_refresh_log"))
            # Moving a source row records both old and new portfolio roots,
            # then refreshes each root once at flush rather than per row.
            connection.execute(
                text(
                    "UPDATE cashflows SET portfolio_id = :moved_portfolio_id "
                    "WHERE transaction_id = 'CUT-T2'"
                ),
                {"moved_portfolio_id": MOVED_PORTFOLIO_ID},
            )
            connection.execute(text("SELECT flush_deferred_portfolio_cashflow_source_cuts()"))
            assert connection.execute(
                text("SELECT portfolio_id FROM source_cut_refresh_log ORDER BY portfolio_id")
            ).scalars().all() == [PORTFOLIO_ID, MOVED_PORTFOLIO_ID]
            assert _cut(connection)[0] == 1
            assert _cut(connection, portfolio_id=MOVED_PORTFOLIO_ID)[0] == 1
        finally:
            _restore_refresh_function(connection)

        # Restore the moved row before the same-root late-writer fence proof.
        # The deferred setting remains transaction-local, so explicitly flush
        # the restoration at the durable boundary too.
        connection.execute(
            text(
                "UPDATE cashflows SET portfolio_id = :portfolio_id WHERE transaction_id = 'CUT-T2'"
            ),
            {"portfolio_id": PORTFOLIO_ID},
        )
        connection.execute(text("SELECT flush_deferred_portfolio_cashflow_source_cuts()"))

    _assert_late_writer_cannot_publish_a_stale_cut(db_engine)
    _assert_fk_insert_refresh_uses_a_key_share_compatible_lock(db_engine)
    _assert_overlapping_bulk_refreshes_complete_in_portfolio_order(db_engine)

    with db_engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM cashflows WHERE portfolio_id IN (:portfolio_id, :moved_portfolio_id)"
            ),
            {"portfolio_id": PORTFOLIO_ID, "moved_portfolio_id": MOVED_PORTFOLIO_ID},
        )
        connection.execute(
            text(
                "DELETE FROM transactions WHERE portfolio_id IN "
                "(:portfolio_id, :moved_portfolio_id)"
            ),
            {"portfolio_id": PORTFOLIO_ID, "moved_portfolio_id": MOVED_PORTFOLIO_ID},
        )
        connection.execute(
            text("DELETE FROM portfolios WHERE portfolio_id = :portfolio_id"),
            {"portfolio_id": PORTFOLIO_ID},
        )
        connection.execute(
            text("DELETE FROM portfolios WHERE portfolio_id = :portfolio_id"),
            {"portfolio_id": MOVED_PORTFOLIO_ID},
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM portfolio_cashflow_source_cuts "
                    "WHERE portfolio_id = :portfolio_id"
                ),
                {"portfolio_id": PORTFOLIO_ID},
            )
            == 0
        )


def _assert_late_writer_cannot_publish_a_stale_cut(db_engine) -> None:
    worker_pid: Queue[int] = Queue()

    def late_writer() -> None:
        with db_engine.connect() as connection:
            transaction = connection.begin()
            try:
                worker_pid.put(int(connection.scalar(text("SELECT pg_backend_pid()"))))
                connection.execute(
                    text("SELECT set_config('lotus.cashflow_source_cut_deferred', 'off', true)")
                )
                connection.execute(
                    text("UPDATE cashflows SET amount = 202 WHERE transaction_id = 'CUT-T2'")
                )
                connection.execute(
                    text("SELECT refresh_portfolio_cashflow_source_cut(:portfolio_id)"),
                    {"portfolio_id": PORTFOLIO_ID},
                )
                transaction.commit()
            except BaseException:
                transaction.rollback()
                raise

    with db_engine.connect() as first_writer, ThreadPoolExecutor(max_workers=1) as executor:
        first_transaction = first_writer.begin()
        try:
            first_writer.execute(
                text("SELECT set_config('lotus.cashflow_source_cut_deferred', 'off', true)")
            )
            first_writer.execute(
                text("UPDATE cashflows SET amount = 102 WHERE transaction_id = 'CUT-T1'")
            )
            first_writer.execute(
                text("SELECT refresh_portfolio_cashflow_source_cut(:portfolio_id)"),
                {"portfolio_id": PORTFOLIO_ID},
            )
            future = executor.submit(late_writer)
            late_writer_pid = worker_pid.get(timeout=5)
            _wait_until_writer_blocks_on_portfolio_cut(first_writer, late_writer_pid)
            first_transaction.commit()
            future.result(timeout=10)
        except BaseException:
            first_transaction.rollback()
            raise

    with db_engine.begin() as connection:
        cut_after_late_writer = _cut(connection)
        connection.execute(
            text("SELECT refresh_portfolio_cashflow_source_cut(:portfolio_id)"),
            {"portfolio_id": PORTFOLIO_ID},
        )
        assert _cut(connection) == cut_after_late_writer


def _assert_fk_insert_refresh_uses_a_key_share_compatible_lock(db_engine) -> None:
    """A supported source insert must not deadlock against its portfolio FK lock."""

    def insert_settlement_source() -> None:
        with db_engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(
                        """
                        INSERT INTO transactions (
                            transaction_id, portfolio_id, instrument_id, security_id,
                            transaction_type, quantity, price, gross_transaction_amount,
                            trade_currency, currency, transaction_date, settlement_date
                        ) VALUES (
                            'CUT-KEY-SHARE', :portfolio_id, 'CUT-KEY-SHARE', 'CUT-KEY-SHARE',
                            'DEPOSIT', 1, 1, 1, 'USD', 'USD',
                            TIMESTAMPTZ '2026-01-03 08:00:00+00',
                            TIMESTAMPTZ '2026-01-04 08:00:00+00'
                        )
                        """
                    ),
                    {"portfolio_id": PORTFOLIO_ID},
                )
                transaction.commit()
            except BaseException:
                transaction.rollback()
                raise

    completed_while_key_shared = False
    with db_engine.connect() as key_share_holder, ThreadPoolExecutor(max_workers=1) as executor:
        holder_transaction = key_share_holder.begin()
        try:
            key_share_holder.execute(
                text("SELECT 1 FROM portfolios WHERE portfolio_id = :portfolio_id FOR KEY SHARE"),
                {"portfolio_id": PORTFOLIO_ID},
            )
            future = executor.submit(insert_settlement_source)
            try:
                future.result(timeout=3)
                completed_while_key_shared = True
            except FutureTimeoutError:
                pass
        finally:
            holder_transaction.rollback()
        future.result(timeout=5)

    assert completed_while_key_shared


def _assert_overlapping_bulk_refreshes_complete_in_portfolio_order(db_engine) -> None:
    """Two bulk source writes touching the same roots must not form a lock cycle."""

    with db_engine.begin() as connection:
        # Preserve opposite physical portfolio order in the two UPDATE sets.
        # The trigger must impose its own root order instead of relying on that
        # incidental source order.
        for transaction_id, portfolio_id, amount in (
            ("CUT-BULK-A1", PORTFOLIO_ID, "301"),
            ("CUT-BULK-B1", MOVED_PORTFOLIO_ID, "302"),
            ("CUT-BULK-B2", MOVED_PORTFOLIO_ID, "303"),
            ("CUT-BULK-A2", PORTFOLIO_ID, "304"),
        ):
            _insert_transaction_cashflow_source(
                connection,
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                amount=amount,
            )

        trigger_definition = connection.scalar(
            text(
                "SELECT pg_get_functiondef("
                "'refresh_portfolio_cashflow_source_cut_trigger()'::regprocedure)"
            )
        )
        assert trigger_definition.count("ORDER BY portfolio_id") == 5

    start = Barrier(2)

    def update_bulk(*, transaction_ids: tuple[str, str]) -> None:
        with db_engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text("SELECT set_config('lotus.cashflow_source_cut_deferred', 'off', true)")
                )
                start.wait(timeout=5)
                connection.execute(
                    text(
                        "UPDATE cashflows SET amount = amount + 1 "
                        "WHERE transaction_id IN (:first_transaction_id, :second_transaction_id)"
                    ),
                    {
                        "first_transaction_id": transaction_ids[0],
                        "second_transaction_id": transaction_ids[1],
                    },
                )
                transaction.commit()
            except BaseException:
                transaction.rollback()
                raise

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            update_bulk,
            transaction_ids=("CUT-BULK-A1", "CUT-BULK-B1"),
        )
        second = executor.submit(
            update_bulk,
            transaction_ids=("CUT-BULK-B2", "CUT-BULK-A2"),
        )
        first.result(timeout=10)
        second.result(timeout=10)


def _insert_transaction_cashflow_source(
    connection, *, transaction_id: str, portfolio_id: str, amount: str
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id, portfolio_id, instrument_id, security_id,
                transaction_type, quantity, price, gross_transaction_amount,
                trade_currency, currency, transaction_date, settlement_date
            ) VALUES (
                :transaction_id, :portfolio_id, :transaction_id, :transaction_id,
                'DEPOSIT', 1, 1, :amount, 'USD', 'USD',
                TIMESTAMPTZ '2026-01-05 08:00:00+00',
                TIMESTAMPTZ '2026-01-06 08:00:00+00'
            )
            """
        ),
        {"transaction_id": transaction_id, "portfolio_id": portfolio_id, "amount": amount},
    )
    connection.execute(
        text(
            """
            INSERT INTO cashflows (
                transaction_id, portfolio_id, security_id, cashflow_date, epoch,
                amount, currency, classification, timing, calculation_type,
                is_position_flow, is_portfolio_flow
            ) VALUES (
                :transaction_id, :portfolio_id, :transaction_id, DATE '2026-01-06', 0,
                :amount, 'USD', 'CASHFLOW_IN', 'SETTLED', 'BOOKED', FALSE, TRUE
            )
            """
        ),
        {"transaction_id": transaction_id, "portfolio_id": portfolio_id, "amount": amount},
    )


def _wait_until_writer_blocks_on_portfolio_cut(connection, worker_pid: int) -> None:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        wait_type = connection.scalar(
            text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
            {"pid": worker_pid},
        )
        if wait_type == "Lock":
            return
        sleep(0.05)
    pytest.fail("late cashflow writer did not wait on the durable portfolio cut lock")
