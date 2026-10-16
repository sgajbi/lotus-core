"""Offline ownership controls; mocks do not qualify PostgreSQL or Docker."""

import ast
import base64
import copy
import hashlib
import json
import os
import py_compile
import runpy
import shlex
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.engine import make_url

from tests.test_support import operator_source_database as profile

pytestmark = pytest.mark.unit
NOW = datetime.now(UTC)


def seed_command(root, pin, mode="initial", *arguments):
    from scripts.validation.qualify_source_receipts import SOURCE_SEED

    return [sys.executable, "-I", "-B", "-c", SOURCE_SEED, str(root), pin, mode, *arguments]


def seed_environment():
    return {
        name: os.environ[name]
        for name in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP")
        if name in os.environ
    }


@pytest.mark.parametrize("hidden", ["skip-worktree", "assume-unchanged"])
@pytest.mark.parametrize("mode", ["initial", "api"])
def test_trusted_seed_refuses_hidden_cli_before_any_repository_instruction(tmp_path, hidden, mode):
    from tests.test_support.source_receipt_process_custody import source_prefix

    root, _, _ = provenance_repository(tmp_path, bootstrap=True)
    path = root / "scripts/validation/qualify_source_receipts.py"
    pin = provenance_git(root, "rev-parse", "HEAD:scripts/validation/qualify_source_receipts.py")
    marker = tmp_path / "unchecked-bootstrap-executed"
    provenance_git(root, "update-index", "--" + hidden, path.relative_to(root).as_posix())
    path.write_bytes(
        path.read_bytes() + f"\nPath({str(marker)!r}).write_text('executed')\n".encode()
    )
    assert not provenance_git(root, "status", "--porcelain")
    wire = b"" if mode == "initial" else source_prefix((path.read_bytes(), b"api"), 1) + b"x"
    result = subprocess.run(
        seed_command(root, pin, mode, "--help"),
        input=wire,
        env=seed_environment(),
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 2 and not result.stdout and not result.stderr
    assert not marker.exists()


@pytest.mark.parametrize("pin_kind", ["valid", "wrong", "malformed"])
def test_initial_seed_uses_independent_pin_before_help(tmp_path, pin_kind):
    root, _, _ = provenance_repository(tmp_path, bootstrap=True)
    pin = provenance_git(root, "rev-parse", "HEAD:scripts/validation/qualify_source_receipts.py")
    if pin_kind != "valid":
        pin = "0" * 40 if pin_kind == "wrong" else "HEAD"
    result = subprocess.run(
        seed_command(root, pin, "initial", "--help"),
        env=seed_environment(),
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == (0 if pin_kind == "valid" else 2)
    assert bool(result.stdout.startswith(b"usage:")) == (pin_kind == "valid")
    assert not result.stderr


@pytest.mark.parametrize("hidden", ["skip-worktree", "assume-unchanged"])
def test_api_capture_refuses_hidden_api_source(tmp_path, monkeypatch, hidden):
    from scripts.validation import qualify_source_receipts as runner

    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    provenance = runner.SourceProvenance(value, root).qualify()
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(
        runner, "__file__", str(root / "scripts/validation/qualify_source_receipts.py")
    )
    monkeypatch.setattr(runner, "_active_provenance", provenance)
    path = root / "tests/test_support/portfolio_source_http_process.py"
    provenance_git(root, "update-index", "--" + hidden, path.relative_to(root).as_posix())
    path.write_bytes(path.read_bytes() + b"\nraise AssertionError('unchecked API')\n")
    assert not provenance_git(root, "status", "--porcelain")
    with pytest.raises(runner.EnvironmentRefused, match="SOURCE_RECEIPT_IMPORT_REFUSED"):
        runner.snapshot_launch("api")


@pytest.mark.parametrize("mode", ["child", "cleanup"])
def test_captured_cli_survives_later_path_mutation(tmp_path, monkeypatch, mode):
    from scripts.validation import qualify_source_receipts as runner
    from tests.test_support.source_receipt_process_custody import source_prefix

    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    provenance = runner.SourceProvenance(value, root).qualify()
    path = root / "scripts/validation/qualify_source_receipts.py"
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "__file__", str(path))
    monkeypatch.setattr(runner, "_active_provenance", provenance)
    command, snapshots = runner.snapshot_launch(mode, ["--help"])
    marker = tmp_path / "reopened-source"
    path.write_bytes(
        path.read_bytes() + f"\nPath({str(marker)!r}).write_text('executed')\n".encode()
    )
    result = subprocess.run(
        command,
        input=source_prefix(snapshots, 1) + b"x",
        env=seed_environment(),
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0 and result.stdout.startswith(b"usage:") and not result.stderr
    assert not marker.exists()


@pytest.mark.parametrize(
    "name",
    ["GIT_DIR", "DOCKER_CONTEXT", "PGHOST", "PYTHONPATH", "DATABASE_URL", "LOTUS_REPOSITORY_ROOT"],
)
def test_environment_protected_case_collisions_refuse_even_equal_values(name):
    from scripts.validation.qualify_source_receipts import EnvironmentRefused, validate_environment

    with pytest.raises(EnvironmentRefused, match="SOURCE_RECEIPT_INHERITED_OVERRIDE"):
        validate_environment({name: "", name.lower(): ""})


def test_unrelated_proxy_case_pair_is_preserved():
    from scripts.validation.qualify_source_receipts import profile_environment, validate_environment

    environment = {"HTTP_PROXY": "upper", "http_proxy": "lower"}
    validate_environment(environment)
    child = profile_environment(environment)
    assert {name: child[name] for name in environment} == environment


@pytest.mark.parametrize("changed", [False, True])
def test_api_entry_executes_only_committed_captured_body(tmp_path, monkeypatch, changed):
    from scripts.validation import qualify_source_receipts as runner

    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    path = root / "tests/test_support/portfolio_source_http_process.py"
    marker = tmp_path / "captured-api-executed"
    body = f"from pathlib import Path\nPath({str(marker)!r}).write_text('verified')\n".encode()
    path.write_bytes(body)
    provenance_git(root, "add", "--all")
    provenance_git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "captured API fixture",
    )
    value["source_sha"] = provenance_git(root, "rev-parse", "HEAD")
    value["source_tree"] = provenance_git(root, "rev-parse", "HEAD^{tree}")
    provenance = runner.SourceProvenance(value, root).qualify()
    provenance.object(path)  # Capture the admitted identity before a pathname race.
    path.write_bytes(b"raise AssertionError('working API reopened')\n")
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setenv("LOTUS_SOURCE_RECEIPT_ADMISSION", "public")
    monkeypatch.setenv("LOTUS_SOURCE_RECEIPT_ADMISSION_SHA256", "a" * 64)
    monkeypatch.setattr(runner, "read_admission", lambda *args: value)
    monkeypatch.setattr(runner, "bootstrap", lambda *args: provenance)
    runtime = MagicMock()
    monkeypatch.setattr(runner, "load_runtime", runtime)
    monkeypatch.setattr(runner, "require_supported_os", lambda: None)
    if changed:
        with pytest.raises(runner.EnvironmentRefused, match="SOURCE_RECEIPT_IMPORT_REFUSED"):
            runner.api_entry(body + b"# changed\n", 1)
        assert not marker.exists()
        runtime.assert_not_called()
    else:
        runner.api_entry(body, 1)
        assert marker.read_text() == "verified"
        runtime.assert_called_once()


def test_synthetic_admission_clock_is_created_at_test_setup(monkeypatch):
    # Full-suite collection can precede these tests by more than the admission lifetime.
    monkeypatch.setattr(sys.modules[__name__], "NOW", datetime.now(UTC) - timedelta(hours=1))
    admission_clock.__wrapped__(monkeypatch)
    assert abs(datetime.now(UTC).timestamp() - NOW.timestamp()) < 5
    value = admitted()
    for field, seconds in (
        ("issued_at", -10),
        ("run_deadline", 120),
        ("cleanup_deadline", 180),
        ("parent_expiry", 300),
    ):
        assert datetime.fromisoformat(value[field]).timestamp() - NOW.timestamp() == seconds


def test_module_git_prerequisite_clock_is_fresh_before_function_fixture(monkeypatch):
    from scripts.validation import qualify_source_receipts as runner

    monkeypatch.setattr(sys.modules[__name__], "NOW", datetime.now(UTC) - timedelta(hours=1))
    qualified = MagicMock()
    constructor = MagicMock(return_value=SimpleNamespace(qualify_git_version=qualified))
    monkeypatch.setattr(runner, "SourceProvenance", constructor)
    before = datetime.now(UTC).timestamp()
    native_git_prerequisite.__wrapped__()
    value = constructor.call_args.args[0]
    issued = datetime.fromisoformat(value["issued_at"]).timestamp()
    assert before <= issued + 10 <= datetime.now(UTC).timestamp()
    for field, seconds in (
        ("run_deadline", 130),
        ("cleanup_deadline", 190),
        ("parent_expiry", 310),
    ):
        assert datetime.fromisoformat(value[field]).timestamp() - issued == seconds
    qualified.assert_called_once_with()


@pytest.mark.parametrize("caller_override", [False, True])
@pytest.mark.parametrize("environment_override", [False, True])
@pytest.mark.parametrize("pin_origin", ["command-line", "environment"])
def test_make_qualification_dry_run_keeps_fixed_isolated_entry(
    caller_override, environment_override, pin_origin
):
    from scripts.validation.qualify_source_receipts import SOURCE_SEED

    root = Path(__file__).resolve().parents[3]
    environment = {"PATH": os.environ["PATH"], "LC_ALL": "C"}
    if "SYSTEMROOT" in os.environ:
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    if environment_override:
        environment.update(
            SOURCE_RECEIPT_PYTHON="echo UNSAFE_SOURCE_LAUNCHER",
            REPOSITORY_PYTHON="echo UNSAFE_REPOSITORY_LAUNCHER",
        )
    command = [
        "make",
        "--no-print-directory",
        "--dry-run",
        "qualify-source-receipts",
        "SOURCE_RECEIPT_ADMISSION=/synthetic/admission.json",
        "SOURCE_RECEIPT_ADMISSION_SHA256=" + "0" * 64,
        "LOTUS_WORKSPACE_ROOT=/synthetic/workspace",
    ]
    if pin_origin == "command-line":
        command.append("SOURCE_RECEIPT_BOOTSTRAP_BLOB=" + "a" * 40)
    else:
        environment["SOURCE_RECEIPT_BOOTSTRAP_BLOB"] = "a" * 40
    if caller_override:
        command += [
            "SOURCE_RECEIPT_PYTHON=echo UNSAFE_SOURCE_LAUNCHER",
            "REPOSITORY_PYTHON=echo UNSAFE_REPOSITORY_LAUNCHER",
        ]
    result = subprocess.run(
        command, cwd=root, env=environment, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert shlex.split(result.stdout.strip()) == [
        "python",
        "-I",
        "-B",
        "-c",
        "exec(__import__('base64').b64decode('"
        + base64.b64encode(SOURCE_SEED.encode()).decode()
        + "'))",
        root.as_posix(),
        "a" * 40 if pin_origin == "command-line" else "",
        "initial",
        "--admission",
        "/synthetic/admission.json",
        "--admission-sha256",
        "0" * 64,
        "--workspace-root",
        "/synthetic/workspace",
    ]


@pytest.mark.parametrize("mutation", [None, "override-assignment", "direct-recipe-variable"])
def test_make_qualification_uses_existing_production_static_authority(tmp_path, mutation):
    from scripts.quality.required_status_checks.make_authority import load_make_target_authority
    from scripts.quality.required_status_checks.model import RequiredStatusChecksError

    root = Path(__file__).resolve().parents[3]
    source = root / "Makefile"
    if mutation is None:
        assert "qualify-source-receipts" in load_make_target_authority(source)
        return
    content = source.read_text(encoding="utf-8")
    if mutation == "override-assignment":
        content += "\noverride SOURCE_RECEIPT_PYTHON := echo UNSAFE\n"
    else:
        fixed = "python -I -B -c"
        assert content.count("\t" + fixed) == 1
        content = content.replace("\t" + fixed, "\t$(SOURCE_RECEIPT_PYTHON)")
    altered = tmp_path / "Makefile"
    altered.write_text(content, encoding="utf-8")
    with pytest.raises(RequiredStatusChecksError, match="Makefile execution state must be static"):
        load_make_target_authority(altered)


def provenance_git(root, *arguments):
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return result.stdout.decode().strip()


def provenance_repository(tmp_path, *, bootstrap=False, managed=False, imports=""):
    workspace = tmp_path / "workspace"
    primary = workspace / "lotus-core"
    primary.mkdir(parents=True)
    provenance_git(primary, "init", "-q")
    (primary / ".gitignore").write_text("*.py[cod]\n__pycache__/\npytest/\nuvicorn/\nignored_*/\n")
    node = primary / profile.NODE.split("::")[0]
    node.parent.mkdir(parents=True)
    node.write_text("cash-only source")
    if bootstrap:
        source = Path(__file__).resolve().parents[3]
        for name in (
            "scripts/validation/qualify_source_receipts.py",
            "scripts/development/repository_import_guard.py",
            "scripts/development/repository_python.py",
            "tests/test_support/operator_source_database.py",
            "tests/test_support/source_receipt_process_custody.py",
            "tests/test_support/portfolio_source_http_process.py",
            "alembic/versions/c178b2c3d539_add_portfolio_source_observations.py",
            "alembic/versions/c181b2c3d542_add_portfolio_source_fact_verifications.py",
        ):
            target = primary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / name).read_bytes())
        for name in (
            "tests/__init__.py",
            "tests/test_support/__init__.py",
            "scripts/__init__.py",
            "scripts/validation/__init__.py",
            "scripts/development/__init__.py",
        ):
            target = primary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("")
        package = primary / "src/libs/portfolio-common/portfolio_common/__init__.py"
        package.parent.mkdir(parents=True)
        package.write_text("QUALIFIED = True\n")
        if imports:
            with (primary / "tests/test_support/operator_source_database.py").open("a") as stream:
                stream.write("\n" + imports + "\n")
    provenance_git(primary, "add", "--all")
    provenance_git(
        primary,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "synthetic qualification source",
    )
    root = primary
    if managed:
        root = workspace / "worktrees/owned-core"
        provenance_git(primary, "worktree", "add", "-q", "-b", "owned-fixture", str(root))
    value = admitted()
    # Native fixtures use the real clock; keep each original window relative to creation.
    issued = datetime.now(UTC)
    for field, seconds in (
        ("issued_at", -10),
        ("run_deadline", 120),
        ("cleanup_deadline", 180),
        ("parent_expiry", 300),
    ):
        value[field] = (issued + timedelta(seconds=seconds)).isoformat()
    value.update(
        source_sha=provenance_git(root, "rev-parse", "HEAD"),
        source_tree=provenance_git(root, "rev-parse", "HEAD^{tree}"),
    )
    return root, workspace, value


