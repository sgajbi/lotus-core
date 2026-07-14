"""Protect aggregate transaction-processing infrastructure ownership."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[6]


def test_transaction_processing_observability_uses_owned_package() -> None:
    """Keep runtime telemetry out of the flat infrastructure root."""

    source_root = (
        REPOSITORY_ROOT / "src/services/portfolio_transaction_processing_service/app/infrastructure"
    )
    root_exports = (source_root / "__init__.py").read_text(encoding="utf-8")

    assert (source_root / "transaction_processing/observability.py").is_file()
    assert not (source_root / "prometheus_observability.py").exists()
    assert not (
        REPOSITORY_ROOT / "tests/unit/services/portfolio_transaction_processing_service/"
        "test_prometheus_observability.py"
    ).exists()
    assert "PrometheusTransactionProcessingObserver" not in root_exports
