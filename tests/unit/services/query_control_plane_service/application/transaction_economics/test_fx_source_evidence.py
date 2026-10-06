"""Independent source presence and existing-producer receipt compatibility controls."""

import importlib.util
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Transaction, TransactionSourceRevision
from portfolio_common.domain.calculation_lineage import (
    build_calculation_lineage,
    calculation_lineage_binds_output,
    calculation_lineage_from_payload,
    canonical_content_hash,
)
from portfolio_common.domain.tenant import TenantId
from portfolio_common.domain.transaction.numeric_policy import (
    TRANSACTION_COST_LEDGER_OUTPUT_V1,
)
from portfolio_common.domain.transaction.payload_identity import (
    transaction_payload_fingerprint,
    transaction_payload_pre_upstream_fingerprint,
)
from portfolio_common.domain.transaction.source_evidence_revision import (
    retained_fx_output_payload,
)
from portfolio_common.financial_numeric import ExactNumeric
from portfolio_common.infrastructure.transaction_source_evidence import (
    _material_source_row,
    transaction_receipt_output,
)

from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    baseline_processing,
)
from src.services.query_control_plane_service.app.application.transaction_economics import (
    performance_policy,
    performance_rows,
)
from src.services.query_control_plane_service.app.infrastructure import (
    transaction_economics_sources,
)
from tests.test_support.fx_source_evidence import TENANT, fx_source_fixture


@pytest.mark.parametrize(
    "column",
    [column for column in Transaction.__table__.columns if isinstance(column.type, ExactNumeric)],
    ids=lambda column: column.name,
)
def test_source_cut_binds_every_persisted_numeric_column_without_scale_or_value_loss(column):
    assert (column.type.precision, column.type.scale) == (18, 10)
    raw, _, ledger = fx_source_fixture(Decimal("0"), Decimal("0"))
    row = (ledger, SimpleNamespace(id=17, payload=raw), None, None, None)
    setattr(ledger, column.name, Decimal("12"))
    first = canonical_content_hash(_material_source_row(row, TENANT.value))
    setattr(ledger, column.name, Decimal("12.0000000000"))
    assert canonical_content_hash(_material_source_row(row, TENANT.value)) == first
    assert str(getattr(ledger, column.name)) == "12.0000000000"
    setattr(ledger, column.name, Decimal("12.0000000001"))
    assert canonical_content_hash(_material_source_row(row, TENANT.value)) != first
    setattr(ledger, column.name, None)
    missing = canonical_content_hash(_material_source_row(row, TENANT.value))
    setattr(ledger, column.name, Decimal("0"))
    assert canonical_content_hash(_material_source_row(row, TENANT.value)) != missing
    assert _material_source_row(row, TENANT.value)["booked_output"].keys() == (
        transaction_receipt_output(ledger, TENANT.value).keys()
    )


@pytest.mark.parametrize(
    "axis", ["root", "receipt", "fingerprint", "revision", "intent", "operation"]
)
def test_source_cut_keeps_all_non_numeric_authority_material_distinguishable(axis):
    raw, _, ledger = fx_source_fixture(Decimal("0"), Decimal("0"))
    root = SimpleNamespace(id=17, payload=raw)
    revision = SimpleNamespace(
        **{c.name: None for c in TransactionSourceRevision.__table__.columns}
    )
    intent = SimpleNamespace(payload={"source": "original"})
    operation = SimpleNamespace(
        tenant_id=TENANT.value,
        job_id="job",
        entity_type="transaction",
        endpoint="/ingest/transaction-source-corrections",
        status="queued",
        accepted_count=1,
    )
    row = (ledger, root, revision, intent, operation)
    first = canonical_content_hash(_material_source_row(row, TENANT.value))
    if axis == "root":
        root.payload = raw | {"realized_fx_pnl_local": "1"}
    elif axis == "receipt":
        ledger.calculation_lineage = ledger.calculation_lineage | {"algorithm_version": 99}
    elif axis == "fingerprint":
        ledger.payload_fingerprint = "changed"
    elif axis == "revision":
        revision.revision_sha256 = "a" * 64
    elif axis == "intent":
        intent.payload = {"source": "changed"}
    else:
        operation.status = "completed"
    assert canonical_content_hash(_material_source_row(row, TENANT.value)) != first


