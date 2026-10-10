"""Fixed native targets; neither receipts nor environment choose executable commands."""

TEST_TARGETS = {
    "coverage-shard-unit": "unit",
    "coverage-shard-unit-db": "unit-db",
    "coverage-shard-critical-db": "critical-db-coverage",
    "coverage-shard-integration-lite": "integration-lite",
    "coverage-shard-ops-contract": "ops-contract",
    "test-critical-lifecycle-db": "critical-lifecycle-db",
    "test-query-authority-db-contract": "query-authority-db-contract",
    "test-transaction-buy-contract": "transaction-buy-contract",
    "test-transaction-sell-contract": "transaction-sell-contract",
    "test-transaction-dividend-contract": "transaction-dividend-contract",
    "test-transaction-interest-contract": "transaction-interest-contract",
    "test-transaction-fx-contract": "transaction-fx-contract",
    "test-transaction-portfolio-flow-bundle-contract": "transaction-portfolio-flow-bundle-contract",
    "test-transaction-processing-contract": "transaction-processing-contract",
}
RUNTIME_TARGETS = frozenset(
    {
        "coverage-aggregate",
        "build-runtime-image-set",
        "generate-runtime-sbom",
        "write-runtime-build-provenance",
        "test-e2e-smoke",
        "test-docker-smoke",
        "lotus-core-validate",
        "test-latency-gate",
        "test-performance-load-gate",
        "test-fixed-income-book-cost-recovery-gate",
        "test-derived-state-recovery-gate",
    }
)
TARGETS = frozenset(TEST_TARGETS) | RUNTIME_TARGETS


def selected_commands(target: str, mode: str) -> tuple[tuple[str, ...], ...]:
    if target not in TARGETS:
        raise ValueError(f"unregistered PR validation target: {target}")
    if mode != "docs-only":
        return (("make", target),)
    commands: list[tuple[str, ...]] = [
        ("make", "quality-wiki-docs-gate"),
        ("make", "docs-evidence-pack"),
    ]
    if target in TEST_TARGETS:
        commands.append(
            (
                "python",
                "scripts/development/repository_python.py",
                "scripts/quality/test_manifest.py",
                "--suite",
                TEST_TARGETS[target],
                "--collect-only",
                "--quiet",
            )
        )
    return tuple(commands)
