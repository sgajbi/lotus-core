from __future__ import annotations

from pathlib import Path

E2E_ROOT = Path("tests/e2e")
TRANSACTION_INGEST_ROUTE = '"/ingest/transactions"'
INSTRUMENT_INGEST_ROUTE = '"/ingest/instruments"'
INTENTIONAL_UNRESOLVED_REFERENCE_MARKER = "E2E_INTENTIONAL_UNRESOLVED_INSTRUMENT_REFERENCE"
REQUEST_CONTRACT_ONLY_MODULES = {"test_ingestion_service_api.py"}


def test_transaction_e2e_producers_own_instrument_reference_preconditions() -> None:
    """Prevent unrelated E2E scenarios from poisoning the ordered consumer lane."""

    missing_reference_ownership: list[str] = []
    for path in sorted(E2E_ROOT.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if TRANSACTION_INGEST_ROUTE not in source:
            continue
        if path.name in REQUEST_CONTRACT_ONLY_MODULES:
            continue
        if INSTRUMENT_INGEST_ROUTE in source:
            continue
        if INTENTIONAL_UNRESOLVED_REFERENCE_MARKER in source:
            continue
        missing_reference_ownership.append(path.as_posix())

    assert missing_reference_ownership == [], (
        "E2E modules that publish transactions must settle instrument references, "
        "or declare the intentional unresolved-reference marker in a dedicated "
        f"dependency-failure scenario: {missing_reference_ownership}"
    )
