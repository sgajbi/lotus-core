from pathlib import Path

import pytest

from scripts.quality import ingestion_gateway_rate_limit_policy_guard as guard


def test_gateway_rate_limit_policy_guard_accepts_current_truth() -> None:
    assert guard.evaluate_gateway_rate_limit_policy() == []


@pytest.mark.parametrize("templates", [None, {}, "not-a-list", [None], [123], [["nested"]]])
def test_gateway_policy_refuses_untyped_endpoint_configuration(templates) -> None:
    policy = guard._load_policy()
    policy["required_endpoint_templates"] = templates
    findings = guard.evaluate_gateway_rate_limit_policy(policy=policy, required_phrases={})
    assert findings == [{"endpoints": ["required_endpoint_templates must be a list of strings"]}]


def test_gateway_policy_refuses_duplicate_flow_template_before_set_conversion() -> None:
    policy = guard._load_policy()
    policy["required_endpoint_templates"].append("/ingest/portfolio-flow-source-cuts")
    assert guard.evaluate_gateway_rate_limit_policy(policy=policy, required_phrases={}) == [
        {"endpoints": ["required_endpoint_templates must contain unique templates"]}
    ]


def test_gateway_policy_refuses_wrong_flow_template_without_relaxing_budget() -> None:
    policy = guard._load_policy()
    policy["required_endpoint_templates"] = [
        "/ingest/portfolio-flow-source-cut" if e == "/ingest/portfolio-flow-source-cuts" else e
        for e in policy["required_endpoint_templates"]
    ]
    findings = guard.evaluate_gateway_rate_limit_policy(policy=policy, required_phrases={})
    assert findings and "missing router endpoint templates" in str(findings)
    assert "not found in routers" in str(findings)
    assert policy["rolling_window"] == guard._load_policy()["rolling_window"]


@pytest.mark.parametrize(
    "missing_endpoint",
    [
        "/ingest/transactions",
        "/ingest/transactions/{transaction_id}/source-evidence",
        "/ingest/portfolio-cash-availability-observations",
        "/ingest/portfolio-funding-investment-observations",
        "/ingest/portfolio-flow-event-observations",
        "/ingest/portfolio-flow-source-cuts",
    ],
)
def test_gateway_rate_limit_policy_guard_rejects_missing_endpoint(missing_endpoint: str) -> None:
    policy = guard._load_policy()
    router_endpoints = set(policy["required_endpoint_templates"])
    policy["required_endpoint_templates"] = [
        endpoint
        for endpoint in policy["required_endpoint_templates"]
        if endpoint != missing_endpoint
    ]

    findings = guard.evaluate_gateway_rate_limit_policy(
        policy=policy,
        router_endpoints=router_endpoints,
        required_phrases={},
    )

    assert findings == [
        {"endpoints": [f"policy missing router endpoint templates: ['{missing_endpoint}']"]}
    ]


def test_gateway_rate_limit_policy_guard_discovers_post_route_templates_and_excludes_preview(
    tmp_path: Path,
) -> None:
    router_root = tmp_path / "routers"
    router_root.mkdir()
    (router_root / "uploads.py").write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "router = APIRouter()",
                '@router.post("/ingest/uploads/preview")',
                "async def preview():",
                "    pass",
                '@router.post("/ingest/uploads/commit")',
                "async def commit():",
                "    pass",
                '@router.get("/ingest/uploads/status")',
                "async def status():",
                "    pass",
            ]
        ),
        encoding="utf-8",
    )

    assert guard._literal_write_route_templates(router_root) == {"/ingest/uploads/commit"}


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
