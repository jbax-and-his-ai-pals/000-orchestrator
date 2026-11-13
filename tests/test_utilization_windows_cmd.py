"""Regression: .cmd tools (openclaw.CMD) must reach cmd.exe as ONE command-line string.

A list argv made subprocess escape the inner quotes, so cmd.exe could not find the tool and the OpenAI
collector always reported 'unavailable' (found in pre-playtest check, 2026-11-13). These tests launch a REAL
.cmd file through cmd.exe; only tool discovery (shutil.which) is mocked.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import utilization as u  # noqa: E402


@unittest.skipUnless(os.name == "nt", "Windows-only cmd.exe quoting")
class WindowsCmdQuoting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="orch cmd test ")  # path contains spaces on purpose
        self.tool = Path(self.tmp.name) / "fake tool.cmd"
        self.tool.write_text("@echo off\r\necho usage-line %1 %2\r\n", encoding="ascii")

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_cmd_file_runs_through_command_output(self):
        with mock.patch.object(u.shutil, "which", return_value=str(self.tool)):
            out = u.command_output("openclaw", ["models", "status"], 20)
        self.assertEqual(out.strip(), "usage-line models status")

    def test_old_list_argv_form_fails(self):
        comspec = str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "cmd.exe")
        old = [comspec, "/d", "/s", "/c", '""' + str(self.tool) + '" models status"']
        r = subprocess.run(old, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(r.returncode, 0, "old list form unexpectedly worked; regression test would be vacuous")


if __name__ == "__main__":
    unittest.main()
