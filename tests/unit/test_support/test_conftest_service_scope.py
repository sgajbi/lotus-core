from scripts.test_manifest import SUITE_RUNTIME_MODE
from tests.conftest import (
    DB_ONLY_SERVICES,
    DB_PLUS_KAFKA_SERVICES,
    FULL_STACK_SERVICES,
    _test_services_for_scope,
)


def test_manifest_db_direct_suites_use_isolated_infrastructure_services() -> None:
    db_direct_suites = [
        suite_name
        for suite_name, runtime_mode in SUITE_RUNTIME_MODE.items()
        if runtime_mode == "db_direct"
    ]

    assert db_direct_suites
    for suite_name in db_direct_suites:
        assert tuple(_test_services_for_scope(suite_name)) in {
            tuple(DB_ONLY_SERVICES),
            tuple(DB_PLUS_KAFKA_SERVICES),
        }


def test_db_direct_integration_scopes_use_db_only_services() -> None:
    assert _test_services_for_scope("integration-lite") == DB_ONLY_SERVICES
    assert _test_services_for_scope("ops-contract") == DB_ONLY_SERVICES


def test_integration_all_keeps_kafka_infrastructure_without_live_workers() -> None:
    assert _test_services_for_scope("integration-all") == DB_PLUS_KAFKA_SERVICES
    assert "kafka" in DB_PLUS_KAFKA_SERVICES
    assert "kafka-topic-creator" in DB_PLUS_KAFKA_SERVICES
    assert "ingestion_service" not in DB_PLUS_KAFKA_SERVICES
    assert "query_service" not in DB_PLUS_KAFKA_SERVICES


def test_unit_db_scope_uses_db_only_services() -> None:
    assert _test_services_for_scope("unit-db") == DB_ONLY_SERVICES


def test_transaction_contract_scope_uses_db_only_services() -> None:
    assert _test_services_for_scope("transaction-buy-contract") == DB_ONLY_SERVICES
    assert _test_services_for_scope("transaction-sell-contract") == DB_ONLY_SERVICES
    assert _test_services_for_scope("transaction-dividend-contract") == DB_ONLY_SERVICES
    assert _test_services_for_scope("transaction-interest-contract") == DB_ONLY_SERVICES
    assert _test_services_for_scope("transaction-fx-contract") == DB_ONLY_SERVICES
    assert (
        _test_services_for_scope("transaction-portfolio-flow-bundle-contract") == DB_ONLY_SERVICES
    )


def test_unspecified_scopes_keep_full_stack_services() -> None:
    assert _test_services_for_scope("pytest") == FULL_STACK_SERVICES
