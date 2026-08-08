from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.transaction import (
    TransactionIdentityFamily,
    TransactionIdentityOwnership,
)
from portfolio_common.infrastructure.persistence.transaction_identity_guard import (
    GeneratedTransactionIdentityCollisionError,
    transaction_identity_update_allowed,
)
from sqlalchemy.dialects import postgresql


def _compiled_predicate(ownership: TransactionIdentityOwnership) -> str:
    return str(
        transaction_identity_update_allowed(DBTransaction, ownership).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_source_identity_rejects_both_generated_child_families() -> None:
    sql = _compiled_predicate(
        TransactionIdentityOwnership(
            family=TransactionIdentityFamily.SOURCE,
            transaction_id="SOURCE-1",
            portfolio_id="PORT-1",
        )
    )

    assert "trim(transactions.portfolio_id) = 'PORT-1'" in sql
    assert "NOT" in sql
    assert sql.count("coalesce(") == 2
    assert "'-CASHLEG'" in sql
    assert "'-ACCRUED-INTEREST'" in sql


def test_generated_cash_identity_requires_same_family_and_origin() -> None:
    sql = _compiled_predicate(
        TransactionIdentityOwnership(
            family=TransactionIdentityFamily.GENERATED_SETTLEMENT_CASH,
            transaction_id="SOURCE-1-CASHLEG",
            portfolio_id="PORT-1",
            originating_transaction_id="SOURCE-1",
            originating_transaction_type="BUY",
        )
    )

    assert "upper(trim(transactions.transaction_type)) = 'ADJUSTMENT'" in sql
    assert "upper(trim(transactions.cash_entry_mode)) = 'AUTO_GENERATE'" in sql
    assert "trim(transactions.originating_transaction_id) = 'SOURCE-1'" in sql
    assert "upper(trim(transactions.originating_transaction_type)) = 'BUY'" in sql


def test_redemption_interest_identity_requires_same_family_and_origin() -> None:
    sql = _compiled_predicate(
        TransactionIdentityOwnership(
            family=TransactionIdentityFamily.REDEMPTION_ACCRUED_INTEREST,
            transaction_id="REDEMPTION-1-ACCRUED-INTEREST",
            portfolio_id="PORT-1",
            originating_transaction_id="REDEMPTION-1",
            originating_transaction_type="MATURITY_REDEMPTION",
        )
    )

    assert "upper(trim(transactions.transaction_type)) = 'INTEREST'" in sql
    assert "'REDEMPTION_ACCRUED_INTEREST'" in sql
    assert "trim(transactions.originating_transaction_id) = 'REDEMPTION-1'" in sql
    assert "REDEMPTION_TO_ACCRUED_INTEREST" in sql
    assert "upper(trim(transactions.originating_transaction_type)) = 'MATURITY_REDEMPTION'" in sql


def test_collision_error_exposes_stable_reason_code() -> None:
    error = GeneratedTransactionIdentityCollisionError("SOURCE-1-CASHLEG")

    assert error.reason_code == "generated_transaction_identity_collision"
    assert str(error) == (
        "generated_transaction_identity_collision: ownership conflict for SOURCE-1-CASHLEG"
    )
