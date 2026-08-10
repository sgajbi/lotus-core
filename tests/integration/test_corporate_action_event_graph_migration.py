"""PostgreSQL lifecycle and constraint proof for corporate-action parent graphs."""

from __future__ import annotations

import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from portfolio_common.domain.calculation_lineage import (
    FinancialSourceReference,
    canonical_content_hash,
)
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.lifecycle]

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c152b2c3d519_feat_add_corporate_action_event_graph.py"
)
TABLES = {
    "corporate_action_events",
    "corporate_action_manifest_versions",
    "corporate_action_manifest_nodes",
    "corporate_action_manifest_edges",
    "corporate_action_child_observations",
    "corporate_action_readiness_evaluations",
}


def _bind_operations(migration: dict[str, Any], connection) -> None:
    operations = Operations(MigrationContext.configure(connection))
    migration["upgrade"].__globals__["op"] = operations
    migration["downgrade"].__globals__["op"] = operations


def _normalize_to_previous_revision(migration: dict[str, Any], connection) -> None:
    if TABLES.intersection(inspect(connection).get_table_names()):
        migration["downgrade"]()


def _expect_integrity_error(
    connection,
    statement,
    parameters,
    *,
    match: str | None = None,
) -> None:
    savepoint = connection.begin_nested()
    with pytest.raises(IntegrityError, match=match):
        connection.execute(statement, parameters)
    savepoint.rollback()


def _child_payload_and_hash(
    *,
    transaction_id: str,
    transaction_type: str,
    child_role: str,
    dependency_transaction_ids: tuple[str, ...] = (),
    instrument_id: str | None = None,
    source_instrument_id: str | None = None,
    target_instrument_id: str | None = None,
) -> tuple[str, str]:
    child = corporate_action.CorporateActionEventChild(
        transaction_id=transaction_id,
        transaction_type=transaction_type,
        child_role=child_role,
        dependency_transaction_ids=dependency_transaction_ids,
        instrument_id=instrument_id,
        source_instrument_id=source_instrument_id,
        target_instrument_id=target_instrument_id,
    )
    return json.dumps(child.lineage_payload()), child.content_hash


def _manifest_payload_and_hash(
    policy: corporate_action.CorporateActionCohortPolicy | None = None,
    *,
    identity_suffix: str = "DB-001",
) -> tuple[str, str, str]:
    if policy is None:
        policy = next(
            candidate
            for candidate in corporate_action.CORPORATE_ACTION_COHORT_POLICIES
            if candidate.corporate_action_type == "DEMERGER"
        )
    source_transaction_id = f"CA-SOURCE-{identity_suffix}"
    target_transaction_id = f"CA-TARGET-{identity_suffix}"
    source = corporate_action.CorporateActionEventChild(
        transaction_id=source_transaction_id,
        transaction_type=policy.source_transaction_type,
        child_role=policy.source_role,
        instrument_id="SOURCE-SEC",
        source_instrument_id="SOURCE-SEC",
    )
    target = corporate_action.CorporateActionEventChild(
        transaction_id=target_transaction_id,
        transaction_type=policy.target_transaction_type,
        child_role="TARGET_POSITION_ADD",
        dependency_transaction_ids=(source.transaction_id,),
        instrument_id="TARGET-SEC",
        source_instrument_id="SOURCE-SEC",
        target_instrument_id="TARGET-SEC",
    )
    manifest = corporate_action.CorporateActionParentManifest(
        corporate_action_event_id=f"CA-EVENT-{identity_suffix}",
        portfolio_id="CA-PORT-DB-001",
        linked_transaction_group_id=f"CA-GROUP-{identity_suffix}",
        parent_event_reference=f"CA-PARENT-{identity_suffix}",
        corporate_action_type=policy.corporate_action_type,
        version=1,
        completion_declared=True,
        expected_children=(source, target),
        source_reference=FinancialSourceReference(
            source_system="custodian-ca",
            source_record_id="CA-SOURCE-RECORD-001",
            source_revision="revision-1",
            source_content_hash="a" * 64,
            observed_at=datetime(2026, 8, 9, 1, tzinfo=UTC),
        ),
    )
    payload = manifest.lineage_payload()
    source_payload = dict(cast(dict[str, object], payload["source_reference"]))
    source_payload["observed_at"] = datetime(2026, 8, 9, 1, tzinfo=UTC).isoformat()
    payload["source_reference"] = source_payload
    execution_plan_hash = canonical_content_hash(
        {
            "canonical_payload_version": 1,
            "manifest_content_hash": manifest.content_hash,
            "ordered_transaction_ids": [source.transaction_id, target.transaction_id],
        }
    )
    return json.dumps(payload), manifest.content_hash, execution_plan_hash


