"""Frozen collection query/row/cardinality contract; no registered route or live proof implied."""

import json
from copy import deepcopy
from datetime import UTC, date, datetime

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import (
    DeclaredCoverage,
    ExpectedPopulation,
    HistoricalRegistryCut,
    InputRole,
    SourceCutIdentity,
    ordered_content_root,
)
from portfolio_common.portfolio_financial_source_cut_admission import (
    FinancialInput,
    financial_input_from_payload,
)
from pydantic import ValidationError

from src.services.query_control_plane_service.app.contracts.portfolio_financial_source_cuts import (
    FinancialInputEvidence,
    FinancialSourceCutQuery,
    HistoricalRegistryQuery,
    SourceCutReadResponse,
)

pytestmark = pytest.mark.unit
H = "a" * 64


def query():
    return dict(
        source_system="producer",
        registry_scope_id="registry/opaque",
        source_cut_id="cut/opaque",
        revision=1,
        content_hash=H,
        view="CUT",
        page=dict(page_size=500, page_token=None),
    )


def empty_registry_response():
    stamp = datetime(2026, 10, 16, tzinfo=UTC)
    identity = SourceCutIdentity(
        "tenant",
        "producer",
        "registry",
        "cut",
        1,
        "v1",
        date(2025, 1, 1),
        date(2025, 1, 31),
        "SG",
        stamp,
        stamp,
        None,
        None,
    )
    member_root = ordered_content_root("PortfolioHistoricalRegistryMembers:v1", ())[1]
    chunks_root = ordered_content_root("NeutralSourceChunks:v1", ())[1]
    manifest = HistoricalRegistryCut(
        identity,
        ExpectedPopulation("independent", "v1", 0, H),
        DeclaredCoverage.COMPLETE,
        0,
        member_root,
        0,
        chunks_root,
    )
    root = manifest.content_hash
    return dict(
        tenant_id="tenant",
        generated_at=stamp,
        as_of_date=date(2025, 1, 31),
        content_hash="sha256:" + root,
        source_digest="sha256:" + root,
        product_name="PortfolioHistoricalRegistry",
        product_version="v1",
        source_address=dict(
            source_system="producer", registry_scope_id="registry", source_cut_id="cut", revision=1
        ),
        batch_manifest_hash=root,
        portfolio_id=None,
        view="CUT",
        receipt_job_id="job",
        received_at=stamp,
        completed_at=stamp,
        compatibility_posture="UNAVAILABLE",
        pagination=dict(
            total_count=1,
            returned_count=1,
            next_page_token=None,
            ordered_set_hash=ordered_content_root("NeutralSourceCutHeaders:v1", [root])[1],
            root_item_count=1,
            root_kind="CUT_HEADERS",
            ordering="single_cut",
        ),
        rows=[
            dict(
                row_kind="REGISTRY_CUT",
                manifest=manifest,
                receipt_job_id="job",
                received_at=stamp,
                completed_at=stamp,
            )
        ],
    )


def test_exact_opaque_ids_are_body_selectors_and_hash_means_batch_root():
    assert HistoricalRegistryQuery.model_validate(query()).source_cut_id == "cut/opaque"
    assert (
        FinancialSourceCutQuery.model_validate(
            query() | {"portfolio_id": "portfolio/opaque"}
        ).portfolio_id
        == "portfolio/opaque"
    )
    for changes in (
        {"tenant_id": "foreign"},
        {"content_hash": "sha256:" + H},
        {"revision": True},
        {"page": {"page_size": True}},
        {"view": "latest"},
        {"source_system": " "},
    ):
        with pytest.raises(ValidationError):
            HistoricalRegistryQuery.model_validate(query() | changes)


def test_empty_source_population_has_one_retained_manifest_not_absent_header():
    response = empty_registry_response()
    parsed = SourceCutReadResponse.model_validate(response)
    assert parsed.rows[0].manifest.supplied_count == 0
    assert parsed.authoritative_use_available is False
    assert parsed.population_verification == "UNVERIFIED"
    for changes in (
        {"rows": [], "pagination": response["pagination"] | {"returned_count": 0}},
        {"batch_manifest_hash": "b" * 64},
        {"content_hash": response["batch_manifest_hash"]},
        {"view": "MEMBERS"},
        {"qualification": "QUALIFIED"},
        {"tenant_id": "foreign"},
        {
            "source_address": dict(
                source_system="foreign",
                registry_scope_id="registry",
                source_cut_id="cut",
                revision=1,
            )
        },
    ):
        with pytest.raises(ValidationError):
            SourceCutReadResponse.model_validate(response | changes)


