"""Closed shared consumer contract and bounded batched read qualification."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.api_contract.transaction_source_evidence import TransactionSourceEvidence
from portfolio_common.infrastructure.transaction_source_evidence import (
    SqlAlchemyTransactionSourceEvidence,
)
from pydantic import ValidationError

from tests.test_support.fx_source_evidence import TENANT, fx_source_fixture


def test_closed_unavailable_contract_cannot_claim_amounts_or_raw_authority():
    values = dict(
        consumer="core-qcp",
        tenant_id=TENANT.value,
        portfolio_id="QCP-FX-PORT",
        transaction_id="TX",
        selection="current",
        status="UNAVAILABLE",
        source_cut_sha256="a" * 64,
    )
    proof = TransactionSourceEvidence(**values)
    assert proof.realized_fx_pnl_local is None
    for added in (
        {"raw_payload": {}},
        {"authorization": {}},
        {"realized_fx_pnl_local": Decimal("0")},
    ):
        with pytest.raises(ValidationError):
            TransactionSourceEvidence(**values, **added)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "local,base", [(None, Decimal("12")), (Decimal("0"), Decimal("-12")), (None, None)]
)
async def test_shared_read_independently_qualifies_original_source_in_one_borrowed_read(
    local, base
):
    raw, _, transaction = fx_source_fixture(local, base)
    result = MagicMock()
    result.all.return_value = [(transaction, SimpleNamespace(id=17, payload=raw), None, None, None)]
    session = AsyncMock()
    session.execute.return_value = result
    proofs = await SqlAlchemyTransactionSourceEvidence(session).read(
        tenant_id=TENANT.value,
        portfolio_id=transaction.portfolio_id,
        transaction_ids=[transaction.transaction_id],
        consumer="core-qcp",
    )
    proof = proofs[transaction.transaction_id]
    assert (proof.realized_fx_pnl_local, proof.realized_fx_pnl_base) == (local, base)
    assert proof.status == ("QUALIFIED" if local is not None and base is not None else "INCOMPLETE")
    assert proof.producer_algorithm_version == 2
    assert proof.root_raw_id == "17"
    assert proof.consumer == "core-qcp"
    assert proof.confirmed_at is None
    assert proof.original_local_present is (local is not None)
    assert proof.original_base_present is (base is not None)
    assert "RawTransactionPersisted" in session.execute.call_args.args[0].compile().params.values()
    session.execute.assert_awaited_once()
    for method in (session.flush, session.commit, session.rollback, session.close):
        method.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_read_batches_multiple_records_and_refuses_ambiguous_or_foreign_revision():
    raw, _, transaction = fx_source_fixture(Decimal("0"), Decimal("12"))
    row = (transaction, SimpleNamespace(id=17, payload=raw), None, None, None)
    result = MagicMock()
    result.all.return_value = [row, row]
    session = AsyncMock()
    session.execute.return_value = result
    adapter = SqlAlchemyTransactionSourceEvidence(session)
    proofs = await adapter.read(
        tenant_id=TENANT.value,
        portfolio_id=transaction.portfolio_id,
        transaction_ids=[transaction.transaction_id, "not-owned"],
        consumer="core-ledger",
    )
    assert all(proof.status == "UNAVAILABLE" for proof in proofs.values())
    session.execute.assert_awaited_once()
    result.all.return_value = [row]
    proofs = await adapter.read(
        tenant_id=TENANT.value,
        portfolio_id=transaction.portfolio_id,
        transaction_ids=[transaction.transaction_id],
        consumer="core-ledger",
        selection="revision",
        revision_id="foreign",
    )
    assert proofs[transaction.transaction_id].status == "UNAVAILABLE"
