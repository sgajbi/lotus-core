"""Fixed Windows native receipt qualification; operator provisioning is separate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import types
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINIMUM_GIT_VERSION = (2, 50, 1)
# This literal is also the independently reviewed Make/export entry. Never load it
# by importing this working file before verifying its public committed blob pin.
SOURCE_SEED = """import hashlib,os,re,sys,threading,types
def take(size):
 result=[]
 def read():
  data=bytearray()
  try:
   while len(data)<size:
    chunk=os.read(sys.stdin.fileno(),size-len(data))
    if not chunk: break
    data.extend(chunk)
   result.append(bytes(data))
  except OSError: pass
 worker=threading.Thread(target=read,daemon=True)
 worker.start()
 worker.join(max(0,deadline-time.monotonic()))
 if worker.is_alive() or not result or len(result[0])!=size: os._exit(2)
 return result[0]
def checked(data,pin):
 data=data.replace(b'\\r\\n',b'\\n')
 digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\\0'+data).hexdigest()
 if not re.fullmatch('[0-9a-f]{40}',pin) or digest!=pin: os._exit(2)
 return data
try:
 import time
 deadline=time.monotonic()+5
 root,pin,mode=sys.argv[1:4]
 path=os.path.join(root,'scripts','validation','qualify_source_receipts.py')
 api=b''
 private_size=None
 if mode=='initial':
  with open(path,'rb') as stream: raw=stream.read(2097153)
  if len(raw)>2097152: os._exit(2)
 elif mode in ('child','cleanup','api'):
  sizes=[int.from_bytes(take(4),'big') for _ in range(3)]
  if not sizes[0] or not sizes[2] or sum(sizes)+12>65536: os._exit(2)
  if bool(sizes[1])!=(mode=='api'): os._exit(2)
  raw=take(sizes[0])
  api=take(sizes[1])
  private_size=sizes[2]
 else: os._exit(2)
 raw=checked(raw,pin)
 module=types.ModuleType('scripts.validation.qualify_source_receipts')
 module.__file__=path
 module.__dict__.update(
  _SOURCE_RECEIPT_BOOTSTRAP_ONLY=True,_SOURCE_RECEIPT_VERIFIED_ENTRY=True,
  _SOURCE_RECEIPT_CAPTURED=raw,_SOURCE_RECEIPT_PIN=pin,
  _SOURCE_RECEIPT_PRIVATE_SIZE=private_size)
 sys.modules[module.__name__]=module
 sys.argv=[path]+sys.argv[4:]
 exec(compile(raw,path,'exec'),module.__dict__)
 if mode=='api': module.api_entry(api,private_size)
 else:
  code=module.main()
  sys.stdout.flush()
  os._exit(code)
except SystemExit as result:
 sys.stdout.flush()
 os._exit(result.code if type(result.code) is int else 2)
