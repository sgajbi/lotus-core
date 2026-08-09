from __future__ import annotations

from copy import deepcopy

from scripts.quality.outbox_capacity_profile_guard import (
    CONTRACT_PATH,
    REPO_ROOT,
    _load_json,
    validate_outbox_capacity_contract,
)


def test_repository_outbox_capacity_profile_and_bindings_are_valid() -> None:
    contract = _load_json(REPO_ROOT / CONTRACT_PATH)

    assert validate_outbox_capacity_contract(contract, repo_root=REPO_ROOT) == []


def test_outbox_capacity_profile_rejects_claim_lease_below_delivery_fence() -> None:
    contract = deepcopy(_load_json(REPO_ROOT / CONTRACT_PATH))
    contract["profiles"]["bank_day_safe_v1"]["environment"][
        "OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS"
    ] = 125

    assert {
        "profile": "bank_day_safe_v1",
        "claim_lease_below_delivery_fence": 126,
    } in validate_outbox_capacity_contract(contract, repo_root=REPO_ROOT)


def test_outbox_capacity_profile_rejects_runtime_binding_drift() -> None:
    contract = deepcopy(_load_json(REPO_ROOT / CONTRACT_PATH))
    contract["profiles"]["bank_day_safe_v1"]["environment"]["OUTBOX_DISPATCHER_BATCH_SIZE"] = 999

    findings = validate_outbox_capacity_contract(contract, repo_root=REPO_ROOT)

    assert any(finding.get("binding") == "development" for finding in findings)
    assert any(finding.get("binding") == "production_safe_baseline" for finding in findings)
