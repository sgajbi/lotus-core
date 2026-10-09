"""Actual signed consumer admission and safe retained replay, without PostgreSQL claims."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.fx_cut_authorization import authenticate_fx_cut_authorization
from portfolio_common.fx_source_admission import FxSourceAdmissionRejected
from portfolio_common.fx_source_configuration import load_fx_source_policies

from src.services.persistence_service.app.consumers import fx_source_cut
from src.services.persistence_service.app.consumers.fx_rate_consumer import FxRateConsumer
from src.services.persistence_service.app.repositories import fx_source_repository
from src.services.persistence_service.app.repositories.fx_source_repository import FxSourceConflict
from tests.test_support.fx_source_fixtures import (
    configure_synthetic_fx_source,
    signed_event,
    synthetic_revision,
)

pytestmark = [pytest.mark.unit, pytest.mark.security, pytest.mark.contract, pytest.mark.asyncio]
NOW = datetime(2026, 10, 9, tzinfo=UTC)


@pytest.mark.parametrize(
    "variant", ["fresh", "exact-expired", "new-fresh", "new-expired", "conflict"]
)
async def test_retained_replay_binds_original_attestation_not_any_renewed_token(
    monkeypatch, variant
):
    configure_synthetic_fx_source(monkeypatch)
    original = signed_event(accepted_at=NOW)
    event = (
        signed_event(accepted_at=NOW + timedelta(seconds=1))
        if variant.startswith("new")
        else original
    )
    _, original_digest = authenticate_fx_cut_authorization(
        original.authorization, original.source_cut(), relay_policy=load_fx_source_policies().relay
    )
    row = (
        None
        if variant == "fresh"
        else SimpleNamespace(
            cut_id=original.source_cut().cut_id,
            content_hash="0" * 64 if variant == "conflict" else original.source_cut().content_hash,
            admission_receipt={"attestation_sha256": original_digest},
        )
    )
    db = AsyncMock()
    db.scalar.return_value = row
    clock = NOW + timedelta(seconds=302 if "expired" in variant else 2)

    class Clock:
        @staticmethod
        def now(_timezone):
            return clock

    monkeypatch.setattr(fx_source_cut, "datetime", Clock)
    if variant == "new-expired":
        with pytest.raises(FxSourceAdmissionRejected, match="EXPIRED_OR_FUTURE"):
            await fx_source_cut.prepare_fx_source_cut(db, event)
    elif variant == "conflict":
        with pytest.raises(FxSourceConflict, match="CUT_VERSION_CONFLICT"):
            await fx_source_cut.prepare_fx_source_cut(db, event)
    else:
        prepared = await fx_source_cut.prepare_fx_source_cut(db, event)
        assert prepared.verified.durable_replay is (variant == "exact-expired")
        assert prepared.verified.admission.cut == original.source_cut()


async def test_changed_content_never_reads_retained_authority_before_authentication(monkeypatch):
    configure_synthetic_fx_source(monkeypatch)
    event = signed_event(accepted_at=NOW)
    modified = event.authorization.model_copy(update={"signature": "0" * 64})
    event = event.model_copy(update={"authorization": modified})
    db = AsyncMock()
    with pytest.raises(FxSourceAdmissionRejected, match="SIGNATURE_INVALID"):
        await fx_source_cut.prepare_fx_source_cut(db, event)
    db.scalar.assert_not_awaited()


@pytest.mark.parametrize("existing_head", [False, True])
async def test_exact_uncommitted_predecessor_is_typed_pending(existing_head):
    member = synthetic_revision(source_revision="3", predecessor_revision_id="a" * 64)
    db = AsyncMock()
    db.scalars.return_value = SimpleNamespace(
        all=lambda: [SimpleNamespace(revision_id="b" * 64)] if existing_head else []
    )
    db.get.return_value = None
    with pytest.raises(FxSourceConflict, match="FX_SOURCE_PREDECESSOR_PENDING") as failure:
        await fx_source_repository.FxSourceRepository(db)._require_predecessor(member)
    assert type(failure.value).__name__ == "FxSourcePredecessorPending"
    assert member.predecessor_revision_id in str(failure.value)
    db.get.assert_awaited_once()


async def test_retained_non_head_predecessor_is_terminal_not_pending():
    member = synthetic_revision(source_revision="3", predecessor_revision_id="a" * 64)
    db = AsyncMock()
    db.scalars.return_value = SimpleNamespace(all=lambda: [SimpleNamespace(revision_id="b" * 64)])
    db.get.return_value = SimpleNamespace(revision_id="a" * 64)
    with pytest.raises(FxSourceConflict, match="STALE_PREDECESSOR") as failure:
        await fx_source_repository.FxSourceRepository(db)._require_predecessor(member)
    assert type(failure.value) is FxSourceConflict


async def test_only_typed_pending_conflict_crosses_retry_boundary(monkeypatch):
    configure_synthetic_fx_source(monkeypatch)
    db = AsyncMock()
    db.scalar.return_value = None
    prepared = await fx_source_cut.prepare_fx_source_cut(db, signed_event())
    consumer = FxRateConsumer(
        bootstrap_servers="synthetic", topic="fx_rates.raw.received", group_id="synthetic"
    )
    repository = MagicMock()
    repository.retain_admitted_cut = AsyncMock(
        side_effect=fx_source_repository.FxSourcePredecessorPending("a" * 64)
    )
    monkeypatch.setattr(
        "src.services.persistence_service.app.consumers.fx_rate_consumer.FxSourceRepository",
        lambda _: repository,
    )
    with pytest.raises(RetryableConsumerError, match="PREDECESSOR_PENDING"):
        await consumer.handle_persistence(db, prepared)
    # A message with the same text but no owning typed distinction is terminal.
    repository.retain_admitted_cut.side_effect = FxSourceConflict("FX_SOURCE_PREDECESSOR_PENDING")
    with pytest.raises(FxSourceConflict):
        await consumer.handle_persistence(db, prepared)


@pytest.mark.parametrize(
    "supplied,expected", [(None, (8, 60)), (0, (8, 60)), (2, (2, 2)), (90, (8, 60))]
)
async def test_fx_retry_budget_is_finite_and_never_weakens_tighter_limits(supplied, expected):
    consumer = FxRateConsumer(
        bootstrap_servers="synthetic",
        topic="fx_rates.raw.received",
        group_id="synthetic",
        retryable_failure_max_attempts=supplied,
        retryable_failure_max_elapsed_seconds=supplied,
    )
    assert (
        consumer._retryable_failure_max_attempts,
        consumer._retryable_failure_max_elapsed_seconds,
    ) == expected