fx_booked_transaction_output_payload = baseline_processing.fx_booked_transaction_output_payload
build_performance_component_economics_totals = (
    performance_policy.build_performance_component_economics_totals
)
missing_performance_component_families = performance_policy.missing_performance_component_families
observed_performance_component_families = performance_policy.observed_performance_component_families
build_performance_component_economics_rows = (
    performance_rows.build_performance_component_economics_rows
)
SqlAlchemyTransactionEconomicsReader = (
    transaction_economics_sources.SqlAlchemyTransactionEconomicsReader
)
_booked_transaction_economics = transaction_economics_sources._booked_transaction_economics


@pytest.fixture
def legacy_producer():
    path = (
        Path(__file__).resolve().parents[5]
        / "fixtures/transaction_source_confirmation/fx_baseline_v1_325d.py"
    )
    name = (
        "src.services.portfolio_transaction_processing_service.app.domain"
        ".transaction.fx._legacy_unit_producer"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_fx_processed_transaction


def use_legacy_receipt(raw, processed, ledger, producer):
    fields = {
        name: None if raw[name] is None else Decimal(raw[name])
        for name in (
            "realized_capital_pnl_local",
            "realized_fx_pnl_local",
            "realized_total_pnl_local",
            "realized_capital_pnl_base",
            "realized_fx_pnl_base",
            "realized_total_pnl_base",
        )
    }
    old = producer(replace(processed, calculation_lineage=None, **fields))
    assert old.calculation_lineage is not None
    ledger.calculation_lineage = old.calculation_lineage.lineage_payload()
    assert ledger.calculation_lineage["algorithm_version"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [1, 2])
async def test_live_qcp_preserves_missing_vs_explicit_zero_with_equal_booked_amounts(
    version, legacy_producer
):
    missing_raw, missing_processed, missing = fx_source_fixture(None, None)
    zero_raw, zero_processed, zero = fx_source_fixture(Decimal("0"), Decimal("0"))
    if version == 1:
        use_legacy_receipt(missing_raw, missing_processed, missing, legacy_producer)
        use_legacy_receipt(zero_raw, zero_processed, zero, legacy_producer)
    assert transaction_receipt_output(missing, TENANT.value) == transaction_receipt_output(
        zero, TENANT.value
    )
    absent = await qualify(missing_raw, missing)
    supplied = await qualify(zero_raw, zero)
    assert (absent.local, absent.base, absent.reason) == (
        None,
        None,
        "FX_SOURCE_INCOMPLETE",
    )
    assert (supplied.local, supplied.base, supplied.reason) == (
        Decimal("0"),
        Decimal("0"),
        "FX_SOURCE_QUALIFIED",
    )
    assert absent.source_evidence is not None and supplied.source_evidence is not None
    assert not absent.source_evidence.original_local_present
    assert not absent.source_evidence.original_base_present
    assert supplied.source_evidence.original_local_present
    assert supplied.source_evidence.original_base_present
    assert absent.source_evidence.source_cut_sha256 != supplied.source_evidence.source_cut_sha256


async def qualify(raw, ledger, *, tenant=TENANT):
    """Exercise live QCP composition and shared qualification, not a test-only oracle."""
    result = MagicMock()
    result.all.return_value = (
        [(ledger, SimpleNamespace(id=17, payload=raw), None, None, None)]
        if tenant == TENANT
        else []
    )
    session = AsyncMock()
    session.execute.return_value = result
    evidence = await SqlAlchemyTransactionEconomicsReader(session)._fx_source_evidence(
        [ledger], portfolio_id=ledger.portfolio_id, tenant_id=tenant
    )
    session.execute.assert_awaited_once()
    for method in (session.commit, session.flush, session.rollback, session.close):
        method.assert_not_awaited()
    return evidence[ledger.transaction_id]


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("12"), Decimal("-12")])
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.asyncio
async def test_existing_producer_output_and_independent_source_qualify_exact_figures(
    amount, version, legacy_producer
):
    raw, processed, ledger = fx_source_fixture(amount, amount)
    if version == 1:
        use_legacy_receipt(raw, processed, ledger, legacy_producer)
    assert canonical_content_hash(
        retained_fx_output_payload(transaction_receipt_output(ledger, TENANT.value))
    ) == canonical_content_hash(fx_booked_transaction_output_payload(processed))
    evidence = await qualify(raw, ledger)
    assert (evidence.local, evidence.base, evidence.reason) == (
        amount,
        amount,
        "FX_SOURCE_QUALIFIED",
    )
    booked = _booked_transaction_economics(ledger, costs=(), fx_pnl_source_evidence=evidence)
    row = build_performance_component_economics_rows([booked])[0]
    assert (row.realized_fx_pnl_local, row.realized_fx_pnl_base) == (amount, amount)
    assert "realized_fx_pnl" in observed_performance_component_families([row])
    totals = {
        item.component_family: item
        for item in build_performance_component_economics_totals(
            [row], portfolio_base_currency="USD"
        )
    }
    assert totals["realized_fx_pnl"].amount == amount
    assert totals["realized_fx_pnl"].missing_evidence_count == 0


