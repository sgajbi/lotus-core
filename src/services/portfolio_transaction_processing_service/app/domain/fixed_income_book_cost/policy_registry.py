"""Exact-identity registry for governed amortized-cost policies."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .policy import AmortizedCostPolicy


class AmortizedCostPolicyRegistryError(ValueError):
    """Base error for ambiguous or unsupported policy registry state."""


class DuplicateAmortizedCostPolicyError(AmortizedCostPolicyRegistryError):
    """Raised when one policy identity is registered more than once."""


class UnsupportedAmortizedCostPolicyError(AmortizedCostPolicyRegistryError):
    """Raised when source authority references an unregistered policy identity."""


@dataclass(frozen=True, slots=True)
class AmortizedCostPolicyIdentity:
    """Stable policy lookup key carried by source-owned lot assignments."""

    policy_id: str
    policy_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str):
            raise TypeError("policy_id must be a string")
        normalized_policy_id = self.policy_id.strip()
        if not normalized_policy_id:
            raise ValueError("policy_id must be nonblank")
        object.__setattr__(self, "policy_id", normalized_policy_id)
        if not isinstance(self.policy_version, int) or isinstance(self.policy_version, bool):
            raise TypeError("policy_version must be an integer")
        if self.policy_version < 1:
            raise ValueError("policy_version must be positive")


class AmortizedCostPolicyRegistry:
    """Resolve only explicitly registered accounting methodology.

    Transport and product metadata may select an exact policy identity, but they cannot create,
    infer, or silently fall back to calculation semantics. Registration therefore rejects even
    identical duplicate identities so deployment configuration remains unambiguous.
    """

    def __init__(self, policies: Iterable[AmortizedCostPolicy]) -> None:
        registered: dict[AmortizedCostPolicyIdentity, AmortizedCostPolicy] = {}
        for policy in policies:
            if not isinstance(policy, AmortizedCostPolicy):
                raise TypeError("policies must contain AmortizedCostPolicy values")
            identity = AmortizedCostPolicyIdentity(policy.policy_id, policy.policy_version)
            if identity in registered:
                raise DuplicateAmortizedCostPolicyError(
                    "amortized-cost policy identity is registered more than once: "
                    f"{identity.policy_id}@{identity.policy_version}"
                )
            registered[identity] = policy
        self._registered = registered

    def resolve(self, *, policy_id: str, policy_version: int) -> AmortizedCostPolicy:
        """Return exact policy semantics or fail closed without version fallback."""

        identity = AmortizedCostPolicyIdentity(policy_id, policy_version)
        policy = self._registered.get(identity)
        if policy is None:
            raise UnsupportedAmortizedCostPolicyError(
                "amortized-cost policy is not registered: "
                f"{identity.policy_id}@{identity.policy_version}"
            )
        return policy

    @property
    def identities(self) -> tuple[AmortizedCostPolicyIdentity, ...]:
        """Expose deterministic supportability evidence without leaking mutable state."""

        return tuple(
            sorted(
                self._registered,
                key=lambda identity: (identity.policy_id, identity.policy_version),
            )
        )
