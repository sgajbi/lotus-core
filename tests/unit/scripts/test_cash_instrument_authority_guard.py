from pathlib import Path

from scripts.quality.cash_instrument_authority_guard import (
    SERVICES_ROOT,
    find_cash_instrument_authority_findings,
)


def _write_service_source(root: Path, source: str) -> None:
    path = root / SERVICES_ROOT / "classification.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_guard_allows_metadata_owned_cash_classification(tmp_path: Path) -> None:
    _write_service_source(
        tmp_path,
        "def is_cash(product_type):\n    return str(product_type).strip().upper() == 'CASH'\n",
    )

    assert find_cash_instrument_authority_findings(tmp_path) == []


def test_guard_rejects_instrument_identifier_cash_prefix_inference(tmp_path: Path) -> None:
    _write_service_source(
        tmp_path,
        "def is_cash(transaction):\n"
        "    return transaction.instrument_id.upper().startswith('CASH_')\n",
    )

    findings = find_cash_instrument_authority_findings(tmp_path)

    assert len(findings) == 1
    assert findings[0].line_no == 2
    assert findings[0].path.endswith("classification.py")
    assert "instrument_id" in findings[0].expression


def test_guard_rejects_security_identifier_cash_prefix_inference(tmp_path: Path) -> None:
    _write_service_source(
        tmp_path,
        'def is_cash(security_id):\n    return security_id.strip().startswith("CASH")\n',
    )

    findings = find_cash_instrument_authority_findings(tmp_path)

    assert len(findings) == 1
    assert "security_id" in findings[0].expression
