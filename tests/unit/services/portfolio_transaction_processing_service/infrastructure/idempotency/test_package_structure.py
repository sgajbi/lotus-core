"""Protect transaction-processing idempotency infrastructure ownership."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]


def test_idempotency_adapter_is_not_embedded_in_unit_of_work() -> None:
    source_root = (
        REPOSITORY_ROOT / "src/services/portfolio_transaction_processing_service/app/infrastructure"
    )
    adapter_source = source_root / "idempotency/processing_claims.py"
    unit_of_work_source = source_root / "transaction_processing/unit_of_work.py"
    root_exports = (source_root / "__init__.py").read_text(encoding="utf-8")

    assert adapter_source.is_file()
    assert "class SqlAlchemyTransactionIdempotencyAdapter" not in unit_of_work_source.read_text(
        encoding="utf-8"
    )
    assert "SqlAlchemyTransactionIdempotencyAdapter" not in root_exports
    assert "TRANSACTION_PROCESSING_SERVICE_NAME" not in root_exports