except BaseException: os._exit(2)
"""
SOURCE_RECEIPT_MIGRATIONS = {
    "c178b2c3d539_add_portfolio_source_observations.py": ("c178b2c3d539", "c177b2c3d538"),
    "c181b2c3d542_add_portfolio_source_fact_verifications.py": ("c181b2c3d542", "c179b2c3d540"),
}
OVERRIDES = (
    "HOST_DATABASE_URL",
    "DATABASE_URL",
    "PYTEST_ADDOPTS",
    "PYTEST_PLUGINS",
    "PGHOST",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
    "PGSERVICE",
    "PGOPTIONS",
    "PGPASSFILE",
    "PGSERVICEFILE",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "LOTUS_POSTGRES_HOST_PORT",
    "COMPOSE_PROJECT_NAME",
)


class EnvironmentRefused(RuntimeError):
    """Credential-free refusal usable before importing repository modules."""


def read_admission(path, expected_hash):
    """Read only the hash-pinned public envelope before qualification imports."""
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise EnvironmentRefused("SOURCE_RECEIPT_ADMISSION_HASH_INVALID")
    with Path(path).open("rb") as stream:
        raw = stream.read(32769)
    if len(raw) > 32768 or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise EnvironmentRefused("SOURCE_RECEIPT_ADMISSION_HASH_MISMATCH")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EnvironmentRefused("SOURCE_RECEIPT_DUPLICATE_FIELD")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise EnvironmentRefused("SOURCE_RECEIPT_ADMISSION_INVALID") from None
    if type(value) is not dict:
        raise EnvironmentRefused("SOURCE_RECEIPT_ADMISSION_INVALID")
    return value


def bootstrap_observe(command, root, deadline):
    """The explicit pre-import exception: bounded fixed, read-only native Git only."""
    observation_deadline = min(time.time() + 5, deadline)
    remaining = observation_deadline - time.time()
    if remaining <= 0:
        raise EnvironmentRefused("SOURCE_RECEIPT_ADMISSION_EXPIRED")
    environment = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP")
        if key in os.environ
    }
    process = subprocess.Popen(
        command,
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    output, failure, lock = bytearray(), [], threading.Lock()

    def refuse(code):
        with lock:
            if not failure:
                failure.append(code)
        try:
            process.kill()
        except OSError:
            pass

    def drain():
        try:
            while chunk := process.stdout.read(4096):
                if len(output) + len(chunk) > 65536:
                    refuse("SOURCE_RECEIPT_OBSERVATION_REFUSED")
                elif not failure:
                    output.extend(chunk)
        except OSError:
            refuse("SOURCE_RECEIPT_OBSERVATION_REFUSED")

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        process.wait(timeout=max(0, observation_deadline - time.time()))
    except subprocess.TimeoutExpired:
        refuse("SOURCE_RECEIPT_OBSERVATION_REFUSED")
    finally:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            refuse("SOURCE_RECEIPT_OBSERVATION_REFUSED")
        reader.join(timeout=1)
        if reader.is_alive():
            refuse("SOURCE_RECEIPT_OBSERVATION_REFUSED")
        process.stdout.close()
    if failure or reader.is_alive() or process.returncode != 0 or time.time() >= deadline:
        raise EnvironmentRefused(failure[0] if failure else "SOURCE_RECEIPT_OBSERVATION_REFUSED")
    return bytes(output)


class SourceProvenance:
    """One profile-only policy, with startup or already-qualified owned transport."""

    def __init__(self, admission, root=ROOT, *, observe=bootstrap_observe, cleanup=False):
        self.root = Path(root).resolve()
        self.admission = admission
        self.observe = observe
        self.objects = {}
        for key in ("source_sha", "source_tree", "platform_source_sha"):
            if not isinstance(admission.get(key), str) or not re.fullmatch(
                r"[0-9a-f]{40}", admission[key]
            ):
                raise EnvironmentRefused("SOURCE_RECEIPT_SOURCE_INVALID")
        try:
            expires = datetime.fromisoformat(
                admission["cleanup_deadline" if cleanup else "run_deadline"]
            )
            if expires.utcoffset() is None:
                raise ValueError
            self.deadline = expires.timestamp()
        except (KeyError, TypeError, ValueError):
            raise EnvironmentRefused("SOURCE_RECEIPT_ADMISSION_EXPIRED") from None
        self.filter_flags = []
        self.owned_top_levels = set()
        self.git_version_qualified = False

    def qualify_git_version(self):
        # This fixed observation intentionally precedes all version-dependent options.
        raw = self.observe(["git", "--version"], self.root, self.deadline)
        match = re.fullmatch(
            rb"git version (\d{1,3})\.(\d{1,3})\.(\d{1,3})(?:\.windows\.\d{1,3})?\r?\n?",
            raw,
        )
        if match is None:
            raise EnvironmentRefused("SOURCE_RECEIPT_GIT_VERSION_INVALID")
        if tuple(int(part) for part in match.groups()) < MINIMUM_GIT_VERSION:
            raise EnvironmentRefused("SOURCE_RECEIPT_GIT_VERSION_UNSUPPORTED")
        self.git_version_qualified = True

    def git(self, arguments, root=None):
        if time.time() >= self.deadline:
            raise EnvironmentRefused("SOURCE_RECEIPT_ADMISSION_EXPIRED")
        root = self.root if root is None else Path(root).resolve()
        fixed = (
            ["config", "--null", "--name-only", "--list"],
            ["rev-parse", "--show-toplevel"],
            ["rev-parse", "--path-format=absolute", "--git-common-dir"],
            ["status", "--porcelain", "--untracked-files=all"],
        )
        object_expression = r"[0-9a-f]{40}(?::[^\x00\\]+)?"
        valid = arguments in fixed or (
            len(arguments) == 3
            and (
                arguments[:2] == ["rev-parse", "--verify"]
                and (
                    arguments[2] in {"HEAD", "HEAD^{tree}"}
                    or re.fullmatch(object_expression, arguments[2])
                )
                or arguments[:2] == ["cat-file", "-t"]
                and re.fullmatch(r"[0-9a-f]{40}", arguments[2])
                or arguments[:2] == ["cat-file", "blob"]
                and re.fullmatch(
                    r"[0-9a-f]{40}:automation/canonical_runtime_lease\.py", arguments[2]
                )
                or arguments[:2] == ["ls-tree", "-z"]
                and re.fullmatch(object_expression, arguments[2])
            )
        )
        if not valid:
            raise EnvironmentRefused("SOURCE_RECEIPT_OBSERVATION_REFUSED")
        if not self.git_version_qualified:
            self.qualify_git_version()
        command = [
            "git",
            "--no-replace-objects",
            "--no-lazy-fetch",
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "--work-tree=" + str(root),
            "-C",
            str(root),
            *self.filter_flags,
            *arguments,
        ]
        return self.observe(command, root, self.deadline)

    def qualify(self):
        # Config key names are data; no values, helper commands, hooks or filters execute.
        names = self.git(["config", "--null", "--name-only", "--list"]).decode().split("\0")
        drivers = set()
        for name in names:
            if name.startswith("filter."):
                match = re.fullmatch(
                    r"(filter\.[A-Za-z0-9._/-]+)\.(?:clean|smudge|process|required)", name
                )
                if match:
                    drivers.add(match[1])
                elif name.rsplit(".", 1)[-1] in {"clean", "smudge", "process", "required"}:
                    raise EnvironmentRefused("SOURCE_RECEIPT_GIT_FILTER_REFUSED")
        if len(drivers) > 64:
            raise EnvironmentRefused("SOURCE_RECEIPT_GIT_FILTER_REFUSED")
        self.filter_flags = [
            flag
            for driver in sorted(drivers)
            for setting in ("clean=", "smudge=", "process=", "required=false")
            for flag in ("-c", driver + "." + setting)
        ]
        top = self.git(["rev-parse", "--show-toplevel"]).decode().strip()
        if Path(top).resolve() != self.root:
            raise EnvironmentRefused("SOURCE_RECEIPT_WORKTREE_REFUSED")
        for field, expression in (("source_sha", "HEAD"), ("source_tree", "HEAD^{tree}")):
            if (
                self.git(["rev-parse", "--verify", expression]).decode().strip()
                != self.admission[field]
            ):
                raise EnvironmentRefused("SOURCE_RECEIPT_SOURCE_MISMATCH")
        if self.git(["status", "--porcelain", "--untracked-files=all"]):
            raise EnvironmentRefused("SOURCE_RECEIPT_DIRTY_SOURCE")
        if not self.owned_top_levels:
            for relative in ("", "src/libs/portfolio-common", "scripts/development/python_startup"):
                expression = self.admission["source_sha"] + (":" + relative if relative else "")
                # Optional canonical roots can be absent in a small reviewed source fixture.
                if relative and not (self.root / relative).exists():
                    continue
                for row in self.git(["ls-tree", "-z", expression]).split(b"\0"):
                    if row:
                        metadata, name = row.split(b"\t", 1)
                        # Migration storage is distinct from the installed Alembic package.
                        # Any origin inside that storage still requires committed-source proof.
                        if not relative and name == b"alembic":
                            continue
                        candidate = name.decode().removesuffix(".py")
                        if candidate.isidentifier() and (
                            metadata.split()[1] == b"tree" or name.endswith(b".py")
                        ):
                            self.owned_top_levels.add(candidate)
        return self

    def object(self, path, kind="blob"):
        relative = Path(path).resolve().relative_to(self.root).as_posix()
        key = (relative, kind)
        if key not in self.objects:
            expression = self.admission["source_sha"] + ":" + relative
            oid = self.git(["rev-parse", "--verify", expression]).decode().strip()
            if self.git(["cat-file", "-t", oid]).decode().strip() != kind:
                raise EnvironmentRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
            self.objects[key] = oid
        return self.objects[key]

    def source(self, path):
        path = Path(path).resolve()
        if path.suffix != ".py":
            raise EnvironmentRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
        with path.open("rb") as stream:
            data = stream.read(2 * 1024 * 1024 + 1)
        return self.snapshot(path, data)

    def snapshot(self, path, data):
        """Authenticate captured bytes; execution must never reopen their origin."""
        normalized = data.replace(b"\r\n", b"\n")
        oid = hashlib.sha1(
            b"blob " + str(len(normalized)).encode() + b"\0" + normalized
        ).hexdigest()
        if len(data) > 2 * 1024 * 1024 or oid != self.object(path):
            raise EnvironmentRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
        return data

    def verify_migration_sources(self):
        for name in SOURCE_RECEIPT_MIGRATIONS:
            self.source(self.root / "alembic/versions" / name)

    def migration(self, name):
        """Execute one verified snapshot with the fixed callers' run_path globals."""
        if name not in SOURCE_RECEIPT_MIGRATIONS:
            raise EnvironmentRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
        if time.time() >= self.deadline:
            raise EnvironmentRefused("SOURCE_RECEIPT_ADMISSION_EXPIRED")
        path = self.root / "alembic/versions" / name
        code = compile(self.source(path), str(path), "exec", dont_inherit=True)
        if time.time() >= self.deadline:
            raise EnvironmentRefused("SOURCE_RECEIPT_ADMISSION_EXPIRED")
        module = types.ModuleType("<run_path>")
        module.__dict__.update(__file__=str(path), __cached__=None, __package__="")
        missing = object()
        previous = sys.modules.get(module.__name__, missing)
        previous_argv = sys.argv[0]
        sys.modules[module.__name__], sys.argv[0] = module, str(path)
        try:
            exec(code, module.__dict__)
            return dict(module.__dict__)
        finally:
            sys.argv[0] = previous_argv
            if previous is missing:
                sys.modules.pop(module.__name__, None)
            else:
                sys.modules[module.__name__] = previous

    def platform_helper(self, workspace):
        common = Path(
            self.git(["rev-parse", "--path-format=absolute", "--git-common-dir"]).decode().strip()
        ).resolve()
        primary = common.parent
        if common.name != ".git" or Path(workspace).resolve() != primary.parent:
            raise EnvironmentRefused("SOURCE_RECEIPT_WORKSPACE_REFUSED")
        primary_common = (
            self.git(["rev-parse", "--path-format=absolute", "--git-common-dir"], primary)
            .decode()
            .strip()
        )
        if Path(primary_common).resolve() != common:
            raise EnvironmentRefused("SOURCE_RECEIPT_WORKSPACE_REFUSED")
        platform = primary.parent / "lotus-platform"
        pin = self.admission["platform_source_sha"]
        if self.git(["rev-parse", "--verify", "HEAD"], platform).decode().strip() != pin:
            raise EnvironmentRefused("SOURCE_RECEIPT_PLATFORM_PIN_REFUSED")
        relative = "automation/canonical_runtime_lease.py"
        data = self.git(["cat-file", "blob", pin + ":" + relative], platform)
        path = platform / relative
        with path.open("rb") as stream:
            actual = stream.read(65537)
        if len(actual) > 65536 or actual.replace(b"\r\n", b"\n") != data.replace(b"\r\n", b"\n"):
            raise EnvironmentRefused("SOURCE_RECEIPT_PLATFORM_PIN_REFUSED")
        return primary, platform, path, data


