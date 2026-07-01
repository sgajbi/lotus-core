from pathlib import Path

from scripts import ingestion_gateway_rate_limit_policy_guard as guard


def test_gateway_rate_limit_policy_guard_accepts_current_truth() -> None:
    assert guard.evaluate_gateway_rate_limit_policy() == []


def test_gateway_rate_limit_policy_guard_rejects_missing_endpoint() -> None:
    policy = guard._load_policy()
    router_endpoints = set(policy["required_endpoint_templates"])
    policy["required_endpoint_templates"] = [
        endpoint
        for endpoint in policy["required_endpoint_templates"]
        if endpoint != "/ingest/transactions"
    ]

    findings = guard.evaluate_gateway_rate_limit_policy(
        policy=policy,
        router_endpoints=router_endpoints,
        required_phrases={},
    )

    assert findings == [
        {"endpoints": ["policy missing router endpoint templates: ['/ingest/transactions']"]}
    ]


def test_gateway_rate_limit_policy_guard_rejects_missing_docs_anchor(tmp_path: Path) -> None:
    doc_path = tmp_path / "docs" / "operations"
    doc_path.mkdir(parents=True)
    (doc_path / "ingestion-api-gold-standard.md").write_text(
        "Scaled deployments need gateway enforcement.\n",
        encoding="utf-8",
    )

    findings = guard.evaluate_gateway_rate_limit_policy(
        router_endpoints=set(guard._load_policy()["required_endpoint_templates"]),
        repo_root=tmp_path,
        required_phrases={
            "docs/operations/ingestion-api-gold-standard.md": (
                "lotus-core-ingestion-write-global-v1",
            )
        },
    )

    assert findings == [
        {
            "file": "docs/operations/ingestion-api-gold-standard.md",
            "missing_phrases": ["lotus-core-ingestion-write-global-v1"],
        }
    ]
