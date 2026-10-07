"""Source attribution and fail-closed availability without consumer policy derivation."""

from datetime import UTC, datetime

from portfolio_common.domain.portfolio_source_observations import (
    CashAvailabilityObservation,
    ObservationFamily,
)
from portfolio_common.source_data_product_metadata import (
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
    def __init__(self, reader: PortfolioSourceObservationReader):
        self.reader = reader

    async def query(
        self, *, tenant_id: str, portfolio_id: str, request: PortfolioSourceObservationsRequest
    ) -> PortfolioSourceObservationsResponse:
        cash, funding = await self.reader.read_snapshot(
            tenant_id=tenant_id, portfolio_id=portfolio_id, request=request
        )
        reasons = ["SOURCE_PRODUCER_UNQUALIFIED", "JOINED_SOURCE_CUT_COMPATIBILITY_UNPROVEN"]
        cash_evidence = self._project(
            cash,
            request.cash,
            ObservationFamily.CASH_AVAILABILITY,
            tenant_id,
            portfolio_id,
            request,
            reasons,
        )
        funding_evidence = self._project(
            funding,
            request.funding_investment,
            ObservationFamily.FUNDING_INVESTMENT,
            tenant_id,
            portfolio_id,
            request,
            reasons,
        )
        payload = {
            "portfolio_id": portfolio_id,
            "as_of_date": request.as_of_date,
            "cash": cash_evidence.model_dump() if cash_evidence else None,
            "funding_investment": funding_evidence.model_dump() if funding_evidence else None,
            "reason_codes": reasons,
        }
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
            **{**metadata, **payload, "cash": cash_evidence, "funding_investment": funding_evidence}
        )

    @staticmethod
    def _project(
        record: PersistedSourceObservation | None,
        selector: ObservationSelector | None,
        family: ObservationFamily,
        tenant_id: str,
        portfolio_id: str,
        request: PortfolioSourceObservationsRequest,
        reasons: list[str],
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
