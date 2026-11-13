"""Regression: .cmd tools (openclaw.CMD) must reach cmd.exe as ONE command-line string.

A list argv made subprocess escape the inner quotes, so cmd.exe could not find the tool and the OpenAI
collector always reported 'unavailable' (found in pre-playtest check, 2026-11-13).
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import utilization as u  # noqa: E402


@unittest.skipUnless(os.name == "nt", "Windows-only cmd.exe quoting")
class WindowsCmdQuoting(unittest.TestCase):
    def test_cmd_tool_is_passed_as_single_string(self):
        seen = {}

        def fake_run(argv, **kw):
            seen["argv"] = argv
            return mock.Mock(returncode=0, stdout="ok\n")

        with mock.patch.object(u.shutil, "which", return_value=r"C:\tools\openclaw.CMD"), \
                mock.patch.object(u.Path, "resolve", lambda self: self), \
                mock.patch.object(u.subprocess, "run", side_effect=fake_run):
            self.assertEqual(u.command_output("openclaw", ["models", "status"], 5), "ok\n")
        self.assertIsInstance(seen["argv"], str)
        self.assertIn('/c ""C:\\tools\\openclaw.CMD" models status"', seen["argv"])
        self.assertNotIn('\\"', seen["argv"])


if __name__ == "__main__":
    unittest.main()
