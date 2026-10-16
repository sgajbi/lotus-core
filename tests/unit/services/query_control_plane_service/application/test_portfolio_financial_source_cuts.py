"""Independent commitment vectors distinguish logical capture artifacts from segments."""

import base64
import hashlib
from datetime import UTC, datetime

import pytest
from portfolio_common.domain.portfolio_financial_source_cuts import InputRole

from src.services.query_control_plane_service.app.application import (
    portfolio_financial_source_cuts as retained,
)
from src.services.query_control_plane_service.app.contracts.portfolio_financial_source_cuts import (
    CaptureSegmentEvidence,
)

pytestmark = pytest.mark.unit
READ_ROOT_CONTRACTS = retained.READ_ROOT_CONTRACTS
capture_artifact_projection = retained.capture_artifact_projection
source_read_item_hash = retained.source_read_item_hash
source_read_root = retained.source_read_root


def segment(index):
    whole = b"a" * 524288 + b"b"
    raw = whole[:524288] if index == 0 else whole[524288:]
    return CaptureSegmentEvidence(
        capture_id="a" * 64,
        role="CASH",
        source_page_index=0,
        source_product="PortfolioFinancialSourceObservations",
        product_version="v1",
        selector_hash="b" * 64,
        typed_content_hash="c" * 64,
        raw_hash=hashlib.sha256(whole).hexdigest(),
        byte_count=len(whole),
        segment_index=index,
        segment_count=2,
        segment_hash=hashlib.sha256(raw).hexdigest(),
        bytes_base64=base64.b64encode(raw).decode(),
        serializer_id="native-source-json:v1",
        schema_version="v1",
        mime_type="application/json",
        source_context=dict(
            capture_origin="ACQUIRED_NATIVE_DTO",
            captured_at=datetime(2026, 10, 16, tzinfo=UTC),
            snapshot_epoch=None,
            request_scope=None,
            receipt_job_id="receipt",
            source_revision="r1",
            selector_json="{}",
            export_job_id=None,
            refresh_of_job_id=None,
            returned_count=1,
            total_count=1,
            next_page_token=None,
        ),
    )


def test_logical_artifact_commitment_is_invariant_to_transport_segment():
    first, last = segment(0), segment(1)
    assert capture_artifact_projection(first) == capture_artifact_projection(last)
    item_hash = source_read_item_hash("CAPTURE_ARTIFACTS", first)
    seed = hashlib.sha256((READ_ROOT_CONTRACTS["CAPTURE_ARTIFACTS"] + "\0").encode()).digest()
    state = hashlib.sha256(seed + bytes.fromhex(item_hash)).digest()
    expected = hashlib.sha256(state + b"\0" + b"1").hexdigest()
    assert source_read_root("CAPTURE_ARTIFACTS", [first]) == (1, expected)
    assert source_read_root("CAPTURE_ARTIFACTS", [last]) == (1, expected)
    assert source_read_root("CAPTURE_ARTIFACTS", [first, last])[0] == 2
    assert (
        source_read_item_hash(
            "CAPTURE_ARTIFACTS", first.model_copy(update={"source_page_index": 1})
        )
        != item_hash
    )
    assert (
        source_read_item_hash(
            "CAPTURE_ARTIFACTS", first.model_copy(update={"role": InputRole.READINESS})
        )
        != item_hash
    )


@pytest.mark.parametrize("kind", list(READ_ROOT_CONTRACTS))
def test_empty_root_retains_domain_and_zero_count(kind):
    seed = hashlib.sha256((READ_ROOT_CONTRACTS[kind] + "\0").encode()).digest()
    assert source_read_root(kind, []) == (0, hashlib.sha256(seed + b"\0" + b"0").hexdigest())


def test_wrong_root_item_kind_refuses():
    with pytest.raises(ValueError, match="mismatch"):
        source_read_root("CUT_HEADERS", [segment(0)])
    with pytest.raises(ValueError, match="unsupported"):
        source_read_root("unknown", [])


