"""Keep raw SQL transaction fixtures aligned with the current schema."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
INTEGRATION_TEST_ROOT = REPO_ROOT / "tests" / "integration"
PAYLOAD_FINGERPRINT_MIGRATION_TEST = (
    INTEGRATION_TEST_ROOT / "test_transaction_payload_fingerprint_migration.py"
)
RAW_TRANSACTION_INSERT = re.compile(
    r"\binsert\s+into\s+"
    r"(?:(?:[a-z_][a-z0-9_]*|\"[^\"]+\")\s*\.\s*)?"
    r"(?:transactions|\"transactions\")\s*"
    r"\((?P<columns>[^)]*)\)\s*(?:values|select)\b",
    flags=re.IGNORECASE | re.DOTALL,
)


def _missing_payload_fingerprint_lines(source: str) -> list[int]:
    return [
        source.count("\n", 0, match.start()) + 1
        for match in RAW_TRANSACTION_INSERT.finditer(source)
        if "payload_fingerprint"
        not in {column.strip().strip('"').lower() for column in match.group("columns").split(",")}
    ]


def test_raw_transaction_insert_detector_rejects_missing_fingerprint() -> None:
    source = """
        INSERT INTO public.transactions (
            transaction_id, portfolio_id, transaction_date
        ) VALUES ('TXN-1', 'PORT-1', now())
    """

    assert _missing_payload_fingerprint_lines(source) == [2]


def test_raw_transaction_insert_detector_accepts_explicit_fingerprint() -> None:
    source = """
        INSERT INTO "transactions" (
            transaction_id, portfolio_id, transaction_date, payload_fingerprint
        ) SELECT transaction_id, portfolio_id, transaction_date, payload_fingerprint
        FROM staged_transactions
    """

    assert _missing_payload_fingerprint_lines(source) == []


def test_current_schema_raw_transaction_fixtures_supply_fingerprint() -> None:
    violations: list[str] = []
    for path in sorted(INTEGRATION_TEST_ROOT.rglob("*.py")):
        if path == PAYLOAD_FINGERPRINT_MIGRATION_TEST:
            continue
        source = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(REPO_ROOT).as_posix()}:{line}"
            for line in _missing_payload_fingerprint_lines(source)
        )

    assert violations == [], (
        "Raw INSERT INTO transactions fixtures against the current schema must "
        "provide payload_fingerprint explicitly; only the c173 downgrade/upgrade "
        "migration proof is exempt:\n" + "\n".join(violations)
    )