def test_schema_has_closed_row_discriminators_and_explicit_separate_graph_roots():
    schema = SourceCutReadResponse.model_json_schema()
    definitions = schema["$defs"]
    assert definitions["FinancialInputEvidence"]["additionalProperties"] is False
    assert {"input_content_hash", "graph_content_hash", "graph", "declaration"} <= definitions[
        "FinancialInputEvidence"
    ]["properties"].keys()
    assert definitions["SourceCutPagination"]["properties"]["root_kind"]
    assert schema["properties"]["rows"]["items"]["discriminator"]["propertyName"] == "row_kind"


def test_response_transport_preserves_domain_identity_and_json_hash():
    payload = empty_registry_response()
    manifest = payload["rows"][0]["manifest"]
    parsed = SourceCutReadResponse.model_validate(payload)
    assert parsed.rows[0].manifest is manifest
    restored = SourceCutReadResponse.model_validate_json(parsed.model_dump_json())
    assert type(restored.rows[0].manifest) is HistoricalRegistryCut
    assert restored.rows[0].manifest == manifest
    assert restored.rows[0].manifest.content_hash == manifest.content_hash
    # Strict Python hydration requires domain instances rather than coercing mappings.
    with pytest.raises(ValidationError):
        SourceCutReadResponse.model_validate(parsed.model_dump(mode="json"))


@pytest.mark.parametrize(
    "path,bad",
    [
        (("identity", "unexpected"), True),
        (("expected_population", "unexpected"), True),
        (("identity", "revision"), True),
        (("identity", "revision"), "1"),
        (("supplied_count",), "0"),
        (("expected_population", "count"), True),
        (("identity", "observed_at"), "2026-10-16T00:00:00"),
        (("identity", "coverage_to"), "2024-12-31"),
        (("identity", "predecessor_hash"), H),
        (("members_root",), "bad"),
        (("declared_coverage",), "QUALIFIED"),
    ],
)
def test_response_json_refuses_closed_nested_declaration_drift(path, bad):
    parsed = SourceCutReadResponse.model_validate(empty_registry_response())
    payload = parsed.model_dump(mode="json")
    target = payload["rows"][0]["manifest"]
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = bad
    with pytest.raises(ValidationError):
        SourceCutReadResponse.model_validate_json(json.dumps(payload))


def financial_header_response():
    from tests.unit.services.query_control_plane_service.application import (
        test_portfolio_financial_source_cuts as read_tests,
    )

    _, query, cut, _ = read_tests.financial_fixture()
    data = empty_registry_response()
    root = cut.header.manifest.content_hash
    return SourceCutReadResponse.model_validate(
        data
        | dict(
            product_name="PortfolioFinancialSourceCut",
            portfolio_id=query.portfolio_id,
            batch_manifest_hash=root,
            content_hash="sha256:" + root,
            source_digest="sha256:" + root,
            receipt_job_id=cut.header.receipt_job_id,
            received_at=cut.header.received_at,
            completed_at=cut.header.completed_at,
            rows=[cut.header],
            pagination=data["pagination"]
            | {"ordered_set_hash": ordered_content_root("NeutralSourceCutHeaders:v1", [root])[1]},
        )
    )


def test_exact_route_response_subclasses_preserve_wire_and_refuse_other_valid_product():
    from src.services.query_control_plane_service.app.contracts import (
        portfolio_financial_source_cuts as contracts,
    )

    registry = SourceCutReadResponse.model_validate(empty_registry_response())
    financial = financial_header_response()
    for response, model, wrong in (
        (registry, contracts.HistoricalRegistryReadResponse, financial),
        (financial, contracts.FinancialSourceCutReadResponse, registry),
    ):
        narrowed = model.model_validate(response, from_attributes=True)
        assert narrowed.model_dump(mode="json") == response.model_dump(mode="json")
        assert (
            model.model_json_schema()["properties"]["product_name"]["const"]
            == response.product_name
        )
        with pytest.raises(ValidationError):
            model.model_validate(wrong, from_attributes=True)
        with pytest.raises(ValidationError):
            model.model_validate(
                response.model_copy(update={"product_version": "v2"}), from_attributes=True
            )
        with pytest.raises(ValidationError):
            model.model_validate(
                response.model_copy(update={"view": "latest"}), from_attributes=True
            )


