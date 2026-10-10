import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

from scripts.quality.check_monetary_float_usage import main, scan_repo


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


def test_monetary_float_guard_ignores_time_dimension_on_cost_metric(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "monitoring.py"
    source_file.write_text(
        "def observe_cost_basis_lock(*, outcome: str, seconds: float) -> None:\n"
        "    histogram.labels(outcome).observe(seconds)\n",
        encoding="utf-8",
    )

    assert scan_repo(tmp_path) == []


def test_monetary_float_guard_still_flags_cost_amount_annotation(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "cost.py"
    source_file.write_text(
        "def calculate_cost(*, amount: float) -> None:\n    pass\n",
        encoding="utf-8",
    )

    assert scan_repo(tmp_path) == ["src/cost.py:1:def calculate_cost(*, amount: float) -> None:"]


def test_monetary_float_guard_ignores_generic_parser_value_conversion(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "settings.py"
    source_file.write_text(
        "def parse(raw):\n    value = float(raw)\n    return value\n",
        encoding="utf-8",
    )

    assert scan_repo(tmp_path) == []


def test_monetary_float_guard_ignores_duration_annotation_in_cost_observer(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "monitoring.py"
    source_file.write_text(
        "def observe_cost_basis_processing_lock_wait(*, outcome: str, seconds: float) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    assert scan_repo(tmp_path) == []


def test_monetary_float_guard_flags_monetary_parameter_annotation(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "pricing.py"
    source_file.write_text(
        "def calculate(*, market_value: float) -> None:\n    pass\n",
        encoding="utf-8",
    )

    assert scan_repo(tmp_path) == [
        "src/pricing.py:1:def calculate(*, market_value: float) -> None:"
    ]


def test_monetary_float_guard_flags_monetary_return_annotation(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "pricing.py"
    source_file.write_text(
        "def calculate_price(\n    raw: str,\n) -> float:\n    return 0.0\n",
        encoding="utf-8",
    )

    assert scan_repo(tmp_path) == ["src/pricing.py:3:) -> float:"]


def test_monetary_float_guard_flags_monetary_annotated_assignment(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "pricing.py"
    source_file.write_text("market_value: float = 0.0\n", encoding="utf-8")

    assert scan_repo(tmp_path) == ["src/pricing.py:1:market_value: float = 0.0"]


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


def _git(root, *arguments):
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def acquired_platform(tmp_path, monkeypatch):
    """Real independent Git checkout with an action/native-binding source pin."""
    _git(tmp_path, "init")
    foreign = tmp_path / ".lotus-platform"
    foreign.mkdir()
    _git(foreign, "init")
    _git(foreign, "config", "user.name", "Guard Fixture")
    _git(foreign, "config", "user.email", "fixture@example.invalid")
    _git(foreign, "config", "core.autocrlf", "false")
    _git(foreign, "remote", "add", "origin", "https://github.com/sgajbi/lotus-platform.git")
    source = foreign / "automation" / "validation.py"
    source.parent.mkdir()
    source.write_text(
        "def compare(actual_value, expected_value, tolerance):\n"
        "    return abs(float(actual_value) - float(expected_value)) <= tolerance\n",
        encoding="utf-8",
    )
    (foreign / ".gitignore").write_text("ignored.py\n__pycache__/\n", encoding="utf-8")
    _git(foreign, "add", "automation/validation.py", ".gitignore")
    _git(foreign, "-c", "commit.gpgsign=false", "commit", "-m", "Foreign fixture source")
    pin = _git(foreign, "rev-parse", "HEAD")
    action = tmp_path / ".github/actions/acquire-images/action.yml"
    action.parent.mkdir(parents=True)
    action.write_text(
        yaml.safe_dump(
            {
                "runs": {
                    "using": "composite",
                    "steps": [
                        {
                            "uses": "actions/checkout@v6",
                            "with": {
                                "repository": "sgajbi/lotus-platform",
                                "ref": pin,
                                "persist-credentials": False,
                                "path": ".lotus-platform",
                            },
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    binding = tmp_path / "scripts/release/image_acquisition_bindings.py"
    binding.parent.mkdir(parents=True)
    binding.write_text(f'GOVERNANCE_SHA = "{pin}"\n', encoding="utf-8")
    expected_action = yaml.safe_load(action.read_text(encoding="utf-8"))

    def validate_action_payload(payload):
        # Isolate the existing validator's public API from this unique local Git pin.
        # The actual acquisition validator owns its fixed production action/pin tests.
        if payload != expected_action:
            raise ValueError("Core image acquisition composite execution drifted")

    monkeypatch.setitem(
        sys.modules,
        "scripts.quality.required_status_checks.image_acquisition_action",
        SimpleNamespace(validate_action_payload=validate_action_payload),
    )
    return tmp_path, foreign, source, action, binding


def test_pinned_foreign_checkout_is_not_core_monetary_source(acquired_platform):
    root, foreign, _, _, _ = acquired_platform
    assert scan_repo(foreign)  # Same real foreign code is a finding without proven ownership.
    assert scan_repo(root) == []


@pytest.mark.parametrize(
    "source, expected",
    [
        ("from decimal import Decimal\namount: Decimal = Decimal('1.00')\n", []),
        ("amount = float('1.00')\n", [".internal/pricing.py:1:amount = float('1.00')"]),
        ("amount: float = 1.00\n", [".internal/pricing.py:1:amount: float = 1.00"]),
    ],
)
def test_core_hidden_source_is_scanned_beside_verified_foreign_source(
    acquired_platform,
    source,
    expected,
):
    root, _, _, _, _ = acquired_platform
    internal = root / ".internal"
    internal.mkdir()
    (internal / "pricing.py").write_text(source, encoding="utf-8")
    assert scan_repo(root) == expected


@pytest.mark.parametrize(
    "defect",
    [
        "missing-action",
        "missing-binding",
        "mutable-pin",
        "binding-drift",
        "wrong-repository",
        "wrong-path",
        "credentials",
        "wrong-head",
        "wrong-origin",
        "no-independent-git",
        "modified",
        "staged",
        "injected",
        "ignored-injection",
        "core-tracked",
        "assume-unchanged",
        "missing-quality-validator",
        "quality-validator-refusal",
    ],
)
def test_foreign_ownership_evidence_defects_fail_closed(acquired_platform, defect):
    root, foreign, source, action, binding = acquired_platform
    if defect == "missing-action":
        action.unlink()
    elif defect == "missing-binding":
        binding.unlink()
    elif defect in {"mutable-pin", "wrong-repository", "wrong-path", "credentials"}:
        payload = yaml.safe_load(action.read_text(encoding="utf-8"))
        settings = payload["runs"]["steps"][0]["with"]
        key, value = {
            "mutable-pin": ("ref", "main"),
            "wrong-repository": ("repository", "attacker/lotus-platform"),
            "wrong-path": ("path", "src"),
            "credentials": ("persist-credentials", True),
        }[defect]
        settings[key] = value
        action.write_text(yaml.safe_dump(payload), encoding="utf-8")
    elif defect == "binding-drift":
        binding.write_text(f'GOVERNANCE_SHA = "{"0" * 40}"\n', encoding="utf-8")
    elif defect == "wrong-head":
        _git(foreign, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "Drift")
    elif defect == "wrong-origin":
        _git(foreign, "remote", "set-url", "origin", "https://example.invalid/platform.git")
    elif defect == "no-independent-git":
        (foreign / ".git").rename(foreign / "git-metadata-not-active")
    elif defect == "core-tracked":
        blob = _git(foreign, "rev-parse", "HEAD:automation/validation.py")
        _git(
            root,
            "update-index",
            "--add",
            "--cacheinfo",
            f"100644,{blob},.lotus-platform/automation/validation.py",
        )
        assert _git(root, "ls-files", "--", ".lotus-platform")
    elif defect == "missing-quality-validator":
        sys.modules["scripts.quality.required_status_checks.image_acquisition_action"] = None
    elif defect == "quality-validator-refusal":

        def refuse_action(_payload):
            raise RuntimeError("Native quality authority refused the action")

        sys.modules["scripts.quality.required_status_checks.image_acquisition_action"] = (
            SimpleNamespace(validate_action_payload=refuse_action)
        )
    elif defect in {"injected", "ignored-injection"}:
        filename = "ignored.py" if defect == "ignored-injection" else "injected.py"
        (foreign / filename).write_text("amount = float('1.00')\n", encoding="utf-8")
    else:
        if defect == "assume-unchanged":
            _git(foreign, "update-index", "--assume-unchanged", "automation/validation.py")
        source.write_text("amount: float = 1.00\n", encoding="utf-8")
        if defect == "staged":
            _git(foreign, "add", "automation/validation.py")
    with pytest.raises(ValueError, match="Foreign source ownership verification failed"):
        scan_repo(root)


def test_missing_foreign_ownership_exits_nonzero_before_allowlisting(
    acquired_platform,
    monkeypatch,
    capsys,
):
    root, _, _, action, _ = acquired_platform
    action.unlink()
    monkeypatch.setattr(sys, "argv", ["guard", "--repo-root", str(root), "--update-allowlist"])
    assert main() == 1
    assert "Foreign source ownership verification failed" in capsys.readouterr().out
    assert not (root / "docs/standards/monetary-float-allowlist.json").exists()


@pytest.mark.parametrize(
    "source, expected_exit",
    [
        ("from decimal import Decimal\namount: Decimal = Decimal('1.00')\n", 0),
        ("amount = float('1.00')\n", 1),
        ("amount: float = 1.00\n", 1),
    ],
)
def test_native_guard_exit_preserves_core_monetary_policy(
    acquired_platform,
    monkeypatch,
    source,
    expected_exit,
):
    root, _, _, _, _ = acquired_platform
    (root / "pricing.py").write_text(source, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["guard", "--repo-root", str(root)])
    assert main() == expected_exit