def _seed_book_scope(connection) -> None:
    connection.execute(
        text(
            """
            INSERT INTO portfolios (
                portfolio_id,
                tenant_id,
                legal_book_id,
                base_currency,
                open_date,
                risk_exposure,
                investment_time_horizon,
                portfolio_type,
                booking_center_code,
                client_id,
                is_leverage_allowed,
                status
            ) VALUES
            (
                'CA-PORT-DB-001',
                'TENANT-SG',
                'PB-SG-01',
                'USD',
                DATE '2026-01-01',
                'BALANCED',
                'LONG_TERM',
                'DISCRETIONARY',
                'SG',
                'CA-CLIENT-001',
                false,
                'ACTIVE'
            ),
            (
                'CA-PORT-DB-002',
                'TENANT-CH',
                'PB-CH-01',
                'CHF',
                DATE '2026-01-01',
                'BALANCED',
                'LONG_TERM',
                'ADVISORY',
                'CH',
                'CA-CLIENT-002',
                false,
                'ACTIVE'
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO transactions (
                transaction_id,
                portfolio_id,
                instrument_id,
                security_id,
                transaction_type,
                quantity,
                price,
                gross_transaction_amount,
                trade_currency,
                currency,
                transaction_date,
                trade_fee
            ) VALUES
            (
                'CA-SOURCE-DB-001',
                'CA-PORT-DB-001',
                'SOURCE-SEC',
                'SOURCE-SEC',
                'DEMERGER_OUT',
                10,
                100,
                1000,
                'USD',
                'USD',
                TIMESTAMPTZ '2026-08-09 01:00:00+00',
                0
            ),
            (
                'CA-CROSS-BOOK-DB-001',
                'CA-PORT-DB-002',
                'CH-SOURCE-SEC',
                'CH-SOURCE-SEC',
                'DEMERGER_OUT',
                10,
                100,
                1000,
                'CHF',
                'CHF',
                TIMESTAMPTZ '2026-08-09 01:00:00+00',
                0
            ),
            (
                'CA-TARGET-DB-001',
                'CA-PORT-DB-001',
                'TARGET-SEC',
                'TARGET-SEC',
                'DEMERGER_IN',
                10,
                100,
                1000,
                'USD',
                'USD',
                TIMESTAMPTZ '2026-08-09 01:00:00+00',
                0
            ),
            (
                'CA-UNEXPECTED-DB-001',
                'CA-PORT-DB-001',
                'UNEXPECTED-SEC',
                'UNEXPECTED-SEC',
                'DEMERGER_IN',
                1,
                100,
                100,
                'USD',
                'USD',
                TIMESTAMPTZ '2026-08-09 01:00:00+00',
                0
            )
            """
        )
    )


