"""Typed registry authority never widens old grants or mistakes page limits for scale."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from portfolio_common.domain.portfolio_financial_source_cuts import (
    EffectiveDeclaration,
    HistoricalRegistryMember,
    SourceCutIdentity,
)
from portfolio_common.portfolio_financial_source_chunk_admission import retained_chunk_commitment
from portfolio_common.portfolio_financial_source_cut_admission import (
    closed_source_json,
    parse_registry_source_grants,
    registry_member_root,
    require_chunk_budget,
    require_exact_replay,
    require_registry_source_grant,
)

pytestmark = pytest.mark.unit


# Frozen before boundary extraction against the original signed application verifier.
RETAINED_CHUNK_VECTORS = json.loads(r"""
{
  "boundary": "Synthetic decoder/hash preservation only; original signed3db verifier accepted both",
  "vectors": [
    {
      "kind": "registry",
      "count": 1,
      "typed_hash": "cd6fe15101d25cd74353a30d0c28f07e60789a5c1d5110e9e737ea3dcbca2aa2",
      "raw_hash": "68a48427e424646f5aa82b9eef4240518269158d8f912762c13a8970951bfa90",
      "body": {
        "source_system": "producer",
        "registry_scope_id": "scope",
        "source_cut_id": "cut",
        "revision": 1,
        "chunk_index": 0,
        "typed_content_hash": "cd6fe15101d25cd74353a30d0c28f07e60789a5c1d5110e9e737ea3dcbca2aa2",
        "members": [
          {
            "source_member_id": "member",
            "provider_namespace": "provider",
            "core_portfolio_id": null,
            "member_revision": 1,
            "declarations": [
              {
                "effective_from": "2025-01-01",
                "effective_to": null,
                "definition_version": "v1",
                "provenance_reference": "issued",
                "currency": "USD",
                "discretionary": null,
                "included": false
              }
            ]
          }
        ]
      }
    },
    {
      "kind": "financial",
      "count": 1,
      "typed_hash": "e42014c5a11ae2562c6c2910e930012a14bcf6369d2b18dbc2e52ff9216e015f",
      "raw_hash": "53c2316255ad8c0df06ba0b1dcf039ab578141e54cc05a97c0c314f79320aa22",
      "body": {
        "source_system": "producer",
        "registry_scope_id": "scope",
        "source_cut_id": "cut",
        "revision": 1,
        "chunk_index": 0,
        "typed_content_hash": "e42014c5a11ae2562c6c2910e930012a14bcf6369d2b18dbc2e52ff9216e015f",
        "selections": [
          {
            "portfolio_id": "portfolio",
            "currency": "USD",
            "prior_date": "2024-12-31",
            "month_end_date": "2025-01-31",
            "registry_root": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "member_revision": 1,
            "selections": [
              {
                "role": "PRIOR_ASSETS",
                "product_name": "PortfolioTimeseriesInput",
                "product_version": "v1",
                "selector": {
                  "kind": "VALUATION",
                  "as_of_date": "2025-01-31",
                  "from_date": "2024-12-31",
                  "to_date": "2025-01-31",
                  "reporting_currency": "USD",
                  "consumer_system": "lotus-manage",
                  "export_job_id": null,
                  "export_content_hash": null,
                  "refresh_of_job_id": null
                },
                "selector_hash": "a9b1e1c9a930845fd0ed46c695b85fda4dad7476c1fb8f292814866875550fef",
                "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "receipt_job_id": "receipt",
                "source_revision": "1"
              },
              {
                "role": "MONTH_END_ASSETS",
                "product_name": "PortfolioTimeseriesInput",
                "product_version": "v1",
                "selector": {
                  "kind": "VALUATION",
                  "as_of_date": "2025-01-31",
                  "from_date": "2024-12-31",
                  "to_date": "2025-01-31",
                  "reporting_currency": "USD",
                  "consumer_system": "lotus-manage",
                  "export_job_id": null,
                  "export_content_hash": null,
                  "refresh_of_job_id": null
                },
                "selector_hash": "a9b1e1c9a930845fd0ed46c695b85fda4dad7476c1fb8f292814866875550fef",
                "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "receipt_job_id": "receipt",
                "source_revision": "1"
              },
              {
                "role": "CASH",
                "product_name": "PortfolioFinancialSourceObservations",
                "product_version": "v1",
                "selector": {
                  "kind": "CASH",
                  "as_of_date": "2025-01-31",
                  "producer_id": "producer",
                  "source_record_id": "record",
                  "observation_id":
                  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "content_hash":
                  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "source_cut_id": "native-cut",
                  "source_version": 1
                },
                "selector_hash": "81c10a98370d696b1d083b7dcb3e340406c1aa00051b0e736089e33cf523be92",
                "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "receipt_job_id": "receipt",
                "source_revision": "1"
              },
              {
                "role": "READINESS",
                "product_name": "PortfolioFinancialSourceObservations",
                "product_version": "v1",
                "selector": {
                  "kind": "READINESS",
                  "as_of_date": "2025-01-31",
                  "producer_id": "producer",
                  "source_record_id": "record",
                  "observation_id":
                  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "content_hash":
                  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "source_cut_id": "native-cut",
                  "source_version": 1
                },
                "selector_hash": "0a8a1ecf0a294b1804d15f3809b036269eb9ccec954fbd4cc95be1138c7ee427",
                "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "receipt_job_id": "receipt",
                "source_revision": "1"
              },
              {
                "role": "FLOWS",
                "product_name": "PortfolioFinancialFlowObservations",
                "product_version": "v1",
                "selector": {
                  "kind": "FLOWS",
                  "source_system": "producer",
                  "source_cut_id": "flow-cut",
                  "cut_revision": 1,
                  "manifest_hash":
                  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "from_date": "2025-01-01",
                  "to_date": "2025-01-31",
                  "currency": "USD"
                },
                "selector_hash": "76b50318ca27f228a16300842289be2c83379ce97069c75a2ebbc5a426276316",
                "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "receipt_job_id": "receipt",
                "source_revision": "1"
              }
            ],
            "settled_unencumbered": null,
            "compatibility": null
          }
        ]
      }
    }
  ]
}
""")["vectors"]


def retained_chunk_vector(registry):
    vector = RETAINED_CHUNK_VECTORS[0 if registry else 1]
    body = json.loads(json.dumps(vector["body"]))
    identity = SourceCutIdentity(
        "tenant",
        "producer",
        "scope",
        "cut",
        1,
        "v1",
        date(2025, 1, 1),
        date(2025, 1, 31),
        "SG",
        datetime(2025, 2, 1, tzinfo=UTC),
        datetime(2025, 2, 2, tzinfo=UTC),
        None,
        None,
    )
    return vector, body, identity


def test_retained_financial_graph_round_trip_preserves_domain_hash_and_unknowns():
    from portfolio_common.portfolio_financial_source_cut_admission import (
        financial_input_from_payload,
    )
    from portfolio_common.portfolio_financial_source_cut_decoding import (
        retained_financial_cut_from_payload,
    )
    from pydantic import TypeAdapter

    _, body, identity = retained_chunk_vector(False)
    graph = financial_input_from_payload(identity, body["selections"][0])
    wire = TypeAdapter(type(graph)).dump_python(graph, mode="json")
    restored = retained_financial_cut_from_payload(wire)
    assert restored == graph
    assert restored.content_hash == graph.content_hash
    assert restored.settled_unencumbered is None and restored.compatibility is None
    assert all("selector" not in item for item in wire["selections"])


@pytest.mark.parametrize(
    "path,bad",
    [
        (("identity", "unexpected"), True),
        (("identity", "revision"), True),
        (("identity", "revision"), "1"),
        (("identity", "observed_at"), "2025-02-01T00:00:00"),
        (("identity", "predecessor_hash"), "a" * 64),
        (("selections", 0, "unexpected"), True),
        (("selections", 0, "role"), "CASH"),
        (("member_revision",), "1"),
        (("registry_root",), "bad"),
        (("month_end_date",), "2024-01-01"),
    ],
)
def test_retained_graph_refuses_nested_extras_and_coercion(path, bad):
    from portfolio_common.portfolio_financial_source_cut_admission import (
        financial_input_from_payload,
    )
    from portfolio_common.portfolio_financial_source_cut_decoding import (
        retained_financial_cut_from_payload,
    )
    from pydantic import TypeAdapter

    _, body, identity = retained_chunk_vector(False)
    graph = financial_input_from_payload(identity, body["selections"][0])
    wire = TypeAdapter(type(graph)).dump_python(graph, mode="json")
    target = wire
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = bad
    with pytest.raises(ValueError):
        retained_financial_cut_from_payload(wire)


@pytest.mark.parametrize("registry", [True, False])
def test_retained_chunk_translation_preserves_original_raw_and_typed_golden_values(registry):
    vector, body, identity = retained_chunk_vector(registry)
    raw = json.dumps(body).encode()
    assert hashlib.sha256(raw).hexdigest() == vector["raw_hash"]
    result = retained_chunk_commitment(identity, raw, registry=registry, chunk_index=0)
    assert result == (vector["count"], vector["typed_hash"])
    assert type(result) is tuple and type(result[0]) is int and type(result[1]) is str
    # Actual raw-byte ceiling accepts its boundary; no history/population cap is inferred.
    padded = raw + b" " * (1_048_576 - len(raw))
    assert retained_chunk_commitment(identity, padded, registry=registry, chunk_index=0) == result


@pytest.mark.parametrize("registry", [True, False])
@pytest.mark.parametrize(
    "mutation",
    [
        "malformed",
        "deep",
        "utf8",
        "duplicate",
        "extra",
        "address",
        "revision_bool",
        "index_bool",
        "typed",
        "rows",
        "bytes",
        "strict_record",
    ],
)
def test_retained_chunk_translation_refuses_hostile_bytes_types_scope_and_budgets(
    registry, mutation
):
    _, body, identity = retained_chunk_vector(registry)
    collection = "members" if registry else "selections"
    if mutation == "extra":
        body["bank_approved"] = True
    elif mutation == "address":
        body["registry_scope_id"] = "foreign"
    elif mutation == "revision_bool":
        body["revision"] = True
    elif mutation == "index_bool":
        body["chunk_index"] = True
    elif mutation == "typed":
        body["typed_content_hash"] = "b" * 64
    elif mutation == "rows":
        body[collection] *= 501
    elif mutation == "strict_record":
        body[collection][0]["member_revision"] = True
    raw = json.dumps(body).encode()
    if mutation == "malformed":
        raw = b"{"
    elif mutation == "deep":
        raw = b"[" * 1500 + b"0" + b"]" * 1500
    elif mutation == "utf8":
        raw = b"\xff"
    elif mutation == "duplicate":
        raw = raw.replace(b'"revision": 1', b'"revision": 1, "revision": 1')
    elif mutation == "bytes":
        raw += b" " * (1_048_577 - len(raw))
    with pytest.raises(ValueError):
        retained_chunk_commitment(identity, raw, registry=registry, chunk_index=0)


def test_deep_json_policy_normalizes_recursion_to_existing_malformed_value_contract():
    with pytest.raises(ValueError, match="nesting"):
        closed_source_json("[" * 1500 + "0" + "]" * 1500)
    with pytest.raises(ValueError):
        parse_registry_source_grants("[" * 1500 + "0" + "]" * 1500)
    assert closed_source_json("[]") == []
    assert parse_registry_source_grants("[]") == ()


def test_empty_default_refuses_and_exact_grant_never_crosses_tenant_scope_or_product():
    scope = dict(
        tenant_id="tenant",
        source_system="producer",
        registry_scope_id="scope",
        product="PortfolioHistoricalRegistry",
    )
    with pytest.raises(PermissionError):
        require_registry_source_grant(parse_registry_source_grants("[]"), **scope)
    grants = parse_registry_source_grants(
        json.dumps(
            [
                dict(
                    tenant_id="tenant",
                    source_system="producer",
                    registry_scope_id="scope",
                    products=["PortfolioHistoricalRegistry"],
                )
            ]
        )
    )
    require_registry_source_grant(grants, **scope)
    for changes in (
        {"tenant_id": "foreign"},
        {"registry_scope_id": "other"},
        {"source_system": "foreign"},
        {"product": "PortfolioFinancialSourceCut"},
    ):
        with pytest.raises(PermissionError):
            require_registry_source_grant(grants, **(scope | changes))


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        '["tenant|producer|*|product"]',
        '[{"tenant_id":"t","source_system":"s","registry_scope_id":"*","products":["PortfolioHistoricalRegistry"]}]',
        '[{"tenant_id":"t","source_system":"s","registry_scope_id":"r","products":["PortfolioHistoricalRegistry"],"wildcard":true}]',
    ],
)
def test_registry_grant_shape_cannot_fall_back_to_existing_parser(raw):
    with pytest.raises((ValueError, TypeError)):
        parse_registry_source_grants(raw)


def test_page_budget_bounds_rows_bytes_and_exact_native_count():
    assert len(require_chunk_budget(b"a" * 1_048_576, 500)) == 64
    for raw, count in [(b"", 0), (b"a" * 1_048_577, 1), (b"a", 501), (b"a", True), (b"a", -1)]:
        with pytest.raises(ValueError):
            require_chunk_budget(raw, count)


def test_streamed_member_root_has_no_total_count_limit_but_refuses_duplicates():
    row = HistoricalRegistryMember(
        "0000",
        "provider",
        None,
        1,
        (EffectiveDeclaration(date(2025, 1, 1), None, "v1", "source", "USD", None, True),),
    )
    count, root = registry_member_root(
        replace(row, source_member_id=f"{i:04}") for i in range(1001)
    )
    assert count == 1001 and len(root) == 64
    with pytest.raises(ValueError):
        registry_member_root([row, row])
    with pytest.raises(ValueError):
        registry_member_root([replace(row, source_member_id="z"), row])


def test_replay_binds_raw_and_typed_hash_independently():
    h, other = "a" * 64, "b" * 64
    require_exact_replay(h, h, typed_hash=h, raw_hash=h)
    for typed, raw in ((other, h), (h, other)):
        with pytest.raises(ValueError):
            require_exact_replay(h, h, typed_hash=typed, raw_hash=raw)


def test_authority_and_member_roots_refuse_duck_objects_and_bypassed_constructors():
    scope = dict(
        tenant_id="tenant",
        source_system="producer",
        registry_scope_id="scope",
        product="PortfolioHistoricalRegistry",
    )
    grant = SimpleNamespace(
        tenant_id="tenant",
        source_system="producer",
        registry_scope_id="scope",
        products={"PortfolioHistoricalRegistry"},
    )
    with pytest.raises(PermissionError, match="governed"):
        require_registry_source_grant([grant], **scope)
    with pytest.raises(ValueError, match="typed"):
        registry_member_root(
            [
                SimpleNamespace(
                    provider_namespace="provider", source_member_id="member", content_hash="a" * 64
                )
            ]
        )
    row = HistoricalRegistryMember(
        "member",
        "provider",
        None,
        1,
        (EffectiveDeclaration(date(2025, 1, 1), None, "v1", "source", "USD", None, True),),
    )
    object.__setattr__(row, "member_revision", False)
    with pytest.raises(ValueError, match="revision"):
        registry_member_root([row])
