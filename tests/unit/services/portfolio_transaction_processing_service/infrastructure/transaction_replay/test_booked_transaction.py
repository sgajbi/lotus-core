"""Verify canonical booked transaction replay adaptation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.domain.transaction import transaction_payload_fingerprint
from portfolio_common.domain.transaction.fee_components import TRANSACTION_FEE_COMPONENT_FIELDS
from portfolio_common.events import TransactionEvent
from portfolio_common.reprocessing_replay import ReprocessingReplayError
from sqlalchemy.exc import DBAPIError

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayDependencyUnavailable,
    BookedTransactionReplayInvariantViolation,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    build_transaction_semantic_identity,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.semantic_identity import (  # noqa: E501
    build_transaction_correction_identity,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_mapping.booked_transaction import (  # noqa: E501
    to_booked_transaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
    SqlAlchemyBookedTransactionReplayAdapter,
    fee_authority,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay.fee_authority import (  # noqa: E501
    qualify_transaction_fee_source,
)


def _fee_preparation_batch(fields, *, raw_source=False):
    rows, costs, raw, receipts, expected = [], [], [], [], {}
    for index in range(2):
        original, canonical, fee_rows, _ = _retained_fee_fixture(fields)
        transaction_id = f"PREP-{index}"
        original = TransactionEvent.model_validate(
            original.model_dump(mode="python") | {"transaction_id": transaction_id}
        )
        canonical = canonical | {
            "transaction_id": transaction_id,
            "economic_event_id": f"EVT-BUY-P1-{transaction_id}",
            "linked_transaction_group_id": f"LTG-BUY-P1-{transaction_id}",
            "payload_fingerprint": transaction_payload_fingerprint(
                original.model_dump(mode="python")
            ),
        }
        identity = build_transaction_semantic_identity(to_booked_transaction(original))
        rows.append(canonical)
        costs.extend(cost | {"transaction_id": transaction_id} for cost in fee_rows)
        receipts.append(
            {
                "tenant_id": original.tenant_id,
                "portfolio_id": original.portfolio_id,
                "service_name": "portfolio-transaction-processing",
                "semantic_key": identity.semantic_key,
                "payload_fingerprint": identity.payload_fingerprint,
            }
        )
        if raw_source:
            raw.append({"aggregate_id": "P1", "payload": original.model_dump(mode="python")})
        expected[transaction_id] = {
            name: getattr(original, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS
        } | {"trade_fee": original.trade_fee}
    return rows, [costs, raw, receipts, []], expected


def _fee_fact_session(facts):
    session = AsyncMock()
    results = []
    for values in facts:
        result = MagicMock()
        result.mappings.return_value.all.return_value = values
        results.append(result)
    session.execute.side_effect = results
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_source", [False, True])
@pytest.mark.parametrize("fields", [{}, {"gst": Decimal(0)}, {"brokerage": Decimal(1)}])
async def test_fee_batch_requests_receipts_only_without_original_authority(
    monkeypatch, fields, raw_source
):
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_source_repository as module,
    )

    rows, facts, expected = _fee_preparation_batch(fields, raw_source=raw_source)
    constructor = MagicMock(wraps=fee_authority._correction_fee_hypotheses)
    monkeypatch.setattr(fee_authority, "_correction_fee_hypotheses", constructor)
    session = _fee_fact_session(facts)
    assert (
        await module.load_qualified_transaction_fee_sources(
            session, rows, lock_sources=True, allow_retained_receipt=True, derived_financial=True
        )
        == expected
    )
    statements = [call.args[0] for call in session.execute.await_args_list]
    # Without raw, the fixture retains a derived FX cut that requires material authority.
    assert len(statements) == (2 if raw_source else 4)
    from sqlalchemy.dialects import postgresql

    assert "FOR SHARE OF transaction_costs" in str(
        statements[0].compile(dialect=postgresql.dialect())
    )
    assert "FOR SHARE OF outbox_events" in str(statements[1].compile(dialect=postgresql.dialect()))
    assert constructor.call_count == (0 if raw_source else len(rows))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage", ["duplicate", "currency", "unknown", "zero", "negative", "infinite"]
)
async def test_prepared_query_positive_fees_never_replace_cost_validation(damage):
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_source_repository as module,
    )

    rows, facts, _ = _fee_preparation_batch({"brokerage": Decimal(1)})
    cost = facts[0][0]
    if damage == "duplicate":
        facts[0].append(dict(cost))
    elif damage == "currency":
        cost["currency"] = "EUR"
    elif damage == "unknown":
        cost["fee_type"] = "unqualified"
    elif damage == "infinite":
        cost["amount"] = Decimal("Infinity")
    else:
        cost["amount"] = Decimal(0) if damage == "zero" else Decimal(-1)
    session = _fee_fact_session(facts)
    # Malformed costs are a deliberate typed source refusal, never fallback permission.
    with pytest.raises(ReprocessingReplayError) as failure:
        await module.load_qualified_transaction_fee_sources(
            session,
            rows,
            allow_retained_receipt=True,
            derived_financial=True,
        )
    assert failure.value.reason_code == "TRANSACTION_REPLAY_SOURCE_INVALID"
    assert failure.value.failed_transaction_ids == ["PREP-0"]
    assert session.execute.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["unknown", "negative", "infinite"])
async def test_malformed_fee_authority_is_typed_before_any_replay_publication(monkeypatch, damage):
    from portfolio_common.reprocessing_repository import ReprocessingRepository

    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        booked_transaction as module,
    )

    rows, facts, _ = _fee_preparation_batch({"brokerage": Decimal(1)})
    cost = facts[0][0]
    if damage == "unknown":
        cost["fee_type"] = "unqualified"
    else:
        cost["amount"] = Decimal(-1) if damage == "negative" else Decimal("Infinity")
    session = _fee_fact_session(facts)
    monkeypatch.setattr(module, "load_transaction_replay_rows", AsyncMock(return_value=rows))
    publisher = MagicMock()
    replayer = ReprocessingRepository.from_ports(
        reader=module.SqlAlchemyQualifiedTransactionReplayReader(session), publisher=publisher
    )
    with pytest.raises(ReprocessingReplayError) as failure:
        await replayer.reprocess_transactions_by_ids([row["transaction_id"] for row in rows])
    assert failure.value.reason_code == "TRANSACTION_REPLAY_SOURCE_INVALID"
    assert failure.value.failed_transaction_ids == ["PREP-0"]
    publisher.publish_replay_message.assert_not_called()
    publisher.confirm_replay_delivery.assert_not_called()
    assert session.execute.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["canonical", "cost"])
async def test_fee_preparation_rechecks_changed_input_after_receipt_query(monkeypatch, mutation):
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_source_repository as module,
    )

    _, _, canonical, costs, ordinary, correction = _corrected_fee_fixture(
        fields={"brokerage": Decimal(1)}
    )
    rows, facts = [canonical], [costs, [], [ordinary], [correction]]
    constructor = MagicMock(wraps=fee_authority._correction_fee_hypotheses)
    monkeypatch.setattr(fee_authority, "_correction_fee_hypotheses", constructor)
    session = _fee_fact_session(facts)
    execute = session.execute.side_effect

    async def change_after_query(statement):
        result = next(execute)
        if "transaction-correction:" in str(statement.compile().params):
            if mutation == "canonical":
                rows[0]["quantity"] += Decimal(1)
            else:
                facts[0][0]["amount"] = Decimal(2)
        return result

    session.execute.side_effect = change_after_query
    with pytest.raises(ReprocessingReplayError):
        await module.load_qualified_transaction_fee_sources(
            session, rows, allow_retained_receipt=True, derived_financial=True
        )
    assert constructor.call_count == len(rows)


def test_prepared_hypotheses_are_defensive_immutable_and_input_specific(monkeypatch):
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_authority as module,
    )

    _, row, _, _ = _retained_fee_fixture({})
    row["linked_component_ids"] = ["component-1"]
    positive = {}
    preparation = module._FeeAuthorityPreparation()
    constructor = MagicMock(wraps=module._correction_fee_hypotheses)
    monkeypatch.setattr(module, "_correction_fee_hypotheses", constructor)
    first = preparation.correction_hypotheses(row, positive)
    assert preparation.correction_hypotheses(row, positive) is first
    with pytest.raises(TypeError):
        first[0][2]["gst"] = Decimal(99)
    row["linked_component_ids"].append("component-2")
    second = preparation.correction_hypotheses(row, positive)
    assert second is not first
    positive["brokerage"] = Decimal(1)
    third = preparation.correction_hypotheses(row, positive)
    assert third is not second and constructor.call_count == 3
    assert all(projection["brokerage"] == Decimal(1) for _, _, projection in third)
    assert any(projection["brokerage"] is None for _, _, projection in first)
    standalone = module._correction_fee_hypotheses(row, positive)
    assert [
        (key, fingerprint, dict(projection)) for key, fingerprint, projection in third
    ] == standalone


def test_distinct_rows_with_same_transaction_id_do_not_share_preparation():
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_authority as module,
    )

    _, first, _, _ = _retained_fee_fixture({})
    second = first | {"quantity": first["quantity"] + Decimal(1)}
    left = module._FeeAuthorityPreparation().correction_hypotheses(first, {})
    right = module._FeeAuthorityPreparation().correction_hypotheses(second, {})
    assert {key for key, _, _ in left}.isdisjoint(key for key, _, _ in right)


@pytest.mark.asyncio
@pytest.mark.parametrize("presence_mask", range(32))
async def test_original_source_batch_preserves_every_none_zero_mask_without_receipts(presence_mask):
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_source_repository as module,
    )

    fields = {
        name: Decimal(0) if presence_mask & (1 << index) else None
        for index, name in enumerate(TRANSACTION_FEE_COMPONENT_FIELDS)
    }
    original, canonical, costs, _ = _retained_fee_fixture(fields, source_fx=True)
    session = _fee_fact_session(
        [
            costs,
            [
                {
                    "aggregate_id": original.portfolio_id,
                    "payload": original.model_dump(mode="python"),
                }
            ],
        ]
    )
    projected = await module.load_qualified_transaction_fee_sources(
        session, [canonical], allow_retained_receipt=True, derived_financial=True
    )
    assert projected == {"TXN": fields | {"trade_fee": original.trade_fee}}
    assert session.execute.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", [None, "raw-conflict", "duplicate", "foreign", "fingerprint"])
async def test_mixed_batch_receipt_scope_is_pending_only_and_original_exam_is_not_repeated(
    monkeypatch, damage
):
    from sqlalchemy.dialects import postgresql

    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_source_repository as module,
    )

    rows, facts, expected = _fee_preparation_batch({}, raw_source=True)
    _, corrected, canonical, costs, ordinary, correction = _corrected_fee_fixture()
    rows.append(canonical)
    facts[0].extend(costs)
    facts[2] = [ordinary]
    facts[3] = [correction]
    if damage == "raw-conflict":
        facts[1][0]["payload"]["quantity"] += Decimal(1)
    elif damage == "duplicate":
        facts[3].append(dict(correction))
    elif damage == "foreign":
        correction["tenant_id"] = "foreign"
    elif damage == "fingerprint":
        correction["payload_fingerprint"] = "sha256:" + "f" * 64
    examine = MagicMock(wraps=module._qualify_original_fee_source)
    monkeypatch.setattr(module, "_qualify_original_fee_source", examine)
    session = _fee_fact_session(facts)
    if damage:
        with pytest.raises(ReprocessingReplayError):
            await module.load_qualified_transaction_fee_sources(
                session,
                rows,
                lock_sources=True,
                allow_retained_receipt=True,
                derived_financial=True,
            )
        if damage == "raw-conflict":
            assert session.execute.await_count == 2
            return
    else:
        projected = await module.load_qualified_transaction_fee_sources(
            session, rows, lock_sources=True, allow_retained_receipt=True, derived_financial=True
        )
        assert projected == expected | {
            "TXN": {name: getattr(corrected, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS}
            | {"trade_fee": corrected.trade_fee}
        }
    assert examine.call_count == len(rows)
    assert session.execute.await_count == 4
    statements = [call.args[0] for call in session.execute.await_args_list[2:]]
    for statement in statements:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        assert "FOR SHARE OF processed_events" in sql
        assert "ORDER BY processed_events.id" in sql
        parameters = str(statement.compile().params)
        assert "PREP-" not in parameters
        assert "tenant-test" in parameters and "P1" in parameters


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["ordinary", "correction"])
@pytest.mark.parametrize("mutation", ["canonical", "cost", "raw"])
async def test_mixed_batch_rejects_changed_original_input_after_receipt_await(boundary, mutation):
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_source_repository as module,
    )

    rows, facts, _ = _fee_preparation_batch({"brokerage": Decimal(1)}, raw_source=True)
    _, _, canonical, costs, ordinary, correction = _corrected_fee_fixture()
    rows.append(canonical)
    facts[0].extend(costs)
    facts[2], facts[3] = [ordinary], [correction]
    session = _fee_fact_session(facts)
    results = session.execute.side_effect
    calls = 0

    async def execute(statement):
        nonlocal calls
        calls += 1
        result = next(results)
        if calls == (3 if boundary == "ordinary" else 4):
            if mutation == "canonical":
                rows[0]["quantity"] += Decimal(1)
            elif mutation == "cost":
                facts[0][0]["amount"] = Decimal(2)
            else:
                facts[1][0]["payload"]["quantity"] += Decimal(1)
        return result

    session.execute.side_effect = execute
    with pytest.raises(ReprocessingReplayError) as failure:
        await module.load_qualified_transaction_fee_sources(
            session, rows, allow_retained_receipt=True, derived_financial=True
        )
    assert failure.value.failed_transaction_ids == ["PREP-0"]
    assert calls == (3 if boundary == "ordinary" else 4)


@pytest.mark.asyncio
@pytest.mark.parametrize("retained,derived", [(False, False), (False, True), (True, False)])
async def test_fee_modes_do_not_eagerly_prepare_corrections(monkeypatch, retained, derived):
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_source_repository as module,
    )

    rows, facts, expected = _fee_preparation_batch({}, raw_source=True)
    constructor = MagicMock(wraps=fee_authority._correction_fee_hypotheses)
    monkeypatch.setattr(fee_authority, "_correction_fee_hypotheses", constructor)
    assert (
        await module.load_qualified_transaction_fee_sources(
            _fee_fact_session(facts[:3]),
            rows,
            allow_retained_receipt=retained,
            derived_financial=derived,
        )
        == expected
    )
    constructor.assert_not_called()


@pytest.mark.asyncio
async def test_empty_fee_batch_needs_no_preparation_or_query(monkeypatch):
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_source_repository as module,
    )

    constructor = MagicMock(wraps=fee_authority._correction_fee_hypotheses)
    monkeypatch.setattr(fee_authority, "_correction_fee_hypotheses", constructor)
    session = AsyncMock()
    assert (
        await module.load_qualified_transaction_fee_sources(
            session, [], allow_retained_receipt=True, derived_financial=True
        )
        == {}
    )
    session.execute.assert_not_called()
    constructor.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(("replayed_count", "expected"), [(0, False), (1, True)])
async def test_replay_adapter_maps_canonical_replay_count(
    replayed_count: int,
    expected: bool,
) -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    session_factory = MagicMock(return_value=session)
    replayer = AsyncMock()
    replayer.reprocess_transactions_by_ids.return_value = replayed_count
    replayer_factory = MagicMock(return_value=replayer)
    adapter = SqlAlchemyBookedTransactionReplayAdapter(
        session_factory=session_factory,
        replayer_factory=replayer_factory,
    )

    replayed = await adapter.replay_booked_transaction(
        transaction_id="TXN-REPLAY-01",
        correlation_id="corr-replay-01",
    )

    assert replayed is expected
    session_factory.assert_called_once_with()
    replayer_factory.assert_called_once_with(session)
    replayer.reprocess_transactions_by_ids.assert_awaited_once_with(
        ["TXN-REPLAY-01"],
        correlation_id="corr-replay-01",
    )
    session.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_replay_adapter_rejects_impossible_unique_transaction_cardinality() -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    replayer = AsyncMock()
    replayer.reprocess_transactions_by_ids.return_value = 2
    adapter = SqlAlchemyBookedTransactionReplayAdapter(
        session_factory=MagicMock(return_value=session),
        replayer_factory=MagicMock(return_value=replayer),
    )

    with pytest.raises(BookedTransactionReplayInvariantViolation, match="zero or one record"):
        await adapter.replay_booked_transaction(
            transaction_id="TXN-REPLAY-DUPLICATE",
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_replay_adapter_forwards_stable_repair_delivery_identity() -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    replayer = AsyncMock()
    replayer.reprocess_transactions_by_ids.return_value = 1
    adapter = SqlAlchemyBookedTransactionReplayAdapter(
        session_factory=MagicMock(return_value=session),
        replayer_factory=MagicMock(return_value=replayer),
    )

    replayed = await adapter.replay_booked_transaction(
        transaction_id="TXN-REPLAY-01",
        correlation_id="corr-replay-01",
        repair_delivery_id="repair-command-001",
    )

    assert replayed is True
    replayer.reprocess_transactions_by_ids.assert_awaited_once_with(
        ["TXN-REPLAY-01"],
        correlation_id="corr-replay-01",
        repair_delivery_id="repair-command-001",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependency_error",
    [
        DBAPIError("SELECT", {}, RuntimeError("database unavailable")),
        ReprocessingReplayError(
            "publisher unavailable",
            failed_transaction_ids=["TXN-REPLAY-01"],
        ),
    ],
)
async def test_replay_adapter_maps_infrastructure_dependency_failures(
    dependency_error: Exception,
) -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    replayer = AsyncMock()
    replayer.reprocess_transactions_by_ids.side_effect = dependency_error
    adapter = SqlAlchemyBookedTransactionReplayAdapter(
        session_factory=MagicMock(return_value=session),
        replayer_factory=MagicMock(return_value=replayer),
    )

    with pytest.raises(BookedTransactionReplayDependencyUnavailable) as exc_info:
        await adapter.replay_booked_transaction(
            transaction_id="TXN-REPLAY-01",
            correlation_id="corr-replay-01",
        )

    assert exc_info.value.__cause__ is dependency_error


@pytest.mark.parametrize("fee_shape", ["complete", "sparse", "zero-only", "aggregate-only", "none"])
def test_qualified_fee_projection_retains_source_presence_and_aggregate(fee_shape):
    original, canonical, costs, raw = _fee_source_fixture(fee_shape)
    fees = qualify_transaction_fee_source(canonical, costs, [raw])
    assert fees == {name: getattr(original, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS} | {
        "trade_fee": original.trade_fee
    }
    restored = TransactionEvent.model_validate(
        {key: value for key, value in canonical.items() if key in TransactionEvent.model_fields}
        | fees
    )
    assert restored.trade_fee == original.trade_fee


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "currency",
        "amount",
        "duplicate",
        "tenant",
        "portfolio",
        "transaction",
        "raw-fee",
        "ambiguous",
    ],
)
def test_qualified_fee_projection_refuses_lost_or_conflicting_authority(damage):
    original, canonical, costs, raw = _fee_source_fixture("sparse")
    sources = [raw]
    if damage == "missing":
        sources = []
    elif damage == "currency":
        costs[0]["currency"] = "SGD"
    elif damage == "amount":
        costs[0]["amount"] = Decimal("2")
    elif damage == "duplicate":
        costs.append(dict(costs[0]))
    elif damage == "tenant":
        raw["payload"]["tenant_id"] = "other-tenant"
    elif damage == "portfolio":
        raw["aggregate_id"] = "other-portfolio"
    elif damage == "transaction":
        raw["payload"]["transaction_id"] = "other-source"
    elif damage == "raw-fee":
        raw["payload"]["brokerage"] = "2"
    elif damage == "ambiguous":
        sources.append(
            {
                "aggregate_id": raw["aggregate_id"],
                "payload": raw["payload"]
                | {
                    "brokerage": "2",
                    "trade_fee": "2",
                },
            }
        )
    with pytest.raises(ValueError):
        qualify_transaction_fee_source(canonical, costs, sources)


@pytest.mark.parametrize("derived", [False, True])
@pytest.mark.parametrize("presence", range(32))
def test_raw_authority_preserves_every_zero_presence_with_canonical_validation(
    monkeypatch, presence, derived
):
    fields = {
        name: Decimal(0) if presence & (1 << index) else None
        for index, name in enumerate(TRANSACTION_FEE_COMPONENT_FIELDS)
    }
    original = TransactionEvent.model_validate(vars(_replay_transaction("TXN")) | fields)
    payload = original.model_dump(mode="python")
    canonical = {
        key: value for key, value in payload.items() if key not in TRANSACTION_FEE_COMPONENT_FIELDS
    } | {"payload_fingerprint": transaction_payload_fingerprint(payload)}
    raw = {"aggregate_id": original.portfolio_id, "payload": original.model_dump(mode="json")}
    validate = MagicMock(wraps=TransactionEvent.model_validate)
    fingerprint = MagicMock(wraps=transaction_payload_fingerprint)
    hypotheses = MagicMock(wraps=fee_authority._fee_presence_hypotheses)
    monkeypatch.setattr(fee_authority, "TransactionEvent", SimpleNamespace(model_validate=validate))
    monkeypatch.setattr(fee_authority, "transaction_payload_fingerprint", fingerprint)
    monkeypatch.setattr(fee_authority, "_fee_presence_hypotheses", hypotheses)

    projected = qualify_transaction_fee_source(canonical, [], [raw], derived_financial=derived)

    assert projected == fields | {"trade_fee": original.trade_fee}
    assert validate.call_count == 3
    assert fingerprint.call_count == 3
    assert hypotheses.call_count == 0


@pytest.mark.parametrize("derived", [False, True])
@pytest.mark.parametrize("shape", ["complete", "sparse", "zero-only", "aggregate-only", "none"])
def test_all_matching_raw_rows_preserve_fee_projection(monkeypatch, shape, derived):
    original, canonical, costs, raw = _fee_source_fixture(shape)
    hypotheses = MagicMock(wraps=fee_authority._fee_presence_hypotheses)
    monkeypatch.setattr(fee_authority, "_fee_presence_hypotheses", hypotheses)

    projected = qualify_transaction_fee_source(
        canonical, costs, [raw, raw], derived_financial=derived
    )

    assert projected == {
        name: getattr(original, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS
    } | {"trade_fee": original.trade_fee}
    assert hypotheses.call_count == 0


@pytest.mark.parametrize("derived", [False, True])
@pytest.mark.parametrize(
    "damage", ["aggregate", "tenant", "transaction", "portfolio", "fee", "malformed", "missing"]
)
def test_matching_first_raw_row_never_hides_later_bad_authority(damage, derived):
    _original, canonical, costs, raw = _fee_source_fixture("sparse")
    later = raw | {"payload": dict(raw["payload"])}
    if damage == "aggregate":
        later["aggregate_id"] = "foreign"
    elif damage == "missing":
        later.pop("payload")
    else:
        field, value = {
            "tenant": ("tenant_id", "foreign"),
            "transaction": ("transaction_id", "foreign"),
            "portfolio": ("portfolio_id", "foreign"),
            "fee": ("brokerage", "2"),
            "malformed": ("gross_transaction_amount", "not-a-number"),
        }[damage]
        later["payload"][field] = value
    with pytest.raises((ValueError, KeyError)):
        qualify_transaction_fee_source(canonical, costs, [raw, later], derived_financial=derived)


@pytest.mark.parametrize("derived,models,hashes", [(False, 2, 2), (True, 32, 32)])
def test_absent_raw_authority_keeps_exhaustive_fallback(monkeypatch, derived, models, hashes):
    original, canonical, costs, _raw = _fee_source_fixture("none")
    validate = MagicMock(wraps=TransactionEvent.model_validate)
    fingerprint = MagicMock(wraps=transaction_payload_fingerprint)
    monkeypatch.setattr(fee_authority, "TransactionEvent", SimpleNamespace(model_validate=validate))
    monkeypatch.setattr(fee_authority, "transaction_payload_fingerprint", fingerprint)

    projected = qualify_transaction_fee_source(canonical, costs, [], derived_financial=derived)

    assert projected == dict.fromkeys(TRANSACTION_FEE_COMPONENT_FIELDS) | {
        "trade_fee": original.trade_fee
    }
    assert validate.call_count == models
    assert fingerprint.call_count == hashes


def test_all_raw_rows_still_require_one_unique_projection(monkeypatch):
    _original, canonical, costs, raw = _fee_source_fixture("none")
    later = raw | {"payload": raw["payload"] | {"gst": "0"}}
    # A substituted oracle exercises the ambiguity guard, not a real hash collision.
    monkeypatch.setattr(
        fee_authority,
        "transaction_payload_fingerprint",
        lambda _payload: canonical["payload_fingerprint"],
    )
    with pytest.raises(ValueError, match="Ambiguous original named fee presence"):
        qualify_transaction_fee_source(canonical, costs, [raw, later], derived_financial=True)


def _fee_source_fixture(shape):
    fields = {
        "complete": dict.fromkeys(TRANSACTION_FEE_COMPONENT_FIELDS, Decimal("0"))
        | {"brokerage": Decimal("1")},
        "sparse": {"brokerage": Decimal("1")},
        "zero-only": {"brokerage": Decimal("0")},
        "aggregate-only": {"trade_fee": Decimal("1")},
        "none": {},
    }[shape]
    original = TransactionEvent.model_validate(vars(_replay_transaction("TXN")) | fields)
    payload = original.model_dump(mode="python")
    canonical = {
        key: value for key, value in payload.items() if key not in TRANSACTION_FEE_COMPONENT_FIELDS
    }
    canonical["payload_fingerprint"] = transaction_payload_fingerprint(payload)
    costs = [
        {
            "transaction_id": original.transaction_id,
            "fee_type": name,
            "amount": getattr(original, name),
            "currency": "USD",
        }
        for name in TRANSACTION_FEE_COMPONENT_FIELDS
        if getattr(original, name) is not None and getattr(original, name) > 0
    ]
    raw = {
        "aggregate_id": original.portfolio_id,
        "payload": original.model_dump(mode="json", exclude={"tenant_id"}),
    }
    return original, canonical, costs, raw


@pytest.mark.parametrize("shape", ["complete", "sparse", "zero-only", "aggregate-only", "none"])
def test_derived_financial_presence_requires_exact_original_hash_with_stale_aggregate(shape):
    original, canonical, costs, _raw = _fee_source_fixture(shape)
    canonical["trade_fee"] = Decimal("99")
    if shape in {"none", "aggregate-only"}:
        # No named authority authorizes replacement of an independently booked aggregate.
        with pytest.raises(ValueError):
            qualify_transaction_fee_source(canonical, costs, [], derived_financial=True)
        return
    fees = qualify_transaction_fee_source(canonical, costs, [], derived_financial=True)
    assert fees == {name: getattr(original, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS} | {
        "trade_fee": original.trade_fee
    }
    assert canonical["trade_fee"] == Decimal("99")
    for damage in ("payload_fingerprint", "gross_transaction_amount", "portfolio_id"):
        corrupted = dict(canonical)
        corrupted[damage] = Decimal("999") if damage == "gross_transaction_amount" else "foreign"
        with pytest.raises(ValueError):
            qualify_transaction_fee_source(corrupted, costs, [], derived_financial=True)


@pytest.mark.parametrize("damage", ["tenant", "portfolio", "transaction"])
def test_derived_presence_refuses_foreign_retained_raw_authority(damage):
    _original, canonical, costs, raw = _fee_source_fixture("sparse")
    canonical["trade_fee"] = Decimal("99")
    if damage == "portfolio":
        raw["aggregate_id"] = "foreign"
    else:
        raw["payload"]["tenant_id" if damage == "tenant" else "transaction_id"] = "foreign"
    with pytest.raises(ValueError):
        qualify_transaction_fee_source(canonical, costs, [raw], derived_financial=True)


@pytest.mark.parametrize(
    "damage",
    [None, "tenant_id", "portfolio_id", "service_name", "semantic_key", "payload_fingerprint"],
)
def test_derived_presence_requires_independent_exact_scoped_material_receipt(damage):
    original, canonical, costs, receipt = _retained_fee_fixture(
        {"brokerage": Decimal("1"), "gst": Decimal("0")}
    )
    canonical["trade_fee"] = Decimal("99")
    if damage is not None:
        receipt[damage] = "foreign"
        with pytest.raises(ValueError):
            qualify_transaction_fee_source(
                canonical,
                costs,
                [],
                [receipt],
                allow_retained_receipt=True,
                derived_financial=True,
            )
    else:
        fees = qualify_transaction_fee_source(
            canonical, costs, [], [receipt], allow_retained_receipt=True, derived_financial=True
        )
        assert fees == {
            name: getattr(original, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS
        } | {"trade_fee": original.trade_fee}


def test_aggregate_engine_allocation_never_becomes_original_named_brokerage():
    original, canonical, costs, raw = _fee_source_fixture("aggregate-only")
    costs.append(
        {
            "transaction_id": "TXN",
            "fee_type": "brokerage",
            "amount": Decimal("1"),
            "currency": "USD",
        }
    )
    projected = qualify_transaction_fee_source(canonical, costs, [raw])
    assert all(projected[name] is None for name in TRANSACTION_FEE_COMPONENT_FIELDS)
    costs[0]["amount"] = Decimal("2")
    with pytest.raises(ValueError):
        qualify_transaction_fee_source(canonical, costs, [raw])


def _replay_transaction(transaction_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        transaction_id=transaction_id,
        portfolio_id="P1",
        tenant_id="tenant-test",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime(2026, 3, 11, tzinfo=UTC),
        transaction_type="BUY",
        quantity=Decimal(10),
        price=Decimal(100),
        gross_transaction_amount=Decimal(1000),
        currency="USD",
        trade_currency="USD",
        trade_fee=Decimal(0),
    )


def _retained_fee_fixture(fields=None, *, source_fx=False, epoch=None):
    original = TransactionEvent.model_validate(
        vars(_replay_transaction("TXN"))
        | (fields or {})
        | {"epoch": epoch}
        | (
            {"transaction_fx_rate_origin": "SOURCE_BOOKED", "transaction_fx_rate": Decimal("1.3")}
            if source_fx
            else {}
        )
    )
    identity = build_transaction_semantic_identity(to_booked_transaction(original))
    receipt = {
        "tenant_id": original.tenant_id,
        "portfolio_id": original.portfolio_id,
        "service_name": "portfolio-transaction-processing",
        "semantic_key": identity.semantic_key,
        "payload_fingerprint": identity.payload_fingerprint,
    }
    canonical = {
        key: value
        for key, value in original.model_dump(mode="python").items()
        if key not in TRANSACTION_FEE_COMPONENT_FIELDS
    }
    canonical.update(
        payload_fingerprint=transaction_payload_fingerprint(original.model_dump(mode="python")),
        economic_event_id="EVT-BUY-P1-TXN",
        linked_transaction_group_id="LTG-BUY-P1-TXN",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        net_cost=Decimal("1000"),
        gross_cost=Decimal("1000"),
    )
    if not source_fx:
        canonical.update(
            transaction_fx_rate_origin="REFERENCE_DERIVED", transaction_fx_rate=Decimal("1.2")
        )
    costs = [
        {
            "transaction_id": "TXN",
            "fee_type": name,
            "amount": getattr(original, name),
            "currency": "USD",
        }
        for name in TRANSACTION_FEE_COMPONENT_FIELDS
        if getattr(original, name) is not None and getattr(original, name) > 0
    ]
    if (
        all(getattr(original, name) is None for name in TRANSACTION_FEE_COMPONENT_FIELDS)
        and original.trade_fee
    ):
        costs.append(
            {
                "transaction_id": "TXN",
                "fee_type": "brokerage",
                "amount": original.trade_fee,
                "currency": "USD",
            }
        )
    return original, canonical, costs, receipt


def _corrected_fee_fixture(*, source_fx=False, fields=None):
    original, canonical, costs, ordinary = _retained_fee_fixture(
        fields, source_fx=source_fx, epoch=0
    )
    changed_date = datetime(2026, 3, 12, tzinfo=UTC)
    corrected = original.model_copy(update={"transaction_date": changed_date})
    canonical["transaction_date"] = changed_date
    identity = build_transaction_correction_identity(to_booked_transaction(corrected))
    correction = ordinary | {
        "semantic_key": identity.semantic_key,
        "payload_fingerprint": identity.payload_fingerprint,
    }
    return original, corrected, canonical, costs, ordinary, correction


@pytest.mark.parametrize("source_fx", [False, True])
@pytest.mark.parametrize(
    "fields", [{}, {"gst": Decimal(0)}, {"brokerage": Decimal(1)}, {"trade_fee": Decimal(1)}]
)
def test_historical_derived_cut_requires_exact_committed_correction(source_fx, fields):
    original, corrected, canonical, costs, ordinary, correction = _corrected_fee_fixture(
        source_fx=source_fx, fields=fields
    )
    original_hash = canonical["payload_fingerprint"]
    ordinary_copy = ordinary.copy()
    result = qualify_transaction_fee_source(
        canonical,
        costs,
        [],
        [ordinary, correction],
        allow_retained_receipt=True,
        derived_financial=True,
    )
    assert result == {
        name: getattr(corrected, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS
    } | {"trade_fee": corrected.trade_fee}
    assert canonical["payload_fingerprint"] == original_hash
    assert ordinary == ordinary_copy
    assert original.transaction_date != corrected.transaction_date


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "tenant",
        "service",
        "portfolio",
        "key",
        "epoch",
        "version",
        "fingerprint",
        "date",
        "quantity",
        "fee",
        "source-fx",
        "source-origin",
        "duplicate",
        "ambiguous",
        "ordinary-only",
        "no-ordinary",
        "default",
        "not-derived",
        "unclaimed",
        "raw-conflict",
    ],
)
def test_historical_correction_cannot_widen_original_or_unrelated_authority(damage):
    _, corrected, canonical, costs, ordinary, correction = _corrected_fee_fixture(source_fx=True)
    receipts = [ordinary, correction]
    raw = []
    if damage in {"missing", "ordinary-only"}:
        receipts = [ordinary]
    elif damage == "no-ordinary":
        receipts = [correction]
    elif damage in {"tenant", "service", "portfolio"}:
        field = {"tenant": "tenant_id", "service": "service_name", "portfolio": "portfolio_id"}[
            damage
        ]
        correction[field] = "foreign"
    elif damage == "key":
        correction["semantic_key"] = correction["semantic_key"].replace(":TXN:", ":OTHER:")
    elif damage == "epoch":
        correction["semantic_key"] = correction["semantic_key"].replace(":0:sha256:", ":1:sha256:")
    elif damage == "version":
        identity = build_transaction_correction_identity(to_booked_transaction(corrected))
        correction.update(
            semantic_key=identity.legacy_semantic_key,
            payload_fingerprint=identity.legacy_payload_fingerprint,
        )
    elif damage == "fingerprint":
        correction["payload_fingerprint"] = "sha256:" + "f" * 64
    elif damage == "date":
        canonical["transaction_date"] = datetime(2026, 3, 13, tzinfo=UTC)
    elif damage == "quantity":
        canonical["quantity"] += 1
    elif damage == "fee":
        costs.append(
            {
                "transaction_id": "TXN",
                "fee_type": "brokerage",
                "amount": Decimal(1),
                "currency": "USD",
            }
        )
    elif damage == "source-fx":
        canonical["transaction_fx_rate"] = Decimal("1.5")
    elif damage == "source-origin":
        canonical["transaction_fx_rate_origin"] = "REFERENCE_DERIVED"
    elif damage == "duplicate":
        receipts.append(correction.copy())
    elif damage == "ambiguous":
        alternative = corrected.model_copy(update={"gst": Decimal(0)})
        identity = build_transaction_correction_identity(to_booked_transaction(alternative))
        receipts.append(
            correction
            | {
                "semantic_key": identity.semantic_key,
                "payload_fingerprint": identity.payload_fingerprint,
            }
        )
    elif damage == "raw-conflict":
        raw = [
            {
                "aggregate_id": canonical["portfolio_id"],
                "payload": corrected.model_dump(mode="python"),
            }
        ]
    with pytest.raises(ValueError):
        qualify_transaction_fee_source(
            canonical,
            costs,
            raw,
            receipts,
            allow_retained_receipt=damage not in {"default", "unclaimed"},
            derived_financial=damage != "not-derived",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("row_count", [2, 5])
async def test_exact_correction_receipts_use_one_constant_extra_batch(row_count):
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_source_repository as module,
    )

    rows, ordinary_receipts, corrections = [], [], []
    for index in range(row_count):
        _, corrected, canonical, _, ordinary, correction = _corrected_fee_fixture()
        transaction_id = f"TXN-{index}"
        changed = corrected.model_copy(update={"transaction_id": transaction_id})
        correction_identity = build_transaction_correction_identity(to_booked_transaction(changed))
        rows.append(
            canonical
            | {
                "transaction_id": transaction_id,
                "economic_event_id": None,
                "linked_transaction_group_id": None,
            }
        )
        ordinary_receipts.append(
            ordinary | {"semantic_key": f"transaction-processing:v1:P1:{transaction_id}:0"}
        )
        corrections.append(
            correction
            | {
                "semantic_key": correction_identity.semantic_key,
                "payload_fingerprint": correction_identity.payload_fingerprint,
            }
        )
    session = AsyncMock()
    results = []
    for values in ([], [], ordinary_receipts, corrections):
        result = MagicMock()
        result.mappings.return_value.all.return_value = values
        results.append(result)
    session.execute.side_effect = results
    projected = await module.load_qualified_transaction_fee_sources(
        session, rows, lock_sources=True, allow_retained_receipt=True, derived_financial=True
    )
    assert set(projected) == {f"TXN-{index}" for index in range(row_count)}
    statements = [call.args[0] for call in session.execute.await_args_list]
    assert len(statements) == 4  # fees, raw, ordinary receipts, exact correction receipts
    assert "FOR UPDATE" in str(statements[-1])
    parameters = statements[-1].compile().params.values()
    for correction in corrections:
        assert correction["semantic_key"] in parameters
    assert not any("%" in str(value) for value in parameters)


@pytest.mark.parametrize("presence_mask", range(32))
def test_retained_receipt_recovers_every_named_zero_presence_without_defaults(presence_mask):
    fields = {
        name: Decimal(0)
        for index, name in enumerate(TRANSACTION_FEE_COMPONENT_FIELDS)
        if presence_mask & (1 << index)
    }
    original, canonical, costs, receipt = _retained_fee_fixture(fields)
    projected = qualify_transaction_fee_source(
        canonical, costs, [], [receipt], allow_retained_receipt=True
    )
    assert projected == {
        name: getattr(original, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS
    } | {"trade_fee": original.trade_fee}


@pytest.mark.parametrize("shape", ["complete", "sparse", "aggregate-only", "no-fee"])
def test_retained_receipt_preserves_positive_amounts_and_aggregate_representation(shape):
    fields = {
        "complete": dict.fromkeys(TRANSACTION_FEE_COMPONENT_FIELDS, Decimal(0))
        | {"brokerage": Decimal(1)},
        "sparse": {"brokerage": Decimal(1), "gst": Decimal(0)},
        "aggregate-only": {"trade_fee": Decimal(1)},
        "no-fee": {},
    }[shape]
    original, canonical, costs, receipt = _retained_fee_fixture(fields)
    projected = qualify_transaction_fee_source(
        canonical, costs, [], [receipt], allow_retained_receipt=True
    )
    assert projected == {
        name: getattr(original, name) for name in TRANSACTION_FEE_COMPONENT_FIELDS
    } | {"trade_fee": original.trade_fee}


@pytest.mark.parametrize("original_aggregate", [None, Decimal(0)])
def test_retained_receipt_uniquely_qualifies_aggregate_none_zero_hypothesis(original_aggregate):
    original, canonical, costs, receipt = _retained_fee_fixture({"trade_fee": original_aggregate})
    canonical["trade_fee"] = Decimal(0)
    projected = qualify_transaction_fee_source(
        canonical, costs, [], [receipt], allow_retained_receipt=True
    )
    assert (
        projected["trade_fee"] is None
        if original_aggregate is None
        else projected["trade_fee"] == 0
    )
    assert all(projected[name] is None for name in TRANSACTION_FEE_COMPONENT_FIELDS)


@pytest.mark.parametrize(
    "damage",
    [
        "amount",
        "quantity",
        "date",
        "source-system",
        "custom-id",
        "tenant",
        "portfolio",
        "service",
        "epoch",
        "physical-only",
        "correction",
        "missing",
        "conflict",
        "positive-loss",
        "aggregate-conflict",
        "uncommitted-first-claim",
    ],
)
def test_retained_receipt_does_not_authorize_changed_source_or_unrelated_claim(damage):
    original, canonical, costs, receipt = _retained_fee_fixture({"brokerage": Decimal(1)})
    receipts = [receipt]
    if damage == "amount":
        canonical["gross_transaction_amount"] += 1
    elif damage == "quantity":
        canonical["quantity"] += 1
    elif damage == "date":
        canonical["transaction_date"] = datetime(2026, 3, 12, tzinfo=UTC)
    elif damage == "source-system":
        canonical["source_system"] = "CHANGED"
    elif damage == "custom-id":
        canonical["economic_event_id"] = "CUSTOM"
    elif damage == "tenant":
        receipt["tenant_id"] = "other"
    elif damage == "portfolio":
        receipt["portfolio_id"] = "other"
    elif damage == "service":
        receipt["service_name"] = "cashflow-calculator"
    elif damage == "epoch":
        receipt["semantic_key"] = receipt["semantic_key"][:-1] + "1"
    elif damage == "physical-only":
        receipt.update(semantic_key=None, payload_fingerprint=None)
    elif damage == "correction":
        receipt["semantic_key"] = receipt["semantic_key"].replace(
            "transaction-processing", "transaction-correction"
        )
    elif damage == "missing":
        receipts = []
    elif damage == "conflict":
        receipts.append(receipt | {"payload_fingerprint": "sha256:" + "f" * 64})
    elif damage == "positive-loss":
        costs = []
    elif damage == "aggregate-conflict":
        canonical["trade_fee"] = Decimal(2)
    with pytest.raises(ValueError):
        qualify_transaction_fee_source(
            canonical,
            costs,
            [],
            receipts,
            allow_retained_receipt=damage != "uncommitted-first-claim",
        )


def test_explicit_zero_receipt_does_not_certify_unversioned_source():
    _, canonical, costs, receipt = _retained_fee_fixture(epoch=0)
    canonical["epoch"] = None
    with pytest.raises(ValueError):
        qualify_transaction_fee_source(canonical, costs, [], [receipt], allow_retained_receipt=True)


@pytest.mark.parametrize("damage", [None, "value", "origin", "v1-only", "conflicting-v2"])
def test_retained_source_booked_fx_never_downgrades_version(damage):
    original, canonical, costs, receipt = _retained_fee_fixture(source_fx=True)
    identity = build_transaction_semantic_identity(to_booked_transaction(original))
    legacy = receipt | {
        "semantic_key": identity.legacy_semantic_key,
        "payload_fingerprint": identity.legacy_payload_fingerprint,
    }
    receipts = [receipt, legacy]
    if damage == "value":
        canonical["transaction_fx_rate"] = Decimal("1.5")
    elif damage == "origin":
        canonical["transaction_fx_rate_origin"] = "REFERENCE_DERIVED"
    elif damage == "v1-only":
        receipts = [legacy]
    elif damage == "conflicting-v2":
        receipt["payload_fingerprint"] = "sha256:" + "f" * 64
    if damage:
        with pytest.raises(ValueError):
            qualify_transaction_fee_source(
                canonical, costs, [], receipts, allow_retained_receipt=True
            )
    else:
        projected = qualify_transaction_fee_source(
            canonical, costs, [], receipts, allow_retained_receipt=True
        )
        assert all(projected[name] is None for name in TRANSACTION_FEE_COMPONENT_FIELDS)


@pytest.mark.asyncio
async def test_source_batch_queries_each_fact_family_once_and_qualifies_before_publication(
    monkeypatch,
):
    from portfolio_common.reprocessing_repository import ReprocessingRepository

    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        fee_source_repository as module,
    )

    _, first, _, first_receipt = _retained_fee_fixture()
    _, second, _, second_receipt = _retained_fee_fixture({"gst": Decimal(0)})
    second = second | {
        "transaction_id": "TXN2",
        "economic_event_id": "EVT-BUY-P1-TXN2",
        "linked_transaction_group_id": "LTG-BUY-P1-TXN2",
    }
    original_second = TransactionEvent.model_validate(
        vars(_replay_transaction("TXN2")) | {"gst": Decimal(0)}
    )
    second_identity = build_transaction_semantic_identity(to_booked_transaction(original_second))
    second_receipt = second_receipt | {
        "semantic_key": second_identity.semantic_key,
        "payload_fingerprint": second_identity.payload_fingerprint,
    }
    session = AsyncMock()
    result_sets = []
    for rows in ([], [], [first_receipt, second_receipt]):
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        result_sets.append(result)
    session.execute.side_effect = result_sets
    projected = await module.load_qualified_transaction_fee_sources(
        session, [first, second], lock_sources=True, allow_retained_receipt=True
    )
    assert set(projected) == {"TXN", "TXN2"}
    assert projected["TXN"]["gst"] is None and projected["TXN2"]["gst"] == 0
    statements = [str(call.args[0]) for call in session.execute.await_args_list]
    assert len(statements) == 3
    assert sum("transaction_costs" in stmt for stmt in statements) == 1
    assert sum("outbox_events" in stmt for stmt in statements) == 1
    assert sum("processed_events" in stmt for stmt in statements) == 1
    # The repository owns fee facts; the reader/publication seam belongs to transport.
    from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_replay import (  # noqa: E501
        booked_transaction as transport,
    )

    # A corrupt second member rejects the complete source batch before Kafka publication.
    session.execute.side_effect = result_sets
    second_receipt["payload_fingerprint"] = "sha256:" + "f" * 64
    monkeypatch.setattr(
        transport, "load_transaction_replay_rows", AsyncMock(return_value=[first, second])
    )
    publisher = MagicMock()
    replayer = ReprocessingRepository.from_ports(
        reader=transport.SqlAlchemyQualifiedTransactionReplayReader(session), publisher=publisher
    )
    with pytest.raises(ReprocessingReplayError) as failure:
        await replayer.reprocess_transactions_by_ids(["TXN", "TXN2"])
    assert failure.value.failed_transaction_ids == ["TXN2"]
    publisher.publish_replay_message.assert_not_called()


@pytest.mark.parametrize("derived", [False, True])
@pytest.mark.parametrize("later_bad", [False, True])
@pytest.mark.parametrize(
    "fault",
    [
        "currency",
        "trade_currency",
        "quantity",
        "price",
        "gross",
        "date",
        "precision",
        "fx",
        "interest-net",
        "interest-deductions",
        "redemption",
    ],
)
def test_valid_raw_authority_cannot_bypass_canonical_model_refusal(derived, later_bad, fault):
    from portfolio_common.domain.transaction.type_registry import (
        production_transaction_types_for_lifecycle_families,
    )
    from pydantic import ValidationError

    _original, canonical, costs, raw = _fee_source_fixture("sparse")
    if fault in {"currency", "trade_currency"}:
        canonical.pop(fault)
    elif fault in {"quantity", "price", "gross"}:
        canonical["gross_transaction_amount" if fault == "gross" else fault] = Decimal(-1)
    elif fault == "date":
        canonical["transaction_date"] = "not-a-date"
    elif fault == "precision":
        canonical["quantity"] = Decimal("1.0000000000000000000000000001")
    elif fault == "fx":
        canonical["transaction_fx_rate"] = Decimal(0)
    elif fault == "interest-net":
        canonical.update(transaction_type="INTEREST", net_interest_amount=Decimal(-1))
    elif fault == "interest-deductions":
        canonical.update(
            transaction_type="INTEREST",
            gross_transaction_amount=Decimal(1),
            withholding_tax_amount=Decimal(2),
        )
    else:
        canonical.update(
            transaction_type=sorted(
                production_transaction_types_for_lifecycle_families("redemption")
            )[0],
            settlement_date=None,
        )
    sources = [raw]
    if later_bad:
        sources.append(
            {"aggregate_id": "foreign"}
        )  # Missing payload must not mask earlier canonical failure.
    with pytest.raises(ValidationError):
        qualify_transaction_fee_source(canonical, costs, sources, derived_financial=derived)


def test_missing_canonical_identity_precedes_later_bad_raw():
    _original, canonical, costs, raw = _fee_source_fixture("sparse")
    canonical.pop("transaction_id")
    with pytest.raises(KeyError, match="transaction_id"):
        qualify_transaction_fee_source(canonical, costs, [raw, {"aggregate_id": "foreign"}])
