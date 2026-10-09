"""Verify independent fact receipts; no FX grants or implicit institutional approval."""

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import ValidationError

from .domain.portfolio_source_observations import (
    ObservationConflict,
    ObservationCoverage,
    require_observation_identity,
)
from .domain.portfolio_source_verification import (
    ObservationVerificationClaims,
    ObservationVerificationScope,
    ObservationVerificationSubject,
    SignedObservationVerificationReceipt,
)


def observation_verification_claims_bytes(claims: ObservationVerificationClaims) -> bytes:
    """Versioned exact wire material; producer facts retain their original digest."""
    return json.dumps(
        claims.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ObservationVerificationKey:
    """Server-injected fact-verification trust, not a submission or FX relay grant.

    Explicit scope prevents a key from approving another producer, consumer,
    portfolio or family. Revocation is read at verification time; none of this
    configuration is deserialized from an ingestion body or caller header.
    """

    issuer_id: str
    key_id: str
    scope: ObservationVerificationScope
    valid_from: datetime
    valid_to: datetime
    secret: str = field(repr=False)
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("issuer_id", "key_id"):
            require_observation_identity(getattr(self, name), name)
        if not isinstance(self.scope, ObservationVerificationScope):
            raise ValueError("verification key requires typed source scope")
        ObservationVerificationScope.model_validate(
            self.scope.model_dump(mode="python", warnings="error")
        )
        if not isinstance(self.valid_from, datetime) or not isinstance(self.valid_to, datetime):
            raise ValueError("verification key requires aware validity instants")
        instants = (self.valid_from, self.valid_to, self.revoked_at)
        if any(
            value is not None and (not isinstance(value, datetime) or value.utcoffset() is None)
            for value in instants
        ):
            raise ValueError("verification key requires aware validity instants")
        if (
            self.valid_to <= self.valid_from
            or not isinstance(self.secret, str)
            or len(self.secret.encode("utf-8")) < 32
        ):
            raise ValueError("invalid observation verification key configuration")


@dataclass(frozen=True, slots=True)
class VerifiedObservationReceipt:
    """Cryptographic source binding only; persistence/assembly approval not implied."""

    receipt: SignedObservationVerificationReceipt
    attestation_sha256: str


@dataclass(frozen=True, slots=True)
class ObservationReceiptVerifier:
    keys: tuple[ObservationVerificationKey, ...] = ()

    def __post_init__(self) -> None:
        if type(self.keys) is not tuple or any(
            not isinstance(key, ObservationVerificationKey) for key in self.keys
        ):
            raise ValueError("verification keys require immutable typed configuration")
        if len({(key.issuer_id, key.key_id) for key in self.keys}) != len(self.keys):
            raise ValueError("duplicate observation verification key")

    def verify(
        self,
        receipt: SignedObservationVerificationReceipt,
        *,
        expected: ObservationVerificationSubject,
        now: datetime,
    ) -> VerifiedObservationReceipt:
        try:
            # Frozen Pydantic models do not validate model_construct/model_copy.
            receipt = SignedObservationVerificationReceipt.model_validate(
                receipt.model_dump(mode="python", warnings="error")
            )
            expected = ObservationVerificationSubject.model_validate(
                expected.model_dump(mode="python", warnings="error")
            )
        except (ValidationError, ValueError, AttributeError, TypeError) as exc:
            raise ObservationConflict("SOURCE_VERIFICATION_SHAPE_INVALID") from exc
        claims = receipt.claims
        key = next(
            (
                key
                for key in self.keys
                if (key.issuer_id, key.key_id) == (claims.issuer_id, claims.key_id)
            ),
            None,
        )
        if key is None:
            raise ObservationConflict("SOURCE_VERIFICATION_AUTHORITY_UNAVAILABLE")
        material = observation_verification_claims_bytes(claims)
        signature = hmac.new(key.secret.encode("utf-8"), material, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, receipt.signature):
            raise ObservationConflict("SOURCE_VERIFICATION_SIGNATURE_INVALID")
        if claims.subject != expected or key.scope != ObservationVerificationScope.from_subject(
            expected
        ):
            raise ObservationConflict("SOURCE_VERIFICATION_BINDING_MISMATCH")
        if (
            not isinstance(now, datetime)
            or now.utcoffset() is None
            or not key.valid_from <= claims.issued_at < claims.expires_at <= key.valid_to
            or not claims.issued_at <= now < claims.expires_at
            or (key.revoked_at is not None and now >= key.revoked_at)
        ):
            raise ObservationConflict("SOURCE_VERIFICATION_EXPIRED_OR_REVOKED")
        if expected.envelope.coverage != ObservationCoverage.COMPLETE:
            raise ObservationConflict("SOURCE_VERIFICATION_COVERAGE_INCOMPLETE")
        digest = hashlib.sha256(material + receipt.signature.encode("ascii")).hexdigest()
        return VerifiedObservationReceipt(receipt, digest)


@dataclass(frozen=True, slots=True)
class ObservationCutRegistration:
    """Independently supplied complete manifest binding from the owning producer."""

    scope: ObservationVerificationScope
    source_cut_id: str
    manifest_hash: str

    def __post_init__(self) -> None:
        from .domain.calculation_lineage import require_sha256_digest

        require_observation_identity(self.source_cut_id, "registered_source_cut")
        require_sha256_digest(self.manifest_hash, "registered_manifest_hash")


@dataclass(frozen=True, slots=True)
class ObservationVerificationAuthority:
    verifier: ObservationReceiptVerifier = field(default_factory=ObservationReceiptVerifier)
    cuts: tuple[ObservationCutRegistration, ...] = ()

    def __post_init__(self) -> None:
        if type(self.cuts) is not tuple or any(
            not isinstance(cut, ObservationCutRegistration) for cut in self.cuts
        ):
            raise ValueError("typed immutable cut registration required")
        identities = [(cut.scope.model_dump_json(), cut.source_cut_id) for cut in self.cuts]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate source cut registration")

    def verify_fact(self, fact, receipt, *, consumer_id, as_of_date, now):
        # Never resolve a complete cut from the submitted receipt's manifest digest.
        scope_subject = ObservationVerificationSubject.from_observation(
            fact,
            source_cut_manifest_hash="0" * 64,
            consumer_id=consumer_id,
            as_of_date=as_of_date,
        )
        scope = ObservationVerificationScope.from_subject(scope_subject)
        cut = next(
            (
                cut
                for cut in self.cuts
                if cut.scope == scope and cut.source_cut_id == fact.envelope.source_cut_id
            ),
            None,
        )
        if cut is None:
            raise ObservationConflict("SOURCE_VERIFICATION_CUT_UNAVAILABLE")
        expected = scope_subject.model_copy(update={"source_cut_manifest_hash": cut.manifest_hash})
        return self.verifier.verify(receipt, expected=expected, now=now)