class QualifiedSourceLoader(importlib.machinery.SourceFileLoader):
    def __init__(self, name, path, provenance):
        super().__init__(name, path)
        self.provenance = provenance

    def get_code(self, fullname):
        # Keep normal cache files, but execute verified source rather than ignored bytecode.
        return compile(self.provenance.source(self.path), self.path, "exec", dont_inherit=True)


class ProfileImportGuard:
    def __init__(self, provenance, finders):
        self.provenance, self.finders = provenance, tuple(finders)
        self.runtime = (Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve())

    def find_spec(self, fullname, path=None, target=None):
        spec = None
        for finder in self.finders:
            method = getattr(finder, "find_spec", None)
            if method and (spec := method(fullname, path, target)) is not None:
                break
        if spec is None or spec.origin in {"built-in", "frozen"}:
            return spec
        locations = [Path(value).resolve() for value in spec.submodule_search_locations or ()]
        if spec.origin:
            locations.append(Path(spec.origin).resolve())
        for location in locations:
            if location.is_relative_to(self.provenance.root):
                if spec.origin and location == Path(spec.origin).resolve():
                    self.provenance.source(location)
                    spec.loader = QualifiedSourceLoader(fullname, str(location), self.provenance)
                else:
                    self.provenance.object(location, "tree")
            elif not any(location.is_relative_to(root) for root in self.runtime):
                raise EnvironmentRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
            elif fullname.split(".", 1)[0] in self.provenance.owned_top_levels:
                raise EnvironmentRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
        if not locations:
            raise EnvironmentRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
        return spec


