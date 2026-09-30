# -*- coding: utf-8 -*-
"""XP'ye ozgu kaynak kurallari.

* Tum .py ve .bat dosyalari ASCII olmali: XP konsolu (cp857/cp437) ASCII
  disi karakter basarken UnicodeEncodeError verir; Tk 8.6 ise emoji gibi
  BMP disi karakterlerde coker.
* Python 3.4'te olmayan soz dizimi kullanilmamali (f-string vb.). Tam kontrol
  gelistirme ortaminda Python 3.4 yorumlayicisi ve 'vermin' ile yapilir; bu
  test en sik hatalari her ortamda yakalar.
"""

import io
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def project_files(exts):
    for base in ("uvpd_xp", "tests", "."):
        folder = os.path.join(ROOT, base)
        for dirpath, dirnames, filenames in os.walk(folder):
            if base == "." and dirpath != folder:
                continue
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                if fn.endswith(exts):
                    yield os.path.join(dirpath, fn)


class SourceRules(unittest.TestCase):
    def test_sources_are_ascii(self):
        bad = []
        for path in project_files((".py", ".bat")):
            with io.open(path, "rb") as fh:
                data = fh.read()
            try:
                data.decode("ascii")
            except UnicodeDecodeError as exc:
                bad.append("{0}: bayt {1}".format(os.path.relpath(path, ROOT), exc.start))
        self.assertEqual(bad, [], "ASCII olmayan dosyalar: {0}".format(bad))

    def test_no_py36_syntax(self):
        patterns = [
            (re.compile(r"""(?<![A-Za-z0-9_])[fF][rR]?["']"""), "f-string"),
            (re.compile(r"^\s*from\s+__future__\s+import\s+annotations", re.M), "__future__ annotations"),
            (re.compile(r"^\s*from\s+dataclasses\s+import|^\s*import\s+dataclasses", re.M), "dataclasses"),
            (re.compile(r"^\s*(from\s+typing\s+import|import\s+typing)", re.M), "typing"),
            (re.compile(r"\.trace_add\("), "trace_add (3.6+)"),
            (re.compile(r"ttk\.Spinbox"), "ttk.Spinbox (3.7+)"),
            (re.compile(r"timespec="), "isoformat(timespec=) (3.6+)"),
            (re.compile(r"math\.(inf|nan|isclose)\b"), "math.inf/nan/isclose (3.5+)"),
        ]
        bad = []
        for path in project_files((".py",)):
            if os.path.basename(path) == "test_source_rules.py":
                continue
            with io.open(path, encoding="ascii") as fh:
                text = fh.read()
            for rx, what in patterns:
                if rx.search(text):
                    bad.append("{0}: {1}".format(os.path.relpath(path, ROOT), what))
        self.assertEqual(bad, [])

    def test_launchers_never_close_silently(self):
        """Her baslatici: dosya kontrolu yapar, her hata yolunda bekler (pause),
        baska bir .bat dosyasina bagimli degildir (ZIP icinden calistirma)."""
        launchers = ["baslat.bat", "baslat-simulasyon.bat", "test-baglanti.bat",
                     "teshis.bat", "testleri-calistir.bat"]
        for name in launchers:
            with io.open(os.path.join(ROOT, name), encoding="ascii") as fh:
                text = fh.read()
            self.assertIn('if not exist "%~dp0program.py" goto eksik', text, name)
            self.assertNotIn("call ", text.lower(), name)
            for label in (":eksik", ":pyyok", ":hata", ":son"):
                self.assertIn(label, text, name)
            son = text[text.index(":son"):]
            self.assertIn("pause", son, name)
            # hicbir yol :eof'a pause olmadan erken cikmamali
            self.assertNotIn("if not defined PY goto :eof", text, name)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "_python_bul.bat")))

    def test_batch_files_use_crlf(self):
        for path in project_files((".bat",)):
            with io.open(path, "rb") as fh:
                data = fh.read()
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""),
                             "{0} CRLF degil".format(os.path.basename(path)))


if __name__ == "__main__":
    unittest.main()
