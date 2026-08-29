from pathlib import Path

from scripts.quality.durable_lease_clock_guard import find_durable_lease_clock_findings


def test_durable_lease_clock_guard_allows_database_clock_expression(tmp_path: Path) -> None:
    source = tmp_path / "src" / "leases.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from sqlalchemy import func\n"
        "stmt = update(Job).values(lease_expires_at=func.clock_timestamp() + "
        "func.make_interval(0, 0, 0, 0, 0, 0, 30))\n",
        encoding="utf-8",
    )

    assert find_durable_lease_clock_findings(repo_root=tmp_path) == []


def test_durable_lease_clock_guard_rejects_application_datetime_deadline(tmp_path: Path) -> None:
    source = tmp_path / "src" / "leases.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from datetime import datetime, timedelta, timezone\n"
        "lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)\n",
        encoding="utf-8",
    )

    findings = find_durable_lease_clock_findings(repo_root=tmp_path)

    assert [(finding.target, finding.line) for finding in findings] == [("lease_expires_at", 2)]


def test_durable_lease_clock_guard_rejects_application_clock_keyword(tmp_path: Path) -> None:
    source = tmp_path / "src" / "leases.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from datetime import datetime\nbuild(valuation_lease_expires_at=datetime.utcnow())\n",
        encoding="utf-8",
    )

    findings = find_durable_lease_clock_findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert findings[0].target == "valuation_lease_expires_at"


def test_durable_lease_clock_guard_rejects_indirect_application_clock_deadline(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "leases.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from datetime import datetime, timezone\n"
        "lease_expiry = datetime.now(timezone.utc)\n"
        "build(lease_expires_at=lease_expiry)\n",
        encoding="utf-8",
    )

    findings = find_durable_lease_clock_findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert findings[0].target == "lease_expires_at"


def test_durable_lease_clock_guard_rejects_aliased_application_clock_deadline(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "leases.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from datetime import datetime as dt\nbuild(lease_expires_at=dt.now())\n",
        encoding="utf-8",
    )

    findings = find_durable_lease_clock_findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert findings[0].target == "lease_expires_at"


def test_durable_lease_clock_guard_rejects_expanded_deadline_mapping(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "leases.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from datetime import datetime, timedelta, timezone\n"
        "values_to_update = {\n"
        "    'lease_expires_at': datetime.now(timezone.utc) + timedelta(seconds=30),\n"
        "}\n"
        "stmt.values(**values_to_update)\n",
        encoding="utf-8",
    )

    findings = find_durable_lease_clock_findings(repo_root=tmp_path)

    assert len(findings) == 1
    assert findings[0].target == "lease_expires_at"


def test_durable_lease_clock_guard_rejects_positional_deadline_mapping(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "leases.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from datetime import datetime, timezone\n"
        "values_to_update = {'lease_expires_at': datetime.now(timezone.utc)}\n"
        "stmt.values(values_to_update)\n"
        "stmt.values({'lease_expires_at': datetime.now(timezone.utc)})\n",
        encoding="utf-8",
    )

    findings = find_durable_lease_clock_findings(repo_root=tmp_path)

    assert [finding.target for finding in findings] == [
        "lease_expires_at",
        "lease_expires_at",
    ]


def test_durable_lease_clock_guard_rejects_injected_clock_helpers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "leases.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "lease_expires_at = _clock.utc_now()\nbuild(lease_expires_at=application_deadline())\n",
        encoding="utf-8",
    )

    findings = find_durable_lease_clock_findings(repo_root=tmp_path)

    assert [finding.target for finding in findings] == [
        "lease_expires_at",
        "lease_expires_at",
    ]


def test_durable_lease_clock_guard_scopes_taint_to_each_function(tmp_path: Path) -> None:
    source = tmp_path / "src" / "leases.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from datetime import datetime, timezone\n"
        "from sqlalchemy import func\n"
        "\n"
        "def application_clock_deadline():\n"
        "    now = datetime.now(timezone.utc)\n"
        "    build(lease_expires_at=now)\n"
        "\n"
        "def database_clock_deadline():\n"
        "    now = func.clock_timestamp()\n"
        "    build(lease_expires_at=now)\n",
        encoding="utf-8",
    )

    findings = find_durable_lease_clock_findings(repo_root=tmp_path)

    assert [(finding.target, finding.line) for finding in findings] == [
        ("lease_expires_at", 6),
    ]


def test_durable_lease_clock_guard_scans_class_level_defaults(tmp_path: Path) -> None:
    source = tmp_path / "src" / "models.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from datetime import datetime, timezone\n"
        "\n"
        "class Job:\n"
        "    lease_expires_at = mapped_column(\n"
        "        default=lambda: datetime.now(timezone.utc),\n"
        "    )\n",
        encoding="utf-8",
    )

    findings = find_durable_lease_clock_findings(repo_root=tmp_path)

    assert [(finding.target, finding.line) for finding in findings] == [
        ("lease_expires_at", 4),
    ]
