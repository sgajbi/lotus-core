"""Validate the RFC-0083 implementation closure ledger."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "docs" / "standards" / "rfc-0083-implementation-ledger.json"
LEDGER_SPEC_VERSION = "1.0.0"
APPLICATION = "lotus-core"
GOVERNING_RFCS = {"RFC-0082", "RFC-0083"}
EXPECTED_SLICES = set(range(12))
EXPECTED_SLICE_ARTIFACTS = {
    0: {
        "docs/architecture/RFC-0083-target-state-gap-analysis.md",
        "REPOSITORY-ENGINEERING-CONTEXT.md",
    },
    1: {
        "docs/standards/temporal-vocabulary.md",
        "docs/standards/temporal-vocabulary-allowlist.json",
        "scripts/temporal_vocabulary_guard.py",
        "tests/unit/scripts/test_temporal_vocabulary_guard.py",
    },
    2: {
        "docs/standards/route-contract-family-registry.json",
        "scripts/route_contract_family_guard.py",
        "tests/unit/scripts/test_route_contract_family_guard.py",
    },
    3: {
        "docs/architecture/RFC-0083-portfolio-reconstruction-target-model.md",
        "src/libs/portfolio-common/portfolio_common/reconstruction_identity.py",
        "tests/unit/libs/portfolio-common/test_reconstruction_identity.py",
    },
    4: {
        "docs/architecture/RFC-0083-ingestion-source-lineage-target-model.md",
        "src/libs/portfolio-common/portfolio_common/ingestion_evidence.py",
        "tests/unit/libs/portfolio-common/test_ingestion_evidence.py",
    },
    5: {
        "docs/architecture/RFC-0083-reconciliation-data-quality-target-model.md",
        "src/libs/portfolio-common/portfolio_common/reconciliation_quality.py",
        "tests/unit/libs/portfolio-common/test_reconciliation_quality.py",
    },
    6: {
        "docs/architecture/RFC-0083-source-data-product-catalog.md",
        "src/libs/portfolio-common/portfolio_common/source_data_products.py",
        "tests/unit/libs/portfolio-common/test_source_data_products.py",
        "scripts/analytics_input_consumer_contract_guard.py",
        "scripts/source_data_product_contract_guard.py",
        "tests/unit/scripts/test_analytics_input_consumer_contract_guard.py",
        "tests/unit/scripts/test_source_data_product_contract_guard.py",
    },
    7: {
        "docs/architecture/RFC-0083-market-reference-data-target-model.md",
        "src/libs/portfolio-common/portfolio_common/market_reference_quality.py",
        "tests/unit/libs/portfolio-common/test_market_reference_quality.py",
    },
    8: {
        "docs/architecture/RFC-0083-endpoint-consolidation-disposition.md",
        "src/services/query_service/app/routers/reporting.py",
        "tests/integration/services/query_service/test_main_app.py",
    },
    9: {
        "docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md",
        "src/libs/portfolio-common/portfolio_common/source_data_security.py",
        "tests/unit/libs/portfolio-common/test_source_data_security.py",
        "src/libs/portfolio-common/portfolio_common/enterprise_readiness.py",
        "tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py",
        "src/services/query_service/app/enterprise_readiness.py",
        "src/services/query_service/app/settings.py",
        "tests/unit/services/query_service/test_enterprise_readiness.py",
        "tests/unit/services/query_service/test_settings.py",
        "src/services/query_control_plane_service/app/enterprise_readiness.py",
        "src/services/query_control_plane_service/app/settings.py",
        "tests/unit/services/query_control_plane_service/test_control_plane_enterprise_readiness.py",
        "tests/unit/services/query_control_plane_service/test_control_plane_settings.py",
    },
    10: {
        "docs/architecture/RFC-0083-eventing-supportability-target-model.md",
        "src/libs/portfolio-common/portfolio_common/event_supportability.py",
        "src/libs/portfolio-common/portfolio_common/events.py",
        "tests/unit/libs/portfolio-common/test_event_supportability.py",
        "scripts/event_runtime_contract_guard.py",
        "tests/unit/scripts/test_event_runtime_contract_guard.py",
        "src/libs/portfolio-common/portfolio_common/outbox_repository.py",
        "tests/unit/libs/portfolio-common/test_outbox_repository.py",
    },
    11: {
        "docs/architecture/RFC-0083-production-readiness-closure.md",
        "docs/standards/rfc-0083-implementation-ledger.json",
        "scripts/rfc0083_closure_guard.py",
        "tests/unit/scripts/test_rfc0083_closure_guard.py",
    },
}


def load_ledger(path: Path = LEDGER_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_ledger(payload: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    if payload.get("specVersion") != LEDGER_SPEC_VERSION:
        errors.append(f"ledger specVersion must be {LEDGER_SPEC_VERSION!r}")
    if payload.get("application") != APPLICATION:
        errors.append(f"ledger application must be {APPLICATION!r}")
    if set(payload.get("governingRfcs", [])) != GOVERNING_RFCS:
        errors.append("ledger governingRfcs must contain RFC-0082 and RFC-0083")
    if payload.get("closureStatus") != "target-model-and-guarded-artifact-closure":
        errors.append("ledger closureStatus must describe guarded target-model closure")
    if payload.get("runtimeProductionStatus") != "not-production-closed":
        errors.append("ledger must not claim runtime production closure without full proof")
    remaining_runtime_proof = payload.get("remainingRuntimeProof")
    if not isinstance(remaining_runtime_proof, list) or not remaining_runtime_proof:
        errors.append("ledger must list remaining runtime proof")
    else:
        for proof_item in remaining_runtime_proof:
            if not isinstance(proof_item, str) or not proof_item.strip():
                errors.append(f"ledger has invalid remaining runtime proof: {proof_item!r}")

    slices = payload.get("slices")
    if not isinstance(slices, list):
        return errors + ["ledger slices must be a list"]

    seen_slices: set[int] = set()
    for item in slices:
        if not isinstance(item, dict):
            errors.append(f"ledger slice entry must be an object: {item!r}")
            continue
        slice_number = item.get("slice")
        if not isinstance(slice_number, int):
            errors.append(f"ledger slice entry has invalid slice number: {item!r}")
            continue
        if slice_number in seen_slices:
            errors.append(f"duplicate RFC-0083 slice in ledger: {slice_number}")
        seen_slices.add(slice_number)
        _require_non_empty_string(item, "title", errors, slice_number)
        _require_non_empty_string(item, "validationLane", errors, slice_number)
        status = item.get("status")
        if status != "completed":
            errors.append(f"slice {slice_number} status must be completed for closure")
        artifacts = item.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"slice {slice_number} must list artifacts")
            continue
        artifact_set: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, str) or not artifact.strip():
                errors.append(f"slice {slice_number} has invalid artifact path: {artifact!r}")
                continue
            artifact_set.add(artifact)
            if Path(artifact).is_absolute():
                errors.append(f"slice {slice_number} artifact must be repo-relative: {artifact}")
                continue
            if not (repo_root / artifact).exists():
                errors.append(f"slice {slice_number} artifact does not exist: {artifact}")
        required_artifacts = EXPECTED_SLICE_ARTIFACTS.get(slice_number, set())
        missing_required_artifacts = sorted(required_artifacts - artifact_set)
        if missing_required_artifacts:
            errors.append(
                f"slice {slice_number} is missing required artifact(s): "
                + ", ".join(missing_required_artifacts)
            )

    missing_slices = EXPECTED_SLICES - seen_slices
    extra_slices = seen_slices - EXPECTED_SLICES
    if missing_slices:
        errors.append("ledger is missing slice(s): " + ", ".join(map(str, sorted(missing_slices))))
    if extra_slices:
        errors.append(
            "ledger contains unknown slice(s): " + ", ".join(map(str, sorted(extra_slices)))
        )
    return errors


def _require_non_empty_string(
    item: dict[str, Any], field_name: str, errors: list[str], slice_number: int
) -> None:
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"slice {slice_number} must define non-empty {field_name}")


def main() -> int:
    errors = evaluate_ledger(load_ledger())
    if errors:
        print("RFC-0083 closure guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("RFC-0083 closure guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