@pytest.mark.parametrize("local,base", [(None, Decimal("12")), (Decimal("0"), None), (None, None)])
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.asyncio
async def test_legacy_normalized_receipt_cannot_recreate_original_missing_basis(
    local, base, version, legacy_producer
):
    raw, processed, ledger = fx_source_fixture(local, base)
    if version == 1:
        use_legacy_receipt(raw, processed, ledger, legacy_producer)
    ledger.payload_fingerprint = transaction_payload_pre_upstream_fingerprint(raw)
    evidence = await qualify(raw, ledger)
    assert (evidence.local, evidence.base) == (local, base)
    assert evidence.reason == "FX_SOURCE_INCOMPLETE"
    row = build_performance_component_economics_rows(
        [_booked_transaction_economics(ledger, costs=(), fx_pnl_source_evidence=evidence)]
    )[0]
    if local is None:
        assert row.realized_total_pnl_local is None
    if base is None:
        assert row.realized_total_pnl_base is None


@pytest.mark.parametrize(
    "field", ["input_content_hash", "calculation_content_hash", "output_content_hash"]
)
@pytest.mark.asyncio
async def test_tampered_receipt_refuses_even_explicit_source_zero(field):
    raw, _, ledger = fx_source_fixture(Decimal("0"), Decimal("0"))
    ledger.calculation_lineage[field] = "f" * 64
    evidence = await qualify(raw, ledger)
    assert evidence.local is None and evidence.base is None


@pytest.mark.parametrize(
    "field",
    ["tenant_id", "transaction_id", "portfolio_id", "security_id", "component_type"],
)
@pytest.mark.asyncio
async def test_foreign_raw_authority_cannot_qualify_ledger(field):
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("-12"))
    raw[field] = "FOREIGN"
    assert (await qualify(raw, ledger)).reason == "FX_SOURCE_AUTHORITY_UNAVAILABLE"


@pytest.mark.parametrize(
    "receipt", [None, {}, {"algorithm_id": "untrusted"}, "raw-untrusted-marker"]
)
@pytest.mark.asyncio
async def test_missing_or_malformed_receipt_has_bounded_unavailable_reason(receipt):
    raw, _, ledger = fx_source_fixture(Decimal("0"), Decimal("0"))
    ledger.calculation_lineage = receipt
    assert (await qualify(raw, ledger)).reason == "FX_SOURCE_AUTHORITY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_changed_output_missing_source_wrong_tenant_and_repeated_read_are_non_mutating():
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("-12"))
    before = deepcopy(ledger.calculation_lineage)
    assert (await qualify(None, ledger)).local is None
    assert (await qualify(raw, ledger, tenant=TenantId("FOREIGN"))).local is None
    assert await qualify(raw, ledger) == await qualify(raw, ledger)
    assert ledger.calculation_lineage == before
    ledger.realized_fx_pnl_local = Decimal("0")
    assert (await qualify(raw, ledger)).local is None


@pytest.mark.asyncio
async def test_mixed_total_retains_missing_evidence_instead_of_summing_unknown_as_zero():
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("12"))
    qualified = _booked_transaction_economics(
        ledger, costs=(), fx_pnl_source_evidence=await qualify(raw, ledger)
    )
    missing = replace(qualified, transaction_id="MISSING", fx_pnl_source_evidence=None)
    rows = build_performance_component_economics_rows([qualified, missing])
    totals = {
        item.component_family: item
        for item in build_performance_component_economics_totals(
            rows, portfolio_base_currency="USD"
        )
    }
    for family in ("realized_fx_pnl", "realized_total_pnl"):
        assert totals[family].amount is None
        assert totals[family].evidence_count == 1
        assert totals[family].missing_evidence_count == 1
        assert family in missing_performance_component_families(
            rows,
            observed_performance_component_families(rows),
            authoritative_empty=False,
        )


