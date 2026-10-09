"""Explicit scoped verifier/cut registration; empty trust and safe errors by default."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter

from .domain.portfolio_source_verification import ObservationVerificationScope
from .portfolio_source_observation_verification import (
    ObservationCutRegistration,
    ObservationReceiptVerifier,
    ObservationVerificationAuthority,
    ObservationVerificationKey,
)
from .runtime_settings import env_str


class _KeyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scope: ObservationVerificationScope
    issuer_id: str
    key_id: str
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    revoked_at: AwareDatetime | None = None
    secret_env: str = Field(pattern=r"^LOTUS_PORTFOLIO_FACT_VERIFICATION_KEY_[A-Z0-9_]{1,64}$")


class _CutEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scope: ObservationVerificationScope
    source_cut_id: str
    manifest_hash: str


def _registry(name: str) -> str:
    raw: str = env_str(name, "[]")
    if len(raw.encode()) > 65536:
        raise ValueError("bounded verification registry")
    return raw


def load_observation_verification_authority() -> ObservationVerificationAuthority:
    try:
        keys = TypeAdapter(list[_KeyEntry]).validate_json(
            _registry("LOTUS_PORTFOLIO_FACT_VERIFICATION_KEYS")
        )
        cuts = TypeAdapter(list[_CutEntry]).validate_json(
            _registry("LOTUS_PORTFOLIO_FACT_VERIFICATION_CUTS")
        )
        if len(keys) > 64 or len(cuts) > 256:
            raise ValueError("bounded verification registry")
        return ObservationVerificationAuthority(
            ObservationReceiptVerifier(
                tuple(
                    ObservationVerificationKey(
                        **item.model_dump(exclude={"scope", "secret_env"}),
                        scope=item.scope,
                        secret=env_str(item.secret_env, ""),
                    )
                    for item in keys
                )
            ),
            tuple(
                ObservationCutRegistration(**item.model_dump(exclude={"scope"}), scope=item.scope)
                for item in cuts
            ),
        )
    except (ValueError, TypeError, KeyError):
        raise ValueError("SOURCE_VERIFICATION_CONFIGURATION_INVALID") from None