def native_provenance_observer(command, root=None, *, environment=None, deadline=None):
    from scripts.validation.qualify_source_receipts import bootstrap_observe

    return bootstrap_observe(command, root, deadline or NOW.timestamp() + 300)


def pinned_parent_fixture(tmp_path, *, managed=False):
    root, workspace, value = provenance_repository(tmp_path, managed=managed)
    platform = workspace / "lotus-platform"
    helper = platform / "automation/canonical_runtime_lease.py"
    helper.parent.mkdir(parents=True)
    marker = tmp_path / "reviewed-helper-executed"
    helper.write_text(
        "import hashlib,json\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('reviewed')\n"
        "def current(book): return book['record']\n"
        "def digest(value): return 'sha256:'+hashlib.sha256("
        "json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()\n"
    )
    provenance_git(platform, "init", "-q")
    provenance_git(platform, "add", "--all")
    provenance_git(
        platform,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "reviewed synthetic helper",
    )
    value["platform_source_sha"] = provenance_git(platform, "rev-parse", "HEAD")
    common = Path(provenance_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    scope = {
        "projects": {"lotus-core": str(common.parent), "canonical-ingress": str(platform)},
        "sources": {"lotus-core": "f" * 40, "lotus-platform": value["platform_source_sha"]},
        "ports": [value["port"]],
    }
    value["scope_digest"] = profile.digest(scope)
    value["bindings_digest"] = profile.digest([])
    record = dict(
        id=value["parent_lease"],
        holder=value["parent_holder"],
        operation=None,
        scopeDigest="sha256:" + value["scope_digest"],
        expiryUtc=value["parent_expiry"],
        bindings=[],
        scope=scope,
    )
    book = platform / "output/canonical-runtime/reservations.v1.json"
    book.parent.mkdir(parents=True)
    book.write_text(json.dumps({"record": record}))
    return root, workspace, value, record, book, helper, marker


def provenance_child(root, value, code, *, userbase=None):
    public = root.parent / "synthetic-public.json"
    raw = json.dumps(value).encode()
    public.write_bytes(raw)
    entry = root / "scripts/validation/qualify_source_receipts.py"
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP")
        if name in os.environ
    }
    if userbase is not None:
        environment["PYTHONUSERBASE"] = str(userbase)
    prefix = (
        "import sys,types,json,pathlib\n"
        "name='scripts.validation.qualify_source_receipts'\n"
        "module=types.ModuleType(name)\n"
        f"module.__file__={str(entry)!r}\n"
        "module._SOURCE_RECEIPT_BOOTSTRAP_ONLY=True\n"
        "sys.modules[name]=module\n"
        "exec(compile(pathlib.Path(module.__file__).read_bytes(),module.__file__,'exec'),module.__dict__)\n"
        f"admission=module.read_admission({str(public)!r},{hashlib.sha256(raw).hexdigest()!r})\n"
        "module.bootstrap(admission)\n"
    )
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", prefix + code],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("shadow", ["pytest", "uvicorn", "pytest_asyncio", "ignored_transitive"])
def test_provenance_rejects_actual_ignored_sourceless_dependency_before_execution(tmp_path, shadow):
    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    marker = tmp_path / "shadow-executed"
    source = tmp_path / "harmless.py"
    source.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
    py_compile.compile(str(source), cfile=str(root / (shadow + ".pyc")), doraise=True)
    assert not provenance_git(root, "status", "--porcelain")
    result = provenance_child(root, value, f"import {shadow}\n")
    assert result.returncode != 0 and not marker.exists()
    assert "SOURCE_RECEIPT_IMPORT_REFUSED" in result.stderr, result.stderr


