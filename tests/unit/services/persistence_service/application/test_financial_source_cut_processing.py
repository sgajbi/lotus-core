"""Acquisition is outside writes; stale workers/outages cannot earn completion."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import (
    FinancialSourceCutManifest,
    HistoricalRegistryCut,
    InputRole,
    ordered_content_root,
)
from portfolio_common.portfolio_financial_source_cut_admission import RegistryMemberInput
from pydantic import TypeAdapter

from src.services.persistence_service.app.application.financial_source_cut_processing import (
    FinancialSourceCutProcessor,
    verify_chunk_step,
    verify_input_page,
    verify_member_page,
)
from src.services.persistence_service.app.ports.financial_source_captures import (
    CapturedSourcePage,
    SourceCaptureBytes,
    SourceCaptureRequest,
    SourceCaptureUnavailable,
)
from src.services.persistence_service.app.ports.financial_source_cut_work import (
    SourceCutClaim,
    SourceCutProgress,
    SourceManifestRejected,
    StaleSourceCutClaim,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]
H = "a" * 64


def request():
    return SourceCaptureRequest(
        "tenant",
        "portfolio",
        InputRole.CASH,
        "PortfolioFinancialSourceObservations",
        "v1",
        b"{}",
        H,
        H,
        "job",
        "r1",
        None,
        currency="USD",
    )


class Work:
    def __init__(self, *, stale=False, finished=False):
        self.in_write = False
        self.stale = stale
        self.finished = finished
        self.completed = 0
        self.saved = 0
        self.deferred = []

    async def claim(self):
        self.in_write = True
        result = SourceCutClaim(
            "work", "tenant", H, "lease", datetime.now(UTC) + timedelta(seconds=30), H
        )
        self.in_write = False
        return result

    async def next_capture(self, claim):
        return None if self.finished else request()

    async def cached_capture(self, selection):
        return None

    async def save_capture(self, claim, page):
        if self.stale:
            raise StaleSourceCutClaim("expired on DB-time revalidation")
        self.saved += 1

    async def complete(self, claim):
        if self.stale:
            raise StaleSourceCutClaim("expired")
        self.completed += 1

    async def defer(self, claim, error_code):
        if self.stale:
            raise StaleSourceCutClaim("expired")
        self.deferred.append(error_code)


class Captures:
    def __init__(self, work, *, unavailable=False):
        self.work = work
        self.unavailable = unavailable
        self.bytes = None

    async def fetch(self, selection):
        assert not self.work.in_write, "network entered an open write transaction"
        if self.unavailable:
            raise SourceCaptureUnavailable("producer offline")

        async def chunks():
            yield b'{"settled":"0"}'

        self.bytes = await SourceCaptureBytes.acquire(chunks())
        return CapturedSourcePage(
            selection,
            self.bytes,
            "qcp-source-json:v1",
            "application/json",
            H,
            "epoch1",
            "scope1",
            1,
            1,
            None,
            "job",
            datetime(2026, 10, 16, tzinfo=UTC),
            "v1",
        )

    async def close(self):
        pass


async def test_one_page_commits_after_fetch_and_retires_owned_spool():
    work = Work()
    captures = Captures(work)
    assert await FinancialSourceCutProcessor(work, captures).step()
    assert work.saved == 1 and work.completed == 0
    assert captures.bytes._stream.closed


@pytest.mark.parametrize("finished", [False, True])
async def test_stale_worker_cannot_save_or_complete(finished):
    work = Work(stale=True, finished=finished)
    captures = Captures(work)
    assert await FinancialSourceCutProcessor(work, captures).step()
    assert work.saved == work.completed == 0 and work.deferred == []
    if captures.bytes is not None:
        assert captures.bytes._stream.closed


async def test_source_outage_is_explicit_pending_not_complete_empty():
    work = Work()
    assert await FinancialSourceCutProcessor(work, Captures(work, unavailable=True)).step()
    assert work.deferred == ["SOURCE_CAPTURE_UNAVAILABLE"]
    assert work.saved == work.completed == 0


async def test_retained_cache_replays_without_contacting_offline_original_source():
    work = Work()
    acquired = await Captures(work).fetch(request())
    cached = replace(acquired, retained_bytes_verified=True)

    async def cache(selection):
        assert selection == cached.request
        return cached

    work.cached_capture = cache
    assert await FinancialSourceCutProcessor(work, Captures(work, unavailable=True)).step()
    assert work.saved == 1 and work.deferred == []
    assert cached.capture_bytes._stream.closed


async def test_large_retained_response_is_segmented_without_total_history_truncation():
    async def chunks():
        for _ in range(5):
            yield b"a" * 524_288

    owned = await SourceCaptureBytes.acquire(chunks())
    try:
        assert owned.byte_count == 5 * 524_288
        assert len(list(owned.segments())) == 5
        assert owned._stream._rolled
        owned._stream.seek(0)
        owned._stream.write(b"b")
        with pytest.raises(SourceCaptureUnavailable, match="RAW_DRIFT"):
            list(owned.segments())
    finally:
        owned.close()


async def test_product_specific_epoch_preserves_unknown_without_fabrication():
    async def chunks():
        yield b"{}"

    owned = await SourceCaptureBytes.acquire(chunks())
    try:
        page = CapturedSourcePage(
            request(),
            owned,
            "qcp-source-json:v1",
            "application/json",
            H,
            None,
            None,
            0,
            0,
            None,
            "job",
            datetime(2026, 10, 16, tzinfo=UTC),
            "v1",
        )
        assert page.snapshot_epoch is None
        with pytest.raises(SourceCaptureUnavailable, match="VALUATION_EPOCH_MISSING"):
            replace(page, request=replace(request(), product_name="PortfolioTimeseriesInput"))
        valuation = replace(
            page,
            snapshot_epoch="actual-native-epoch",
            request=replace(request(), product_name="PortfolioTimeseriesInput"),
        )
        assert valuation.snapshot_epoch == "actual-native-epoch"
        with pytest.raises(SourceCaptureUnavailable, match="EPOCH_INVALID"):
            replace(page, snapshot_epoch=" ")
    finally:
        owned.close()


def registry_verification_fixture():
    member = RegistryMemberInput.model_validate_json(
        json.dumps(
            {
                "source_member_id": "member",
                "provider_namespace": "provider",
                "core_portfolio_id": None,
                "member_revision": 1,
                "declarations": [
                    {
                        "effective_from": "2025-01-01",
                        "effective_to": None,
                        "definition_version": "v1",
                        "provenance_reference": "issued",
                        "currency": "USD",
                        "discretionary": None,
                        "included": False,
                    }
                ],
            }
        )
    )
    typed = canonical_content_hash(
        {
            "contract": "PortfolioHistoricalRegistryChunk:v1",
            "members": [member.to_domain().content_hash],
        }
    )
    body = {
        "source_system": "producer",
        "registry_scope_id": "scope",
        "source_cut_id": "cut",
        "revision": 1,
        "chunk_index": 0,
        "typed_content_hash": typed,
        "members": [member.model_dump(mode="json")],
    }
    raw = json.dumps(body).encode()
    manifest = TypeAdapter(HistoricalRegistryCut).validate_json(
        json.dumps(
            {
                "identity": {
                    "tenant_id": "tenant",
                    "source_system": "producer",
                    "scope_id": "scope",
                    "source_cut_id": "cut",
                    "revision": 1,
                    "definition_version": "v1",
                    "coverage_from": "2025-01-01",
                    "coverage_to": "2025-01-31",
                    "calendar": "SG",
                    "observed_at": "2025-02-01T00:00:00Z",
                    "generated_at": "2025-02-02T00:00:00Z",
                    "predecessor_hash": None,
                    "expected_head_hash": None,
                },
                "expected_population": {
                    "reference": "external",
                    "definition_version": "v1",
                    "count": 1,
                    "content_hash": H,
                },
                "declared_coverage": "COMPLETE",
                "supplied_count": 1,
                "members_root": ordered_content_root(
                    "PortfolioHistoricalRegistryMembers:v1", [member.to_domain().content_hash]
                )[1],
                "chunk_count": 1,
                "chunks_root": ordered_content_root("NeutralSourceChunks:v1", [typed])[1],
            }
        )
    )
    chunk = SimpleNamespace(
        chunk_index=0,
        row_count=1,
        raw_bytes=raw,
        raw_hash=hashlib.sha256(raw).hexdigest(),
        typed_hash=typed,
    )
    row = SimpleNamespace(
        declaration=member.model_dump(mode="json"),
        content_hash=member.to_domain().content_hash,
        provider_namespace="provider",
        source_member_id="member",
    )
    return manifest, chunk, row, body


async def test_resumable_verification_recomputes_ingress_and_member_roots():
    manifest, chunk, row, _ = registry_verification_fixture()
    assert chunk.typed_hash == "cd6fe15101d25cd74353a30d0c28f07e60789a5c1d5110e9e737ea3dcbca2aa2"
    assert chunk.raw_hash == "68a48427e424646f5aa82b9eef4240518269158d8f912762c13a8970951bfa90"
    first = verify_chunk_step({"stage": "VERIFY_CHUNKS"}, manifest, chunk)
    resumed = json.loads(json.dumps(first))
    assert resumed["ordered_root_checkpoint"][1] == 1
    members = verify_chunk_step(resumed, manifest, None)
    assert members["stage"] == "VERIFY_MEMBERS"
    assert verify_member_page(members, manifest, [row], has_more=False)["stage"] == "READY"
    partial = verify_member_page(members, manifest, [row], has_more=True)
    with pytest.raises(SourceManifestRejected, match="ORDER_DRIFT"):
        verify_member_page(partial, manifest, [row], has_more=False)
    with pytest.raises(SourceManifestRejected, match="POPULATION_MISMATCH"):
        verify_member_page(members, manifest, [], has_more=False)


@pytest.mark.parametrize("mutation", ["raw", "typed", "address", "duplicate", "count"])
async def test_retained_chunk_drift_cannot_earn_manifest_verification(mutation):
    manifest, chunk, _, body = registry_verification_fixture()
    if mutation == "raw":
        chunk.raw_bytes += b" "
    elif mutation == "typed":
        chunk.typed_hash = "b" * 64
    elif mutation == "count":
        chunk.row_count = 2
    else:
        if mutation == "address":
            body["registry_scope_id"] = "foreign"
            chunk.raw_bytes = json.dumps(body).encode()
        else:
            chunk.raw_bytes = chunk.raw_bytes.replace(
                b'"revision": 1', b'"revision": 1, "revision": 1'
            )
        chunk.raw_hash = hashlib.sha256(chunk.raw_bytes).hexdigest()
    with pytest.raises(SourceManifestRejected):
        verify_chunk_step({"stage": "VERIFY_CHUNKS"}, manifest, chunk)


@pytest.mark.parametrize("raw", [b"{", b"\xff", b"[" * 1500 + b"0" + b"]" * 1500])
async def test_admission_refusal_preserves_worker_error_and_checkpoint_without_completion(raw):
    manifest, chunk, _, _ = registry_verification_fixture()
    chunk.raw_bytes = raw
    chunk.raw_hash = hashlib.sha256(raw).hexdigest()
    checkpoint = {"stage": "VERIFY_CHUNKS", "verified_rows": 0}
    with pytest.raises(SourceManifestRejected, match="SOURCE_CHUNK_TYPED_DRIFT"):
        verify_chunk_step(checkpoint, manifest, chunk)
    assert checkpoint == {"stage": "VERIFY_CHUNKS", "verified_rows": 0}


async def test_empty_queue_and_completed_work_have_distinct_terminal_effects():
    work = Work(finished=True)
    captures = SimpleNamespace(fetch=AsyncMock())
    assert await FinancialSourceCutProcessor(work, captures).step() is True
    assert work.completed == 1 and work.saved == 0
    work.claim = AsyncMock(return_value=None)
    assert await FinancialSourceCutProcessor(work, captures).step() is False
    assert work.completed == 1
    captures.fetch.assert_not_awaited()


async def test_verification_progress_advances_without_acquisition_or_completion():
    work = Work()
    progress = SourceCutProgress("VERIFY_INPUTS")
    work.next_capture = AsyncMock(return_value=progress)
    work.advance = AsyncMock()
    captures = SimpleNamespace(fetch=AsyncMock())
    assert await FinancialSourceCutProcessor(work, captures).step()
    assert work.advance.await_args.args[1] == progress
    assert work.saved == work.completed == 0 and work.deferred == []
    captures.fetch.assert_not_awaited()


@pytest.mark.parametrize("stale", [False, True])
async def test_manifest_rejection_cannot_complete_and_respects_rejection_fence(stale):
    work = Work()
    work.next_capture = AsyncMock(side_effect=SourceManifestRejected("invalid immutable root"))
    work.reject = AsyncMock(side_effect=StaleSourceCutClaim("lost") if stale else None)
    captures = SimpleNamespace(fetch=AsyncMock())
    assert await FinancialSourceCutProcessor(work, captures).step()
    work.reject.assert_awaited_once()
    assert work.saved == work.completed == 0 and work.deferred == []
    captures.fetch.assert_not_awaited()


@pytest.mark.parametrize("stale", [False, True])
async def test_substituted_acquisition_is_closed_before_defer_without_save(stale):
    work = Work(stale=stale)
    page = await Captures(work).fetch(replace(request(), portfolio_id="foreign"))
    captures = SimpleNamespace(fetch=AsyncMock(return_value=page))
    assert await FinancialSourceCutProcessor(work, captures).step()
    assert page.capture_bytes._stream.closed
    assert work.saved == work.completed == 0
    assert work.deferred == ([] if stale else ["SOURCE_CAPTURE_UNAVAILABLE"])


def financial_verification_fixture(*, compatibility=False):
    identity = registry_verification_fixture()[0].identity
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
    selections = []
    for role in InputRole:
        if role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS):
            selector, product = valuation, "PortfolioTimeseriesInput"
        elif role is InputRole.FLOWS:
            selector = dict(
                kind="FLOWS",
                source_system="producer",
                source_cut_id="flows",
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
                source_record_id="record",
                observation_id=H,
                content_hash=H,
                source_cut_id="native",
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
                receipt_job_id="receipt",
                source_revision="1",
            )
        )
    declaration = dict(
        portfolio_id="portfolio-a",
        currency="USD",
        prior_date="2024-12-31",
        month_end_date="2025-01-31",
        registry_root=H,
        member_revision=1,
        selections=selections,
        settled_unencumbered=None,
        compatibility=None,
    )
    if compatibility:
        declaration["compatibility"] = dict(
            source_system="producer",
            scope_id="scope",
            definition_version="v1",
            registry_root=H,
            role_roots=[[role.value, H] for role in InputRole],
            coverage_from="2025-01-01",
            coverage_to="2025-01-31",
            currency="USD",
            basis_reference="declared-only",
            original_evidence_digest=H,
        )
    row = SimpleNamespace(
        declaration=declaration,
        portfolio_id="portfolio-a",
        content_hash=canonical_content_hash(
            {"contract": "PortfolioFinancialSourceCutInput:v1", "selection": declaration}
        ),
    )
    manifest = FinancialSourceCutManifest(
        identity=identity,
        selection_count=1,
        selections_root=ordered_content_root(
            "PortfolioFinancialSourceCutInputs:v1", [row.content_hash]
        )[1],
        chunk_count=1,
        chunks_root=H,
    )
    return manifest, row


@pytest.mark.parametrize("compatibility", [False, True])
async def test_financial_input_verification_resumes_root_and_retains_unknown_posture(compatibility):
    manifest, row = financial_verification_fixture(compatibility=compatibility)
    initial = {"stage": "VERIFY_INPUTS"}
    partial = verify_input_page(initial, manifest, [row], has_more=True)
    assert initial == {"stage": "VERIFY_INPUTS"}
    assert partial["last_verified_portfolio_id"] == "portfolio-a"
    assert partial.get("compatibility_declaration_count", 0) == int(compatibility)
    resumed = verify_input_page(json.loads(json.dumps(partial)), manifest, [], has_more=False)
    assert resumed["stage"] == "SPAWN_CAPTURES" and resumed["spawned_chunks"] == 0
    assert resumed["ordered_root_checkpoint"] is None


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("selector", "DECLARATION_INVALID"),
        ("portfolio", "TYPED_ORDER_DRIFT"),
        ("typed", "TYPED_ORDER_DRIFT"),
        ("order", "TYPED_ORDER_DRIFT"),
        ("excess", "EXCESS_POPULATION"),
        ("root", "POPULATION_MISMATCH"),
        ("missing", "POPULATION_MISMATCH"),
    ],
)
async def test_financial_input_refusals_do_not_advance_original_checkpoint(mutation, code):
    manifest, row = financial_verification_fixture()
    checkpoint = {"stage": "VERIFY_INPUTS"}
    rows = [row]
    if mutation == "selector":
        row.declaration["selections"][0]["selector_hash"] = "b" * 64
    elif mutation == "portfolio":
        row.portfolio_id = "foreign"
    elif mutation == "typed":
        row.content_hash = "b" * 64
    elif mutation == "order":
        checkpoint["last_verified_portfolio_id"] = row.portfolio_id
    elif mutation == "excess":
        manifest = replace(manifest, selection_count=0)
    elif mutation == "root":
        manifest = replace(manifest, selections_root="b" * 64)
    else:
        rows = []
    saved = dict(checkpoint)
    with pytest.raises(SourceManifestRejected, match=code):
        verify_input_page(checkpoint, manifest, rows, has_more=False)
    assert checkpoint == saved


@pytest.mark.parametrize("mutation", ["index", "bool_count", "negative_count", "excess"])
async def test_chunk_index_and_exact_population_are_verified_before_progress(mutation):
    manifest, chunk, _, _ = registry_verification_fixture()
    if mutation == "index":
        chunk.chunk_index = 1
    elif mutation == "bool_count":
        chunk.row_count = True
    elif mutation == "negative_count":
        chunk.row_count = -1
    else:
        manifest = replace(manifest, supplied_count=0)
    checkpoint = {"stage": "VERIFY_CHUNKS"}
    with pytest.raises(SourceManifestRejected, match="INDEX_OR_COUNT|EXCESS_POPULATION"):
        verify_chunk_step(checkpoint, manifest, chunk)
    assert checkpoint == {"stage": "VERIFY_CHUNKS"}


async def test_two_nonempty_financial_pages_reconcile_order_and_final_root():
    manifest, first = financial_verification_fixture(compatibility=True)
    declaration = first.declaration | {"portfolio_id": "portfolio-b"}
    second = SimpleNamespace(
        portfolio_id="portfolio-b",
        declaration=declaration,
        content_hash=canonical_content_hash(
            {"contract": "PortfolioFinancialSourceCutInput:v1", "selection": declaration}
        ),
    )
    manifest = replace(
        manifest,
        selection_count=2,
        selections_root=ordered_content_root(
            "PortfolioFinancialSourceCutInputs:v1", [first.content_hash, second.content_hash]
        )[1],
    )
    partial = verify_input_page({"stage": "VERIFY_INPUTS"}, manifest, [first], has_more=True)
    resumed = verify_input_page(json.loads(json.dumps(partial)), manifest, [second], has_more=False)
    assert resumed["last_verified_portfolio_id"] == "portfolio-b"
    assert resumed["compatibility_declaration_count"] == 2
    assert resumed["stage"] == "SPAWN_CAPTURES" and resumed["ordered_root_checkpoint"] is None


async def test_member_excess_population_refuses_without_replacing_checkpoint():
    manifest, _, row, _ = registry_verification_fixture()
    manifest = replace(manifest, supplied_count=0)
    checkpoint = {"stage": "VERIFY_MEMBERS"}
    with pytest.raises(SourceManifestRejected, match="MEMBER_EXCESS_POPULATION"):
        verify_member_page(checkpoint, manifest, [row], has_more=True)
    assert checkpoint == {"stage": "VERIFY_MEMBERS"}