def registry_fixture(count=3):
    from datetime import date

    from portfolio_common.domain.portfolio_financial_source_cuts import (
        DeclaredCoverage,
        EffectiveDeclaration,
        ExpectedPopulation,
        HistoricalRegistryCut,
        HistoricalRegistryMember,
        SourceCutIdentity,
        ordered_content_root,
    )

    from src.services.query_control_plane_service.app.contracts import (
        portfolio_financial_source_cuts as contracts,
    )
    from src.services.query_control_plane_service.app.ports.portfolio_financial_source_cuts import (
        RetainedCut,
    )

    stamp = datetime(2026, 10, 16, tzinfo=UTC)
    members = [
        contracts.RegistryMemberEvidence(member=member, member_content_hash=member.content_hash)
        for index in range(count)
        for member in [
            HistoricalRegistryMember(
                f"member-{index:05d}",
                "producer",
                None,
                1,
                (
                    EffectiveDeclaration(
                        date(2025, 1, 1), None, "v1", "synthetic", "USD", None, False
                    ),
                ),
            )
        ]
    ]
    root = source_read_root("REGISTRY_MEMBERS", members)[1]
    manifest = HistoricalRegistryCut(
        SourceCutIdentity(
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
        ),
        ExpectedPopulation("independent", "v1", count, "a" * 64),
        DeclaredCoverage.COMPLETE,
        count,
        root,
        1 if count else 0,
        ordered_content_root("NeutralSourceChunks:v1", ())[1],
    )
    cut = RetainedCut(
        contracts.RegistryCutEvidence(
            manifest=manifest, receipt_job_id="original-job", received_at=stamp, completed_at=stamp
        )
    )
    query = contracts.HistoricalRegistryQuery(
        source_system="producer",
        registry_scope_id="registry",
        source_cut_id="cut",
        revision=1,
        content_hash=manifest.content_hash,
        view="MEMBERS",
        page={"page_size": 2, "page_token": None},
    )

    class Reader:
        calls = []

        async def cut(self, tenant, product, request):
            self.calls.append((tenant, product, request.source_cut_id))
            return cut

        async def members(self, tenant, request):
            for row in members:
                yield row

    return Reader(), query, cut, members


def retained_service(reader, **kwargs):
    from portfolio_common.page_tokens import PageTokenCodec

    return retained.PortfolioFinancialSourceCutsService(
        reader, PageTokenCodec(secret="synthetic-read-test"), **kwargs
    )


async def read_registry(service, query, **kwargs):
    return await service.query(
        tenant_id="tenant",
        service_identity="lotus-manage",
        product="PortfolioHistoricalRegistry",
        request=query,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_keyset_all_members_include_unmapped_and_excluded_and_source_off_replay():
    reader, query, cut, members = registry_fixture(503)
    service = retained_service(reader)
    seen, roots = [], set()
    while True:
        response = await read_registry(service, query)
        seen.extend(response.rows)
        roots.add(response.pagination.ordered_set_hash)
        assert response.generated_at == cut.header.completed_at
        assert response.content_hash == "sha256:" + query.content_hash
        assert len(response.model_dump_json().encode()) <= service.response_byte_budget
        assert response.authoritative_use_available is False
        if response.pagination.next_page_token is None:
            break
        query = query.model_copy(
            update={
                "page": query.page.model_copy(
                    update={"page_token": response.pagination.next_page_token}
                )
            }
        )
    assert seen == members and roots == {cut.header.manifest.members_root}
    assert all(
        row.member.core_portfolio_id is None and not row.member.declarations[0].included
        for row in seen
    )
    replay = await read_registry(
        service,
        query.model_copy(update={"page": query.page.model_copy(update={"page_token": None})}),
    )
    assert replay.rows == tuple(members[:2])


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("tenant_id", "other"), ("service_identity", "other")])
async def test_signed_cursor_rejects_tenant_and_actual_service_substitution(field, value):
    reader, query, _, _ = registry_fixture()
    service = retained_service(reader)
    first = await read_registry(service, query)
    continued = query.model_copy(
        update={
            "page": query.page.model_copy(update={"page_token": first.pagination.next_page_token})
        }
    )
    with pytest.raises(ValueError):
        await service.query(
            **(
                {
                    "tenant_id": "tenant",
                    "service_identity": "lotus-manage",
                    "product": "PortfolioHistoricalRegistry",
                    "request": continued,
                }
                | {field: value}
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"source_cut_id": "other"},
        {"registry_scope_id": "other"},
        {"source_system": "other"},
        {"revision": 2},
        {"content_hash": "b" * 64},
        {"view": "CUT"},
    ],
)
async def test_signed_cursor_refuses_exact_selector_root_or_view_substitution(changes):
    reader, query, _, _ = registry_fixture()
    service = retained_service(reader)
    first = await read_registry(service, query)
    continued = query.model_copy(
        update=changes
        | {"page": query.page.model_copy(update={"page_token": first.pagination.next_page_token})}
    )
    with pytest.raises(ValueError, match="scope"):
        await read_registry(service, continued)


