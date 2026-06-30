import json
import sys

from scripts.check_monetary_float_usage import main, scan_repo


def test_monetary_float_guard_flags_money_like_float_conversion(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "pricing.py"
    source_file.write_text(
        "def market_value(row):\n    return float(row.market_value)\n",
        encoding="utf-8",
    )

    findings = scan_repo(tmp_path)

    assert findings == ["src/pricing.py:2:return float(row.market_value)"]


def test_monetary_float_guard_ignores_operational_delay_conversions(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "dispatcher.py"
    source_file.write_text(
        "def retry_delay_seconds(bounded_delay, retry_max_delay_seconds):\n"
        "    if bounded_delay >= retry_max_delay_seconds:\n"
        "        return float(bounded_delay)\n"
        "    return float(min(retry_max_delay_seconds, bounded_delay))\n",
        encoding="utf-8",
    )

    assert scan_repo(tmp_path) == []


def test_monetary_float_guard_ignores_generic_parser_value_conversion(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "settings.py"
    source_file.write_text(
        "def parse(raw):\n    value = float(raw)\n    return value\n",
        encoding="utf-8",
    )

    assert scan_repo(tmp_path) == []


def test_monetary_float_guard_fails_stale_allowlist_entries(tmp_path, monkeypatch, capsys):
    allowlist_path = tmp_path / "allowlist.json"
    allowlist_path.write_text(
        json.dumps(
            {
                "allowlist": [
                    {
                        "finding": "src/pricing.py:2:return float(row.market_value)",
                        "justification": "Migrated finding should not remain suppressed.",
                        "owner": "platform-governance",
                        "review_by": "2099-01-01",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_monetary_float_usage.py",
            "--repo-root",
            str(tmp_path),
            "--allowlist",
            "allowlist.json",
        ],
    )

    assert main() == 1
    assert "no longer match active findings" in capsys.readouterr().out