def test_corporate_action_event_graph_apply_constraints_and_rollback(
    db_engine,
    clean_db,
) -> None:
    migration: dict[str, Any] = runpy.run_path(str(MIGRATION))

    with db_engine.begin() as connection:
        _bind_operations(migration, connection)
        _normalize_to_previous_revision(migration, connection)
        assert not TABLES.intersection(inspect(connection).get_table_names())

        migration["upgrade"]()
        inspector = inspect(connection)
        assert TABLES.issubset(inspector.get_table_names())
        assert {
            "ck_ca_event_manifest_status_shape",
            "ck_ca_event_counters_nonnegative",
            "ck_ca_event_readiness_status",
        } <= {
            constraint["name"]
            for constraint in inspector.get_check_constraints("corporate_action_events")
        }
        assert {
            "ck_ca_manifest_chain_shape",
            "ck_ca_manifest_hashes",
            "ck_ca_manifest_payload_object",
            "ck_ca_manifest_observed_at_finite",
        } <= {
            constraint["name"]
            for constraint in inspector.get_check_constraints("corporate_action_manifest_versions")
        }
        assert "uq_ca_readiness_manifest_ready" not in {
            index["name"]
            for index in inspector.get_indexes("corporate_action_readiness_evaluations")
        }
        unicode_payload, unicode_content_hash = _child_payload_and_hash(
            transaction_id='CA-É-"QUOTED"-😀',
            transaction_type="DEMERGER_OUT",
            child_role="SOURCE_POSITION_REDUCE",
            dependency_transaction_ids=("依存-😀", "A-É"),
            instrument_id="証券-É-😀",
        )
        assert (
            connection.scalar(
                text("SELECT canonical_ca_child_payload_hash(CAST(:payload AS jsonb))"),
                {"payload": unicode_payload},
            )
            == unicode_content_hash
        )
        json_escape_vector = 'quote" backslash\\ controls\b\f\n\r\t low\x01\x1f delete\x7f'
        assert connection.scalar(
            text("SELECT canonical_ca_json_string(:value)"),
            {"value": json_escape_vector},
        ) == json.dumps(json_escape_vector)

        _seed_book_scope(connection)
        event_insert = text(
            """
            INSERT INTO corporate_action_events (
                tenant_id,
                legal_book_id,
                portfolio_id,
                corporate_action_event_id,
                linked_transaction_group_id,
                parent_event_reference
            ) VALUES (
                :tenant_id,
                'PB-SG-01',
                'CA-PORT-DB-001',
                :event_reference,
                :group_reference,
                :parent_reference
            )
            RETURNING id
            """
        )
        event_id = connection.execute(
            event_insert,
            {
                "tenant_id": "TENANT-SG",
                "event_reference": "CA-EVENT-DB-001",
                "group_reference": "CA-GROUP-DB-001",
                "parent_reference": "CA-PARENT-DB-001",
            },
        ).scalar_one()
        _expect_integrity_error(
            connection,
            event_insert,
            {
                "tenant_id": " TENANT-SG ",
                "event_reference": "CA-EVENT-DB-INVALID",
                "group_reference": "CA-GROUP-DB-INVALID",
                "parent_reference": "CA-PARENT-DB-INVALID",
            },
        )
        _expect_integrity_error(
            connection,
            text(
                """
                UPDATE corporate_action_events
                SET parent_event_reference = 'CA-PARENT-DB-TAMPERED'
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
            match="event identity is immutable",
        )

        manifest_payload, manifest_content_hash, execution_plan_content_hash = (
            _manifest_payload_and_hash()
        )
        manifest_hash_select = text(
            "SELECT canonical_ca_manifest_payload_hash(CAST(:payload AS jsonb))"
        )
        for policy in corporate_action.CORPORATE_ACTION_COHORT_POLICIES:
            policy_payload, policy_content_hash, _ = _manifest_payload_and_hash(
                policy,
                identity_suffix=f"POLICY-{policy.corporate_action_type}",
            )
            assert (
                connection.scalar(
                    manifest_hash_select,
                    {"payload": policy_payload},
                )
                == policy_content_hash
            )
        assert (
            connection.scalar(
                manifest_hash_select,
                {"payload": manifest_payload},
            )
            == manifest_content_hash
        )
        forged_manifest_payload = json.loads(manifest_payload)
        forged_manifest_payload["parent_event_reference"] = "forged-parent-reference"
        assert (
            connection.scalar(
                manifest_hash_select,
                {"payload": json.dumps(forged_manifest_payload)},
            )
            != manifest_content_hash
        )
        reordered_manifest_payload = json.loads(manifest_payload)
        reordered_manifest_payload["expected_children"].reverse()
        assert (
            connection.scalar(
                manifest_hash_select,
                {"payload": json.dumps(reordered_manifest_payload)},
            )
            == manifest_content_hash
        )
        dependency_order_a = json.loads(manifest_payload)
        dependency_order_a["expected_children"][1]["dependency_transaction_ids"].append(
            "ZZZ-NONCANONICAL-DEPENDENCY"
        )
        dependency_order_b = json.loads(json.dumps(dependency_order_a))
        dependency_order_b["expected_children"].reverse()
        dependency_order_b["expected_children"][0]["dependency_transaction_ids"].reverse()
        assert connection.scalar(
            manifest_hash_select,
            {"payload": json.dumps(dependency_order_a)},
        ) == connection.scalar(
            manifest_hash_select,
            {"payload": json.dumps(dependency_order_b)},
        )

        unsupported_manifest_payload = json.loads(manifest_payload)
        unsupported_manifest_payload["corporate_action_type"] = "UNSUPPORTED_EVENT"
        _expect_integrity_error(
            connection,
            manifest_hash_select,
            {"payload": json.dumps(unsupported_manifest_payload)},
            match="no governed cohort policy",
        )
        disallowed_type_payload = json.loads(manifest_payload)
        disallowed_type_payload["expected_children"][0]["transaction_type"] = "SELL"
        _expect_integrity_error(
            connection,
            manifest_hash_select,
            {"payload": json.dumps(disallowed_type_payload)},
            match="governed cohort shape",
        )
        disallowed_role_payload = json.loads(manifest_payload)
        disallowed_role_payload["expected_children"][0]["child_role"] = "TARGET_POSITION_ADD"
        _expect_integrity_error(
            connection,
            manifest_hash_select,
            {"payload": json.dumps(disallowed_role_payload)},
            match="source child violates cohort policy",
        )
        manifest_insert = text(
            """
            INSERT INTO corporate_action_manifest_versions (
                event_id,
                manifest_version,
                corporate_action_type,
                completion_declared,
                source_system,
                source_record_id,
                source_revision,
                source_content_hash,
                source_observed_at,
                manifest_content_hash,
                previous_manifest_id,
                previous_manifest_content_hash,
                expected_node_count,
                expected_edge_count,
                opened_observation_sequence,
                manifest_payload
            ) VALUES (
                :event_id,
                :manifest_version,
                'DEMERGER',
                true,
                'custodian-ca',
                'CA-SOURCE-RECORD-001',
                :source_revision,
                :source_content_hash,
                TIMESTAMPTZ '2026-08-09 01:00:00+00',
                :manifest_content_hash,
                :previous_manifest_id,
                :previous_manifest_content_hash,
                2,
                1,
                0,
                CAST(:manifest_payload AS jsonb)
            )
            RETURNING id
            """
        )
        manifest_id = connection.execute(
            manifest_insert,
            {
                "event_id": event_id,
                "manifest_version": 1,
                "source_revision": "revision-1",
                "source_content_hash": "a" * 64,
                "manifest_content_hash": manifest_content_hash,
                "previous_manifest_id": None,
                "previous_manifest_content_hash": None,
                "manifest_payload": manifest_payload,
            },
        ).scalar_one()
        _expect_integrity_error(
            connection,
            manifest_insert,
            {
                "event_id": event_id,
                "manifest_version": 2,
                "source_revision": "revision-2",
                "source_content_hash": "c" * 64,
                "manifest_content_hash": "d" * 64,
                "previous_manifest_id": None,
                "previous_manifest_content_hash": None,
                "manifest_payload": '{"version":2}',
            },
        )
        _expect_integrity_error(
            connection,
            manifest_insert,
            {
                "event_id": event_id,
                "manifest_version": 2,
                "source_revision": "revision-wrong-hash",
                "source_content_hash": "c" * 64,
                "manifest_content_hash": "d" * 64,
                "previous_manifest_id": manifest_id,
                "previous_manifest_content_hash": "0" * 64,
                "manifest_payload": '{"version":2}',
            },
        )
        _expect_integrity_error(
            connection,
            manifest_insert,
            {
                "event_id": event_id,
                "manifest_version": 3,
                "source_revision": "revision-skipped",
                "source_content_hash": "c" * 64,
                "manifest_content_hash": "d" * 64,
                "previous_manifest_id": manifest_id,
                "previous_manifest_content_hash": manifest_content_hash,
                "manifest_payload": '{"version":3}',
            },
        )
        connection.execute(
            manifest_insert,
            {
                "event_id": event_id,
                "manifest_version": 2,
                "source_revision": "revision-2",
                "source_content_hash": "c" * 64,
                "manifest_content_hash": "d" * 64,
                "previous_manifest_id": manifest_id,
                "previous_manifest_content_hash": manifest_content_hash,
                "manifest_payload": '{"version":2}',
            },
        )
        _expect_integrity_error(
            connection,
            manifest_insert,
            {
                "event_id": event_id,
                "manifest_version": 2,
                "source_revision": "revision-concurrent-loser",
                "source_content_hash": "5" * 64,
                "manifest_content_hash": "6" * 64,
                "previous_manifest_id": manifest_id,
                "previous_manifest_content_hash": manifest_content_hash,
                "manifest_payload": '{"version":2,"candidate":"loser"}',
            },
        )
        connection.execute(
            text(
                """
                UPDATE corporate_action_events
                SET current_manifest_version = 1,
                    readiness_status = 'AWAITING_CHILDREN',
                    state_version = 1
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
        )
        _expect_integrity_error(
            connection,
            text(
                """
                UPDATE corporate_action_events
                SET current_manifest_version = 3
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
        )

        node_insert = text(
            """
            INSERT INTO corporate_action_manifest_nodes (
                manifest_id,
                transaction_id,
                transaction_type,
                child_role,
                instrument_id,
                source_instrument_id,
                target_instrument_id,
                child_content_hash,
                resolved_execution_ordinal
            ) VALUES (
                :manifest_id,
                :transaction_id,
                :transaction_type,
                :child_role,
                :instrument_id,
                :source_instrument_id,
                :target_instrument_id,
                :child_content_hash,
                :resolved_execution_ordinal
            )
            """
        )
        source_payload, source_content_hash = _child_payload_and_hash(
            transaction_id="CA-SOURCE-DB-001",
            transaction_type="DEMERGER_OUT",
            child_role="SOURCE_POSITION_REDUCE",
            instrument_id="SOURCE-SEC",
            source_instrument_id="SOURCE-SEC",
        )
        target_payload, target_content_hash = _child_payload_and_hash(
            transaction_id="CA-TARGET-DB-001",
            transaction_type="DEMERGER_IN",
            child_role="TARGET_POSITION_ADD",
            dependency_transaction_ids=("CA-SOURCE-DB-001",),
            instrument_id="TARGET-SEC",
            source_instrument_id="SOURCE-SEC",
            target_instrument_id="TARGET-SEC",
        )
        unexpected_payload, unexpected_content_hash = _child_payload_and_hash(
            transaction_id="CA-UNEXPECTED-DB-001",
            transaction_type="ADJUSTMENT",
            child_role="UNEXPECTED_SETTLEMENT",
            instrument_id="SOURCE-SEC",
        )
        source_node = {
            "manifest_id": manifest_id,
            "transaction_id": "CA-SOURCE-DB-001",
            "transaction_type": "DEMERGER_OUT",
            "child_role": "SOURCE_POSITION_REDUCE",
            "instrument_id": "SOURCE-SEC",
            "source_instrument_id": "SOURCE-SEC",
            "target_instrument_id": None,
            "child_content_hash": source_content_hash,
            "resolved_execution_ordinal": 0,
        }
        target_node = source_node | {
            "transaction_id": "CA-TARGET-DB-001",
            "transaction_type": "DEMERGER_IN",
            "child_role": "TARGET_POSITION_ADD",
            "instrument_id": "TARGET-SEC",
            "target_instrument_id": "TARGET-SEC",
            "child_content_hash": target_content_hash,
            "resolved_execution_ordinal": 1,
        }
        connection.execute(node_insert, [source_node, target_node])
        _expect_integrity_error(
            connection,
            node_insert,
            target_node
            | {
                "transaction_id": "CA-TARGET-DB-INVALID",
                "instrument_id": " TARGET-SEC ",
                "child_content_hash": "4" * 64,
                "resolved_execution_ordinal": 2,
            },
        )
        edge_insert = text(
            """
            INSERT INTO corporate_action_manifest_edges (
                manifest_id,
                predecessor_transaction_id,
                successor_transaction_id
            ) VALUES (
                :manifest_id,
                :predecessor_transaction_id,
                :successor_transaction_id
            )
            """
        )
        readiness_insert = text(
            """
            INSERT INTO corporate_action_readiness_evaluations (
                event_id,
                state_version,
                manifest_id,
                through_observation_sequence,
                readiness_status,
                manifest_content_hash,
                execution_plan_content_hash,
                findings,
                ordered_transaction_ids,
                correlation_id
            ) VALUES (
                :event_id,
                :state_version,
                :manifest_id,
                :through_observation_sequence,
                'READY',
                :manifest_content_hash,
                :execution_plan_content_hash,
                CAST('[]' AS jsonb),
                CAST(:ordered_transaction_ids AS jsonb),
                'corr-ca-db-001'
            )
            """
        )
        readiness = {
            "event_id": event_id,
            "state_version": 2,
            "manifest_id": manifest_id,
            "through_observation_sequence": 1,
            "manifest_content_hash": manifest_content_hash,
            "execution_plan_content_hash": execution_plan_content_hash,
            "ordered_transaction_ids": '["CA-SOURCE-DB-001","CA-TARGET-DB-001"]',
        }
        _expect_integrity_error(
            connection,
            readiness_insert,
            readiness,
            match="READY plan does not match manifest edges",
        )
        connection.execute(
            edge_insert,
            {
                "manifest_id": manifest_id,
                "predecessor_transaction_id": "CA-SOURCE-DB-001",
                "successor_transaction_id": "CA-TARGET-DB-001",
            },
        )
        _expect_integrity_error(
            connection,
            edge_insert,
            {
                "manifest_id": manifest_id,
                "predecessor_transaction_id": "MISSING-NODE",
                "successor_transaction_id": "CA-TARGET-DB-001",
            },
        )
        reversed_edge = connection.begin_nested()
        connection.execute(
            edge_insert,
            {
                "manifest_id": manifest_id,
                "predecessor_transaction_id": "CA-TARGET-DB-001",
                "successor_transaction_id": "CA-SOURCE-DB-001",
            },
        )
        _expect_integrity_error(
            connection,
            readiness_insert,
            readiness,
            match="manifest graph has no canonical execution order",
        )
        reversed_edge.rollback()

        observation_insert = text(
            """
            INSERT INTO corporate_action_child_observations (
                event_id,
                observation_sequence,
                transaction_id,
                transaction_epoch,
                delivery_event_id,
                correlation_id,
                observed_content_hash,
                observed_payload,
                observed_at
            ) VALUES (
                :event_id,
                :observation_sequence,
                :transaction_id,
                :transaction_epoch,
                :delivery_event_id,
                'corr-ca-db-001',
                :observed_content_hash,
                CAST(:observed_payload AS jsonb),
                TIMESTAMPTZ '2026-08-09 01:01:00+00'
            )
            """
        )
        observation = {
            "event_id": event_id,
            "observation_sequence": 1,
            "transaction_id": "CA-SOURCE-DB-001",
            "transaction_epoch": 0,
            "delivery_event_id": "delivery-ca-db-001",
            "observed_content_hash": source_content_hash,
            "observed_payload": source_payload,
        }
        connection.execute(observation_insert, observation)
        _expect_integrity_error(connection, observation_insert, observation)
        _expect_integrity_error(
            connection,
            observation_insert,
            observation
            | {
                "observation_sequence": 2,
                "observed_content_hash": "2" * 64,
            },
        )
        _expect_integrity_error(
            connection,
            observation_insert,
            observation
            | {
                "observation_sequence": 2,
                "transaction_id": "CA-CROSS-BOOK-DB-001",
                "delivery_event_id": "delivery-ca-db-cross-book",
                "observed_content_hash": "2" * 64,
            },
        )
        connection.execute(
            text(
                """
                UPDATE corporate_action_events
                SET last_observation_sequence = 1,
                    state_version = 2
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
        )
        _expect_integrity_error(
            connection,
            readiness_insert,
            readiness,
            match="latest child observations",
        )
        target_observation = observation | {
            "observation_sequence": 2,
            "transaction_id": "CA-TARGET-DB-001",
            "delivery_event_id": "delivery-ca-db-002",
            "observed_content_hash": target_content_hash,
            "observed_payload": target_payload,
        }
        connection.execute(observation_insert, target_observation)
        _expect_integrity_error(
            connection,
            readiness_insert,
            readiness | {"through_observation_sequence": 2},
            match="stale against event state",
        )
        connection.execute(
            text(
                """
                UPDATE corporate_action_events
                SET last_observation_sequence = 2
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
        )
        readiness["through_observation_sequence"] = 2
        forged_payload_savepoint = connection.begin_nested()
        connection.execute(
            observation_insert,
            target_observation
            | {
                "observation_sequence": 3,
                "transaction_epoch": 1,
                "delivery_event_id": "delivery-ca-db-forged-payload",
                "observed_payload": source_payload,
            },
        )
        connection.execute(
            text(
                """
                UPDATE corporate_action_events
                SET last_observation_sequence = 3
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
        )
        _expect_integrity_error(
            connection,
            readiness_insert,
            readiness | {"through_observation_sequence": 3},
            match="latest child observations",
        )
        forged_payload_savepoint.rollback()
        _expect_integrity_error(
            connection,
            readiness_insert,
            readiness | {"ordered_transaction_ids": '["CA-TARGET-DB-001","CA-SOURCE-DB-001"]'},
            match="READY plan does not match manifest node order",
        )
        _expect_integrity_error(
            connection,
            readiness_insert,
            readiness | {"execution_plan_content_hash": "0" * 64},
            match="execution-plan hash is not canonical",
        )
        _expect_integrity_error(
            connection,
            readiness_insert,
            readiness | {"manifest_content_hash": "0" * 64},
            match="READY evidence does not match complete manifest",
        )
        unexpected_observation_savepoint = connection.begin_nested()
        unexpected_observation = target_observation | {
            "observation_sequence": 3,
            "transaction_id": "CA-UNEXPECTED-DB-001",
            "delivery_event_id": "delivery-ca-db-unexpected",
            "observed_content_hash": unexpected_content_hash,
            "observed_payload": unexpected_payload,
        }
        connection.execute(observation_insert, unexpected_observation)
        connection.execute(
            text(
                """
                UPDATE corporate_action_events
                SET last_observation_sequence = 3
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
        )
        _expect_integrity_error(
            connection,
            readiness_insert,
            readiness | {"through_observation_sequence": 3},
            match="latest child observations",
        )
        unexpected_observation_savepoint.rollback()
        connection.execute(readiness_insert, readiness)

        awaiting_insert = text(
            """
            INSERT INTO corporate_action_readiness_evaluations (
                event_id,
                state_version,
                manifest_id,
                through_observation_sequence,
                readiness_status,
                manifest_content_hash,
                execution_plan_content_hash,
                findings,
                ordered_transaction_ids,
                correlation_id
            ) VALUES (
                :event_id,
                :state_version,
                :manifest_id,
                :through_observation_sequence,
                'AWAITING_CHILDREN',
                :manifest_content_hash,
                NULL,
                CAST('[{"code":"CHILD_CORRECTION_OBSERVED"}]' AS jsonb),
                CAST('[]' AS jsonb),
                'corr-ca-db-001'
            )
            """
        )
        connection.execute(
            text(
                """
                UPDATE corporate_action_events
                SET readiness_status = 'AWAITING_CHILDREN',
                    state_version = 3
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
        )
        connection.execute(
            awaiting_insert,
            {
                "event_id": event_id,
                "state_version": 3,
                "manifest_id": manifest_id,
                "through_observation_sequence": 2,
                "manifest_content_hash": manifest_content_hash,
            },
        )
        corrected_observation = target_observation | {
            "observation_sequence": 3,
            "transaction_epoch": 1,
            "delivery_event_id": "delivery-ca-db-003",
        }
        connection.execute(observation_insert, corrected_observation)
        _expect_integrity_error(
            connection,
            observation_insert,
            corrected_observation
            | {
                "observation_sequence": 4,
                "delivery_event_id": "delivery-ca-db-same-epoch-conflict",
                "observed_content_hash": source_content_hash,
            },
            match="correction epoch must increase monotonically",
        )
        _expect_integrity_error(
            connection,
            observation_insert,
            target_observation
            | {
                "observation_sequence": 4,
                "delivery_event_id": "delivery-ca-db-lower-epoch",
            },
            match="correction epoch must increase monotonically",
        )
        connection.execute(
            text(
                """
                UPDATE corporate_action_events
                SET last_observation_sequence = 3,
                    readiness_status = 'READY',
                    state_version = 4
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
        )
        connection.execute(
            readiness_insert,
            readiness | {"state_version": 4, "through_observation_sequence": 3},
        )

        immutable_mutations = (
            text(
                "UPDATE corporate_action_manifest_versions "
                "SET source_revision = 'tampered' WHERE id = :id"
            ),
            text("DELETE FROM corporate_action_manifest_nodes WHERE manifest_id = :id"),
            text(
                "UPDATE corporate_action_manifest_edges SET successor_transaction_id = "
                "'CA-SOURCE-DB-001' WHERE manifest_id = :id"
            ),
            text("DELETE FROM corporate_action_child_observations WHERE event_id = :id"),
            text(
                "UPDATE corporate_action_readiness_evaluations "
                "SET correlation_id = 'tampered' WHERE event_id = :id"
            ),
        )
        for index, mutation in enumerate(immutable_mutations):
            _expect_integrity_error(
                connection,
                mutation,
                {"id": manifest_id if index < 3 else event_id},
                match="ledger rows are immutable",
            )
        _expect_integrity_error(
            connection,
            readiness_insert,
            readiness | {"state_version": 4, "through_observation_sequence": 3},
        )

        migration["downgrade"]()
        assert not TABLES.intersection(inspect(connection).get_table_names())
        migration["upgrade"]()
        assert TABLES.issubset(inspect(connection).get_table_names())
