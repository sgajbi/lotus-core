"""Behavior tests for QCP-owned DPM portfolio population products."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from portfolio_common.domain.tenant import TenantAuthorityMismatchError, TenantContext, TenantId
from portfolio_common.page_tokens import PageTokenCodec
from portfolio_common.source_data_product_metadata import SOURCE_METADATA_UNAVAILABLE_HASH

from src.services.query_control_plane_service.app.application.dpm_portfolio_population import (
    DpmPortfolioPopulationService,
)
from src.services.query_control_plane_service.app.contracts.dpm_portfolio_population import (
    CioModelChangeAffectedCohortRequest,
    DpmPortfolioUniverseCandidateRequest,
)
from src.services.query_control_plane_service.app.domain.dpm_portfolio_population import (
    ApprovedModelPortfolio,
    DiscretionaryMandatePopulationMember,
)

TENANT_CONTEXT = TenantContext(TenantId("TENANT_SG"), identity_verified=True)


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 5, 3, 10, tzinfo=UTC)


class _PageTokens:
    def __init__(self) -> None:
        self.cursor: dict[str, object] = {}
        self.encoded: list[dict[str, object]] = []

    def decode(self, token: str | None) -> dict[str, object]:
        return self.cursor if token else {}

    def encode(self, payload: dict[str, object]) -> str:
        self.encoded.append(payload)
        return "next-page"


class _Reader:
    def __init__(self) -> None:
        self.model: ApprovedModelPortfolio | None = _model()
        self.affected: list[DiscretionaryMandatePopulationMember] = [_mandate()]
        self.universe: list[DiscretionaryMandatePopulationMember] = [_mandate()]
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def resolve_approved_model(self, **kwargs):
        self.calls.append(("model", kwargs))
        return self.model

    async def list_affected_mandates(self, **kwargs):
        self.calls.append(("affected", kwargs))
        return self.affected

    async def list_universe_candidates(self, **kwargs):
        self.calls.append(("universe", kwargs))
        return self.universe


def _model() -> ApprovedModelPortfolio:
    return ApprovedModelPortfolio(
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        model_portfolio_version="2026.05",
        approval_status="approved",
        approved_at=datetime(2026, 5, 1, 8, tzinfo=UTC),
        effective_from=date(2026, 5, 1),
        effective_to=None,
        source_system="lotus-core",
        source_record_id="model:2026.05",
        observed_at=datetime(2026, 5, 1, 8, tzinfo=UTC),
        created_at=datetime(2026, 5, 1, 7, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 9, tzinfo=UTC),
    )


def _mandate(
    *, portfolio_id: str = "PB_SG_GLOBAL_BAL_001", mandate_id: str = "MANDATE_001"
) -> DiscretionaryMandatePopulationMember:
    return DiscretionaryMandatePopulationMember(
        portfolio_id=portfolio_id,
        mandate_id=mandate_id,
        client_id="CIF_SG_GLOBAL_BAL_001",
        booking_center_code="Singapore",
        jurisdiction_code="SG",
        discretionary_authority_status="active",
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        policy_pack_id="POLICY_PACK_BALANCED",
        mandate_objective="balanced_growth_income",
        risk_profile="balanced",
        investment_horizon="medium_term",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        binding_version=7,
        source_record_id=f"mandate:{mandate_id}",
        observed_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        created_at=datetime(2026, 5, 3, 7, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )


def _service(reader: _Reader, tokens: _PageTokens | None = None) -> DpmPortfolioPopulationService:
    return DpmPortfolioPopulationService(
        reader=reader,
        page_tokens=tokens or _PageTokens(),
        clock=_Clock(),
    )


@pytest.mark.asyncio
async def test_resolves_ready_cio_cohort_with_deterministic_source_identity() -> None:
    reader = _Reader()
    request = CioModelChangeAffectedCohortRequest(
        as_of_date=date(2026, 5, 3), tenant_id="TENANT_SG", booking_center_code="Singapore"
    )

    first = await _service(reader).resolve_cio_model_change_cohort(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        request=request,
    )
    second = await _service(reader).resolve_cio_model_change_cohort(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        request=request,
    )

    assert first is not None and second is not None
    assert first.affected_mandates[0].binding_version == 7
    assert first.supportability.state == "READY"
    assert first.data_quality_status == "ACCEPTED"
    assert first.generated_at == datetime(2026, 5, 3, 10, tzinfo=UTC)
    assert first.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert first.snapshot_id == second.snapshot_id
    assert first.model_change_event_id == second.model_change_event_id
    assert first.tenant_id == "TENANT_SG"
    assert reader.calls[1][1]["tenant_id"] == "TENANT_SG"


@pytest.mark.asyncio
async def test_missing_model_stops_before_mandate_read() -> None:
    reader = _Reader()
    reader.model = None

    response = await _service(reader).resolve_cio_model_change_cohort(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_MISSING",
        request=CioModelChangeAffectedCohortRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is None
    assert [name for name, _ in reader.calls] == ["model"]


@pytest.mark.asyncio
async def test_cio_cohort_rejects_caller_tenant_mismatch_before_source_reads() -> None:
    reader = _Reader()

    with pytest.raises(TenantAuthorityMismatchError):
        await _service(reader).resolve_cio_model_change_cohort(
            tenant_context=TENANT_CONTEXT,
            model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
            request=CioModelChangeAffectedCohortRequest(
                as_of_date=date(2026, 5, 3), tenant_id="TENANT_OTHER"
            ),
        )

    assert reader.calls == []


@pytest.mark.asyncio
async def test_empty_affected_cohort_is_explicitly_incomplete() -> None:
    reader = _Reader()
    reader.affected = []

    response = await _service(reader).resolve_cio_model_change_cohort(
        tenant_context=TENANT_CONTEXT,
        model_portfolio_id="MODEL_PB_SG_GLOBAL_BAL_DPM",
        request=CioModelChangeAffectedCohortRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response is not None
    assert response.supportability.reason == "CIO_MODEL_CHANGE_COHORT_EMPTY"
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
async def test_universe_normalizes_scope_and_emits_bounded_continuation() -> None:
    reader = _Reader()
    reader.universe = [_mandate(), _mandate(portfolio_id="PB_002", mandate_id="MANDATE_002")]
    tokens = _PageTokens()
    request = DpmPortfolioUniverseCandidateRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="TENANT_SG",
        booking_center_code=" Singapore ",
        model_portfolio_ids=[" MODEL_B ", "", "MODEL_A", "MODEL_A"],
        page={"page_size": 1},
    )

    response = await _service(reader, tokens).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT, request=request
    )

    assert [row.portfolio_id for row in response.candidates] == ["PB_SG_GLOBAL_BAL_001"]
    assert response.supportability.state == "DEGRADED"
    assert response.data_quality_status == "PARTIAL"
    assert response.page.next_page_token == "next-page"
    assert response.content_hash == SOURCE_METADATA_UNAVAILABLE_HASH
    assert response.source_digest == SOURCE_METADATA_UNAVAILABLE_HASH
    assert response.source_batch_fingerprint is None
    assert reader.calls[-1][1]["booking_center_code"] == "Singapore"
    assert reader.calls[-1][1]["tenant_id"] == "TENANT_SG"
    assert reader.calls[-1][1]["model_portfolio_ids"] == ("MODEL_A", "MODEL_B")
    assert reader.calls[-1][1]["limit"] == 2
    assert tokens.encoded[-1]["last_mandate_id"] == "MANDATE_001"


@pytest.mark.asyncio
async def test_universe_accepts_matching_cursor_and_rejects_wrong_scope() -> None:
    reader = _Reader()
    tokens = _PageTokens()
    request = DpmPortfolioUniverseCandidateRequest(
        as_of_date=date(2026, 5, 3), page={"page_token": "current"}
    )
    initial = await _service(reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(as_of_date=date(2026, 5, 3)),
    )
    tokens.cursor = {
        "scope_fingerprint": initial.page.request_scope_fingerprint,
        "last_portfolio_id": "PB_000",
        "last_mandate_id": "MANDATE_000",
    }

    await _service(reader, tokens).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT, request=request
    )
    assert reader.calls[-1][1]["after_sort_key"] == ("PB_000", "MANDATE_000")

    tokens.cursor["scope_fingerprint"] = "wrong"
    with pytest.raises(ValueError, match="does not match request scope"):
        await _service(reader, tokens).resolve_universe_candidates(
            tenant_context=TENANT_CONTEXT, request=request
        )


@pytest.mark.asyncio
async def test_empty_universe_is_explicitly_incomplete() -> None:
    reader = _Reader()
    reader.universe = []

    response = await _service(reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response.candidates == []
    assert response.supportability.reason == "DPM_PORTFOLIO_UNIVERSE_EMPTY"
    assert response.data_quality_status == "MISSING"
    assert response.content_hash == SOURCE_METADATA_UNAVAILABLE_HASH
    assert response.source_digest == SOURCE_METADATA_UNAVAILABLE_HASH
    assert response.source_batch_fingerprint is None


@pytest.mark.asyncio
async def test_universe_rejects_caller_tenant_mismatch_before_source_reads() -> None:
    reader = _Reader()

    with pytest.raises(TenantAuthorityMismatchError):
        await _service(reader).resolve_universe_candidates(
            tenant_context=TENANT_CONTEXT,
            request=DpmPortfolioUniverseCandidateRequest(
                as_of_date=date(2026, 5, 3), tenant_id="TENANT_OTHER"
            ),
        )

    assert reader.calls == []


@pytest.mark.asyncio
async def test_universe_without_source_evidence_time_fails_closed() -> None:
    reader = _Reader()
    reader.universe = [
        replace(
            _mandate(),
            observed_at=None,
            created_at=None,
            updated_at=None,
        )
    ]

    response = await _service(reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response.supportability.state == "DEGRADED"
    assert response.supportability.reason == "DPM_PORTFOLIO_UNIVERSE_EVIDENCE_TIME_UNAVAILABLE"
    assert response.content_hash == SOURCE_METADATA_UNAVAILABLE_HASH
    assert response.source_digest == SOURCE_METADATA_UNAVAILABLE_HASH
    assert response.source_evidence_current is False
    assert response.freshness_status == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_ready_universe_publishes_stable_core_owned_content_identity() -> None:
    request = DpmPortfolioUniverseCandidateRequest(
        as_of_date=date(2026, 5, 3),
        tenant_id="TENANT_SG",
        booking_center_code="Singapore",
        model_portfolio_ids=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
        page={"page_size": 500},
    )

    first = await _service(_Reader()).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT, request=request
    )
    replay = await _service(_Reader()).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT, request=request
    )

    assert first.supportability.state == "READY"
    assert first.candidates[0].portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert first.content_hash.startswith("sha256:")
    assert first.content_hash != SOURCE_METADATA_UNAVAILABLE_HASH
    assert first.source_digest == first.content_hash
    assert first.source_batch_fingerprint is None
    assert first.data_quality_status == "COMPLETE"
    assert first.source_evidence_current is True
    assert first.freshness_status == "CURRENT"
    assert replay.content_hash == first.content_hash


@pytest.mark.asyncio
async def test_ready_universe_normalizes_tenant_in_scope_and_content_identity() -> None:
    reader = _Reader()
    normalized = await _service(reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(
            as_of_date=date(2026, 5, 3), tenant_id="TENANT_SG"
        ),
    )
    whitespace_equivalent = await _service(reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(
            as_of_date=date(2026, 5, 3), tenant_id=" TENANT_SG "
        ),
    )

    assert normalized.tenant_id == whitespace_equivalent.tenant_id == "TENANT_SG"
    assert (
        normalized.page.request_scope_fingerprint
        == whitespace_equivalent.page.request_scope_fingerprint
    )
    assert normalized.content_hash == whitespace_equivalent.content_hash


@pytest.mark.asyncio
async def test_ready_universe_content_identity_changes_with_source_evidence() -> None:
    request = DpmPortfolioUniverseCandidateRequest(as_of_date=date(2026, 5, 3))
    baseline_reader = _Reader()
    changed_reader = _Reader()
    changed_reader.universe = [
        replace(
            _mandate(),
            updated_at=datetime(2026, 5, 3, 9, 1, tzinfo=UTC),
        )
    ]
    expanded_reader = _Reader()
    expanded_reader.universe = [
        _mandate(),
        _mandate(portfolio_id="PB_SG_GLOBAL_INC_002", mandate_id="MANDATE_002"),
    ]

    baseline = await _service(baseline_reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT, request=request
    )
    changed = await _service(changed_reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT, request=request
    )
    expanded = await _service(expanded_reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT, request=request
    )

    assert changed.candidates == baseline.candidates
    assert changed.content_hash != baseline.content_hash
    assert len(expanded.candidates) == 2
    assert expanded.content_hash not in {baseline.content_hash, changed.content_hash}


@pytest.mark.asyncio
async def test_ready_universe_content_identity_changes_with_selection_and_page_scope() -> None:
    reader = _Reader()
    baseline = await _service(reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(as_of_date=date(2026, 5, 3)),
    )
    filtered = await _service(reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(
            as_of_date=date(2026, 5, 3),
            booking_center_code="Singapore",
        ),
    )
    resized = await _service(reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(
            as_of_date=date(2026, 5, 3),
            page={"page_size": 500},
        ),
    )

    assert filtered.candidates == baseline.candidates
    assert filtered.content_hash != baseline.content_hash
    assert resized.content_hash != baseline.content_hash


@pytest.mark.asyncio
async def test_ready_universe_content_identity_uses_canonical_cursor_not_token_envelope() -> None:
    reader = _Reader()
    initial = await _service(reader).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(as_of_date=date(2026, 5, 3)),
    )
    cursor = {
        "scope_fingerprint": initial.page.request_scope_fingerprint,
        "last_portfolio_id": "PB_000",
        "last_mandate_id": "MANDATE_000",
    }
    codec = PageTokenCodec(secret="test-secret")
    first_token = codec.encode(cursor, expires_at=datetime(2099, 1, 1, tzinfo=UTC))
    second_token = codec.encode(cursor, expires_at=datetime(2100, 1, 1, tzinfo=UTC))

    first = await _service(reader, codec).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(
            as_of_date=date(2026, 5, 3), page={"page_token": first_token}
        ),
    )
    replay = await _service(reader, codec).resolve_universe_candidates(
        tenant_context=TENANT_CONTEXT,
        request=DpmPortfolioUniverseCandidateRequest(
            as_of_date=date(2026, 5, 3), page={"page_token": second_token}
        ),
    )

    assert first.content_hash == replay.content_hash
