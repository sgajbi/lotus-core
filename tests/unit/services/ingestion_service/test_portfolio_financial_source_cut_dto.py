"""Registered command inputs retain strict unknowns and exact source pins."""

import json
from datetime import UTC, date, datetime

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.portfolio_financial_source_cut_admission import (
    ProductSelectionInput,
    RegistryMemberInput,
    ValuationSelector,
)
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.portfolio_financial_source_cut_dto import (
    CutHeader,
    FinancialChunkInput,
    FinancialSealInput,
    RegistryChunkInput,
    RegistrySealInput,
)

pytestmark = pytest.mark.unit
H = "a" * 64


def member_payload(discretionary=None):
    return dict(
        source_member_id="member/opaque",
        provider_namespace="provider",
        core_portfolio_id=None,
        member_revision=1,
        declarations=[
            dict(
                effective_from="2025-01-01",
                effective_to=None,
                definition_version="mandate-v1",
                provenance_reference="issued",
                currency="USD",
                discretionary=discretionary,
                included=False,
            )
        ],
    )


def header():
    return dict(
        source_system="producer",
        registry_scope_id="registry/scope",
        source_cut_id="cut/opaque",
        revision=1,
        definition_version="v1",
        coverage_from=date(2025, 1, 1),
        coverage_to=date(2025, 1, 31),
        calendar="SG",
        observed_at=datetime(2025, 2, 1, tzinfo=UTC),
        generated_at=datetime(2025, 2, 2, tzinfo=UTC),
        predecessor_hash=None,
        expected_head_hash=None,
    )


def test_server_tenant_cannot_be_submitted_or_smuggled_and_opaque_body_ids_survive():
    parsed = CutHeader.model_validate(header())
    assert parsed.to_identity("tenant").scope_id == "registry/scope"
    for extra in ({"tenant_id": "foreign"}, {"bank_approved": True}, {"url": "https://foreign"}):
        with pytest.raises(ValidationError):
            CutHeader.model_validate(header() | extra)


@pytest.mark.parametrize("value", [0, 1, "true", "false"])
def test_json_input_never_coerces_discretionary_boolean(value):
    with pytest.raises(ValidationError):
        RegistryMemberInput.model_validate_json(json.dumps(member_payload(value)))


def test_typed_chunk_hash_binds_false_unknown_member_and_closed_input():
    member = RegistryMemberInput.model_validate(member_payload(False))
    root = canonical_content_hash(
        {
            "contract": "PortfolioHistoricalRegistryChunk:v1",
            "members": [member.to_domain().content_hash],
        }
    )
    raw = dict(
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        chunk_index=0,
        members=[member.model_dump(mode="json")],
        typed_content_hash=root,
    )
    assert RegistryChunkInput.model_validate(raw).members[0].declarations[0].discretionary is False
    raw["members"] = [member_payload(None)]
    with pytest.raises(ValidationError):
        RegistryChunkInput.model_validate(raw)
    with pytest.raises(ValidationError):
        RegistryChunkInput.model_validate(raw | {"chunk_index": True})


def test_seal_uses_only_header_fields_and_retains_independent_population_unknown():
    cut = RegistrySealInput.model_validate(
        header()
        | dict(
            expected_population=dict(
                reference="expected", definition_version="v1", count=0, content_hash=H
            ),
            declared_coverage="COMPLETE",
            supplied_count=0,
            members_root=H,
            chunk_count=0,
            chunks_root=H,
        )
    )
    assert cut.header().to_identity("tenant").tenant_id == "tenant"
    assert cut.expected_population.count == 0
    with pytest.raises(ValidationError):
        RegistrySealInput.model_validate(cut.model_dump() | {"supplied_count": True})


def test_source_selection_binds_native_family_and_exact_typed_selector_not_caller_url():
    selector = ValuationSelector(
        kind="VALUATION",
        as_of_date=date(2025, 1, 31),
        from_date=date(2025, 1, 31),
        to_date=date(2025, 1, 31),
        reporting_currency="USD",
        consumer_system="lotus-manage",
        export_job_id=None,
        export_content_hash=None,
        refresh_of_job_id=None,
    )
    raw = dict(
        role="MONTH_END_ASSETS",
        product_name="PortfolioTimeseriesInput",
        product_version="v1",
        selector=selector.model_dump(mode="json"),
        selector_hash=canonical_content_hash(selector.model_dump(mode="json")),
        content_hash=H,
        receipt_job_id="actual-job",
        source_revision="original",
    )
    assert ProductSelectionInput.model_validate(raw).to_domain().role.value == "MONTH_END_ASSETS"
    for changed in (
        {"role": "CASH"},
        {"selector_hash": "b" * 64},
        {"product_name": "PortfolioFinancialSourceObservations"},
    ):
        with pytest.raises(ValidationError):
            ProductSelectionInput.model_validate(raw | changed)
    with pytest.raises(ValidationError):
        ProductSelectionInput.model_validate(
            raw | {"selector": raw["selector"] | {"url": "https://foreign"}}
        )