@pytest.mark.parametrize("package", [True, False])
def test_provenance_rejects_actual_ignored_package_or_namespace(tmp_path, package):
    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    folder = root / "ignored_package"
    folder.mkdir()
    marker = tmp_path / "package-executed"
    if package:
        (folder / "__init__.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        )
    else:
        (folder / "child.py").write_text("MARKER = True\n")
    result = provenance_child(root, value, "import ignored_package\n")
    assert result.returncode != 0 and not marker.exists()


def test_provenance_preserves_tracked_source_and_normal_cache_without_using_bytecode(tmp_path):
    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    package = root / "src/libs/portfolio-common/portfolio_common/__init__.py"
    cache = Path(py_compile.compile(str(package), doraise=True))
    marker = tmp_path / "poisoned-cache-executed"
    poison = tmp_path / "poisoned-cache.py"
    poison.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
    poisoned_cache = Path(py_compile.compile(str(poison), doraise=True))
    # Preserve valid source metadata while replacing only the cached code payload.
    cache.write_bytes(cache.read_bytes()[:16] + poisoned_cache.read_bytes()[16:])
    original_cache = cache.read_bytes()
    result = provenance_child(
        root,
        value,
        "import pytest,sqlalchemy,psycopg2,asyncpg,uvicorn,portfolio_common\n"
        "assert portfolio_common.QUALIFIED\n"
        "assert sys.flags.isolated and sys.flags.no_user_site and sys.dont_write_bytecode\n"
        "assert 'PYTHONUSERBASE' not in module.profile_environment()\n"
        "print('qualified')\n",
        userbase=tmp_path / "inert-userbase",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "qualified" and cache.read_bytes() == original_cache
    assert not marker.exists()


def test_provenance_refuses_core_worktree_redirect(
    tmp_path, monkeypatch, clean_profile_environment
):
    root, _, value = provenance_repository(tmp_path)
    monkeypatch.setattr(profile, "observe", native_provenance_observer)
    profile.qualify_source(value, root)
    foreign = tmp_path / "clean-copy"
    path = foreign / profile.NODE.split("::")[0]
    path.parent.mkdir(parents=True)
    path.write_text("cash-only source")
    (foreign / ".gitignore").write_bytes((root / ".gitignore").read_bytes())
    provenance_git(root, "config", "core.worktree", str(foreign))
    (root / profile.NODE.split("::")[0]).write_text("unreviewed physical source")
    assert not provenance_git(root, "status", "--porcelain")
    with pytest.raises(profile.ProfileRefused, match="DIRTY_SOURCE"):
        profile.qualify_source(value, root)


def test_provenance_never_executes_configured_clean_filter(
    tmp_path, monkeypatch, clean_profile_environment
):
    root, _, value = provenance_repository(tmp_path)
    marker = tmp_path / "filter-executed"
    poison = tmp_path / "filter.py"
    poison.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
    provenance_git(root, "config", "filter.unreviewed.clean", f'"{sys.executable}" "{poison}"')
    provenance_git(root, "config", "filter.unreviewed.required", "true")
    attributes = root / ".git/info/attributes"
    attributes.write_text("* filter=unreviewed\n")
    (root / profile.NODE.split("::")[0]).write_text("dirty physical source")
    monkeypatch.setattr(profile, "observe", native_provenance_observer)
    with pytest.raises(profile.ProfileRefused, match="DIRTY_SOURCE"):
        profile.qualify_source(value, root)
    assert not marker.exists()


def test_provenance_refuses_transitive_shadow_in_tracked_module(tmp_path):
    root, _, value = provenance_repository(
        tmp_path, bootstrap=True, imports="import ignored_transitive"
    )
    marker = tmp_path / "transitive-executed"
    source = tmp_path / "harmless-transitive.py"
    source.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
    py_compile.compile(str(source), cfile=str(root / "ignored_transitive.pyc"), doraise=True)
    result = provenance_child(root, value, "module.load_runtime()\n")
    assert result.returncode != 0 and "SOURCE_RECEIPT_IMPORT_REFUSED" in result.stderr
    assert not marker.exists()


@pytest.mark.parametrize("shadow", [False, True])
def test_unseeded_api_entry_refuses_before_private_descriptor(tmp_path, shadow):
    marker = tmp_path / "tracked-profile-loaded"
    root, _, value = provenance_repository(
        tmp_path,
        bootstrap=True,
        imports=(
            "import sqlalchemy\nfrom pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('qualified')"
        ),
    )
    poison_marker = tmp_path / "api-shadow-executed"
    if shadow:
        source = tmp_path / "harmless-api-shadow.py"
        source.write_text(
            f"from pathlib import Path\nPath({str(poison_marker)!r}).write_text('executed')\n"
        )
        py_compile.compile(str(source), cfile=str(root / "sqlalchemy.pyc"), doraise=True)
    public = tmp_path / "public-api-admission.json"
    raw = json.dumps(value).encode()
    public.write_bytes(raw)
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP")
        if name in os.environ
    }
    environment.update(
        LOTUS_OPERATOR_SOURCE_RECEIPT="1",
        LOTUS_SOURCE_RECEIPT_ADMISSION=str(public),
        LOTUS_SOURCE_RECEIPT_ADMISSION_SHA256=hashlib.sha256(raw).hexdigest(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(root / "tests/test_support/portfolio_source_http_process.py"),
        ],
        cwd=tmp_path,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # A working script is not a supported trusted entry, even if its imports are valid.
    assert completed.returncode == 2 and not completed.stdout and not completed.stderr
    assert not marker.exists()
    assert not poison_marker.exists()


@pytest.mark.parametrize("operator", [False, True])
@pytest.mark.asyncio
async def test_http_generation_actual_command_preserves_ordinary_entry_and_isolates_operator(
    monkeypatch, operator
):
    from scripts.validation import qualify_source_receipts as runner
    from tests.test_support import source_receipt_process_custody as custody

    selected = [sys.executable, "-I", "-B", "-c", runner.SOURCE_SEED, "root", "a" * 40, "api"]
    launch = MagicMock(return_value=(selected, (b"cli", b"api")))
    monkeypatch.setattr(runner, "snapshot_launch", launch)
    monkeypatch.setattr(custody, "WindowsJob", MagicMock())

    root = Path(__file__).resolve().parents[3]
    path = root / profile.NODE.split("::")[0]
    function = next(
        node
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "http_generation"
    )
    function.decorator_list = []
    popen = MagicMock(side_effect=RuntimeError("captured before private descriptor"))
    environment = {"qualified": "snapshot"}
    namespace = dict(
        __file__=str(path),
        sys=sys,
        os=os,
        Path=Path,
        subprocess=SimpleNamespace(Popen=popen, PIPE=-1),
        repository_environment=lambda: environment,
    )
    if operator:
        monkeypatch.setenv("LOTUS_OPERATOR_SOURCE_RECEIPT", "1")
    else:
        monkeypatch.delenv("LOTUS_OPERATOR_SOURCE_RECEIPT", raising=False)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    with pytest.raises(RuntimeError, match="captured before private descriptor"):
        await namespace["http_generation"](None, {}).__anext__()
    command = popen.call_args.args[0]
    assert command == (
        selected
        if operator
        else [sys.executable, "-m", "tests.test_support.portfolio_source_http_process"]
    )
    assert popen.call_args.kwargs["env"] is environment
    assert launch.call_count == int(operator)
    if operator:
        assert popen.call_args.kwargs["creationflags"] == 0x4 | 0x08000000


@pytest.mark.parametrize("missing", [True, False])
def test_platform_source_pin_is_mandatory_full_sha_before_admission(missing):
    value = admitted()
    if missing:
        del value["platform_source_sha"]
    else:
        value["platform_source_sha"] = "not-a-reviewed-sha"
    with pytest.raises(profile.ProfileRefused, match="ADMISSION_SHAPE|SOURCE_INVALID"):
        profile.validate_admission(value, now=NOW.timestamp(), environment={}, platform="nt")


@pytest.mark.parametrize(
    "arguments",
    [
        ["config", "core.worktree", "foreign"],
        ["status", "--help"],
        ["cat-file", "--filters", "HEAD:file"],
        ["rev-parse", "--verify", "foreign"],
        ["checkout", "HEAD"],
    ],
)
def test_provenance_transport_rejects_nonfixed_git_forms_before_dispatch(arguments):
    from scripts.validation import qualify_source_receipts as runner

    observed = MagicMock()
    provenance = runner.SourceProvenance(admitted(), observe=observed)
    with pytest.raises(runner.EnvironmentRefused, match="OBSERVATION_REFUSED"):
        provenance.git(arguments)
    observed.assert_not_called()


def test_provenance_transport_fixed_form_preserves_deadline_and_safe_flags():
    from scripts.validation import qualify_source_receipts as runner

    observed = MagicMock(side_effect=[b"git version 2.50.1.windows.1\n", b"reviewed"])
    provenance = runner.SourceProvenance(admitted(), observe=observed)
    assert provenance.git(["rev-parse", "--verify", "HEAD"]) == b"reviewed"
    command, root, deadline = observed.call_args.args
    assert observed.call_args_list[0].args == (["git", "--version"], root, deadline)
    assert command[:4] == ["git", "--no-replace-objects", "--no-lazy-fetch", "--no-optional-locks"]
    assert "core.fsmonitor=false" in command and "core.untrackedCache=false" in command
    assert "--work-tree=" + str(root) in command
    assert deadline == datetime.fromisoformat(admitted()["run_deadline"]).timestamp()


@pytest.mark.parametrize(
    "reported,reason",
    [
        (b"git version 2.43.0.windows.1\n", "UNSUPPORTED"),
        (b"git version 2.50.0\n", "UNSUPPORTED"),
        (b"git version 2.50\n", "INVALID"),
        (b"git version 2.50.1-rc1\n", "INVALID"),
        (b"git version 2.50.1\nforeign", "INVALID"),
        (b"", "INVALID"),
    ],
)
def test_git_prerequisite_refuses_before_version_dependent_flags(reported, reason):
    from scripts.validation import qualify_source_receipts as runner

    observed = MagicMock(return_value=reported)
    provenance = runner.SourceProvenance(admitted(), observe=observed)
    with pytest.raises(runner.EnvironmentRefused, match="GIT_VERSION_" + reason):
        provenance.git(["status", "--porcelain", "--untracked-files=all"])
    observed.assert_called_once_with(["git", "--version"], provenance.root, provenance.deadline)


def test_actual_installed_git_satisfies_documented_tested_minimum(tmp_path):
    from scripts.validation import qualify_source_receipts as runner

    root, _, value = provenance_repository(tmp_path)
    provenance = runner.SourceProvenance(value, root).qualify()
    assert runner.MINIMUM_GIT_VERSION == (2, 50, 1)
    assert provenance.git_version_qualified


@pytest.mark.parametrize(
    "name",
    [
        "c178b2c3d539_add_portfolio_source_observations.py",
        "c181b2c3d542_add_portfolio_source_fact_verifications.py",
    ],
)
@pytest.mark.parametrize("hidden", [None, "skip-worktree", "assume-unchanged"])
def test_direct_migration_hidden_or_dirty_bytes_cannot_execute_payload_or_sql(
    tmp_path, monkeypatch, name, hidden
):
    from scripts.validation import qualify_source_receipts as runner

    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    path = root / "alembic/versions" / name
    marker = tmp_path / "unadmitted-migration-executed"
    if hidden:
        provenance_git(root, "update-index", "--" + hidden, path.relative_to(root).as_posix())
    path.write_bytes(
        path.read_bytes()
        + (f"\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n").encode()
    )
    state = provenance_git(root, "status", "--porcelain")
    connection = MagicMock()
    if not hidden:
        assert state
        with pytest.raises(runner.EnvironmentRefused, match="DIRTY_SOURCE"):
            runner.SourceProvenance(value, root).qualify()
    else:
        assert not state
        provenance = runner.SourceProvenance(value, root).qualify()
        # The actual former runpy caller executes the harmless payload despite clean status.
        runpy.run_path(str(path))
        assert marker.read_text() == "executed"
        marker.unlink()
        monkeypatch.setattr(runner, "_active_provenance", provenance)
        with pytest.raises(profile.ProfileRefused, match="IMPORT_REFUSED"):
            profile.operator_migration(connection, name)
    assert not marker.exists()
    connection.assert_not_called()
    assert connection.mock_calls == []


@pytest.mark.parametrize(
    "name",
    [
        "c178b2c3d539_add_portfolio_source_observations.py",
        "c181b2c3d542_add_portfolio_source_fact_verifications.py",
    ],
)
def test_actual_guard_installed_migration_snapshot_preserves_run_path_globals(tmp_path, name):
    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    result = provenance_child(
        root,
        value,
        (
            "import types\n"
            "sentinel=types.ModuleType('sentinel')\n"
            "sys.modules['<run_path>']=sentinel\n"
            "old_argv=sys.argv[0]\n"
            f"migration=module._active_provenance.migration({name!r})\n"
            "assert migration['__name__']=='<run_path>' and migration['__package__']==''\n"
            "assert migration['__cached__'] is None and migration['__spec__'] is None\n"
            "assert migration['__loader__'] is None\n"
            f"expected_file=pathlib.Path(module.ROOT)/'alembic/versions'/{name!r}\n"
            "assert migration['__file__']==str(expected_file)\n"
            "assert migration['upgrade'].__globals__['__file__']==migration['__file__']\n"
            "assert sys.argv[0]==old_argv and sys.modules['<run_path>'] is sentinel\n"
            "import alembic\n"
            "runtime=pathlib.Path(sys.prefix).resolve()\n"
            "assert pathlib.Path(alembic.__file__).resolve().is_relative_to(runtime)\n"
            "print('verified-migration')\n"
        ),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "verified-migration"


def test_verified_migration_snapshot_survives_path_mutation_and_exceeds_git_capture_cap(tmp_path):
    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    name = "c178b2c3d539_add_portfolio_source_observations.py"
    path = root / "alembic/versions" / name
    path.write_bytes(path.read_bytes() + b"\n#" + b"x" * 70023 + b"\n")
    provenance_git(root, "add", "--", path.relative_to(root).as_posix())
    provenance_git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "valid large migration snapshot",
    )
    value.update(
        source_sha=provenance_git(root, "rev-parse", "HEAD"),
        source_tree=provenance_git(root, "rev-parse", "HEAD^{tree}"),
    )
    provenance_git(root, "update-index", "--skip-worktree", path.relative_to(root).as_posix())
    marker = tmp_path / "reopened-migration-executed"
    payload = (
        f'\nfrom pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n'
    ).encode()
    result = provenance_child(
        root,
        value,
        (
            "provenance=module._active_provenance\n"
            "original=provenance.source\n"
            "def raced(path):\n"
            " snapshot=original(path)\n"
            " assert len(snapshot)>65536\n"
            f" pathlib.Path(path).write_bytes(snapshot+{payload!r})\n"
            " return snapshot\n"
            "provenance.source=raced\n"
            f"snapshot=provenance.migration({name!r})\n"
            f"assert not pathlib.Path({str(marker)!r}).exists()\n"
            "assert snapshot['revision']=='c178b2c3d539'\n"
            "print('snapshot-only')\n"
        ),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "snapshot-only" and not marker.exists()


@pytest.mark.parametrize("hidden", ["skip-worktree", "assume-unchanged"])
def test_bootstrap_refuses_hidden_migration_before_first_party_execution(tmp_path, hidden):
    marker = tmp_path / "profile-imported"
    root, _, value = provenance_repository(
        tmp_path,
        bootstrap=True,
        imports=f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')",
    )
    path = root / "alembic/versions/c178b2c3d539_add_portfolio_source_observations.py"
    provenance_git(root, "update-index", "--" + hidden, path.relative_to(root).as_posix())
    path.write_bytes(path.read_bytes() + b"\nraise AssertionError('unadmitted migration')\n")
    assert not provenance_git(root, "status", "--porcelain")
    result = provenance_child(root, value, "module.load_runtime()\n")
    assert result.returncode != 0 and "SOURCE_RECEIPT_IMPORT_REFUSED" in result.stderr
    assert not marker.exists()


def test_migration_exception_restores_module_and_argv_context(tmp_path, monkeypatch):
    from scripts.validation import qualify_source_receipts as runner

    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    name = "c178b2c3d539_add_portfolio_source_observations.py"
    path = root / "alembic/versions" / name
    path.write_bytes(path.read_bytes() + b"\nraise RuntimeError('verified fixture exception')\n")
    provenance_git(root, "add", "--", path.relative_to(root).as_posix())
    provenance_git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "verified exception context",
    )
    value.update(
        source_sha=provenance_git(root, "rev-parse", "HEAD"),
        source_tree=provenance_git(root, "rev-parse", "HEAD^{tree}"),
    )
    sentinel = ModuleType("sentinel")
    monkeypatch.setitem(sys.modules, "<run_path>", sentinel)
    original_argv = sys.argv[0]
    provenance = runner.SourceProvenance(value, root).qualify()
    with pytest.raises(RuntimeError, match="verified fixture exception"):
        provenance.migration(name)
    assert sys.argv[0] == original_argv and sys.modules["<run_path>"] is sentinel


def test_ordinary_http_migration_fixture_aliases_remain_unchanged(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    path = root / profile.NODE.split("::")[0]
    nodes = [
        node
        for node in ast.parse(path.read_text()).body
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id
                in {"observation_schema", "preverification_observation_schema", "observation_lease"}
                for target in node.targets
            )
            or isinstance(node, ast.If)
            and "LOTUS_OPERATOR_SOURCE_RECEIPT" in ast.unparse(node.test)
        )
    ]
    assert len(nodes) == 4
    routes = SimpleNamespace(
        observation_schema=object(),
        preverification_observation_schema=object(),
        observation_lease=object(),
    )
    monkeypatch.delenv("LOTUS_OPERATOR_SOURCE_RECEIPT", raising=False)
    namespace = dict(os=os, routes=routes)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    for name in ("observation_schema", "preverification_observation_schema", "observation_lease"):
        assert namespace[name] is getattr(routes, name)


def test_native_bootstrap_git_capture_cap_refuses_without_disclosing_output(tmp_path):
    from scripts.validation import qualify_source_receipts as runner

    root, _, value = provenance_repository(tmp_path)
    config = root / ".git/config"
    with config.open("a") as stream:
        stream.write("\n[overflow]\n")
        for number in range(5000):
            stream.write(f" longpublickey{number:05d} = harmless\n")
    with pytest.raises(runner.EnvironmentRefused) as error:
        runner.SourceProvenance(value, root).qualify()
    assert error.value.args == ("SOURCE_RECEIPT_OBSERVATION_REFUSED",)


def test_bootstrap_expired_deadline_refuses_before_native_process(monkeypatch):
    from scripts.validation import qualify_source_receipts as runner

    launch = MagicMock()
    monkeypatch.setattr(runner.subprocess, "Popen", launch)
    with pytest.raises(runner.EnvironmentRefused, match="ADMISSION_EXPIRED"):
        runner.bootstrap_observe(["git", "status"], runner.ROOT, NOW.timestamp() - 1)
    launch.assert_not_called()


def test_bootstrap_timeout_retires_and_drains_its_native_process(monkeypatch):
    import io

    from scripts.validation import qualify_source_receipts as runner

    process = MagicMock(returncode=-1)
    process.stdout = io.BytesIO(b"harmless public observation")
    process.wait.side_effect = [subprocess.TimeoutExpired("fixed Git", 5), -1]
    launch = MagicMock(return_value=process)
    monkeypatch.setattr(runner.subprocess, "Popen", launch)
    deadline = NOW.timestamp() + 300
    with pytest.raises(runner.EnvironmentRefused) as error:
        runner.bootstrap_observe(["git", "status"], runner.ROOT, deadline)
    assert error.value.args == ("SOURCE_RECEIPT_OBSERVATION_REFUSED",)
    process.kill.assert_called_once()
    assert process.stdout.closed and process.wait.call_count == 2
    assert 0 < process.wait.call_args_list[0].kwargs["timeout"] <= 5
    assert launch.call_args.kwargs["stdin"] == subprocess.DEVNULL


def test_bootstrap_process_startup_consumes_the_same_observation_window(monkeypatch):
    import io

    from scripts.validation import qualify_source_receipts as runner

    process = MagicMock(returncode=0)
    process.stdout = io.BytesIO(b"public")
    monkeypatch.setattr(runner.subprocess, "Popen", MagicMock(return_value=process))
    clock = MagicMock(side_effect=[100.0, 100.0, 104.0, 104.0])
    monkeypatch.setattr(runner.time, "time", clock)
    assert runner.bootstrap_observe(["git", "status"], runner.ROOT, 200) == b"public"
    assert process.wait.call_args_list[0].kwargs["timeout"] == 1.0
    assert process.stdout.closed


@pytest.fixture(autouse=True)
def admission_clock(monkeypatch):
    """Keep synthetic admissions independent of collection-to-execution delay."""
    monkeypatch.setattr(sys.modules[__name__], "NOW", datetime.now(UTC))
    monkeypatch.setattr(profile, "time", SimpleNamespace(time=lambda: NOW.timestamp()))


@pytest.fixture(scope="module", autouse=True)
def native_git_prerequisite():
    """The complete native controls require the real supported Git, never a spoof."""
    from scripts.validation import qualify_source_receipts as runner

    provenance = runner.SourceProvenance(admitted(now=datetime.now(UTC)))
    provenance.qualify_git_version()


def admitted(*, now=None):
    now = NOW if now is None else now
    nonce = "a" * 32
    schema = "core1227_" + "b" * 32
    return {
        "profile": profile.PROFILE,
        "repository": "sgajbi/lotus-core",
        "source_sha": "c" * 40,
        "source_tree": "d" * 40,
        "platform_source_sha": "e" * 40,
        "nonce": nonce,
        "database": "core_receipt_db_" + nonce,
        "database_oid": 123,
        "database_owner_oid": 200,
        "role": "core_receipt_role_" + nonce,
        "role_oid": 300,
        "host": "127.0.0.1",
        "port": 55432,
        "server_port": 5432,
        "server_address": "172.17.0.2",
        "server_birth": now.isoformat(),
        "container_id": "e" * 64,
        "container_birth": now.isoformat(),
        "parent_lease": "synthetic-parent",
        "parent_holder": "synthetic-owner",
        "scope_digest": "f" * 64,
        "bindings_digest": "1" * 64,
        "issued_at": (now - timedelta(seconds=10)).isoformat(),
        "run_deadline": (now + timedelta(seconds=120)).isoformat(),
        "cleanup_deadline": (now + timedelta(seconds=180)).isoformat(),
        "parent_expiry": (now + timedelta(seconds=300)).isoformat(),
        "database_marker": f"{profile.PROFILE}:{nonce}:300",
        "prerequisite_sha256": "2" * 64,
        "tls": {"sslmode": "require"},
        "operator_isolation_attested": True,
        "cases": [
            {
                "node": profile.NODE,
                "schema": schema,
                "marker": f"core1227-owned:{nonce}:{schema}",
                "http_calls": 14,
                "processes": 4,
            }
        ],
    }


def database_url(value):
    return (
        f"postgresql://{value['role']}:synthetic-private-password@{value['host']}:"
        f"{value['port']}/{value['database']}?sslmode=require"
    )


@pytest.fixture
def compiled_profile_clauses(monkeypatch, tmp_path):
    """Capture the actual fixture and both migrations through offline PostgreSQL compilation."""
    from contextlib import nullcontext

    from sqlalchemy import create_mock_engine, text

    from scripts.validation import qualify_source_receipts as runner
    from tests import conftest as harness

    migration_root, _, migration_admission = provenance_repository(tmp_path, bootstrap=True)
    provenance = runner.SourceProvenance(migration_admission, migration_root).qualify()
    monkeypatch.setattr(runner, "_active_provenance", provenance)

    value = admitted()
    case = value["cases"][0]
    clauses = []
    connection = create_mock_engine(
        "postgresql://",
        lambda sql, *a, **kw: clauses.append(str(sql.compile(dialect=connection.dialect)).strip()),
    )
    connection.scalar = lambda sql: {
        "SELECT current_database()": value["database"],
        "SELECT session_user": value["role"],
    }[str(sql)]
    engine = SimpleNamespace(begin=lambda: nullcontext(connection))
    authority = SimpleNamespace(
        target=SimpleNamespace(database=value["database"], username=value["role"]), **case
    )
    operator = SimpleNamespace(authorize=lambda *a: authority, cleanup=MagicMock())
    monkeypatch.setattr(harness, "_operator_source_session", operator)
    root = Path(__file__).resolve().parents[3]
    fixture_path = root / (
        "tests/integration/services/ingestion_service/"
        "test_portfolio_source_observation_admission_postgresql.py"
    )
    definitions = [
        copy.deepcopy(node)
        for node in ast.parse(fixture_path.read_text()).body
        if isinstance(node, ast.FunctionDef)
        and node.name in ("observation_schema", "observation_migration")
    ]
    assert len(definitions) == 2
    for definition in definitions:
        definition.decorator_list = []
    admission = ModuleType("profile_fixture_admission")
    admission.__dict__.update(__file__=str(fixture_path), text=text)
    exec(
        compile(ast.Module(body=definitions, type_ignores=[]), str(fixture_path), "exec"),
        admission.__dict__,
    )
    routes_path = root / (
        "tests/integration/services/query_control_plane_service/"
        "test_portfolio_source_observation_router_postgresql.py"
    )
    route_fixture = next(
        node
        for node in ast.parse(routes_path.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == "observation_schema"
    )
    route_fixture.decorator_list = []
    routes = ModuleType("profile_fixture_routes")
    routes.__dict__.update(text=text, admission_proof=admission)
    routes.preverification_observation_schema = SimpleNamespace(
        __wrapped__=admission.observation_schema
    )
    routes.fact_verification_migration = MagicMock(side_effect=AssertionError("unverified caller"))
    exec(
        compile(ast.Module(body=[route_fixture], type_ignores=[]), str(routes_path), "exec"),
        routes.__dict__,
    )
    routes.observation_schema = SimpleNamespace(__wrapped__=routes.observation_schema)
    http_path = root / profile.NODE.split("::")[0]
    operator_boundary = next(
        node
        for node in ast.parse(http_path.read_text()).body
        if isinstance(node, ast.If) and "LOTUS_OPERATOR_SOURCE_RECEIPT" in ast.unparse(node.test)
    )
    namespace = dict(os=os, pytest=pytest, routes=routes)
    monkeypatch.setenv("LOTUS_OPERATOR_SOURCE_RECEIPT", "1")
    exec(
        compile(ast.Module(body=[operator_boundary], type_ignores=[]), str(http_path), "exec"),
        namespace,
    )
    fixture = namespace["preverification_observation_schema"].__wrapped__(
        engine, SimpleNamespace(node=SimpleNamespace(nodeid=profile.NODE)), monkeypatch
    )
    lease = next(fixture)
    assert lease[2:] == (case["schema"], case["marker"])
    try:
        assert namespace["observation_schema"].__wrapped__(lease, monkeypatch) is lease
    finally:
        fixture.close()
    operator.cleanup.assert_called_once_with(engine, authority)
    ddl = [sql for sql in clauses if sql.startswith(("CREATE", "ALTER", "COMMENT"))]
    assert len(ddl) == 32
    assert sum(sql.startswith("CREATE TABLE") for sql in ddl) == 8
    assert sum(sql.startswith("CREATE FUNCTION") for sql in ddl) == 3
    assert sum(sql.startswith("CREATE TRIGGER") for sql in ddl) == 8
    assert sum(sql.startswith("ALTER TABLE") for sql in ddl) == 10
    return ddl


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", "managed-compose"),
        ("repository", "foreign/core"),
        ("nonce", "../foreign"),
        ("database", "portfolio_db"),
        ("role", "postgres"),
        ("role_oid", True),
        ("database_oid", 0),
        ("port", 70000),
        ("host", "host1,host2"),
        ("database_owner_oid", 300),
        ("source_sha", "main"),
        ("source_tree", None),
        ("container_id", "unbound"),
        ("scope_digest", "missing"),
        ("bindings_digest", "missing"),
        ("database_marker", "foreign"),
        ("tls", {"options": "search_path=public"}),
        ("tls", {"sslmode": "disable"}),
        ("operator_isolation_attested", False),
        ("run_deadline", NOW.isoformat()),
        ("cleanup_deadline", NOW.isoformat()),
        ("parent_expiry", NOW.isoformat()),
        ("issued_at", (NOW + timedelta(days=1)).isoformat()),
        ("cases", []),
        ("cases", [{"node": "tests/integration"}]),
    ],
)
def test_bad_admission_refuses_before_engine_connect_or_sql(monkeypatch, field, value):
    engine = MagicMock()
    monkeypatch.setattr(profile.OperatorSourceSession, "engine", engine)
    candidate = admitted()
    candidate[field] = value
    with pytest.raises(profile.ProfileRefused):
        profile.validate_admission(candidate, now=NOW.timestamp(), environment={}, platform="nt")
    engine.assert_not_called()
    engine.connect.assert_not_called()
    engine.execute.assert_not_called()