def canonical_roots(root=ROOT):
    root = Path(root).resolve()
    return (
        root / "scripts" / "development" / "python_startup",
        root / "src" / "libs" / "portfolio-common",
        root,
    )


def validate_environment(environment, root=ROOT):
    protected = [
        name.upper()
        for name in environment
        if name.upper().startswith(("GIT_", "DOCKER_", "PG", "PYTHON"))
        or name.upper() in (*OVERRIDES, "LOTUS_REPOSITORY_ROOT")
    ]
    if len(set(protected)) != len(protected):
        raise EnvironmentRefused("SOURCE_RECEIPT_INHERITED_OVERRIDE")
    normalized = {name.upper(): value for name, value in environment.items()}
    if any(name.startswith(("GIT_", "DOCKER_", "PG")) or name in OVERRIDES for name in normalized):
        raise EnvironmentRefused("SOURCE_RECEIPT_INHERITED_OVERRIDE")
    canonical = os.pathsep.join(str(path) for path in canonical_roots(root))
    allowed_python = {
        "PYTHONPATH": ("", canonical),
        "PYTHONNOUSERSITE": ("1",),
        "PYTHONSAFEPATH": ("1",),
        "PYTHON_DOTENV_DISABLED": ("1",),
    }
    if any(
        name.startswith("PYTHON")
        and not (name == "PYTHONUSERBASE" and sys.flags.no_user_site == 1)
        and (name not in allowed_python or value not in allowed_python[name])
        for name, value in normalized.items()
    ) or normalized.get("LOTUS_REPOSITORY_ROOT", str(Path(root).resolve())) != str(
        Path(root).resolve()
    ):
        raise EnvironmentRefused("SOURCE_RECEIPT_PYTHON_OVERRIDE")


