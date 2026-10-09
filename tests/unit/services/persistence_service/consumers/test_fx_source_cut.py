"""Actual signed consumer admission and safe retained replay, without PostgreSQL claims."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.fx_cut_authorization import authenticate_fx_cut_authorization
from portfolio_common.fx_source_admission import FxSourceAdmissionRejected
from portfolio_common.fx_source_configuration import load_fx_source_policies

from src.services.persistence_service.app.consumers import fx_source_cut
from src.services.persistence_service.app.repositories.fx_source_repository import FxSourceConflict
from tests.test_support.fx_source_fixtures import configure_synthetic_fx_source, signed_event

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