@pytest.mark.asyncio
async def test_page_size_and_signed_ordered_set_drift_refuse():
    reader, query, _, members = registry_fixture()
    service = retained_service(reader)
    first = await read_registry(service, query)
    continued = query.model_copy(
        update={
            "page": query.page.model_copy(
                update={"page_token": first.pagination.next_page_token, "page_size": 1}
            )
        }
    )
    with pytest.raises(ValueError, match="scope"):
        await read_registry(service, continued)
    members.reverse()
    with pytest.raises(ValueError, match="order"):
        await read_registry(service, query)


@pytest.mark.asyncio
async def test_complete_empty_has_manifest_and_empty_members_root():
    reader, query, cut, _ = registry_fixture(0)
    service = retained_service(reader)
    members = await read_registry(service, query)
    assert members.rows == () and members.pagination.total_count == 0
    header = await read_registry(service, query.model_copy(update={"view": "CUT"}))
    assert header.rows == (cut.header,) and header.pagination.root_item_count == 1


@pytest.mark.asyncio
async def test_response_byte_budget_can_shorten_row_page_without_history_cap():
    reader, query, _, members = registry_fixture(20)
    query = query.model_copy(update={"page": query.page.model_copy(update={"page_size": 20})})
    service = retained_service(reader, response_byte_budget=4200)
    response = await read_registry(service, query)
    assert 0 < len(response.rows) < 20
    assert response.pagination.total_count == len(members)
    assert response.pagination.next_page_token
    assert len(response.model_dump_json().encode()) <= 4200


@pytest.mark.asyncio
async def test_capture_whole_raw_hash_and_segment_gap_refuse_without_native_catalog():
    reader, query, _, _ = registry_fixture(0)

    async def captures(*args):
        yield segment(0)

    reader.captures = captures
    service = retained_service(reader)
    with pytest.raises(ValueError, match="whole retained"):
        await read_registry(service, query.model_copy(update={"view": "CAPTURES"}))

    async def captures_complete(*args):
        yield segment(0)
        yield segment(1)

    reader.captures = captures_complete
    with pytest.raises(ValueError, match="catalog unavailable"):
        await read_registry(service, query.model_copy(update={"view": "CAPTURES"}))


