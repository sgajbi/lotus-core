"""Standalone resource-free Windows custody contract, with no pytest conftest imports.

Run directly with the reviewed Python 3.11.9 interpreter. One owned dummy chain at
a time; child timeout <=10s, capture4096 bytes, aggregate180s plus custody cleanup.
No temporary files, backend/application imports, services or credentials are used.
"""

import base64
import ctypes
import json
import os
import sys
import time
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tests.test_support import source_receipt_process_custody as custody  # noqa: E402

PAYLOAD = b"source-owned-dummy\x00\n"
RECEIPTS = []


def environment():
    selected = {
        key: os.environ[key]
        for key in (
            "SYSTEMROOT",
            "WINDIR",
            "SystemDrive",
            "ProgramData",
            "ProgramFiles",
            "PATH",
            "TEMP",
            "TMP",
            "APPDATA",
            "LOCALAPPDATA",
        )
        if key in os.environ
    }
    selected.update(
        PYTHON_DOTENV_DISABLED="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        LOTUS_REPOSITORY_ROOT=str(ROOT),
        PYTHONPATH=os.pathsep.join(
            str(path)
            for path in (
                ROOT / "scripts/development/python_startup",
                ROOT / "src/libs/portfolio-common",
                ROOT,
            )
        ),
    )
    return selected


def refusal_child():
    return (
        "import sys; from tests.test_support import source_receipt_process_custody as c\n"
        "try: c.read_launch_bound_private(sys.stdin.buffer)\n"
        "except c.CustodyRefused: print('REFUSED'); sys.exit(7)\n"
        "sys.exit(9)"
    )


