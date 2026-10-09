"""Source attribution and fail-closed availability without consumer policy derivation."""

from datetime import UTC, datetime

from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    ObservationConflict,
    ObservationFamily,
)
from portfolio_common.portfolio_source_observation_verification import (
    ObservationVerificationAuthority,
)
from portfolio_common.source_data_product_metadata import (
    SourceDataDegradationDetail,
    SourceDataDegradationSummary,
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.portfolio_source_observations import (
    CashObservationEvidence,
    FundingInvestmentEvidence,
    ObservationSelector,
    PortfolioSourceObservationsRequest,
    PortfolioSourceObservationsResponse,
)
from ..ports.portfolio_source_observations import (
    PersistedSourceObservation,
    PortfolioSourceObservationReader,
)


class PortfolioSourceObservationsService:
    def __init__(
        self,
        reader: PortfolioSourceObservationReader,
        verification_authority: ObservationVerificationAuthority | None = None,
    ):
        self.reader = reader
        self.verification_authority = verification_authority or ObservationVerificationAuthority()

    async def query(
        self,
        *,
        tenant_id: str,
        portfolio_id: str,
        request: PortfolioSourceObservationsRequest,
        consumer_id: str | None = None,
    ) -> PortfolioSourceObservationsResponse:
        cash, funding = await self.reader.read_snapshot(
            tenant_id=tenant_id, portfolio_id=portfolio_id, request=request
        )
        reasons = ["SOURCE_PRODUCER_UNQUALIFIED", "JOINED_SOURCE_CUT_COMPATIBILITY_UNPROVEN"]
        verified = self._verified_selection(
            ((cash, request.cash), (funding, request.funding_investment)),
            consumer_id=consumer_id,
            request=request,
        )
        cash_evidence = self._project(
            cash,
            request.cash,
            ObservationFamily.CASH_AVAILABILITY,
            tenant_id,
            portfolio_id,
            request,
            reasons,
            verified.get(ObservationFamily.CASH_AVAILABILITY),
        )
        funding_evidence = self._project(
            funding,
            request.funding_investment,
            ObservationFamily.FUNDING_INVESTMENT,
            tenant_id,
            portfolio_id,
            request,
            reasons,
            verified.get(ObservationFamily.FUNDING_INVESTMENT),
        )
        if any(
            selector is not None and (evidence is None or evidence.verification_receipt is None)
            for selector, evidence in (
                (request.cash, cash_evidence),
                (request.funding_investment, funding_evidence),
            )
        ):
            verified = {}
            if cash_evidence is not None:
                cash_evidence = cash_evidence.model_copy(update={"verification_receipt": None})
            if funding_evidence is not None:
                funding_evidence = funding_evidence.model_copy(
                    update={"verification_receipt": None}
                )
        payload = {
            "portfolio_id": portfolio_id,
            "as_of_date": request.as_of_date,
            "cash": cash_evidence.model_dump() if cash_evidence else None,
            "funding_investment": funding_evidence.model_dump() if funding_evidence else None,
            "reason_codes": reasons,
        }
        if verified:
            payload["fact_verification_status"] = "FACT_VERIFIED"
        metadata = source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            generated_at=datetime.now(UTC),
            tenant_id=tenant_id,
            data_quality_status="UNAVAILABLE",
            source_evidence_current=False,
            freshness_status="UNAVAILABLE",
            source_cut_id=None,
            content_hash=stable_content_hash(payload),
            source_refs=[
                f"lotus-core://source/PortfolioFinancialSourceObservations/{portfolio_id}"
            ],
            lineage={"source_owner": "lotus-core", "qualification": "unqualified"},
        )
        return PortfolioSourceObservationsResponse(
            **{
                **metadata,
                **payload,
                "cash": cash_evidence,
                "funding_investment": funding_evidence,
            },
            degradation=_unavailable_degradation(reasons),
        )

    def _verified_selection(self, selection, *, consumer_id, request):
        verified = {}
        if consumer_id is None:
            return verified
        now = datetime.now(UTC)
        for record, selector in selection:
            if selector is None:
                continue
            if record is None:
                return {}
            for receipt in record.verification_receipts:
                try:
                    self.verification_authority.verify_fact(
                        record.fact,
                        receipt,
                        consumer_id=consumer_id,
                        as_of_date=request.as_of_date,
                        now=now,
                    )
                except (ObservationConflict, ValueError):
                    continue
                verified[record.fact.family] = receipt
                break
            else:
                # No partial publication: one invalid selected family removes every receipt.
                return {}
        return verified

    @staticmethod
    def _project(
        record: PersistedSourceObservation | None,
        selector: ObservationSelector | None,
        family: ObservationFamily,
        tenant_id: str,
        portfolio_id: str,
        request: PortfolioSourceObservationsRequest,
        reasons: list[str],
        verification_receipt=None,
    ):
        prefix = family.value.upper()
        if selector is None or record is None:
            reasons.append(f"{prefix}_OBSERVATION_UNAVAILABLE")
            return None
        fact = record.fact
        envelope = fact.envelope
        if (
            envelope.tenant_id != tenant_id
            or envelope.portfolio_id != portfolio_id
            or envelope.producer_id != selector.producer_id
            or envelope.source_record_id != selector.source_record_id
            or fact.family != family
        ):
            reasons.append(f"{prefix}_SOURCE_SCOPE_MISMATCH")
            return None
        if not envelope.is_effective(request.as_of_date):
            reasons.append(f"{prefix}_BUSINESS_DATE_UNAVAILABLE")
            return None
        if record.observation_id != fact.content_hash or record.qualification != "unqualified":
            reasons.append(f"{prefix}_SOURCE_EVIDENCE_INVALID")
            return None
        if not selector.latest_restated and (
            selector.observation_id != record.observation_id
            or selector.content_hash != fact.content_hash
            or selector.source_cut_id != envelope.source_cut_id
            or selector.source_version != envelope.source_revision
        ):
            reasons.append(f"{prefix}_IMMUTABLE_PIN_MISMATCH")
            return None
        if envelope.coverage.value != "complete":
            reasons.append(f"{prefix}_COVERAGE_{envelope.coverage.value.upper()}")
        common = dict(
            observation_id=record.observation_id,
            content_hash=fact.content_hash,
            source_system=envelope.producer_id,
            source_record_id=envelope.source_record_id,
            source_version=envelope.source_revision,
            source_cut_id=envelope.source_cut_id,
            definition_version=envelope.definition_version,
            effective_from=envelope.effective_from,
            effective_to=envelope.effective_to,
            observed_at=envelope.observed_at,
            generated_at=envelope.generated_at,
            received_at=record.received_at,
            receipt_job_id=record.receipt_job_id,
            coverage=envelope.coverage.value,
            coverage_scope=envelope.coverage_scope,
            latest_restated=selector.latest_restated,
            verification_receipt=verification_receipt,
        )
        if isinstance(fact, CashAvailabilityObservation):
            return CashObservationEvidence(
                **common,
                currency=fact.currency,
                settled_amount=fact.settled,
                encumbered_amount=fact.encumbered,
                available_amount=fact.available,
            )
        return FundingInvestmentEvidence(**common, funded=fact.funded, invested=fact.invested)


def _unavailable_degradation(reasons: list[str]) -> SourceDataDegradationSummary:
    """Project bounded reasons, without qualifying facts or inventing source timestamps."""
    details = []
    for reason in reasons:
        if reason.startswith("CASH_AVAILABILITY_"):
            section, fields = "cash", ["cash"]
        elif reason.startswith("FUNDING_INVESTMENT_"):
            section, fields = "funding_investment", ["funding_investment"]
        elif reason == "SOURCE_PRODUCER_UNQUALIFIED":
            section, fields = "product", ["authoritative_state", "cash", "funding_investment"]
        else:
            section, fields = "product", ["compatibility"]
        details.append(
            SourceDataDegradationDetail(
                section=section,
                affected_fields=fields,
                source_kind="UNAVAILABLE",
                source_product_name="PortfolioFinancialSourceObservations",
                freshness_status="UNAVAILABLE",
                reason_code=reason,
            )
        )
    return SourceDataDegradationSummary(
        status="UNAVAILABLE", reason_codes=sorted(set(reasons)), details=details
    )
