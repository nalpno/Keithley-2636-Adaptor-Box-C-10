# -*- coding: utf-8 -*-
"""Teshis onerileri ve XP konsol guvenligi."""

import os
import subprocess
import sys
import unittest

from uvpd_xp import transport as tr
from uvpd_xp.diag import diagnose

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def boom():
    raise tr.TransportError("gpib-32.dll yuklenemedi: bulunamadi")


class DiagTests(unittest.TestCase):
    def test_gpib_device_found(self):
        d = diagnose(gpib_scan=lambda: ["GPIB0::26::INSTR"], visa_scan=lambda: [])
        self.assertEqual(d.backend, tr.BACKEND_GPIB)
        self.assertEqual(d.resources, ["GPIB0::26::INSTR"])
        self.assertIn("GPIB0::26::INSTR", d.suggestion)

    def test_visa_only(self):
        d = diagnose(gpib_scan=boom, visa_scan=lambda: ["USB0::0x05E6::0x2636::1::INSTR"])
        self.assertEqual(d.backend, tr.BACKEND_VISA)

    def test_board_ok_but_no_device(self):
        d = diagnose(gpib_scan=lambda: [], visa_scan=boom)
        self.assertEqual(d.backend, tr.BACKEND_GPIB)
        self.assertIn("hatta cihaz yok", d.suggestion)

    def test_nothing_works(self):
        d = diagnose(gpib_scan=boom, visa_scan=boom)
        self.assertIsNone(d.backend)
        self.assertIn("gpib-32.dll", d.suggestion)
        self.assertIn("=== SISTEM ===", d.text)


class ConsoleTests(unittest.TestCase):
    def run_py(self, code, encoding):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = encoding
        env["PYTHONPATH"] = ROOT
        p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env, cwd=ROOT)
        out, err = p.communicate(timeout=60)
        return p.returncode, out, err

    def test_output_is_not_lost_after_wrapping(self):
        rc, out, err = self.run_py(
            "from uvpd_xp.console import make_console_safe\n"
            "make_console_safe()\nprint('merhaba')", "ascii")
        self.assertEqual(rc, 0, err)
        self.assertIn(b"merhaba", out)

    def test_non_encodable_character_does_not_crash(self):
        rc, out, err = self.run_py(
            "from uvpd_xp.console import make_console_safe\n"
            "make_console_safe()\nprint('a\\u00e7b')", "ascii")
        self.assertEqual(rc, 0, err)
        self.assertIn(b"a?b", out)


if __name__ == "__main__":
    unittest.main()