@pytest.mark.parametrize("raw", [None, [], "not-source", {"transaction_id": "incomplete"}])
@pytest.mark.asyncio
async def test_unusable_original_payload_never_becomes_zero(raw):
    _, _, ledger = fx_source_fixture(Decimal("0"), Decimal("0"))
    assert (await qualify(raw, ledger)).reason == "FX_SOURCE_AUTHORITY_UNAVAILABLE"


@pytest.mark.parametrize("field", ["algorithm_id", "algorithm_version", "intermediate_precision"])
@pytest.mark.asyncio
async def test_internally_valid_receipt_with_foreign_algorithm_policy_is_refused(field):
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("12"))
    receipt = ledger.calculation_lineage
    values = {
        key: receipt[key] for key in ("algorithm_id", "algorithm_version", "intermediate_precision")
    }
    values[field] = "foreign-algorithm" if field == "algorithm_id" else 2
    ledger.calculation_lineage = build_calculation_lineage(
        **values,
        input_payload={"synthetic": "foreign-policy"},
        output_payload=retained_fx_output_payload(transaction_receipt_output(ledger, TENANT.value)),
        numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
    ).lineage_payload()
    assert (await qualify(raw, ledger)).reason == "FX_SOURCE_AUTHORITY_UNAVAILABLE"


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "foreign-output"),
        ("version", "2.0.0"),
        ("precision", 19),
        ("scale", 9),
        ("working_precision", 65),
        ("rounding", "ROUND_DOWN"),
        (None, None),
    ],
)
@pytest.mark.asyncio
async def test_internally_valid_output_bound_receipt_requires_complete_numeric_policy(field, value):
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("-12"))
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity()
    wrong_policy = None if field is None else replace(policy, **{field: value})
    output = retained_fx_output_payload(transaction_receipt_output(ledger, TENANT.value))
    ledger.calculation_lineage = build_calculation_lineage(
        algorithm_id="foreign-exchange-baseline-processing",
        algorithm_version=1,
        intermediate_precision=policy.working_precision,
        input_payload={"synthetic": "wrong-policy-negative"},
        output_payload=output,
        numeric_output_policy=wrong_policy,
    ).lineage_payload()
    decoded = calculation_lineage_from_payload(ledger.calculation_lineage)
    assert decoded is not None and calculation_lineage_binds_output(decoded, output_payload=output)
    evidence = await qualify(raw, ledger)
    assert (evidence.local, evidence.base, evidence.reason) == (
        None,
        None,
        "FX_SOURCE_AUTHORITY_UNAVAILABLE",
    )


@pytest.mark.parametrize("failure", [TypeError, ValueError, ArithmeticError])
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.asyncio
async def test_verification_exception_cannot_promote_source_amount(monkeypatch, failure, version):
    from portfolio_common.infrastructure import transaction_source_evidence as evidence

    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("-12"))
    if version == 1:
        ledger.calculation_lineage = build_calculation_lineage(
            algorithm_id="foreign-exchange-baseline-processing",
            algorithm_version=1,
            intermediate_precision=TRANSACTION_COST_LEDGER_OUTPUT_V1.working_precision,
            numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
            input_payload={"synthetic": "v1-exception-unit-control"},
            output_payload=retained_fx_output_payload(
                transaction_receipt_output(ledger, TENANT.value)
            ),
        ).lineage_payload()

    def refused(*args, **kwargs):
        raise failure("invalid retained authority")

    monkeypatch.setattr(evidence, "verify_retained_fx_source", refused)
    result = await qualify(raw, ledger)
    assert (result.local, result.base, result.reason) == (
        None,
        None,
        "FX_SOURCE_AUTHORITY_UNAVAILABLE",
    )
    assert result.source_evidence.status == "UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize("source_count", [0, 1, 2])