def profile_environment(environment=None):
    source = dict(os.environ if environment is None else environment)
    validate_environment(source)
    child = {name: value for name, value in source.items() if not name.upper().startswith("PYTHON")}
    child.update(
        PYTHONPATH=os.pathsep.join(str(path) for path in canonical_roots()),
        PYTHONNOUSERSITE="1",
        PYTHONSAFEPATH="1",
        PYTHON_DOTENV_DISABLED="1",
        LOTUS_REPOSITORY_ROOT=str(ROOT),
    )
    return child


_active_provenance = None


def bootstrap(admission, *, cleanup=False):
    """Only the fixed isolated script may establish the qualification import path."""
    if not (
        sys.flags.isolated
        and sys.flags.no_user_site
        and sys.flags.ignore_environment
        and sys.dont_write_bytecode
    ):
        raise EnvironmentRefused("SOURCE_RECEIPT_ISOLATED_PYTHON_REQUIRED")
    validate_environment(os.environ)
    provenance = SourceProvenance(admission, cleanup=cleanup).qualify()
    captured = globals().get("_SOURCE_RECEIPT_CAPTURED")
    if captured is None:
        provenance.source(__file__)  # Internal tests/imports; never a supported launch entry.
    else:
        provenance.snapshot(__file__, captured)
        if provenance.object(__file__) != globals().get("_SOURCE_RECEIPT_PIN"):
            raise EnvironmentRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
    provenance.verify_migration_sources()
    global _active_provenance
    _active_provenance = provenance
    roots = [str(path) for path in canonical_roots()]
    sys.path[:] = roots + [path for path in sys.path if path not in roots]
    sys.meta_path[:] = [ProfileImportGuard(provenance, sys.meta_path)]
    # The fixed entry and its later profile imports share this one qualified module.
    sys.modules["scripts.validation.qualify_source_receipts"] = sys.modules[__name__]
    from scripts.development.repository_import_guard import activate_repository_import_guard
    from scripts.development.repository_python import repository_python_roots

    if tuple(repository_python_roots(ROOT)) != canonical_roots():
        raise EnvironmentRefused("SOURCE_RECEIPT_PYTHON_ROOTS_MISMATCH")
    activate_repository_import_guard(ROOT)
    return provenance


