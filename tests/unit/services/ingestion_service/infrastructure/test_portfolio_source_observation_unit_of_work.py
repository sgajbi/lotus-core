"""Creation-effect refusal and ordering; simulated I/O is not PostgreSQL proof."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    FundingInvestmentObservation,
    ObservationCoverage,
    ObservationEnvelope,
)
from portfolio_common.portfolio_source_observation_qualification import (
    ProducerSubmissionGrant,
    UnqualifiedProducerAdmission,
)

from src.services.ingestion_service.app.infrastructure import (
    portfolio_source_observation_unit_of_work as module,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _fact(family, *, tenant="synthetic-tenant"):
    envelope = ObservationEnvelope(
        tenant,
        "synthetic-portfolio",
        "synthetic-producer",
        "record",
        1,
        "cut",
        "v1",
        date(2026, 1, 1),
        None,
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 1, tzinfo=UTC),
        ObservationCoverage.COMPLETE,
        "declared-scope",
    )
    if family == "cash":
        return CashAvailabilityObservation(envelope, "SGD", Decimal("10"), None, Decimal("0"))
    return FundingInvestmentObservation(envelope, False, None)


def _receipt(family, count=1):
    key = "cash_availability" if family == "cash" else "funding_investment"
    return SimpleNamespace(
        endpoint=f"/ingest/portfolio-{key.replace('_', '-')}-observations",
        entity_type=f"portfolio_{key}_observation",
        accepted_count=count,
        tenant_id="synthetic-tenant",
        job_id="synthetic-receipt",
        submitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        status="accepted",
        completed_at=None,
    )


@pytest.fixture
def effects(monkeypatch):
    writer = Mock()
    writer.append_cash_availability_observations = AsyncMock()
    writer.append_funding_investment_observations = AsyncMock()
    factory = Mock(return_value=writer)
    completion = AsyncMock()
    monkeypatch.setattr(module, "PortfolioSourceObservationWriter", factory)
    monkeypatch.setattr(module, "complete_synchronous_observation_receipt", completion)
    session = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock(), execute=AsyncMock())
    return session, factory, writer, completion


async def test_empty_creation_effect_refuses_before_any_effect(effects):
    session, factory, writer, completion = effects
    with pytest.raises(ValueError, match="requires facts"):
        await module.PortfolioSourceObservationStager((), ()).stage(session, _receipt("cash", 0))
    factory.assert_not_called()
    completion.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.parametrize("family", ["cash", "funding"])
@pytest.mark.parametrize("mismatch", ["endpoint", "entity", "count", "tenant", "family"])
async def test_receipt_scope_refuses_before_writer_completion_or_commit(family, mismatch, effects):
    session, factory, writer, completion = effects
    facts = (_fact(family),)
    receipt = _receipt(family)
    if mismatch == "endpoint":
        receipt.endpoint = "/ingest/transactions"
    elif mismatch == "entity":
        receipt.entity_type = "transaction"
    elif mismatch == "count":
        receipt.accepted_count = 2
    elif mismatch == "tenant":
        facts += (replace(facts[0], envelope=replace(facts[0].envelope, tenant_id="foreign")),)
        receipt.accepted_count = 2
    else:
        facts += (_fact("funding" if family == "cash" else "cash"),)
        receipt.accepted_count = 2
    before = vars(receipt).copy()
    with pytest.raises(ValueError, match="does not match its receipt"):
        await module.PortfolioSourceObservationStager(facts, ()).stage(session, receipt)
    assert vars(receipt) == before
    factory.assert_not_called()
    writer.append_cash_availability_observations.assert_not_awaited()
    writer.append_funding_investment_observations.assert_not_awaited()
    completion.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.flush.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.parametrize("family", ["cash", "funding"])
@pytest.mark.parametrize("append_fails", [False, True])
async def test_creation_effect_preserves_append_then_completion_transaction_ownership(
    family,
    append_fails,
    effects,
):
    session, factory, writer, completion = effects
    fact = _fact(family)
    receipt = _receipt(family)
    admissions = (
        UnqualifiedProducerAdmission(
            ProducerSubmissionGrant(
                fact.envelope.tenant_id,
                fact.envelope.portfolio_id,
                fact.envelope.producer_id,
                fact.family,
            )
        ),
    )
    events = []

    async def append(*args, **kwargs):
        events.append("append")
        assert args == ((fact,), admissions)
        assert kwargs == {"receipt_job_id": receipt.job_id, "received_at": receipt.submitted_at}
        if append_fails:
            raise ValueError("synthetic append refusal")

    async def complete(db, row, **kwargs):
        events.append("complete")
        assert db is session and row is receipt
        assert kwargs == {"tenant_id": receipt.tenant_id, "job_id": receipt.job_id}

    selected = (
        writer.append_cash_availability_observations
        if family == "cash"
        else writer.append_funding_investment_observations
    )
    other = (
        writer.append_funding_investment_observations
        if family == "cash"
        else writer.append_cash_availability_observations
    )
    selected.side_effect = append
    completion.side_effect = complete
    stage = module.PortfolioSourceObservationStager((fact,), admissions)
    if append_fails:
        with pytest.raises(ValueError, match="synthetic append refusal"):
            await stage.stage(session, receipt)
        assert events == ["append"]
        completion.assert_not_awaited()
    else:
        await stage.stage(session, receipt)
        assert events == ["append", "complete"]
        completion.assert_awaited_once()
    factory.assert_called_once_with(session)
    other.assert_not_awaited()
    session.commit.assert_not_awaited()
    assert receipt.status == "accepted" and receipt.completed_at is None
