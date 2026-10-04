"""Independent source presence and existing-producer receipt compatibility controls."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.calculation_lineage import (
    build_calculation_lineage,
    calculation_lineage_binds_output,
    calculation_lineage_from_payload,
    canonical_content_hash,
)
from portfolio_common.domain.tenant import TenantId
from portfolio_common.domain.transaction.numeric_policy import TRANSACTION_COST_LEDGER_OUTPUT_V1
from portfolio_common.domain.transaction.payload_identity import (
    transaction_payload_fingerprint,
    transaction_payload_pre_upstream_fingerprint,
)

from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx.baseline_processing import (  # noqa: E501
    fx_booked_transaction_output_payload,
)
from src.services.query_control_plane_service.app.application.transaction_economics.evidence import (  # noqa: E501
    fx_receipt_output_payload,
    qualify_fx_pnl_source_evidence,
)
from src.services.query_control_plane_service.app.application.transaction_economics.performance_policy import (  # noqa: E501
    build_performance_component_economics_totals,
    missing_performance_component_families,
    observed_performance_component_families,
)
from src.services.query_control_plane_service.app.application.transaction_economics.performance_rows import (  # noqa: E501
    build_performance_component_economics_rows,
)
from src.services.query_control_plane_service.app.infrastructure.transaction_economics_sources import (  # noqa: E501
    SqlAlchemyTransactionEconomicsReader,
    _booked_transaction_economics,
    _fx_receipt_ledger_output,
)
from tests.test_support.fx_source_evidence import TENANT, fx_source_fixture


def qualify(raw, ledger, *, tenant=TENANT):
    return qualify_fx_pnl_source_evidence(
        raw_source=raw,
        ledger_output=_fx_receipt_ledger_output(ledger, tenant),
        stored_fingerprint=ledger.payload_fingerprint,
        receipt_payload=ledger.calculation_lineage,
        tenant_id=tenant.value,
        source_portfolio_tenant_id=TENANT.value,
    )


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("12"), Decimal("-12")])
def test_existing_producer_output_and_independent_source_qualify_exact_figures(amount):
    raw, processed, ledger = fx_source_fixture(amount, amount)
    assert canonical_content_hash(
        fx_receipt_output_payload(_fx_receipt_ledger_output(ledger, TENANT))
    ) == (canonical_content_hash(fx_booked_transaction_output_payload(processed)))
    evidence = qualify(raw, ledger)
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
def test_legacy_normalized_receipt_cannot_recreate_original_missing_basis(local, base):
    raw, _, ledger = fx_source_fixture(local, base)
    ledger.payload_fingerprint = transaction_payload_pre_upstream_fingerprint(raw)
    evidence = qualify(raw, ledger)
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
def test_tampered_receipt_refuses_even_explicit_source_zero(field):
    raw, _, ledger = fx_source_fixture(Decimal("0"), Decimal("0"))
    ledger.calculation_lineage[field] = "f" * 64
    evidence = qualify(raw, ledger)
    assert evidence.local is None and evidence.base is None


@pytest.mark.parametrize(
    "field", ["tenant_id", "transaction_id", "portfolio_id", "security_id", "component_type"]
)
def test_foreign_raw_authority_cannot_qualify_ledger(field):
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("-12"))
    raw[field] = "FOREIGN"
    assert qualify(raw, ledger).reason == "FX_SOURCE_AUTHORITY_UNAVAILABLE"


@pytest.mark.parametrize(
    "receipt", [None, {}, {"algorithm_id": "untrusted"}, "raw-untrusted-marker"]
)
def test_missing_or_malformed_receipt_has_bounded_unavailable_reason(receipt):
    raw, _, ledger = fx_source_fixture(Decimal("0"), Decimal("0"))
    ledger.calculation_lineage = receipt
    assert qualify(raw, ledger).reason == "FX_SOURCE_AUTHORITY_UNAVAILABLE"


def test_changed_output_missing_source_wrong_tenant_and_repeated_read_are_non_mutating():
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("-12"))
    before = deepcopy(ledger.calculation_lineage)
    assert qualify(None, ledger).local is None
    assert qualify(raw, ledger, tenant=TenantId("FOREIGN")).local is None
    assert qualify(raw, ledger) == qualify(raw, ledger)
    assert ledger.calculation_lineage == before
    ledger.realized_fx_pnl_local = Decimal("0")
    assert qualify(raw, ledger).local is None


def test_mixed_total_retains_missing_evidence_instead_of_summing_unknown_as_zero():
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("12"))
    qualified = _booked_transaction_economics(
        ledger, costs=(), fx_pnl_source_evidence=qualify(raw, ledger)
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
            rows, observed_performance_component_families(rows), authoritative_empty=False
        )


@pytest.mark.parametrize("raw", [None, [], "not-source", {"transaction_id": "incomplete"}])
def test_unusable_original_payload_never_becomes_zero(raw):
    _, _, ledger = fx_source_fixture(Decimal("0"), Decimal("0"))
    assert qualify(raw, ledger).reason == "FX_SOURCE_AUTHORITY_UNAVAILABLE"


@pytest.mark.parametrize("field", ["algorithm_id", "algorithm_version", "intermediate_precision"])
def test_internally_valid_receipt_with_foreign_algorithm_policy_is_refused(field):
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("12"))
    receipt = ledger.calculation_lineage
    values = {
        key: receipt[key] for key in ("algorithm_id", "algorithm_version", "intermediate_precision")
    }
    values[field] = "foreign-algorithm" if field == "algorithm_id" else 2
    ledger.calculation_lineage = build_calculation_lineage(
        **values,
        input_payload={"synthetic": "foreign-policy"},
        output_payload=fx_receipt_output_payload(_fx_receipt_ledger_output(ledger, TENANT)),
        numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
    ).lineage_payload()
    assert qualify(raw, ledger).reason == "FX_SOURCE_AUTHORITY_UNAVAILABLE"


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
def test_internally_valid_output_bound_receipt_requires_complete_numeric_policy(field, value):
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("-12"))
    policy = TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity()
    wrong_policy = None if field is None else replace(policy, **{field: value})
    output = fx_receipt_output_payload(_fx_receipt_ledger_output(ledger, TENANT))
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
    evidence = qualify(raw, ledger)
    assert (evidence.local, evidence.base, evidence.reason) == (
        None,
        None,
        "FX_SOURCE_AUTHORITY_UNAVAILABLE",
    )


@pytest.mark.parametrize("failure", [TypeError, ValueError, ArithmeticError])
def test_verification_exception_cannot_promote_source_amount(monkeypatch, failure):
    from src.services.query_control_plane_service.app.application.transaction_economics import (
        evidence,
    )

    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("-12"))

    def refused(*args, **kwargs):
        raise failure("invalid retained authority")

    amount = MagicMock(return_value=Decimal("12"))
    monkeypatch.setattr(evidence, "calculation_lineage_binds_output", refused)
    monkeypatch.setattr(evidence, "_qualified_source_amount", amount)
    result = qualify(raw, ledger)
    assert (result.local, result.base, result.reason) == (
        None,
        None,
        "FX_SOURCE_AUTHORITY_UNAVAILABLE",
    )
    amount.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("source_count", [0, 1, 2])
async def test_reader_uses_one_independent_source_and_keeps_original_presence(source_count):
    raw, _, ledger = fx_source_fixture(Decimal("0"), Decimal("12"))
    result = MagicMock()
    result.all.return_value = [(raw, TENANT.value)] * source_count
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


def test_known_base_zero_survives_missing_local_in_page_totals():
    raw, _, ledger = fx_source_fixture(None, Decimal("0"))
    evidence = qualify(raw, ledger)
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


def test_raw_amount_disagreement_with_receipted_output_withholds_only_affected_basis():
    raw, _, ledger = fx_source_fixture(Decimal("12"), Decimal("12"))
    raw["realized_fx_pnl_base"] = "-12"
    ledger.payload_fingerprint = transaction_payload_fingerprint(raw)
    evidence = qualify(raw, ledger)
    assert (evidence.local, evidence.base, evidence.reason) == (
        Decimal("12"),
        None,
        "FX_SOURCE_INCOMPLETE",
    )


@pytest.mark.parametrize(
    "mode,component", [("NONE", "FX_CONTRACT_CLOSE"), ("UPSTREAM_PROVIDED", "FX_CONTRACT_OPEN")]
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
    assert (row.realized_fx_pnl_local, row.realized_fx_pnl_base) == (Decimal("0"), Decimal("0"))
    assert row.fx_pnl_evidence_reason == "FX_SOURCE_NOT_APPLICABLE"