def financial_fixture():
    from portfolio_common.domain.calculation_lineage import canonical_content_hash
    from portfolio_common.domain.portfolio_financial_source_cuts import FinancialSourceCutManifest
    from portfolio_common.portfolio_financial_source_cut_admission import (
        FinancialInput,
        financial_input_from_payload,
    )

    from src.services.query_control_plane_service.app.contracts import (
        portfolio_financial_source_cuts as contracts,
    )
    from src.services.query_control_plane_service.app.ports.portfolio_financial_source_cuts import (
        RetainedCut,
    )

    _, registry_query, registry, _ = registry_fixture(0)
    header = registry.header
    selections = []
    for role in InputRole:
        if role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS):
            day = "2024-12-31" if role is InputRole.PRIOR_ASSETS else "2025-01-31"
            selector = dict(
                kind="VALUATION",
                as_of_date="2025-01-31",
                from_date=day,
                to_date=day,
                reporting_currency="USD",
                consumer_system="lotus-manage",
                export_job_id="synthetic-export",
                export_content_hash="a" * 64,
                refresh_of_job_id=None,
            )
            product = "PortfolioTimeseriesInput"
        elif role is InputRole.FLOWS:
            selector = dict(
                kind="FLOWS",
                source_system="producer",
                source_cut_id="flow-cut",
                cut_revision=1,
                manifest_hash="a" * 64,
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
                observation_id="a" * 64,
                content_hash="a" * 64,
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
                content_hash="a" * 64,
                receipt_job_id="source-job",
                source_revision="1",
            )
        )
    declaration = FinancialInput.model_validate(
        dict(
            portfolio_id="portfolio/opaque",
            currency="USD",
            prior_date="2024-12-31",
            month_end_date="2025-01-31",
            registry_root=registry_query.content_hash,
            member_revision=1,
            selections=selections,
            settled_unencumbered=None,
            compatibility=None,
        )
    )
    graph = financial_input_from_payload(
        header.manifest.identity, declaration.model_dump(mode="json")
    )
    row = contracts.FinancialInputEvidence(
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
    manifest = FinancialSourceCutManifest(header.manifest.identity, 90, "b" * 64, 1, "c" * 64)
    cut = RetainedCut(
        contracts.FinancialCutEvidence(
            manifest=manifest,
            receipt_job_id=header.receipt_job_id,
            received_at=header.received_at,
            completed_at=header.completed_at,
        )
    )
    query = contracts.FinancialSourceCutQuery(
        **(
            registry_query.model_dump(mode="json")
            | {
                "content_hash": manifest.content_hash,
                "portfolio_id": declaration.portfolio_id,
                "view": "INPUTS",
            }
        )
    )

    class Reader:
        async def cut(self, *args):
            return cut

        async def selected_input(self, tenant, request, retained):
            assert tenant == "tenant" and request.portfolio_id == declaration.portfolio_id
            return row

    return Reader(), query, cut, row


@pytest.mark.asyncio
async def test_selected_declaration_graph_root_is_independent_of_batch_and_unrelated_portfolios():
    from portfolio_common.portfolio_financial_source_cut_admission import (
        financial_input_from_payload,
    )

    reader, query, cut, row = financial_fixture()
    response = await retained_service(reader).query(
        tenant_id="tenant",
        service_identity="lotus-manage",
        product="PortfolioFinancialSourceCut",
        request=query,
    )
    assert response.rows == (row,) and response.pagination.root_item_count == 1
    assert cut.header.manifest.selection_count == 90
    assert response.pagination.ordered_set_hash != cut.header.manifest.selections_root
    reconstructed = financial_input_from_payload(
        row.graph.identity, response.rows[0].declaration.model_dump(mode="json")
    )
    assert reconstructed.content_hash == row.graph_content_hash != query.content_hash
    assert tuple(selection.role for selection in reconstructed.selections) == tuple(InputRole)


@pytest.mark.asyncio
async def test_capture_artifact_count_is_distinct_from_segment_count_and_signed_segment_pages():
    reader, query, _, _ = registry_fixture(0)

    async def captures(*args):
        yield segment(0)
        yield segment(1)

    reader.captures = captures

    class SyntheticTransportVerifier:
        def verify(self, artifact, raw, *, identity, financial_input=None):
            assert hashlib.sha256(raw.read()).hexdigest() == artifact.raw_hash

    service = retained_service(reader, capture_verifier=SyntheticTransportVerifier())
    query = query.model_copy(
        update={"view": "CAPTURES", "page": query.page.model_copy(update={"page_size": 1})}
    )
    first = await read_registry(service, query)
    assert first.pagination.total_count == 2 and first.pagination.root_item_count == 1
    assert first.rows == (segment(0),)
    second = await read_registry(
        service,
        query.model_copy(
            update={
                "page": query.page.model_copy(
                    update={"page_token": first.pagination.next_page_token}
                )
            }
        ),
    )
    assert second.rows == (segment(1),) and second.pagination.next_page_token is None
    assert second.pagination.ordered_set_hash == first.pagination.ordered_set_hash


@pytest.mark.asyncio
async def test_signed_capture_cursor_binds_retained_epoch_context_and_rejects_tampering():
    reader, query, _, _ = registry_fixture(0)
    epoch = None

    async def captures(*args):
        for index in range(2):
            item = segment(index)
            yield item.model_copy(
                update={
                    "source_context": item.source_context.model_copy(
                        update={"snapshot_epoch": epoch}
                    )
                }
            )

    reader.captures = captures

    class SyntheticTransportVerifier:
        def verify(self, *args, **kwargs):
            pass

    service = retained_service(reader, capture_verifier=SyntheticTransportVerifier())
    query = query.model_copy(
        update={"view": "CAPTURES", "page": query.page.model_copy(update={"page_size": 1})}
    )
    first = await read_registry(service, query)
    continuation = query.model_copy(
        update={
            "page": query.page.model_copy(update={"page_token": first.pagination.next_page_token})
        }
    )
    epoch = "actual-different-source-epoch"
    with pytest.raises(ValueError, match="commitment changed"):
        await read_registry(service, continuation)
    malformed = query.model_copy(
        update={"page": query.page.model_copy(update={"page_token": "invalid-signed-cursor"})}
    )
    with pytest.raises(ValueError):
        await read_registry(service, malformed)