def load_runtime():
    global profile, read_launch_bound_private, read_private
    global require_current_job, require_supported_os, run_owned
    from tests.test_support import operator_source_database as profile
    from tests.test_support.source_receipt_process_custody import (
        read_launch_bound_private,
        read_private,
        require_current_job,
        require_supported_os,
        run_owned,
    )

    if _active_provenance is not None:
        _active_provenance.observe = lambda command, root, deadline: profile.observe(
            command, root, deadline=deadline
        )


# Internal unit imports retain their old interface; supported entries bootstrap first.
if __name__ != "__main__" and not globals().get("_SOURCE_RECEIPT_BOOTSTRAP_ONLY"):
    load_runtime()


def private_input(*, launch_bound=False):
    reader = read_launch_bound_private if launch_bound else read_private
    raw = (
        reader(sys.stdin.buffer, size=globals().get("_SOURCE_RECEIPT_PRIVATE_SIZE"))
        if launch_bound
        else reader(sys.stdin.buffer)
    )
    value = json.loads(raw, object_pairs_hook=profile.unique_fields)
    if type(value) is not dict or set(value) != {"database_url"}:
        raise profile.ProfileRefused("SOURCE_RECEIPT_PRIVATE_INPUT_SHAPE")
    return value["database_url"]


def snapshot_launch(mode, arguments=()):
    """Capture qualified source once; the fixed seed executes only these bytes."""
    if _active_provenance is None or mode not in ("child", "cleanup", "api"):
        raise EnvironmentRefused("SOURCE_RECEIPT_IMPORT_REFUSED")
    cli = _active_provenance.source(__file__)
    api = (
        _active_provenance.source(ROOT / "tests/test_support/portfolio_source_http_process.py")
        if mode == "api"
        else b""
    )
    command = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        SOURCE_SEED,
        str(ROOT),
        _active_provenance.object(__file__),
        mode,
        *arguments,
    ]
    return command, (cli, api)


def api_entry(snapshot, private_size):
    """The seed has authenticated CLI bytes; authenticate API before its first instruction."""
    admission = read_admission(
        os.environ["LOTUS_SOURCE_RECEIPT_ADMISSION"],
        os.environ["LOTUS_SOURCE_RECEIPT_ADMISSION_SHA256"],
    )
    provenance = bootstrap(admission)
    path = ROOT / "tests/test_support/portfolio_source_http_process.py"
    provenance.snapshot(path, snapshot)
    load_runtime()
    require_supported_os()
    namespace = {
        "__name__": "__main__",
        "__file__": str(path),
        "_SOURCE_RECEIPT_API_VERIFIED": True,
        "_SOURCE_RECEIPT_PRIVATE_SIZE": private_size,
    }
    exec(compile(snapshot, str(path), "exec"), namespace)


