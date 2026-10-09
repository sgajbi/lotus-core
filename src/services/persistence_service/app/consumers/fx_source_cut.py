"""Internal FX consumer variant: authenticate then retain within its existing UOW."""

from datetime import UTC, datetime
from typing import Literal

from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.fx_cut_authorization import (
    CommittedFxCutVerification,
    VerifiedFxCutAuthorization,
    authenticate_fx_cut_authorization,
    verify_fx_cut_authorization,
)
from portfolio_common.fx_source_configuration import load_fx_source_policies
from portfolio_common.fx_source_events import FxSourceCutReceivedEvent
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.fx_source_repository import FxSourceConflict, FxSourceRepository


class FxSourceCutRetryable(RetryableConsumerError):
    """Per-message support evidence, never reusable authorization or admission."""

    def __init__(
        self,
        reason: str,
        *,
        attestation_sha256: str | None = None,
        authorization_stage: Literal[
            "unauthenticated", "authenticated", "admitted"
        ] = "unauthenticated",
    ) -> None:
        super().__init__(reason)
        self.attestation_sha256 = attestation_sha256
        self.authorization_stage = authorization_stage


class PreparedFxSourceCut(BaseModel):
    """Never a transport model; constructed only after authenticated server admission."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    received: FxSourceCutReceivedEvent
    verified: VerifiedFxCutAuthorization

    @property
    def tenant_id(self) -> str:
        return self.received.tenant_id


async def prepare_fx_source_cut(
    db: AsyncSession, event: FxSourceCutReceivedEvent
) -> PreparedFxSourceCut:
    event.bounded_payload()
    cut = event.source_cut()
    policies = load_fx_source_policies()
    _, attestation_hash = authenticate_fx_cut_authorization(
        event.authorization, cut, relay_policy=policies.relay
    )
    try:
        existing = await FxSourceRepository(db).find_cut(cut)
    except DBAPIError as error:
        # Authentication has succeeded, but server admission has not completed.
        # Never include SQL, parameters or credentials in the support reason.
        raise FxSourceCutRetryable(
            "FX_SOURCE_DATABASE_RETRY",
            attestation_sha256=attestation_hash,
            authorization_stage="authenticated",
        ) from error
    committed = None
    if existing is not None:
        if existing.content_hash != cut.content_hash:
            raise FxSourceConflict("FX_SOURCE_CUT_VERSION_CONFLICT")
        original_attestation = existing.admission_receipt.get("attestation_sha256", "")
        if original_attestation == attestation_hash:
            committed = CommittedFxCutVerification(
                existing.cut_id, existing.content_hash, original_attestation
            )
    verified = verify_fx_cut_authorization(
        event.authorization,
        cut,
        admission_policy=policies.admission,
        relay_policy=policies.relay,
        now=datetime.now(UTC),
        committed=committed,
    )
    return PreparedFxSourceCut(received=event, verified=verified)