async def test_reader_uses_one_independent_source_and_keeps_original_presence(
    source_count,
):
    raw, _, ledger = fx_source_fixture(Decimal("0"), Decimal("12"))
    result = MagicMock()
    result.all.return_value = [
        (ledger, SimpleNamespace(id=17, payload=raw), None, None, None)
    ] * source_count
    session = AsyncMock()
    session.execute.return_value = result
    evidence = await SqlAlchemyTransactionEconomicsReader(session)._fx_source_evidence(
        [ledger], portfolio_id="QCP-FX-PORT", tenant_id=TENANT
    )
    qualified = evidence[ledger.transaction_id]
    if source_count == 1:
        assert (qualified.local, qualified.base) == (Decimal("0"), Decimal("12"))
        assert qualified.reason == "FX_SOURCE_QUALIFIED"
    else:
        assert (qualified.local, qualified.base) == (None, None)
        assert qualified.reason == "FX_SOURCE_AUTHORITY_UNAVAILABLE"
    statement = session.execute.call_args.args[0]
    parameters = statement.compile().params
    assert TENANT.value in parameters.values()
    assert "RawTransactionPersisted" in parameters.values()
    assert "RawTransaction" in parameters.values()
    assert "QCP-FX-PORT" in parameters.values()
    assert [ledger.transaction_id] in parameters.values()
    session.commit.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_reader_does_not_load_raw_authority_for_non_fx_or_none_mode():
    _, _, ledger = fx_source_fixture(Decimal("12"), Decimal("12"), mode="NONE")
    session = AsyncMock()
    assert (
        await SqlAlchemyTransactionEconomicsReader(session)._fx_source_evidence(
            [ledger], portfolio_id="QCP-FX-PORT", tenant_id=TENANT
        )
        == {}
    )
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_known_base_zero_survives_missing_local_in_page_totals():
    raw, _, ledger = fx_source_fixture(None, Decimal("0"))
    evidence = await qualify(raw, ledger)
    row = build_performance_component_economics_rows(
        [_booked_transaction_economics(ledger, costs=(), fx_pnl_source_evidence=evidence)]
    )[0]
    totals = {
        item.component_family: item
        for item in build_performance_component_economics_totals(
            [row], portfolio_base_currency="USD"
        )
    }
    assert row.realized_fx_pnl_local is None
    assert totals["realized_fx_pnl"].amount == Decimal("0")
    assert totals["realized_fx_pnl"].evidence_count == 1
    assert totals["realized_fx_pnl"].missing_evidence_count == 0


@pytest.mark.asyncio
async def test_raw_amount_disagreement_with_receipted_output_refuses_shared_authority():
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("12"))
    ledger.calculation_lineage = build_calculation_lineage(
        algorithm_id="foreign-exchange-baseline-processing",
        algorithm_version=1,
        intermediate_precision=TRANSACTION_COST_LEDGER_OUTPUT_V1.working_precision,
        numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
        input_payload={"synthetic": "v1-output-only-unit-control"},
        output_payload=retained_fx_output_payload(transaction_receipt_output(ledger, TENANT.value)),
    ).lineage_payload()
    raw["realized_fx_pnl_base"] = "-12"
    ledger.payload_fingerprint = transaction_payload_fingerprint(raw)
    evidence = await qualify(raw, ledger)
    assert (evidence.local, evidence.base, evidence.reason) == (
        None,
        None,
        "FX_SOURCE_AUTHORITY_UNAVAILABLE",
    )


@pytest.mark.parametrize(
    "field",
    [
        "realized_capital_pnl_local",
        "realized_fx_pnl_local",
        "realized_total_pnl_local",
        "realized_capital_pnl_base",
        "realized_fx_pnl_base",
        "realized_total_pnl_base",
    ],
)
@pytest.mark.asyncio
async def test_v2_rejects_changed_original_input_even_with_rewritten_raw_fingerprint(
    field,
):
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("12"))
    assert ledger.calculation_lineage["algorithm_version"] == 2
    raw[field] = "-12"
    ledger.payload_fingerprint = transaction_payload_fingerprint(raw)
    evidence = await qualify(raw, ledger)
    assert (evidence.local, evidence.base, evidence.reason) == (
        None,
        None,
        "FX_SOURCE_AUTHORITY_UNAVAILABLE",
    )


@pytest.mark.parametrize(
    "mode,component",
    [("NONE", "FX_CONTRACT_CLOSE"), ("UPSTREAM_PROVIDED", "FX_CONTRACT_OPEN")],
)
def test_non_realizing_fx_projects_explicit_zero_without_upstream_authority(mode, component):
    _, _, ledger = fx_source_fixture(Decimal("12"), Decimal("-12"))
    booked = replace(
        _booked_transaction_economics(ledger, costs=()),
        fx_realized_pnl_mode=mode,
        component_type=component,
        fx_pnl_source_evidence=None,
    )
    row = build_performance_component_economics_rows([booked])[0]
    assert (row.realized_fx_pnl_local, row.realized_fx_pnl_base) == (
        Decimal("0"),
        Decimal("0"),
    )
    assert row.fx_pnl_evidence_reason == "FX_SOURCE_NOT_APPLICABLE"