def child(admission, database_url, workspace):
    require_current_job()
    profile.qualify_source(admission, ROOT)
    profile.qualify_container(admission)
    profile.qualify_parent(admission, workspace)
    profile.set_connection_bounds()
    profile.configure(admission, database_url, workspace)
    # No extension args, addopts, auto-loaded plugins or alternate test inventory.
    import pytest

    return int(
        pytest.main(
            [
                "-p",
                "pytest_asyncio.plugin",
                "-p",
                "no:cacheprovider",
                "-o",
                "addopts=",
                "--strict-markers",
                "--import-mode=importlib",
                "--tb=no",
                "-q",
                *[case["node"] for case in admission["cases"]],
            ]
        )
    )


def execute(admission, database_url, args):
    from scripts.development.repository_python import repository_environment

    profile.qualify_source(admission, ROOT)
    profile.OperatorSourceSession(admission, database_url, args.workspace_root)
    profile.qualify_container(admission)
    profile.qualify_parent(admission, args.workspace_root)
    receipt, cleanup, counts = None, [], []
    with tempfile.TemporaryDirectory(prefix="core-source-receipt-") as run_dir:
        for case in admission["cases"]:
            with (Path(run_dir) / (case["schema"] + ".json")).open("xb") as stream:
                stream.write(
                    b" " + json.dumps({"http_calls": 0, "processes": 0}).encode().ljust(512, b" ")
                )
        environment = profile_environment(repository_environment())
        environment.update(
            {
                "LOTUS_OPERATOR_SOURCE_RECEIPT": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTHON_DOTENV_DISABLED": "1",
                "LOTUS_SOURCE_RECEIPT_ADMISSION": str(Path(args.admission).resolve()),
                "LOTUS_SOURCE_RECEIPT_ADMISSION_SHA256": args.admission_sha256,
                "LOTUS_SOURCE_RECEIPT_WORKSPACE": str(Path(args.workspace_root).resolve()),
                "LOTUS_SOURCE_RECEIPT_RUN_DIR": run_dir,
            }
        )
        try:
            command, snapshots = snapshot_launch(
                "child",
                [
                    "--child",
                    "--admission",
                    environment["LOTUS_SOURCE_RECEIPT_ADMISSION"],
                    "--admission-sha256",
                    args.admission_sha256,
                    "--workspace-root",
                    environment["LOTUS_SOURCE_RECEIPT_WORKSPACE"],
                ],
            )
            receipt = run_owned(
                command,
                private_input=json.dumps({"database_url": database_url}).encode(),
                environment=environment,
                cwd=ROOT,
                timeout=min(600, profile.instant(admission["run_deadline"]) - time.time() - 20),
                bind_launch=True,
                source_snapshots=snapshots,
            )
            for case in admission["cases"]:
                raw = (Path(run_dir) / (case["schema"] + ".json")).read_bytes()
                observed = json.loads(raw[1:])
                counts.append({"schema": case["schema"], **observed})
        except Exception:
            pass  # Preserve failure in the receipt; never publish a private exception.
        finally:
            cleanup = recover(admission, database_url, args, environment, receipt)
    success = (
        receipt is not None
        and receipt.exit_code == 0
        and not receipt.timed_out
        and not receipt.output_limit_exceeded
        and receipt.descendants_retired
        and receipt.streams_drained
        and len(counts) == len(admission["cases"])
        and all(row["http_calls"] == 14 and row["processes"] == 4 for row in counts)
        and all(len(set(row["pids"])) == len(row["ports"]) == 4 for row in counts)
        and all(row["outcome"] in ("absent", "removed") for row in cleanup)
    )
    print(
        json.dumps(
            {
                "profile": profile.PROFILE,
                "source_sha": admission["source_sha"],
                "process": asdict(receipt) if receipt is not None else None,
                "counts": counts,
                "cleanup": cleanup,
                "success": success,
            }
        )
    )
    return 0 if success else 1


