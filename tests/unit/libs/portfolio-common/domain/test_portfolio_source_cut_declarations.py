"""Extracted declaration identity/public imports and original fixed registry hash remain stable."""

from datetime import UTC, date, datetime

import pytest
from portfolio_common.domain import portfolio_financial_source_cuts as public
from portfolio_common.domain import portfolio_source_cut_declarations as declarations

pytestmark = pytest.mark.unit


def test_original_public_symbols_are_the_actual_extracted_classes_and_validators():
    for name in (
        "DeclaredCoverage",
        "ClosedNeutralDeclaration",
        "EffectiveDeclaration",
        "HistoricalRegistryMember",
        "SourceCutIdentity",
        "ExpectedPopulation",
        "HistoricalRegistryCut",
        "positive_revision",
        "ordered_dates",
        "require_currency",
    ):
        assert getattr(public, name) is getattr(declarations, name)


def test_original_registry_manifest_vector_survives_module_extraction():
    stamp = datetime(2026, 10, 16, tzinfo=UTC)
    identity = declarations.SourceCutIdentity(
        "tenant",
        "producer",
        "scope",
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
    manifest = declarations.HistoricalRegistryCut(
        identity,
        declarations.ExpectedPopulation("independent", "v1", 0, "a" * 64),
        declarations.DeclaredCoverage.COMPLETE,
        0,
        public.ordered_content_root("PortfolioHistoricalRegistryMembers:v1", [])[1],
        0,
        public.ordered_content_root("NeutralSourceChunks:v1", [])[1],
    )
    assert (
        manifest.content_hash == "b13bb541c8faac06dd5d621fcff4c749e7dab75af3a767a7e65cb7810fdb2f2c"
    )
    assert manifest.population_verification == "UNVERIFIED"


@pytest.mark.parametrize("value", [True, 0, -1, "1"])
def test_revision_validator_never_coerces_after_extraction(value):
    with pytest.raises(ValueError):
        declarations.positive_revision(value)