def test_missing_export_pair_or_naive_time_or_blank_scope_is_refused():
    with pytest.raises(ValidationError):
        CutHeader.model_validate(header() | {"observed_at": datetime(2025, 2, 1)})
    with pytest.raises(ValidationError):
        CutHeader.model_validate(header() | {"registry_scope_id": " "})
    with pytest.raises(ValidationError):
        ValuationSelector(
            kind="VALUATION",
            as_of_date=date(2025, 1, 31),
            from_date=date(2025, 1, 31),
            to_date=date(2025, 1, 31),
            reporting_currency="USD",
            consumer_system="lotus-manage",
            export_job_id="job",
            export_content_hash=None,
            refresh_of_job_id=None,
        )


def test_financial_chunk_fixed_empty_root_is_bound_to_closed_typed_input():
    # Independent fixed protocol vector for a complete empty chunk declaration.
    root = "5c37ccd67bf9a1c20846adeac8bbe5a62c663cf8c29e414bab59a714dfe05b8b"
    payload = dict(
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        chunk_index=0,
        selections=[],
        typed_content_hash=root,
    )
    parsed = FinancialChunkInput.model_validate(payload)
    assert parsed.selections == ()
    assert parsed.typed_content_hash == root
    with pytest.raises(ValidationError, match="financial chunk typed hash mismatch"):
        FinancialChunkInput.model_validate(payload | {"typed_content_hash": H})
    with pytest.raises(ValidationError):
        FinancialChunkInput.model_validate(payload | {"tenant_id": "foreign"})


def test_populated_financial_chunk_matches_existing_five_role_protocol_vector():
    valuation = dict(
        kind="VALUATION",
        as_of_date="2025-01-31",
        from_date="2024-12-31",
        to_date="2025-01-31",
        reporting_currency="USD",
        consumer_system="lotus-manage",
        export_job_id=None,
        export_content_hash=None,
        refresh_of_job_id=None,
    )
    observation = dict(
        as_of_date="2025-01-31",
        producer_id="producer",
        source_record_id="record",
        observation_id=H,
        content_hash=H,
        source_cut_id="native-cut",
        source_version=1,
    )
    flow = dict(
        kind="FLOWS",
        source_system="producer",
        source_cut_id="flow-cut",
        cut_revision=1,
        manifest_hash=H,
        from_date="2025-01-01",
        to_date="2025-01-31",
        currency="USD",
    )
    sources = [
        ("PRIOR_ASSETS", "PortfolioTimeseriesInput", valuation),
        ("MONTH_END_ASSETS", "PortfolioTimeseriesInput", valuation),
        ("CASH", "PortfolioFinancialSourceObservations", observation | {"kind": "CASH"}),
        ("READINESS", "PortfolioFinancialSourceObservations", observation | {"kind": "READINESS"}),
        ("FLOWS", "PortfolioFinancialFlowObservations", flow),
    ]
    selections = [
        dict(
            role=role,
            product_name=product,
            product_version="v1",
            selector=selector,
            selector_hash=canonical_content_hash(selector),
            content_hash=H,
            receipt_job_id="receipt",
            source_revision="1",
        )
        for role, product, selector in sources
    ]
    selected = dict(
        portfolio_id="portfolio",
        currency="USD",
        prior_date="2024-12-31",
        month_end_date="2025-01-31",
        registry_root=H,
        member_revision=1,
        selections=selections,
        settled_unencumbered=None,
        compatibility=None,
    )
    payload = dict(
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        chunk_index=0,
        selections=[selected],
        typed_content_hash="e42014c5a11ae2562c6c2910e930012a14bcf6369d2b18dbc2e52ff9216e015f",
    )
    parsed = FinancialChunkInput.model_validate(payload)
    assert parsed.selections[0].portfolio_id == "portfolio"
    assert tuple(s.role.value for s in parsed.selections[0].selections) == tuple(
        role for role, _, _ in sources
    )
    assert parsed.selections[0].settled_unencumbered is None
    assert parsed.selections[0].compatibility is None
    with pytest.raises(ValidationError, match="financial chunk typed hash mismatch"):
        FinancialChunkInput.model_validate(
            payload | {"selections": [selected | {"portfolio_id": "other"}]}
        )


def test_seal_domain_conversion_preserves_exact_server_identity_and_roots():
    financial = FinancialSealInput.model_validate(
        header() | dict(selection_count=0, selections_root=H, chunk_count=0, chunks_root=H)
    )
    manifest = financial.to_domain("server-tenant")
    assert manifest.identity == CutHeader.model_validate(header()).to_identity("server-tenant")
    assert manifest.selection_count == 0
    assert manifest.selections_root == H
    assert manifest.chunk_count == 0
    assert manifest.chunks_root == H
    registry = RegistrySealInput.model_validate(
        header()
        | dict(
            expected_population=dict(
                reference="expected", definition_version="v1", count=0, content_hash=H
            ),
            declared_coverage="COMPLETE",
            supplied_count=0,
            members_root=H,
            chunk_count=0,
            chunks_root=H,
        )
    ).to_domain("server-tenant")
    assert registry.identity == manifest.identity
    assert registry.expected_population.count == 0
    assert registry.members_root == H