def recover(admission, database_url, args, environment, receipt):
    unknown = [
        {"schema": case["schema"], "outcome": "unknown_operator_review_required"}
        for case in admission["cases"]
    ]
    if receipt is None or not receipt.descendants_retired:
        return unknown
    profile.deny_overrides(environment)
    remaining = profile.instant(admission["cleanup_deadline"]) - time.time()
    if remaining <= 20:
        return unknown
    try:
        command, snapshots = snapshot_launch(
            "cleanup",
            [
                "--cleanup-child",
                "--admission",
                environment["LOTUS_SOURCE_RECEIPT_ADMISSION"],
                "--admission-sha256",
                args.admission_sha256,
                "--workspace-root",
                environment["LOTUS_SOURCE_RECEIPT_WORKSPACE"],
            ],
        )
        recovery = run_owned(
            command,
            private_input=json.dumps({"database_url": database_url}).encode(),
            environment=environment,
            cwd=ROOT,
            timeout=min(60, remaining - 20),
            bind_launch=True,
            source_snapshots=snapshots,
        )
        if recovery.exit_code or not recovery.descendants_retired or not recovery.streams_drained:
            return unknown
        raw = (Path(environment["LOTUS_SOURCE_RECEIPT_RUN_DIR"]) / "cleanup.json").read_bytes()
        if len(raw) > 4096:
            return unknown
        results = json.loads(raw)
        if [row["schema"] for row in results] != [row["schema"] for row in unknown]:
            return unknown
        for row in results:
            row["recovery_pid"] = recovery.pid
            row["recovery_exit"] = recovery.exit_code
        return results
    except Exception:
        return unknown


def cleanup_child(admission, database_url, workspace):
    require_current_job()
    profile.qualify_source(admission, ROOT, cleanup=True)
    profile.qualify_container(admission)
    profile.qualify_parent(admission, workspace, cleanup=True)
    profile.set_connection_bounds()
    session = profile.OperatorSourceSession(admission, database_url, workspace, cleanup=True)
    results = []
    for case in admission["cases"]:
        engine = None
        try:
            engine = session.engine(cleanup=True)
            authority = session.authorize(engine, case["node"], cleanup=True)
            outcome = session.cleanup(engine, authority)
        except Exception:
            outcome = "refused_or_unknown_operator_review_required"
        finally:
            if engine is not None:
                engine.dispose()
        results.append({"schema": case["schema"], "outcome": outcome})
    path = Path(os.environ["LOTUS_SOURCE_RECEIPT_RUN_DIR"]) / "cleanup.json"
    with path.open("xb") as stream:
        stream.write(json.dumps(results).encode())
    return 0


def main():
    try:
        if not globals().get("_SOURCE_RECEIPT_VERIFIED_ENTRY"):
            raise EnvironmentRefused("SOURCE_RECEIPT_TRUSTED_SEED_REQUIRED")
        if not (sys.flags.isolated and sys.flags.no_user_site and sys.dont_write_bytecode):
            raise EnvironmentRefused("SOURCE_RECEIPT_ISOLATED_PYTHON_REQUIRED")
        validate_environment(os.environ)
    except Exception:
        print('{"success":false,"reason":"SOURCE_RECEIPT_REFUSED_OR_FAILED"}')
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission", required=True)
    parser.add_argument("--admission-sha256", required=True)
    parser.add_argument("--workspace-root", required=True)
    internal = parser.add_mutually_exclusive_group()
    internal.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    internal.add_argument("--cleanup-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        admission = read_admission(args.admission, args.admission_sha256)
        bootstrap(admission, cleanup=args.cleanup_child)
        load_runtime()
        require_supported_os()
        profile.validate_admission(
            admission,
            now=time.time(),
            environment=os.environ,
            platform=os.name,
            cleanup_mode=args.cleanup_child,
        )
        database_url = private_input(launch_bound=args.child or args.cleanup_child)
        if args.cleanup_child:
            return cleanup_child(admission, database_url, args.workspace_root)
        if args.child:
            return child(admission, database_url, args.workspace_root)
        if os.environ.get("LOTUS_OPERATOR_SOURCE_RECEIPT"):
            raise profile.ProfileRefused("SOURCE_RECEIPT_INHERITED_PROFILE")
        return execute(admission, database_url, args)
    except Exception:
        print('{"success":false,"reason":"SOURCE_RECEIPT_REFUSED_OR_FAILED"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
