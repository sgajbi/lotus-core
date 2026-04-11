from scripts.docker_endpoint_smoke import (
    SMOKE_CSV_TRANSACTION_ID,
    SMOKE_INSTRUMENT_ID,
    SMOKE_ISIN,
    SMOKE_PORTFOLIO_ID,
    SMOKE_SECURITY_ID,
    SMOKE_TRANSACTION_ID,
    SMOKE_TRANSACTION_ID_2,
    build_smoke_cleanup_sql,
)


def test_docker_endpoint_smoke_uses_deterministic_identifiers():
    assert SMOKE_PORTFOLIO_ID == "PORT_SMOKE_CANONICAL"
    assert SMOKE_SECURITY_ID == "SEC_SMOKE_CANONICAL"
    assert SMOKE_INSTRUMENT_ID == "INST_SMOKE_CANONICAL"
    assert SMOKE_TRANSACTION_ID == "TX_SMOKE_CANONICAL"
    assert SMOKE_TRANSACTION_ID_2 == "TX2_SMOKE_CANONICAL"
    assert SMOKE_CSV_TRANSACTION_ID == "TXUP_SMOKE_CANONICAL"
    assert SMOKE_ISIN == "US000SMOKE01"


def test_docker_endpoint_smoke_cleanup_sql_purges_legacy_smoke_rows():
    sql = build_smoke_cleanup_sql()

    assert "delete from transactions where portfolio_id like 'PORT_SMOKE_%';" in sql
    assert "delete from portfolios where portfolio_id like 'PORT_SMOKE_%';" in sql
    assert "delete from market_prices where security_id like 'SEC_SMOKE_%';" in sql
    assert "delete from transaction_costs where transaction_id like 'TX%_SMOKE_%';" in sql