@unittest.skipUnless(os.name == "nt", "Windows-only owned launch contract")
class LaunchBindingWindowsContract(unittest.TestCase):
    halted = False
    started = None

    @classmethod
    def setUpClass(cls):
        cls.started = time.monotonic()

    def setUp(self):
        if type(self).halted or time.monotonic() - type(self).started > 165:
            self.fail("No further native execution after refusal or exhausted aggregate budget")

    def tearDown(self):
        result = self._outcome.result
        if result.errors or result.failures:
            type(self).halted = True

    def owned(
        self,
        code,
        *,
        bound=False,
        payload=PAYLOAD,
        timeout=10,
        expected_exit=0,
        timed_out=False,
        capped=False,
    ):
        output = bytearray()
        try:
            receipt = custody.run_owned(
                [sys.executable, "-B", "-c", code],
                private_input=payload,
                environment=environment(),
                cwd=ROOT,
                timeout=timeout,
                output_limit=4096,
                stdout_capture=output,
                bind_launch=bound,
            )
            RECEIPTS.append({"case": self.id().rsplit(".", 1)[-1], **asdict(receipt)})
            self.assertTrue(receipt.descendants_retired and receipt.streams_drained)
            self.assertEqual(receipt.timed_out, timed_out)
            self.assertEqual(receipt.output_limit_exceeded, capped)
            if expected_exit is not None:
                self.assertEqual(receipt.exit_code, expected_exit)
            self.assertLessEqual(time.monotonic() - type(self).started, 180)
            return receipt, bytes(output)
        except BaseException:
            type(self).halted = True
            raise
        finally:
            output.clear()

    def test_bound_private_dummy_accepts_actual_owned_parent(self):
        code = (
            "import sys,os,json; "
            "from tests.test_support import source_receipt_process_custody as c; "
            "data=c.read_launch_bound_private(sys.stdin.buffer); "
            f"assert data=={PAYLOAD!r}; "
            "print(json.dumps({'pid':os.getpid(),'parent':os.getppid(),'dummy_received':True}))"
        )
        receipt, raw = self.owned(code, bound=True)
        record = json.loads(raw)
        self.assertTrue(record["dummy_received"])
        self.assertIn(receipt.pid, (record["pid"], record["parent"]))
        RECEIPTS[-1].update(worker_pid=record["pid"], observed_parent_pid=record["parent"])

    def test_forged_controller_cannot_impersonate_authority(self):
        controller = custody._process_identity(
            ctypes.wintypes.HANDLE(-1), os.getpid(), time.monotonic() + 5
        )
        controller["image_sha256"] = "f" * 64
        envelope = {
            "schema": "source-receipt.launch-bound-private/v1",
            "controller": controller,
            "created": {
                "pid": controller["pid"] + 1,
                "birth_ticks": controller["birth_ticks"] + 1,
                "image_sha256": "a" * 64,
            },
            "payload_b64": base64.b64encode(PAYLOAD).decode(),
        }
        _, raw = self.owned(refusal_child(), payload=json.dumps(envelope).encode(), expected_exit=7)
        self.assertEqual(raw.strip(), b"REFUSED")

    def test_capture_cap_preserves_retirement(self):
        self.owned(
            "import sys,time; sys.stdout.write('x'*10000); sys.stdout.flush(); time.sleep(20)",
            timeout=2,
            expected_exit=None,
            capped=True,
        )

    def test_raw_byte_default_is_unchanged(self):
        code = f"import sys; assert sys.stdin.buffer.read()=={PAYLOAD!r}; print('RAW_OK')"
        _, raw = self.owned(code)
        self.assertEqual(raw.strip(), b"RAW_OK")

    def test_raw_input_cannot_impersonate_launch_envelope(self):
        _, raw = self.owned(refusal_child(), payload=b'{"dummy":"no-binding"}', expected_exit=7)
        self.assertEqual(raw.strip(), b"REFUSED")

    def test_timeout_keeps_terminal_owned_receipt(self):
        self.owned("import time; time.sleep(20)", timeout=0.5, expected_exit=None, timed_out=True)

    def profile_caller(self, mode, *, bound):
        # Model only the boundary AFTER independently verified entry, admission and
        # isolated bootstrap. Actual native binding/reader/dispatch remain exercised;
        # this mocked caller fixture is not bootstrap/source-authentication proof.
        code = (
            "import sys,json,os; from pathlib import Path\n"
            "from types import SimpleNamespace,ModuleType\n"
            "from tests.test_support import source_receipt_process_custody as c\n"
            "name='scripts.validation.qualify_source_receipts'\n"
            "r=ModuleType(name)\n"
            f"r.__file__={str(ROOT / 'scripts/validation/qualify_source_receipts.py')!r}\n"
            "r._SOURCE_RECEIPT_BOOTSTRAP_ONLY=True\n"
            "sys.modules[name]=r\n"
            "exec(compile(Path(r.__file__).read_bytes(),r.__file__,'exec'),r.__dict__)\n"
            "r.profile=SimpleNamespace(unique_fields=lambda pairs:dict(pairs),"
            "validate_admission=lambda *a,**k:None)\n"
            "r.require_supported_os=c.require_supported_os\n"
            "r.read_private=c.read_private\n"
            "r.read_launch_bound_private=c.read_launch_bound_private\n"
            "flags={name:getattr(sys.flags,name) for name in dir(sys.flags) "
            "if not name.startswith('_')}\n"
            "flags.update(isolated=1,no_user_site=1,ignore_environment=1)\n"
            "sys.flags=SimpleNamespace(**flags)\n"
            "r._SOURCE_RECEIPT_VERIFIED_ENTRY=True\n"
            "r.validate_environment=lambda *a: None\n"
            "r.read_admission=lambda *a: {}\n"
            "r.bootstrap=lambda *a,**k: None\n"
            "r.load_runtime=lambda: None\n"
            f"sys.argv=['runner',{mode!r},'--admission','unused','--admission-sha256',"
            "'unused','--workspace-root','unused']\n"
            "def dispatched(a,url,w):\n"
            " assert url=='dummy'\n"
            " print(json.dumps({'dummy_received':True,'pid':os.getpid(),'parent':os.getppid()}))\n"
            " return 0\n"
            f"r.{'child' if mode == '--child' else 'cleanup_child'}=dispatched\n"
            "sys.exit(r.main())"
        )
        receipt, raw = self.owned(
            code,
            bound=bound,
            payload=b'{"database_url":"dummy"}',
            expected_exit=0 if bound else 2,
        )
        record = json.loads(raw)
        if bound:
            self.assertTrue(record["dummy_received"])
            self.assertIn(receipt.pid, (record["pid"], record["parent"]))
            RECEIPTS[-1].update(worker_pid=record["pid"], observed_parent_pid=record["parent"])
        else:
            self.assertEqual(
                record, {"success": False, "reason": "SOURCE_RECEIPT_REFUSED_OR_FAILED"}
            )

    def test_profile_normal_caller_accepts_bound_private_input(self):
        self.profile_caller("--child", bound=True)

    def test_profile_normal_caller_refuses_raw_private_input(self):
        self.profile_caller("--child", bound=False)

    def test_profile_recovery_caller_accepts_bound_private_input(self):
        self.profile_caller("--cleanup-child", bound=True)

    def test_profile_recovery_caller_refuses_raw_private_input(self):
        self.profile_caller("--cleanup-child", bound=False)


if __name__ == "__main__":
    if os.name != "nt" or sys.version_info[:3] != (3, 11, 9):
        raise SystemExit("Exact admitted Windows Python3.11.9 required")
    program = unittest.main(exit=False, verbosity=2)
    print(
        json.dumps(
            {
                "schema": "source-receipt.launch-binding-native/v1",
                "success": program.result.wasSuccessful(),
                "receipts": RECEIPTS,
                "temporary_files_created": 0,
                "backend_or_profile_executed": False,
            },
            sort_keys=True,
        )
    )
    raise SystemExit(0 if program.result.wasSuccessful() else 1)