@pytest.mark.parametrize("name", profile.OVERRIDES)
def test_inherited_overrides_refuse_before_connect(monkeypatch, name):
    engine = MagicMock()
    monkeypatch.setattr(profile.OperatorSourceSession, "engine", engine)
    with pytest.raises(profile.ProfileRefused, match="INHERITED_OVERRIDE"):
        profile.validate_admission(
            admitted(), now=NOW.timestamp(), environment={name: "private"}, platform="nt"
        )
    engine.assert_not_called()


@pytest.mark.parametrize(
    "name",
    [
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
        "DOCKER_API_VERSION",
        "PYTHONPATH",
        "PYTHONUSERBASE",
    ],
)
def test_execution_environment_rejects_client_and_import_overrides(name):
    with pytest.raises(profile.ProfileRefused):
        profile.validate_admission(
            admitted(), now=NOW.timestamp(), environment={name: "foreign-input"}, platform="nt"
        )


def test_admission_rejects_localhost_before_engine(monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr(profile.OperatorSourceSession, "engine", engine)
    value = admitted()
    value["host"] = "localhost"
    with pytest.raises(profile.ProfileRefused, match="ENDPOINT_INVALID"):
        profile.validate_admission(value, now=NOW.timestamp(), environment={}, platform="nt")
    engine.assert_not_called()


def test_container_observation_pins_local_default_context(monkeypatch):
    value = admitted()
    commands = []

    def observation(command, **kwargs):
        commands.append(command)
        if "context" in command:
            return json.dumps("npipe:////./pipe/docker_engine").encode()
        return json.dumps(
            {
                "Id": value["container_id"],
                "State": {"Running": True, "StartedAt": value["container_birth"]},
                "NetworkSettings": {
                    "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(value["port"])}]}
                },
            }
        ).encode()

    monkeypatch.setattr(profile, "observe", observation)
    profile.qualify_container(value)
    assert len(commands) == 2
    assert all(command[:3] == ["docker", "--context", "default"] for command in commands)


@pytest.fixture(autouse=True)
def clean_profile_environment(monkeypatch):
    for name in tuple(os.environ):
        if (
            name.upper().startswith(("GIT_", "PG", "DOCKER_", "PYTHON"))
            or name in profile.OVERRIDES
            or name in {"PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT"}
        ):
            monkeypatch.delenv(name)


@pytest.mark.parametrize(
    "name,value",
    [
        ("GIT_DIR", "private-foreign-root"),
        ("GIT_WORK_TREE", "private-foreign-root"),
        ("GIT_COMMON_DIR", "private-foreign-root"),
        ("GIT_INDEX_FILE", "private-index"),
        ("GIT_OBJECT_DIRECTORY", "private-objects"),
        ("GIT_ALTERNATE_OBJECT_DIRECTORIES", "private-objects"),
        ("GIT_CONFIG", "private-config"),
        ("GIT_CONFIG_SYSTEM", "private-config"),
        ("GIT_CONFIG_GLOBAL", "private-config"),
        ("GIT_CONFIG_NOSYSTEM", "1"),
        ("GIT_CONFIG_COUNT", "1"),
        ("GIT_CONFIG_KEY_0", "core.worktree"),
        ("GIT_CONFIG_VALUE_0", "private-foreign-root"),
        ("GIT_CONFIG_PARAMETERS", "'core.worktree=private-foreign-root'"),
        ("GIT_CEILING_DIRECTORIES", "private-root"),
        ("GIT_DISCOVERY_ACROSS_FILESYSTEM", "1"),
        ("GIT_NAMESPACE", "foreign"),
        ("GIT_REPLACE_REF_BASE", "refs/foreign"),
        ("GIT_SHALLOW_FILE", "private-shallow"),
        ("GIT_FUTURE_CONTEXT_OVERRIDE", "private-future-input"),
        ("GIT_DIR", ""),
        ("git_work_tree", "private-foreign-root"),
    ],
)
def test_git_context_overrides_refuse_before_source_observation(
    monkeypatch, tmp_path, clean_profile_environment, name, value
):
    monkeypatch.setenv(name, value)
    observation = MagicMock(side_effect=AssertionError("source observation reached"))
    monkeypatch.setattr(profile, "observe", observation)
    with pytest.raises(profile.ProfileRefused) as error:
        profile.qualify_source(admitted(), tmp_path)
    assert error.value.args == ("SOURCE_RECEIPT_INHERITED_OVERRIDE",)
    assert name not in str(error.value) and "private" not in str(error.value)
    observation.assert_not_called()


@pytest.mark.parametrize(
    "override,override_value",
    [
        ("GIT_DIR", "private-foreign-root"),
        ("docker_context", ""),
        ("DOCKER_CONFIG", "private-config"),
        ("PYTHONPATH", "private-path"),
        ("pythonuserbase", ""),
    ],
)
@pytest.mark.parametrize(
    "entry",
    [
        "admission",
        "cleanup_admission",
        "source",
        "observation",
        "cli",
        "cli_child",
        "cli_cleanup",
        "child",
        "cleanup_child",
        "execute",
        "recover",
        "api",
    ],
)
def test_git_override_refuses_every_entry_before_git_or_private_dispatch(
    monkeypatch, tmp_path, capsys, clean_profile_environment, entry, override, override_value
):
    from scripts.validation import qualify_source_receipts as runner
    from tests.test_support import source_receipt_process_custody as custody

    value = admitted()
    monkeypatch.setenv(override, override_value)
    observation = MagicMock(side_effect=AssertionError("source observation reached"))
    owned = MagicMock(
        return_value=SimpleNamespace(
            exit_code=0,
            timed_out=False,
            output_limit_exceeded=False,
            descendants_retired=True,
            streams_drained=True,
        )
    )
    monkeypatch.setattr(custody, "run_owned", owned)
    monkeypatch.setattr(custody, "require_current_job", lambda: None)
    monkeypatch.setattr(runner, "require_current_job", lambda: None)
    monkeypatch.setattr(runner, "require_supported_os", lambda: None)
    if entry != "observation":
        monkeypatch.setattr(profile, "observe", observation)
    private = MagicMock()
    monkeypatch.setattr(runner, "private_input", private)
    factory = MagicMock()
    monkeypatch.setattr(profile, "OperatorSourceSession", factory)
    monkeypatch.setattr(profile, "load_admission", lambda *args: value)
    args = SimpleNamespace(workspace_root=str(tmp_path))

    if entry.startswith("cli"):
        argv = [
            "qualify-source-receipts",
            "--admission",
            "synthetic-admission",
            "--admission-sha256",
            "0" * 64,
            "--workspace-root",
            str(tmp_path),
        ]
        argv += {"cli": [], "cli_child": ["--child"], "cli_cleanup": ["--cleanup-child"]}[entry]
        monkeypatch.setattr(sys, "argv", argv)
        assert runner.main() == 2
        assert json.loads(capsys.readouterr().out) == {
            "success": False,
            "reason": "SOURCE_RECEIPT_REFUSED_OR_FAILED",
        }
    else:
        with pytest.raises(profile.ProfileRefused) as error:
            if entry in {"admission", "cleanup_admission"}:
                profile.validate_admission(
                    value,
                    now=NOW.timestamp(),
                    environment=os.environ,
                    platform="nt",
                    cleanup_mode=entry == "cleanup_admission",
                )
            elif entry == "source":
                profile.qualify_source(value, tmp_path)
            elif entry == "observation":
                profile.observe(["git", "rev-parse", "HEAD"], tmp_path)
            elif entry in {"child", "cleanup_child"}:
                getattr(runner, entry)(value, "private", str(tmp_path))
            elif entry == "execute":
                runner.execute(value, "private", args)
            elif entry == "recover":
                runner.recover(
                    value,
                    "private",
                    args,
                    dict(os.environ),
                    SimpleNamespace(descendants_retired=True),
                )
            else:
                monkeypatch.setenv("LOTUS_SOURCE_RECEIPT_ADMISSION", "synthetic-admission")
                monkeypatch.setenv("LOTUS_SOURCE_RECEIPT_ADMISSION_SHA256", "0" * 64)
                profile.attach_api({})
        expected = (
            "PYTHON_OVERRIDE" if override.upper().startswith("PYTHON") else "INHERITED_OVERRIDE"
        )
        assert error.value.args == ("SOURCE_RECEIPT_" + expected,)
    observation.assert_not_called()
    owned.assert_not_called()
    private.assert_not_called()
    if entry != "execute":
        factory.assert_not_called()
    factory.return_value.engine.assert_not_called()


@pytest.mark.parametrize(
    "name",
    [
        "GIT_CONFIG_COUNT",
        "docker_host",
        "DOCKER_FUTURE_OVERRIDE",
        "PYTHONUSERBASE",
        "pythonhome",
        "PGHOST",
        "pytest_addopts",
    ],
)
def test_empty_or_case_variant_overrides_fail_closed(name):
    with pytest.raises(profile.ProfileRefused):
        profile.deny_overrides({name: ""})


def test_profile_environment_accepts_only_canonical_roots_and_preserves_custody():
    from scripts.development.repository_python import repository_python_roots
    from scripts.validation import qualify_source_receipts as runner

    source = {"SYSTEMROOT": "C:/Windows", "LOTUS_SOURCE_RECEIPT_PARENT_PID": "42"}
    child = runner.profile_environment(source)
    assert child["PYTHONPATH"].split(os.pathsep) == [
        str(path) for path in repository_python_roots()
    ]
    assert child["SYSTEMROOT"] == source["SYSTEMROOT"]
    assert child["LOTUS_SOURCE_RECEIPT_PARENT_PID"] == "42"
    assert child["PYTHONNOUSERSITE"] == child["PYTHONSAFEPATH"] == "1"
    profile.deny_overrides(child)
    assert "PYTHONPATH" not in source
    for path in (
        child["PYTHONPATH"] + os.pathsep + "foreign",
        os.pathsep.join(reversed(child["PYTHONPATH"].split(os.pathsep))),
    ):
        with pytest.raises(profile.ProfileRefused, match="PYTHON_OVERRIDE"):
            profile.deny_overrides({"PYTHONPATH": path})
    for name in ("PYTHONNOUSERSITE", "PYTHONSAFEPATH"):
        with pytest.raises(profile.ProfileRefused):
            profile.deny_overrides({name: "0"})


@pytest.mark.parametrize(
    "endpoint",
    [
        "tcp://127.0.0.1:2375",
        "tcp://remote:2376",
        "ssh://remote",
        "unix:///var/run/docker.sock",
        "npipe:////./pipe/foreign",
        None,
        {},
        "",
    ],
)
def test_context_endpoint_refusal_precedes_container_and_engine(monkeypatch, endpoint):
    observation = MagicMock(return_value=json.dumps(endpoint).encode())
    engine = MagicMock()
    monkeypatch.setattr(profile, "observe", observation)
    monkeypatch.setattr(profile.OperatorSourceSession, "engine", engine)
    with pytest.raises(profile.ProfileRefused, match="DOCKER_ENDPOINT_REFUSED"):
        profile.qualify_container(admitted())
    assert observation.call_count == 1
    assert observation.call_args.args[0][3:6] == ["context", "inspect", "default"]
    engine.assert_not_called()


@pytest.mark.parametrize(
    "raw", [b"not-json", b"\xff", b"x" * 65537], ids=["json", "encoding", "oversize"]
)
def test_malformed_context_output_never_reaches_container(monkeypatch, raw):
    observation = MagicMock(return_value=raw)
    monkeypatch.setattr(profile, "observe", observation)
    with pytest.raises(profile.ProfileRefused, match="DOCKER_ENDPOINT_REFUSED"):
        profile.qualify_container(admitted())
    assert observation.call_count == 1


@pytest.mark.parametrize("failure", ["exit", "timeout", "output", "descendants", "streams"])
def test_failed_native_context_receipt_never_reaches_container(monkeypatch, failure):
    from tests.test_support import source_receipt_process_custody as custody

    receipt = SimpleNamespace(
        exit_code=int(failure == "exit"),
        timed_out=failure == "timeout",
        output_limit_exceeded=failure == "output",
        descendants_retired=failure != "descendants",
        streams_drained=failure != "streams",
    )
    owned = MagicMock(return_value=receipt)
    monkeypatch.setattr(custody, "run_owned", owned)
    with pytest.raises(profile.ProfileRefused):
        profile.qualify_container(admitted())
    assert owned.call_count == 1
    assert owned.call_args.kwargs["timeout"] == 5
    assert owned.call_args.kwargs["output_limit"] == 65536


def test_context_and_container_share_validated_environment_snapshot(monkeypatch):
    value = admitted()
    snapshots = []

    def observe(command, **kwargs):
        snapshots.append(dict(kwargs["environment"]))
        if "context" in command:
            monkeypatch.setenv("DOCKER_HOST", "later-change")
            return json.dumps("npipe:////./pipe/docker_engine").encode()
        return json.dumps(
            {
                "Id": value["container_id"],
                "State": {"Running": True, "StartedAt": value["container_birth"]},
                "NetworkSettings": {
                    "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(value["port"])}]}
                },
            }
        ).encode()

    monkeypatch.setattr(profile, "observe", observe)
    profile.qualify_container(value)
    assert len(snapshots) == 2 and snapshots[0] == snapshots[1]
    assert "DOCKER_HOST" not in snapshots[1]


@pytest.mark.parametrize("host", ["localhost", "::1", "0.0.0.0", "127.1", "alias.example"])
def test_alias_admission_and_dsn_fail_before_engine(monkeypatch, host):
    engine = MagicMock()
    monkeypatch.setattr(profile.OperatorSourceSession, "engine", engine)
    value = admitted()
    with pytest.raises(profile.ProfileRefused, match="DSN_REFUSED"):
        profile.OperatorSourceSession(value, database_url(value).replace("127.0.0.1", host))
    value["host"] = host
    with pytest.raises(profile.ProfileRefused, match="ENDPOINT_INVALID"):
        profile.validate_admission(value, now=NOW.timestamp(), environment={}, platform="nt")
    engine.assert_not_called()


def test_api_preflight_refuses_before_private_descriptor(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    stdin = MagicMock()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setenv("LOTUS_OPERATOR_SOURCE_RECEIPT", "1")
    monkeypatch.setenv("DOCKER_CONTEXT", "")
    with pytest.raises(SystemExit) as error:
        runpy.run_path(
            str(root / "tests/test_support/portfolio_source_http_process.py"), run_name="__main__"
        )
    assert error.value.code == 2
    stdin.readline.assert_not_called()


def test_isolated_script_refuses_bad_environment_before_first_party_imports(tmp_path):
    from scripts.validation import qualify_source_receipts as runner

    marker = tmp_path / "first-party-imported"
    code = (
        "import sys,runpy,pathlib\n"
        "class RefuseSource:\n"
        " def find_spec(self,fullname,*args):\n"
        "  if fullname.split('.')[0] in ('scripts','tests'):\n"
        f"   pathlib.Path({str(marker)!r}).write_text(fullname)\n"
        "   raise AssertionError('source imported')\n"
        "sys.meta_path.insert(0,RefuseSource())\n"
        f"runpy.run_path({str(Path(runner.__file__).resolve())!r},run_name='__main__')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        env={**os.environ, "DOCKER_HOST": ""},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 2 and not marker.exists()
    assert json.loads(completed.stdout) == {
        "success": False,
        "reason": "SOURCE_RECEIPT_REFUSED_OR_FAILED",
    }
    assert not completed.stderr


def test_process_startup_and_dependency_markers_old_red_then_isolated_refusal(tmp_path):
    from scripts.validation import qualify_source_receipts as runner

    root = runner.ROOT
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    marker = tmp_path / "imported.jsonl"
    modules = ("sitecustomize", "pytest", "sqlalchemy", "psycopg2", "asyncpg", "uvicorn")
    for name in modules:
        (foreign / (name + ".py")).write_text(
            "from pathlib import Path\n"
            f"with Path({str(marker)!r}).open('a') as stream:\n"
            f" stream.write({name!r} + '\\n')\n"
        )
    bad = {**os.environ, "PYTHONPATH": str(foreign)}
    old = subprocess.run(
        [
            sys.executable,
            "-B",
            str(root / "scripts/development/repository_python.py"),
            "-c",
            "import pytest,sqlalchemy,psycopg2,asyncpg,uvicorn",
        ],
        env=bad,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert old.returncode == 0, old.stderr
    observed = marker.read_text().splitlines()
    assert set(observed) == set(modules)
    new = subprocess.run(
        [sys.executable, "-I", "-B", str(Path(runner.__file__).resolve())],
        env=bad,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert new.returncode == 2 and not new.stderr
    assert json.loads(new.stdout)["reason"] == "SOURCE_RECEIPT_REFUSED_OR_FAILED"
    assert marker.read_text().splitlines() == observed


def test_public_help_is_stdlib_only_without_source_private_or_native_dispatch(tmp_path):
    from scripts.validation import qualify_source_receipts as runner

    entry = str(Path(runner.__file__).resolve())
    code = (
        "import sys,runpy,subprocess\n"
        "class RefuseDependencies:\n"
        " def find_spec(self,fullname,*args):\n"
        "  if fullname.split('.')[0] in ('scripts','tests','pytest','sqlalchemy','uvicorn'):\n"
        "   raise AssertionError('first-party or third-party import during help')\n"
        "class RefusePrivate:\n"
        " @property\n"
        " def buffer(self): raise AssertionError('private input during help')\n"
        "def refuse_native(*args,**kwargs): raise AssertionError('native dispatch during help')\n"
        "sys.meta_path.insert(0,RefuseDependencies())\n"
        "sys.stdin=RefusePrivate()\n"
        "subprocess.Popen=refuse_native\n"
        f"sys.argv=[{entry!r},'--help']\n"
        "trusted={'_SOURCE_RECEIPT_VERIFIED_ENTRY':True}\n"
        f"try: runpy.run_path({entry!r},run_name='__main__',init_globals=trusted)\n"
        "except SystemExit as result: assert result.code==0\n"
    )
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP")
        if name in os.environ
    }
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0 and result.stdout.startswith("usage:") and not result.stderr


@pytest.mark.parametrize("api", [False, True])
def test_valid_isolated_bootstrap_and_sanitized_api_resolve_qualified_dependencies(tmp_path, api):
    root, _, value = provenance_repository(tmp_path, bootstrap=True)
    userbase = tmp_path / "custom-userbase"
    user_site = (
        userbase / f"Python{sys.version_info.major}{sys.version_info.minor}" / "site-packages"
    )
    user_site.mkdir(parents=True)
    marker = tmp_path / "user-site-executed"
    (user_site / "usercustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    )
    code = (
        "import site\n"
        + ("from tests.test_support import portfolio_source_http_process\n" if api else "")
        + "import pytest,sqlalchemy,psycopg2,asyncpg,uvicorn,portfolio_common\n"
        + "assert sys.flags.no_user_site and sys.flags.safe_path\n"
        + "assert site.ENABLE_USER_SITE is False\n"
        + "from scripts.validation.qualify_source_receipts import profile_environment\n"
        + "assert 'PYTHONUSERBASE' not in profile_environment()\n"
        + "names=[type(finder).__name__ for finder in sys.meta_path]\n"
        + "assert 'RepositoryFirstPartyImportGuard' in names\n"
        + "modules=(pytest,sqlalchemy,psycopg2,asyncpg,uvicorn,portfolio_common)\n"
        + "origins={m.__name__:str(pathlib.Path(m.__file__).resolve()) for m in modules}\n"
        + "print(json.dumps(origins))\n"
    )
    completed = provenance_child(root, value, code, userbase=userbase)
    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()
    origins = json.loads(completed.stdout)
    assert Path(origins.pop("portfolio_common")).is_relative_to(root)
    for origin in origins.values():
        assert Path(origin).is_relative_to(Path(sys.prefix).resolve())


def test_custom_userbase_refuses_when_actual_no_user_site_flag_is_absent(tmp_path):
    from scripts.validation import qualify_source_receipts as runner

    environment = runner.profile_environment()
    environment.pop("PYTHONNOUSERSITE")
    environment["PYTHONUSERBASE"] = str(tmp_path / "foreign-user-base")
    code = (
        "import sys,os\n"
        "from scripts.validation import qualify_source_receipts as runner\n"
        "assert not sys.flags.no_user_site\n"
        "try: runner.validate_environment(os.environ)\n"
        "except runner.EnvironmentRefused: print('refused')\n"
        "else: raise AssertionError('non-disabled userbase accepted')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0 and completed.stdout.strip() == "refused", completed.stderr


@pytest.mark.parametrize("missing", ["PYTHONNOUSERSITE", "PYTHONSAFEPATH"])
def test_api_preflight_requires_actual_startup_flags(tmp_path, missing):
    from scripts.validation import qualify_source_receipts as runner

    environment = runner.profile_environment()
    environment.pop(missing)
    environment["LOTUS_OPERATOR_SOURCE_RECEIPT"] = "1"
    # Store Python may inject an inert userbase; leave this independent flag control empty.
    code = (
        "import os\n"
        "os.environ.pop('PYTHONUSERBASE',None)\n"
        "from tests.test_support.portfolio_source_http_process import profile_preflight\n"
        "try: profile_preflight()\n"
        "except ValueError: print('refused')\n"
        "else: raise AssertionError('missing startup flag accepted')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0 and completed.stdout.strip() == "refused", completed.stderr


@pytest.mark.parametrize("missing", ["PYTHONPATH", "LOTUS_REPOSITORY_ROOT"])
def test_api_preflight_requires_complete_canonical_environment_before_descriptor(tmp_path, missing):
    from scripts.validation import qualify_source_receipts as runner

    marker = tmp_path / "private-descriptor-read"
    helper = str(runner.ROOT / "tests/test_support/portfolio_source_http_process.py")
    environment = runner.profile_environment()
    environment["LOTUS_OPERATOR_SOURCE_RECEIPT"] = "1"
    code = (
        "import os,sys,runpy,pathlib\n"
        "assert sys.flags.no_user_site and sys.flags.safe_path\n"
        f"os.environ.pop({missing!r})\n"
        "class NoPrivateRead:\n"
        " def readline(self,*args):\n"
        f"  pathlib.Path({str(marker)!r}).write_text('read')\n"
        "  raise AssertionError('private read reached')\n"
        "sys.stdin=NoPrivateRead()\n"
        f"runpy.run_path({helper!r},run_name='__main__')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 2 and not marker.exists()
    assert not completed.stdout and not completed.stderr


@pytest.mark.parametrize("recovery", [False, True])
def test_fixed_isolated_normal_and_recovery_commands_preserve_private_custody(
    monkeypatch, tmp_path, recovery
):
    from scripts.validation import qualify_source_receipts as runner
    from tests.test_support.source_receipt_process_custody import ProcessReceipt

    value = admitted()
    args = SimpleNamespace(
        admission=str(tmp_path / "admission"),
        admission_sha256="0" * 64,
        workspace_root=str(tmp_path),
    )
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: NOW.timestamp()))
    monkeypatch.setattr(
        runner,
        "_active_provenance",
        SimpleNamespace(source=lambda path: b"qualified-cli", object=lambda path: "a" * 40),
    )
    for name in ("OperatorSourceSession", "qualify_source", "qualify_container", "qualify_parent"):
        monkeypatch.setattr(profile, name, MagicMock())
    owned = MagicMock(return_value=ProcessReceipt(2, False, False, 0, False, True, 42))
    monkeypatch.setattr(runner, "run_owned", owned)
    if recovery:
        environment = runner.profile_environment()
        environment.update(
            LOTUS_SOURCE_RECEIPT_ADMISSION=args.admission,
            LOTUS_SOURCE_RECEIPT_WORKSPACE=args.workspace_root,
        )
        runner.recover(value, "dummy", args, environment, SimpleNamespace(descendants_retired=True))
    else:
        assert runner.execute(value, "dummy", args) == 1
    assert owned.call_count == 1
    command = owned.call_args.args[0]
    kwargs = owned.call_args.kwargs
    assert command[:5] == [sys.executable, "-I", "-B", "-c", runner.SOURCE_SEED]
    assert command[5:8] == [str(runner.ROOT), "a" * 40, "cleanup" if recovery else "child"]
    assert command[8] == ("--cleanup-child" if recovery else "--child")
    assert kwargs["private_input"] == b'{"database_url": "dummy"}'
    assert kwargs["bind_launch"] is True and kwargs["cwd"] == runner.ROOT
    assert kwargs["source_snapshots"] == (b"qualified-cli", b"")
    assert kwargs["timeout"] == (60 if recovery else 100)
    assert "output_limit" not in kwargs
    profile.deny_overrides(kwargs["environment"])
    assert kwargs["environment"]["PYTHONNOUSERSITE"] == "1"
    assert kwargs["environment"]["PYTHONSAFEPATH"] == "1"


def test_nonisolated_fixed_script_refuses_without_private_read(tmp_path):
    from scripts.validation import qualify_source_receipts as runner

    completed = subprocess.run(
        [sys.executable, "-B", str(Path(runner.__file__).resolve())],
        cwd=tmp_path,
        env=runner.profile_environment(),
        input="not-a-private-descriptor",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 2 and not completed.stderr
    assert json.loads(completed.stdout) == {
        "success": False,
        "reason": "SOURCE_RECEIPT_REFUSED_OR_FAILED",
    }


def test_clean_observation_passes_the_validated_environment_snapshot(
    monkeypatch, tmp_path, clean_profile_environment
):
    from tests.test_support import source_receipt_process_custody as custody

    before = dict(os.environ)
    calls = []

    def owned(command, **kwargs):
        calls.append((command, kwargs))
        monkeypatch.setenv("GIT_DIR", "later-private-override")
        kwargs["stdout_capture"].extend(b"observed-source\n")
        return SimpleNamespace(
            exit_code=0,
            timed_out=False,
            output_limit_exceeded=False,
            descendants_retired=True,
            streams_drained=True,
        )

    monkeypatch.setattr(custody, "run_owned", owned)
    assert profile.observe(["git", "rev-parse", "HEAD"], tmp_path) == b"observed-source\n"
    assert len(calls) == 1
    assert calls[0][1]["environment"] == before
    assert calls[0][1]["environment"] is not os.environ
    assert calls[0][1]["cwd"] == tmp_path
    assert calls[0][1]["timeout"] == 5 and calls[0][1]["output_limit"] == 65536
    profile.validate_admission(admitted(), now=NOW.timestamp(), environment=before, platform="nt")


def test_foreign_git_context_hides_dirty_actual_root_but_profile_refuses(
    monkeypatch, tmp_path, clean_profile_environment
):
    from tests.test_support import source_receipt_process_custody as custody

    actual = tmp_path / "actual"
    foreign = tmp_path / "foreign"
    clean = dict(os.environ)

    def git(*arguments, environment=clean):
        return subprocess.run(
            ["git", *arguments],
            cwd=tmp_path,
            env=environment,
            check=True,
            capture_output=True,
            timeout=5,
        ).stdout

    git("init", "--quiet", str(actual))
    git("init", "--quiet", str(foreign))
    (actual / "dirty.txt").write_text("actual source is dirty")
    assert git("-C", str(actual), "status", "--porcelain").strip()
    redirected = dict(clean, GIT_DIR=str(foreign / ".git"), GIT_WORK_TREE=str(foreign))
    assert not git("-C", str(actual), "status", "--porcelain", environment=redirected)
    assert (
        git("-C", str(actual), "rev-parse", "--show-toplevel", environment=redirected)
        .decode()
        .strip()
        .replace("\\", "/")
        == foreign.as_posix()
    )
    assert (
        git("-C", str(actual), "rev-parse", "--show-toplevel").decode().strip().replace("\\", "/")
        == actual.as_posix()
    )
    owned = MagicMock()
    monkeypatch.setattr(custody, "run_owned", owned)
    monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(foreign))
    with pytest.raises(profile.ProfileRefused, match="^SOURCE_RECEIPT_INHERITED_OVERRIDE$"):
        profile.observe(["git", "status", "--porcelain"], actual)
    owned.assert_not_called()


def test_valid_manifest_and_separate_hash_then_tampering(tmp_path):
    value = admitted()
    raw = json.dumps(value).encode()
    path = tmp_path / "admission.json"
    path.write_bytes(raw)
    approved_hash = hashlib.sha256(raw).hexdigest()
    assert profile.load_admission(path, approved_hash) == value
    assert (
        profile.validate_admission(value, now=NOW.timestamp(), environment={}, platform="nt")
        == value
    )
    path.write_bytes(raw + b" ")
    with pytest.raises(profile.ProfileRefused, match="HASH_MISMATCH"):
        profile.load_admission(path, approved_hash)


def test_manifest_bounds_and_unsupported_os(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b"x" * 32769)
    with pytest.raises(profile.ProfileRefused):
        profile.load_admission(path, "0" * 64)
    with pytest.raises(profile.ProfileRefused, match="WINDOWS_REQUIRED"):
        profile.validate_admission(
            admitted(), now=NOW.timestamp(), environment={}, platform="posix"
        )


@pytest.mark.parametrize("change", ["foreign", "public", "duplicate", "budget", "extra"])
def test_case_inventory_refuses_unauthorized_nodes_schemas_and_budgets(change):
    value = admitted()
    case = value["cases"][0]
    if change == "foreign":
        case["node"] = "tests/integration/test_foreign.py"
    elif change == "public":
        case["schema"] = "public"
    elif change == "duplicate":
        value["cases"].append(copy.deepcopy(case))
    elif change == "budget":
        case["http_calls"] = 15
    else:
        case["cleanup_prefix"] = "core"
    with pytest.raises(profile.ProfileRefused):
        profile.validate_admission(value, now=NOW.timestamp(), environment={}, platform="nt")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:private@127.0.0.1:55432/portfolio_db",
        "postgresql://a:private@host1,host2:55432/foreign",
        "sqlite:///foreign.db",
    ],
)
def test_foreign_and_multitarget_dsn_refused_without_engine(url):
    with pytest.raises(profile.ProfileRefused, match="DSN_REFUSED") as error:
        profile.OperatorSourceSession(admitted(), url)
    assert "private" not in str(error.value)


@pytest.mark.parametrize("elapsed", [121, 301])
def test_collection_delay_does_not_mask_dsn_guard_or_disable_expiry(monkeypatch, elapsed):
    import time

    engine = MagicMock()
    monkeypatch.setattr(profile.OperatorSourceSession, "engine", engine)
    monkeypatch.setattr(time, "time", lambda: NOW.timestamp() + elapsed)
    test_foreign_and_multitarget_dsn_refused_without_engine("sqlite:///foreign.db")
    monkeypatch.setattr(profile.time, "time", lambda: NOW.timestamp() + elapsed)
    with pytest.raises(profile.ProfileRefused, match="ADMISSION_EXPIRED"):
        profile.OperatorSourceSession(admitted(), "sqlite:///foreign.db")
    engine.assert_not_called()


def handshake_fixture(monkeypatch):
    from contextlib import nullcontext

    import sqlalchemy
    from portfolio_common.database_models import Base
    from portfolio_common.database_runtime_profile import DatabasePoolMode
    from portfolio_common.db import create_sync_database_engine

    value = admitted()
    engine = create_sync_database_engine(
        runtime_identity="lotus-core-test",
        database_url=database_url(value),
        pool_mode=DatabasePoolMode.NULL,
    )
    connection = MagicMock()
    monkeypatch.setattr(engine, "begin", lambda: nullcontext(connection))
    connection.engine = engine
    connection.dialect = dialect()
    actual = {
        name: value[name]
        for name in (
            "database_oid",
            "database_owner_oid",
            "database",
            "role",
            "role_oid",
            "database_marker",
            "server_address",
            "server_port",
        )
    }
    actual.update(
        current_role=value["role"],
        unsafe_role=False,
        public_create=False,
        schema_create=True,
        server_birth=NOW,
    )
    privileges = [
        dict(relname=name, relkind="r", relowner=200, readable=True, writable=False)
        for name in profile.TABLES
    ]
    inspector = MagicMock()
    inspector.get_columns.side_effect = lambda name, **kw: [
        dict(name=column.name, type=column.type, nullable=column.nullable)
        for column in Base.metadata.tables[name].columns
    ]
    inspector.get_check_constraints.return_value = []
    inspector.get_pk_constraint.return_value = {"name": "synthetic", "constrained_columns": ["id"]}
    inspector.get_unique_constraints.return_value = []
    inspector.get_foreign_keys.return_value = []
    monkeypatch.setattr(sqlalchemy, "inspect", lambda connection: inspector)
    shape = {
        name: {
            "columns": [
                (column.name, str(column.type.compile(dialect=connection.dialect)), column.nullable)
                for column in Base.metadata.tables[name].columns
            ],
            "checks": [],
            "primary_key": {"name": "synthetic", "constrained_columns": ["id"]},
            "unique": [],
            "foreign_keys": [],
        }
        for name in profile.TABLES
    }
    value["prerequisite_sha256"] = profile.digest(shape)
    connection.execute.return_value.mappings.return_value.one.return_value = actual
    connection.execute.return_value.mappings.return_value.all.return_value = privileges
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    return value, engine, connection, actual, privileges


def test_valid_read_only_handshake_issues_exact_schema_and_cleanup(monkeypatch):
    value, engine, connection, actual, _ = handshake_fixture(monkeypatch)
    session = profile.OperatorSourceSession(value, database_url(value))
    assert session.handshake(connection) == actual
    authority = session.authorize(engine, profile.NODE)
    profile.require_schema_authorization(authority, engine=engine, schema=authority.schema)
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = {
        "schema_oid": 1234,
        "nspowner": value["role_oid"],
        "marker": authority.marker,
    }
    assert session.cleanup(engine, authority) == "removed"
    assert any(
        str(call.args[0]).startswith("DROP SCHEMA") for call in connection.execute.call_args_list
    )
    with pytest.raises(profile.ProfileRefused, match="CAPABILITY_INVALID"):
        profile.require_schema_authorization(authority, engine=engine, schema=authority.schema)


@pytest.mark.parametrize(
    "drift", ["role", "oid", "owner", "marker", "birth", "public", "write", "membership"]
)
def test_handshake_drift_cannot_execute_ddl(monkeypatch, drift):
    value, engine, connection, actual, privileges = handshake_fixture(monkeypatch)
    if drift == "write":
        privileges[0]["writable"] = True
    else:
        field, replacement = {
            "role": ("current_role", "foreign"),
            "oid": ("database_oid", 999),
            "owner": ("database_owner_oid", 300),
            "marker": ("database_marker", "foreign"),
            "birth": ("server_birth", NOW - timedelta(seconds=1)),
            "public": ("public_create", True),
            "membership": ("unsafe_role", True),
        }[drift]
        actual[field] = replacement
    session = profile.OperatorSourceSession(value, database_url(value))
    with pytest.raises(profile.ProfileRefused):
        session.authorize(engine, profile.NODE)
    assert not any(
        str(call.args[0]).lstrip().upper().startswith(("CREATE", "ALTER", "DROP"))
        for call in connection.execute.call_args_list
    )


@pytest.mark.parametrize("drift", ["forged", "engine", "process", "schema", "expired", "mutated"])
def test_capability_refuses_forgery_drift_and_expiry_before_sql(monkeypatch, drift):
    value, engine, connection, _, _ = handshake_fixture(monkeypatch)
    session = profile.OperatorSourceSession(value, database_url(value))
    authority = session.authorize(engine, profile.NODE)
    other_engine, schema = engine, authority.schema
    if drift == "forged":
        authority = object.__new__(profile.SourceReceiptSchemaAuthorization)
    elif drift == "engine":
        other_engine = MagicMock()
    elif drift == "process":
        object.__setattr__(authority, "pid", os.getpid() + 1)
    elif drift == "schema":
        schema = "public"
    elif drift == "expired":
        monkeypatch.setattr(profile.time, "time", lambda: NOW.timestamp() + 1000)
    else:
        session.admission["role_oid"] += 1
    connection.execute.reset_mock()
    with pytest.raises(profile.ProfileRefused):
        profile.require_schema_authorization(authority, engine=other_engine, schema=schema)
    connection.execute.assert_not_called()


def test_collection_rejects_extra_node_and_broad_cleanup(monkeypatch):
    value = admitted()
    session = profile.OperatorSourceSession(value, database_url(value))
    monkeypatch.setattr(profile, "operator_session", lambda: session)
    item = SimpleNamespace(nodeid=profile.NODE, fixturenames=["observation_schema"])
    profile.validate_collection([item])
    for bad in (
        SimpleNamespace(nodeid="foreign", fixturenames=[]),
        SimpleNamespace(nodeid=profile.NODE, fixturenames=["clean_db"]),
        SimpleNamespace(nodeid=profile.NODE, fixturenames=["docker_services"]),
    ):
        with pytest.raises(profile.ProfileRefused, match="COLLECTION_REFUSED"):
            profile.validate_collection([bad])


@pytest.mark.parametrize("drift", [None, "head", "dirty", "case_inventory"])
def test_exact_source_and_case_preflight_before_engine(
    monkeypatch, tmp_path, clean_profile_environment, drift
):
    root, _, value = provenance_repository(tmp_path)
    if drift == "case_inventory":
        value["cases"][0]["node"] += "[cash]"
    if drift == "head":
        value["source_sha"] = "0" * 40
    if drift == "dirty":
        (root / profile.NODE.split("::")[0]).write_text("unreviewed source")
    monkeypatch.setattr(profile, "observe", native_provenance_observer)
    engine = MagicMock()
    monkeypatch.setattr(profile.OperatorSourceSession, "engine", engine)
    if drift is None:
        profile.qualify_source(value, root)
    else:
        code = {
            "head": "SOURCE_RECEIPT_SOURCE_MISMATCH",
            "dirty": "SOURCE_RECEIPT_DIRTY_SOURCE",
            "case_inventory": "SOURCE_RECEIPT_SOURCE_CASE_MISMATCH",
        }[drift]
        with pytest.raises(profile.ProfileRefused, match="^" + code + "$"):
            profile.qualify_source(value, root)
    engine.assert_not_called()


@pytest.mark.parametrize(
    "drift",
    [None, "container", "birth", "port", "ambiguous", "oversize", "stopped", "running_type"],
)
def test_container_preflight_refuses_drift_before_engine(monkeypatch, drift):
    value = admitted()
    ports = [{"HostIp": "127.0.0.1", "HostPort": str(value["port"])}]
    actual = {
        "Id": value["container_id"],
        "State": {"Running": True, "StartedAt": value["container_birth"]},
        "NetworkSettings": {"Ports": {"5432/tcp": ports}},
    }
    if drift == "container":
        actual["Id"] = "0" * 64
    elif drift == "birth":
        actual["State"]["StartedAt"] = "foreign"
    elif drift == "port":
        ports[0]["HostPort"] = "1"
    elif drift == "ambiguous":
        ports.append(ports[0])
    elif drift == "stopped":
        actual["State"]["Running"] = False
    elif drift == "running_type":
        actual["State"]["Running"] = "false"
    raw = b"x" * 65537 if drift == "oversize" else json.dumps(actual).encode()
    monkeypatch.setattr(
        profile,
        "observe",
        lambda command, **kw: (
            json.dumps("npipe:////./pipe/docker_engine").encode() if "context" in command else raw
        ),
    )
    engine = MagicMock()
    monkeypatch.setattr(profile.OperatorSourceSession, "engine", engine)
    if drift is None:
        profile.qualify_container(value)
    else:
        with pytest.raises(profile.ProfileRefused):
            profile.qualify_container(value)
    engine.assert_not_called()


@pytest.mark.parametrize(
    "bindings",
    [
        [{"HostIp": "0.0.0.0", "HostPort": "55432"}],
        [{"HostIp": "192.0.2.1", "HostPort": "55432"}],
        [{"HostIp": "::1", "HostPort": "55432"}],
        [
            {"HostIp": "127.0.0.1", "HostPort": "55432"},
            {"HostIp": "192.0.2.1", "HostPort": "55432"},
        ],
        [
            {"HostIp": "192.0.2.1", "HostPort": "55432"},
            {"HostIp": "127.0.0.1", "HostPort": "55432"},
        ],
        [{"HostIp": "127.0.0.1", "HostPort": "55432"}, {"HostIp": "::", "HostPort": "55432"}],
        [
            {"HostIp": "127.0.0.1", "HostPort": "55432"},
            {"HostIp": "127.0.0.1", "HostPort": "55432"},
        ],
        [],
        None,
        {},
        "127.0.0.1",
        [None],
        [[]],
        [{}],
        [{"HostIp": "127.0.0.1"}],
        [{"HostPort": "55432"}],
        [{"HostIp": "127.0.0.1", "HostPort": 55432}],
    ],
)
def test_container_rejects_entire_external_or_malformed_binding_list(monkeypatch, bindings):
    value = admitted()
    raw = json.dumps(
        {
            "Id": value["container_id"],
            "State": {"Running": True, "StartedAt": value["container_birth"]},
            "NetworkSettings": {"Ports": {"5432/tcp": bindings}},
        }
    ).encode()
    monkeypatch.setattr(
        profile,
        "observe",
        lambda command, **kw: (
            json.dumps("npipe:////./pipe/docker_engine").encode() if "context" in command else raw
        ),
    )
    engine = MagicMock()
    monkeypatch.setattr(profile.OperatorSourceSession, "engine", engine)
    with pytest.raises(profile.ProfileRefused, match="^SOURCE_RECEIPT_CONTAINER_MISMATCH$"):
        profile.qualify_container(value)
    engine.assert_not_called()


@pytest.mark.parametrize(
    "drift", [None, "lease", "holder", "operation", "scope", "bindings", "expiry"]
)
def test_parent_lease_preflight_refuses_foreign_and_stale_without_sql(
    monkeypatch, tmp_path, drift, clean_profile_environment
):
    root, workspace, value, record, book, _, marker = pinned_parent_fixture(tmp_path)
    monkeypatch.setattr(profile, "observe", native_provenance_observer)
    field = {
        "lease": "id",
        "holder": "holder",
        "operation": "operation",
        "scope": "scopeDigest",
        "expiry": "expiryUtc",
    }.get(drift)
    if field:
        record[field] = NOW.isoformat() if drift == "expiry" else "foreign"
    if drift == "bindings":
        record["bindings"] = ["foreign"]
    book.write_text(json.dumps({"record": record}))
    original = book.read_bytes()
    if drift is None:
        profile.qualify_parent(value, workspace, root=root)
    else:
        with pytest.raises(profile.ProfileRefused):
            profile.qualify_parent(value, workspace, root=root)
    assert marker.read_text() == "reviewed"
    assert book.read_bytes() == original


@pytest.mark.parametrize("managed", [False, True])
def test_parent_pinned_helper_accepts_primary_and_managed_core(
    monkeypatch, tmp_path, managed, clean_profile_environment
):
    root, workspace, value, record, book, helper, marker = pinned_parent_fixture(
        tmp_path, managed=managed
    )
    monkeypatch.setattr(profile, "observe", native_provenance_observer)
    helper.write_bytes(helper.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    original = book.read_bytes()
    assert record["scope"]["sources"]["lotus-core"] != value["source_sha"]
    profile.qualify_parent(value, workspace, root=root)
    assert marker.exists() and book.read_bytes() == original


def test_source_and_parent_cleanup_use_original_cleanup_deadline(
    monkeypatch, tmp_path, clean_profile_environment
):
    root, workspace, value, _, _, _, marker = pinned_parent_fixture(tmp_path)
    monkeypatch.setattr(profile, "observe", native_provenance_observer)
    value["run_deadline"] = (NOW - timedelta(seconds=1)).isoformat()
    with pytest.raises(profile.ProfileRefused, match="ADMISSION_EXPIRED"):
        profile.qualify_source(value, root)
    assert not marker.exists()
    profile.qualify_source(value, root, cleanup=True)
    profile.qualify_parent(value, workspace, root=root, cleanup=True)
    assert marker.exists()
    marker.unlink()
    value["cleanup_deadline"] = (NOW - timedelta(seconds=1)).isoformat()
    with pytest.raises(profile.ProfileRefused, match="ADMISSION_EXPIRED"):
        profile.qualify_source(value, root, cleanup=True)
    with pytest.raises(profile.ProfileRefused, match="ADMISSION_EXPIRED"):
        profile.qualify_parent(value, workspace, root=root, cleanup=True)
    assert not marker.exists()


@pytest.mark.parametrize(
    "drift",
    [
        "workspace",
        "pin",
        "helper",
        "replacement",
        "core",
        "core-project",
        "platform-project",
        "platform-source",
    ],
)
def test_parent_provenance_refuses_foreign_source_or_scope(
    monkeypatch, tmp_path, drift, clean_profile_environment
):
    root, workspace, value, record, book, helper, marker = pinned_parent_fixture(tmp_path)
    monkeypatch.setattr(profile, "observe", native_provenance_observer)
    if drift == "workspace":
        workspace = tmp_path / "foreign-workspace"
    elif drift == "pin":
        value["platform_source_sha"] = "e" * 40
    elif drift == "helper":
        helper.write_text("raise AssertionError('unreviewed helper executed')\n")
    elif drift == "replacement":
        platform = workspace / "lotus-platform"
        original_oid = provenance_git(
            platform,
            "rev-parse",
            value["platform_source_sha"] + ":automation/canonical_runtime_lease.py",
        )
        helper.write_text("raise AssertionError('replacement helper executed')\n")
        replacement_oid = provenance_git(platform, "hash-object", "-w", str(helper))
        provenance_git(platform, "replace", original_oid, replacement_oid)
    elif drift == "core":
        (root / profile.NODE.split("::")[0]).write_text("dirty")
    elif drift == "core-project":
        record["scope"]["projects"]["lotus-core"] = str(tmp_path / "foreign-core")
    elif drift == "platform-project":
        record["scope"]["projects"]["canonical-ingress"] = str(tmp_path / "foreign-platform")
    else:
        record["scope"]["sources"]["lotus-platform"] = "e" * 40
    book.write_text(json.dumps({"record": record}))
    original = book.read_bytes()
    with pytest.raises(profile.ProfileRefused):
        profile.qualify_parent(value, workspace, root=root)
    if drift in {"workspace", "pin", "helper", "replacement", "core"}:
        assert not marker.exists()
    assert book.read_bytes() == original


@pytest.mark.parametrize(
    "sql",
    [
        'CREATE SCHEMA "foreign" AUTHORIZATION CURRENT_USER',
        'DROP SCHEMA "public" CASCADE',
        'DROP SCHEMA "foreign" CASCADE',
        "DROP TABLE public.portfolios",
        "CREATE TABLE public.foreign (id integer)",
        "ALTER TABLE public.portfolios ADD COLUMN foreign integer",
    ],
)
def test_ddl_scope_rejects_foreign_and_public_even_when_current_schema_is_owned(sql):
    case = admitted()["cases"][0]
    assert not profile.admitted_ddl(sql, case["schema"], case["marker"], case["schema"])


def test_ddl_scope_accepts_only_owned_roots_and_frozen_migration_families():
    case = admitted()["cases"][0]
    schema, marker = case["schema"], case["marker"]
    for sql in (
        f'CREATE SCHEMA "{schema}" AUTHORIZATION CURRENT_USER',
        f"COMMENT ON SCHEMA \"{schema}\" IS '{marker}'",
        f'DROP SCHEMA "{schema}" CASCADE',
    ):
        assert profile.admitted_ddl(sql, schema, marker, "public")
    for sql in (
        f'CREATE TABLE "{schema}".portfolios (LIKE public.portfolios INCLUDING CONSTRAINTS)',
        f'ALTER TABLE "{schema}".portfolios ADD UNIQUE (tenant_id, portfolio_id)',
        "CREATE TABLE portfolio_cash_availability_observations (id integer)",
        "CREATE INDEX ix_fact ON portfolio_source_fact_verifications (id)",
        (
            "CREATE TRIGGER guard BEFORE UPDATE ON portfolio_source_fact_verifications "
            "FOR EACH ROW EXECUTE FUNCTION refuse_source_fact_verification_mutation()"
        ),
        (
            "CREATE FUNCTION refuse_source_fact_verification_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$"
        ),
    ):
        assert profile.admitted_ddl(sql, schema, marker, schema)


def test_ddl_scope_accepts_actual_offline_compiled_fixture_and_migrations(compiled_profile_clauses):
    case = admitted()["cases"][0]
    for statement in compiled_profile_clauses:
        assert profile.admitted_ddl(statement, case["schema"], case["marker"], case["schema"])
        assert profile.admitted_ddl(statement + ";", case["schema"], case["marker"], case["schema"])
    functions = [sql for sql in compiled_profile_clauses if sql.startswith("CREATE FUNCTION")]
    assert all(";" in sql and "$$" in sql for sql in functions)
    assert any("--" in sql for sql in functions)


@pytest.mark.parametrize(
    "suffix",
    [
        "; DROP SCHEMA public CASCADE",
        "; SELECT 1",
        ";/*masked*/SELECT 1",
        " -- masked\n; DROP SCHEMA public CASCADE",
        " /* masked */",
        ";;",
    ],
)
def test_ddl_scope_rejects_tails_on_actual_compiled_clauses(compiled_profile_clauses, suffix):
    case = admitted()["cases"][0]
    for statement in compiled_profile_clauses:
        assert not profile.admitted_ddl(
            statement + suffix, case["schema"], case["marker"], case["schema"]
        )


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE portfolio_cash_availability_observations (id integer",
        "CREATE TABLE portfolio_cash_availability_observations (id integer))",
        "CREATE TABLE portfolio_cash_availability_observations (id integer) SELECT (1)",
        "CREATE TABLE portfolio_cash_availability_observations (note text DEFAULT 'unterminated)",
        'CREATE TABLE portfolio_cash_availability_observations ("unterminated integer)',
        "CREATE TABLE portfolio_cash_availability_observations (note text DEFAULT E'bad\\'tail')",
        "CREATE INDEX ix_fact ON portfolio_source_fact_verifications (id) WHERE true",
        "CREATE TRIGGER guard BEFORE UPDATE ON portfolio_source_fact_verifications "
        "FOR EACH ROW EXECUTE FUNCTION foreign()",
        "CREATE FUNCTION refuse_source_fact_verification_mutation() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END",
        "CREATE FUNCTION refuse_source_fact_verification_mutation() RETURNS trigger "
        "LANGUAGE plpgsql AS $tag$ BEGIN RETURN NULL; END $tag$",
        "CREATE FUNCTION refuse_source_fact_verification_mutation() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$ $$other$$",
    ],
)
def test_ddl_scope_rejects_incomplete_or_unreviewed_syntax(statement):
    case = admitted()["cases"][0]
    assert not profile.admitted_ddl(statement, case["schema"], case["marker"], case["schema"])


@pytest.mark.parametrize("literal", ["'a;--b'", "'it''s;quoted'", "'/*data;*/'", '"semi;column"'])
def test_ddl_scope_retains_ordinary_quoted_semicolons(literal):
    case = admitted()["cases"][0]
    column = f"{literal} text" if literal.startswith('"') else f"note text DEFAULT {literal}"
    statement = f"CREATE TABLE portfolio_cash_availability_observations ({column})"
    assert profile.admitted_ddl(statement, case["schema"], case["marker"], case["schema"])


@pytest.mark.parametrize(
    "body",
    [
        "ADD COLUMN foreign integer",
        "ALTER COLUMN id SET DEFAULT nextval('public.foreign')",
        "ADD UNIQUE (foreign)",
        "ALTER COLUMN updated_at DROP DEFAULT",
    ],
)
def test_ddl_scope_refuses_unreviewed_parent_alter_forms(body):
    case = admitted()["cases"][0]
    statement = f'ALTER TABLE "{case["schema"]}".portfolios {body}'
    assert not profile.admitted_ddl(statement, case["schema"], case["marker"], case["schema"])


def test_registered_ddl_fence_refuses_tails_before_driver(monkeypatch, compiled_profile_clauses):
    from sqlalchemy import text

    value, engine, connection, _, _ = handshake_fixture(monkeypatch)
    session = profile.OperatorSourceSession(value, database_url(value))
    authority = session.authorize(engine, profile.NODE)
    monkeypatch.setattr(session, "handshake", lambda *a, **kw: None)
    object.__setattr__(authority, "schema_oid", 1234)
    connection.scalar.return_value = authority.schema
    connection.execute.return_value.mappings.return_value.one.return_value = {
        "oid": 1234,
        "nspowner": value["role_oid"],
        "marker": authority.marker,
    }
    driver = MagicMock()

    def dispatch(statement):
        clause = text(statement)
        engine.dispatch.before_execute(connection, clause, (), {}, {})
        driver(clause)

    try:
        for statement in compiled_profile_clauses:
            with pytest.raises(profile.ProfileRefused, match="^SOURCE_RECEIPT_DDL_SCOPE_REFUSED$"):
                dispatch(statement + "; DROP SCHEMA public CASCADE")
        driver.assert_not_called()
        dispatch("CREATE TABLE portfolio_cash_availability_observations (id integer)")
        driver.assert_called_once()
    finally:
        profile.retire_schema_authorization(authority)
        engine.dispose()


@pytest.mark.parametrize("drift", ["owner", "marker", "expired"])
def test_cleanup_wrong_identity_and_expiry_never_drop(monkeypatch, drift):
    value, engine, connection, _, _ = handshake_fixture(monkeypatch)
    session = profile.OperatorSourceSession(value, database_url(value))
    authority = session.authorize(engine, profile.NODE)
    row = {"schema_oid": 1234, "nspowner": value["role_oid"], "marker": authority.marker}
    if drift == "expired":
        monkeypatch.setattr(profile.time, "time", lambda: NOW.timestamp() + 1000)
    elif drift == "owner":
        row["nspowner"] = 999
    else:
        row["marker"] = "foreign"
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = row
    connection.execute.reset_mock()
    with pytest.raises(profile.ProfileRefused):
        session.cleanup(engine, authority)
    assert not any(
        str(call.args[0]).startswith("DROP") for call in connection.execute.call_args_list
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows-only counter lock")
def test_http_and_process_budget_overruns_are_retained_and_refused(monkeypatch, tmp_path):
    value = admitted()
    raw = json.dumps(value).encode()
    manifest = tmp_path / "admission.json"
    manifest.write_bytes(raw)
    monkeypatch.setenv("LOTUS_SOURCE_RECEIPT_ADMISSION", str(manifest))
    monkeypatch.setenv("LOTUS_SOURCE_RECEIPT_ADMISSION_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setenv("LOTUS_SOURCE_RECEIPT_RUN_DIR", str(tmp_path))
    case = value["cases"][0]
    counter = tmp_path / (case["schema"] + ".json")
    for event, limit in (("http_calls", 14), ("processes", 4)):
        counter.write_bytes(
            b" " + json.dumps({"http_calls": 0, "processes": 0}).encode().ljust(512, b" ")
        )
        for _ in range(limit):
            profile.budget_event(case["schema"], event)
        with pytest.raises(profile.ProfileRefused, match="BUDGET_EXCEEDED"):
            profile.budget_event(case["schema"], event)
        assert json.loads(counter.read_bytes()[1:])[event] == limit + 1
    counter.write_bytes(
        b" " + json.dumps({"http_calls": 0, "processes": 0}).encode().ljust(512, b" ")
    )
    profile.budget_event(case["schema"], "processes")
    profile.budget_event(case["schema"], "ready", 23456)
    actual = json.loads(counter.read_bytes()[1:])
    assert actual["pids"] == [os.getpid()] and actual["ports"] == [23456]
    with pytest.raises(profile.ProfileRefused, match="LISTENER_REFUSED"):
        profile.budget_event(case["schema"], "ready", 23456)


def test_tls_driver_mapping_preserves_mode_without_connection():
    from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
    from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2

    value = admitted()
    session = profile.OperatorSourceSession(value, database_url(value))
    asynchronous = make_url(session.connection_url(asynchronous=True))
    synchronous = make_url(session.connection_url())
    assert PGDialect_asyncpg().create_connect_args(asynchronous)[1]["ssl"] == "require"
    assert PGDialect_psycopg2().create_connect_args(synchronous)[1]["sslmode"] == "require"
    session.validate_url(asynchronous)
    session.validate_url(synchronous)
    value["tls"]["sslrootcert"] = "foreign.pem"
    with pytest.raises(profile.ProfileRefused, match="TLS_INVALID"):
        profile.validate_admission(value, now=NOW.timestamp(), environment={}, platform="nt")


def test_absent_schema_cleanup_retires_capability_and_separate_deadline(monkeypatch):
    value, engine, connection, _, _ = handshake_fixture(monkeypatch)
    session = profile.OperatorSourceSession(value, database_url(value))
    authority = session.authorize(engine, profile.NODE)
    monkeypatch.setattr(profile.time, "time", lambda: NOW.timestamp() + 140)
    with pytest.raises(profile.ProfileRefused, match="ADMISSION_EXPIRED"):
        profile.require_schema_authorization(authority, engine=engine, schema=authority.schema)
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    assert session.cleanup(engine, authority) == "absent"
    with pytest.raises(profile.ProfileRefused, match="CAPABILITY_INVALID"):
        profile.require_schema_authorization(
            authority, engine=engine, schema=authority.schema, cleanup=True
        )


def test_recovery_requires_confirmed_custody_before_any_sql(monkeypatch, tmp_path):
    from scripts.validation import qualify_source_receipts as runner

    spy = MagicMock()
    monkeypatch.setattr(runner, "run_owned", spy)
    args = SimpleNamespace(admission_sha256="0" * 64)
    for receipt in (None, SimpleNamespace(descendants_retired=False)):
        result = runner.recover(admitted(), "private", args, {}, receipt)
        assert result == [
            {
                "schema": admitted()["cases"][0]["schema"],
                "outcome": "unknown_operator_review_required",
            }
        ]
    spy.assert_not_called()


def test_duplicate_fields_and_empty_parent_fail_before_sql():
    with pytest.raises(profile.ProfileRefused, match="DUPLICATE_FIELD"):
        profile.unique_fields([("database", "first"), ("database", "second")])
    value = admitted()
    value["parent_lease"] = ""
    with pytest.raises(profile.ProfileRefused, match="PARENT_SERVER_INVALID"):
        profile.validate_admission(value, now=NOW.timestamp(), environment={}, platform="nt")


def test_existing_schema_refused_for_setup_and_oid_replacement_refused_for_cleanup(monkeypatch):
    value, engine, connection, _, _ = handshake_fixture(monkeypatch)
    case = value["cases"][0]
    row = {"schema_oid": 1234, "nspowner": value["role_oid"], "marker": case["marker"]}
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = row
    session = profile.OperatorSourceSession(value, database_url(value))
    with pytest.raises(profile.ProfileRefused, match="EXISTING_SCHEMA_REFUSED"):
        session.authorize(engine, profile.NODE)
    authority = session.authorize(engine, profile.NODE, cleanup=True)
    assert authority.schema_oid == 1234
    row["schema_oid"] = 5678
    connection.execute.reset_mock()
    with pytest.raises(profile.ProfileRefused, match="SCHEMA_IDENTITY_REFUSED"):
        session.cleanup(engine, authority)
    assert not any(
        str(call.args[0]).startswith("DROP") for call in connection.execute.call_args_list
    )


@pytest.mark.parametrize("supervised", [False, True])
def test_api_attachment_checks_custody_before_session_engine_or_sql(monkeypatch, supervised):
    from tests.test_support import source_receipt_process_custody as custody

    value = admitted()
    case = value["cases"][0]
    inputs = {"schema": case["schema"], "database_url": database_url(value), "environment": {}}
    monkeypatch.setenv("LOTUS_SOURCE_RECEIPT_ADMISSION", "synthetic-admission")
    monkeypatch.setenv("LOTUS_SOURCE_RECEIPT_ADMISSION_SHA256", "0" * 64)
    monkeypatch.setenv("LOTUS_SOURCE_RECEIPT_WORKSPACE", "synthetic-workspace")
    monkeypatch.setattr(profile, "load_admission", lambda *args: value)
    monkeypatch.setattr(profile, "validate_admission", lambda *args, **kwargs: value)
    monkeypatch.setattr(profile, "set_connection_bounds", lambda: None)
    budget = MagicMock()
    monkeypatch.setattr(profile, "budget_event", budget)
    order = []

    def guard():
        order.append("custody")
        if not supervised:
            raise custody.CustodyRefused("SOURCE_RECEIPT_UNSUPERVISED_CHILD")

    monkeypatch.setattr(custody, "require_current_job", guard)
    session = MagicMock()
    engine = session.engine.return_value
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value.one.return_value = {
        "nspowner": value["role_oid"],
        "marker": case["marker"],
    }
    session.engine.side_effect = lambda: order.append("engine") or engine
    session.handshake.side_effect = lambda connection: order.append("handshake")
    factory = MagicMock(side_effect=lambda *args: order.append("session") or session)
    monkeypatch.setattr(profile, "OperatorSourceSession", factory)
    if supervised:
        assert profile.attach_api(inputs) is session
        assert order == ["custody", "session", "engine", "handshake"]
        budget.assert_called_once_with(case["schema"], "processes")
        engine.dispose.assert_called_once()
    else:
        with pytest.raises(custody.CustodyRefused, match="UNSUPERVISED_CHILD"):
            profile.attach_api(inputs)
        assert order == ["custody"]
        factory.assert_not_called()
        session.engine.assert_not_called()
        engine.begin.assert_not_called()
        connection.execute.assert_not_called()


@pytest.mark.parametrize("first_cleanup", ["removed", "absent"])
def test_two_cases_reuse_engine_with_real_registered_callback_dispatch(monkeypatch, first_cleanup):
    from contextlib import nullcontext

    from portfolio_common.database_runtime_profile import DatabasePoolMode
    from portfolio_common.db import create_sync_database_engine
    from sqlalchemy import event, text

    value = admitted()
    first = value["cases"][0]
    first["node"] = profile.NODE + "[cash]"
    second = copy.deepcopy(first)
    second["node"] = profile.NODE + "[funding_investment]"
    second["schema"] = "core1227_" + "c" * 32
    second["marker"] = f"core1227-owned:{value['nonce']}:{second['schema']}"
    value["cases"].append(second)
    # Real SQLAlchemy registration/dispatch; no DBAPI connection or SQL execution.
    engine = create_sync_database_engine(
        runtime_identity="lotus-core-test",
        database_url=database_url(value),
        pool_mode=DatabasePoolMode.NULL,
    )
    connection, catalog = MagicMock(), {}
    connection.engine = engine
    observed = []

    def unrelated_before(connection, clause, multiparams, params, options):
        observed.append(str(clause).strip())

    def unrelated_after(connection, clause, multiparams, params, options, result):
        pass

    event.listen(engine, "before_execute", unrelated_before)
    event.listen(engine, "after_execute", unrelated_after)
    monkeypatch.setattr(engine, "begin", lambda: nullcontext(connection))
    session = profile.OperatorSourceSession(value, database_url(value))
    monkeypatch.setattr(session, "handshake", lambda *args, **kwargs: None)
    serial = iter((1234, 5678))

    def execute(clause, params=None):
        parameters = params or {}
        engine.dispatch.before_execute(connection, clause, (), parameters, {})
        sql = str(clause).strip()
        result = MagicMock()
        if sql.startswith("CREATE SCHEMA"):
            schema = sql.split('"')[1]
            catalog[schema] = {
                "schema_oid": next(serial),
                "nspowner": value["role_oid"],
                "marker": None,
            }
        elif sql.startswith("COMMENT ON SCHEMA"):
            catalog[sql.split('"')[1]]["marker"] = sql.split("'")[1]
        elif sql.startswith("DROP SCHEMA"):
            del catalog[sql.split('"')[1]]
        if sql.startswith("SELECT") and "pg_namespace" in sql:
            row = catalog.get(parameters["schema"])
            result.mappings.return_value.one_or_none.return_value = row
            result.mappings.return_value.one.return_value = (
                {**row, "oid": row["schema_oid"]} if row else None
            )
            result.scalar.return_value = row["schema_oid"] if row else None
        elif sql == "SELECT current_schema()":
            result.scalar.return_value = "public"
        engine.dispatch.after_execute(connection, clause, (), parameters, {}, result)
        return result

    connection.execute.side_effect = execute
    connection.scalar.side_effect = lambda clause, params=None: execute(clause, params).scalar()
    try:
        retired = session.authorize(engine, first["node"])
        if first_cleanup == "removed":
            connection.execute(
                text(f'CREATE SCHEMA "{first["schema"]}" AUTHORIZATION CURRENT_USER')
            )
            connection.execute(
                text(f"COMMENT ON SCHEMA \"{first['schema']}\" IS '{first['marker']}'")
            )
        assert session.cleanup(engine, retired) == first_cleanup
        with pytest.raises(profile.ProfileRefused, match="CAPABILITY_INVALID"):
            profile.require_schema_authorization(retired, engine=engine, schema=first["schema"])
        current = session.authorize(engine, second["node"])
        connection.execute(text(f'CREATE SCHEMA "{second["schema"]}" AUTHORIZATION CURRENT_USER'))
        connection.execute(
            text(f"COMMENT ON SCHEMA \"{second['schema']}\" IS '{second['marker']}'")
        )
        assert current.schema_oid == (5678 if first_cleanup == "removed" else 1234)
        assert session.cleanup(engine, current) == "removed"
        assert catalog == {}
        assert len(engine.dispatch.before_execute) == len(engine.dispatch.after_execute) == 1
        assert event.contains(engine, "before_execute", unrelated_before)
        assert event.contains(engine, "after_execute", unrelated_after)
        assert sum(sql.startswith("CREATE SCHEMA") for sql in observed) == (
            2 if first_cleanup == "removed" else 1
        )
    finally:
        event.remove(engine, "before_execute", unrelated_before)
        event.remove(engine, "after_execute", unrelated_after)
        engine.dispose()