def test_original_frozen_schema_bytes_remain_exact_after_route_subclasses():
    import hashlib

    # Original producer packet086f577... normalized deterministically before R3 subclass edits.
    schemas = dict(
        HistoricalRegistryQuery=HistoricalRegistryQuery.model_json_schema(),
        FinancialSourceCutQuery=FinancialSourceCutQuery.model_json_schema(),
        SourceCutReadResponse=SourceCutReadResponse.model_json_schema(mode="serialization"),
    )
    raw = (
        json.dumps(schemas, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "cfa0b0287c661100cf60f031d63176bd22209be7a65ed94d13fc98824abe949b"
    )


def test_selected_five_role_graph_reconstructs_without_other_portfolio_rows():
    manifest = empty_registry_response()["rows"][0]["manifest"]
    selections = []
    for role in InputRole:
        if role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS):
            selected_date = "2024-12-31" if role is InputRole.PRIOR_ASSETS else "2025-01-31"
            selector = dict(
                kind="VALUATION",
                as_of_date="2025-01-31",
                from_date=selected_date,
                to_date=selected_date,
                reporting_currency="USD",
                consumer_system="lotus-manage",
                export_job_id="unit-export",
                export_content_hash=H,
                refresh_of_job_id=None,
            )
            product = "PortfolioTimeseriesInput"
        elif role is InputRole.FLOWS:
            selector = dict(
                kind="FLOWS",
                source_system="producer",
                source_cut_id="flow-cut",
                cut_revision=1,
                manifest_hash=H,
                from_date="2025-01-01",
                to_date="2025-01-31",
                currency="USD",
            )
            product = "PortfolioFinancialFlowObservations"
        else:
            selector = dict(
                kind=role.value,
                as_of_date="2025-01-31",
                producer_id="producer",
                source_record_id=role.value,
                observation_id=H,
                content_hash=H,
                source_cut_id="fact-cut",
                source_version=1,
            )
            product = "PortfolioFinancialSourceObservations"
        selections.append(
            dict(
                role=role.value,
                product_name=product,
                product_version="v1",
                selector=selector,
                selector_hash=canonical_content_hash(selector),
                content_hash=H,
                receipt_job_id="unit-job",
                source_revision="1",
            )
        )
    payload = dict(
        portfolio_id="portfolio/opaque",
        currency="USD",
        prior_date="2024-12-31",
        month_end_date="2025-01-31",
        registry_root=manifest.content_hash,
        member_revision=1,
        selections=selections,
        settled_unencumbered=dict(
            amount="0",
            currency="USD",
            business_date="2025-01-31",
            semantic_definition="explicit",
            producer_revision="1",
        ),
        compatibility=None,
    )
    declaration = FinancialInput.model_validate(payload)
    graph = financial_input_from_payload(manifest.identity, payload)
    row = FinancialInputEvidence(
        declaration=declaration,
        input_content_hash=canonical_content_hash(
            {
                "contract": "PortfolioFinancialSourceCutInput:v1",
                "selection": declaration.model_dump(mode="json"),
            }
        ),
        graph=graph,
        graph_content_hash=graph.content_hash,
    )
    assert row.graph.settled_unencumbered.amount == 0
    assert row.graph.compatibility_posture == "UNAVAILABLE"
    assert (
        FinancialInputEvidence.model_validate_json(row.model_dump_json()).graph_content_hash
        == graph.content_hash
    )
    assert row.graph is graph
    wire = row.model_dump(mode="json")
    for path, bad in (
        (("selections", 0, "extra"), True),
        (("identity", "extra"), True),
        (("member_revision",), "1"),
        (("settled_unencumbered", "extra"), True),
        (("settled_unencumbered", "amount"), "NaN"),
    ):
        changed = deepcopy(wire)
        target = changed["graph"]
        for name in path[:-1]:
            target = target[name]
        target[path[-1]] = bad
        with pytest.raises(ValidationError):
            FinancialInputEvidence.model_validate_json(json.dumps(changed))
    for changes in ({"graph_content_hash": H}, {"input_content_hash": H}):
        with pytest.raises(ValidationError):
            FinancialInputEvidence.model_validate(row.model_dump() | changes)
    payload["settled_unencumbered"]["amount"] = 0
    with pytest.raises(ValidationError):
        FinancialInput.model_validate_json(json.dumps(payload))
