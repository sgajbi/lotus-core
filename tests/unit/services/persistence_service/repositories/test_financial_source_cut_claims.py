"""Actual command hydration refuses missing/foreign/typed-drifted persisted manifests."""

from copy import deepcopy

import pytest
from portfolio_common.domain.portfolio_financial_source_cuts import ordered_content_root
from portfolio_common.portfolio_financial_source_cut_models import FinancialSourceCutRow

from src.services.persistence_service.app.ports.financial_source_cut_work import (
    SourceManifestRejected,
)
from src.services.persistence_service.app.repositories import financial_source_cut_claims as claims
from src.services.persistence_service.app.repositories import (
    financial_source_cut_work_repository as facade,
)

pytestmark = pytest.mark.unit


def row():
    return FinancialSourceCutRow(
        tenant_id="tenant",
        product_name="PortfolioHistoricalRegistry",
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        content_hash="b13bb541c8faac06dd5d621fcff4c749e7dab75af3a767a7e65cb7810fdb2f2c",
        declaration=dict(
            source_system="producer",
            registry_scope_id="scope",
            source_cut_id="cut",
            revision=1,
            definition_version="v1",
            coverage_from="2025-01-01",
            coverage_to="2025-01-31",
            calendar="SG",
            observed_at="2026-10-16T00:00:00Z",
            generated_at="2026-10-16T00:00:00Z",
            predecessor_hash=None,
            expected_head_hash=None,
            expected_population={
                "reference": "independent",
                "definition_version": "v1",
                "count": 0,
                "content_hash": "a" * 64,
            },
            declared_coverage="COMPLETE",
            supplied_count=0,
            members_root="1f170cc6ad2a8d93447670608183c3aa9c06d9b44b5ece794542cda793317096",
            chunk_count=0,
            chunks_root=ordered_content_root("NeutralSourceChunks:v1", [])[1],
        ),
    )


def test_facade_reexports_actual_identity_and_claim_fences_without_duplicates():
    for name in ("scope", "predicates", "claim_scope_hash", "manifest_from_row", "require_claim"):
        assert getattr(facade, name) is getattr(claims, name)


def test_complete_valid_original_manifest_hydrates_its_exact_domain_root():
    value = row()
    assert claims.manifest_from_row(value).content_hash == value.content_hash


@pytest.mark.parametrize("mutation", ["missing", "unknown", "scope", "typed", "bool"])
def test_malformed_immutable_manifest_is_explicit_rejection(mutation):
    value = row()
    value.declaration = deepcopy(value.declaration)
    if mutation == "missing":
        del value.declaration["calendar"]
    elif mutation == "unknown":
        value.declaration["approved"] = True
    elif mutation == "scope":
        value.registry_scope_id = "foreign"
    elif mutation == "typed":
        value.content_hash = "b" * 64
    else:
        value.declaration["revision"] = True
    with pytest.raises(SourceManifestRejected):
        claims.manifest_from_row(value)


@pytest.mark.parametrize(
    "path,bad",
    [
        (("expected_population", "unexpected"), True),
        (("expected_population", "count"), True),
        (("expected_population", "count"), "0"),
        (("revision",), "1"),
        (("supplied_count",), True),
        (("chunk_count",), "0"),
        (("observed_at",), "2026-10-16T00:00:00"),
        (("generated_at",), 1792108800),
        (("coverage_to",), "2024-12-31"),
        (("declared_coverage",), "QUALIFIED"),
        (("members_root",), "invalid"),
        (("predecessor_hash",), "a" * 64),
        (("expected_population", "count"), float("nan")),
    ],
)
def test_persisted_manifest_refuses_nested_extras_and_coercion(path, bad):
    value = row()
    target = value.declaration
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = bad
    with pytest.raises(SourceManifestRejected):
        claims.manifest_from_row(value)
