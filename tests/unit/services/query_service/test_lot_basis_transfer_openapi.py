"""Verify the additive basis-transfer supportability route contract."""

from src.services.query_service.app.main import app


def test_openapi_exposes_distinct_source_to_target_basis_transfer_vocabulary() -> None:
    path = (
        "/portfolios/{portfolio_id}/transactions/{source_transaction_id}/lot-basis-transfer-receipt"
    )
    operation = app.openapi()["paths"][path]["get"]

    assert operation["summary"] == "Get Latest Immutable Lot Basis-Transfer Receipt"
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("LotBasisTransferReceiptResponse")
    assert "disposal" not in operation["description"].lower()
