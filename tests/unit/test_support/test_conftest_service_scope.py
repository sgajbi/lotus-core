from tests.conftest import DB_ONLY_SERVICES, FULL_STACK_SERVICES, _test_services_for_scope


def test_unit_db_scope_uses_db_only_services() -> None:
    assert _test_services_for_scope("unit-db") == DB_ONLY_SERVICES


def test_transaction_contract_scope_uses_db_only_services() -> None:
    assert _test_services_for_scope("transaction-buy-contract") == DB_ONLY_SERVICES
    assert _test_services_for_scope("transaction-dividend-contract") == DB_ONLY_SERVICES
    assert _test_services_for_scope("transaction-interest-contract") == DB_ONLY_SERVICES
    assert _test_services_for_scope("transaction-fx-contract") == DB_ONLY_SERVICES


def test_other_scopes_keep_full_stack_services() -> None:
    assert _test_services_for_scope("integration-all") == FULL_STACK_SERVICES
    assert _test_services_for_scope("pytest") == FULL_STACK_SERVICES
