# -*- coding: utf-8 -*-
"""Tum testleri calistirir (harici paket gerekmez).

    python run_tests.py
"""

import os
import sys
import unittest

if sys.version_info[:2] < (3, 3):
    sys.stderr.write("Bu program Python 3.4 gerektirir (bulunan: %s).\n"
                     "Kurulum: https://www.python.org/ftp/python/3.4.4/python-3.4.4.msi\n"
                     % sys.version.split()[0])
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    sys.path.insert(0, HERE)
    suite = unittest.defaultTestLoader.discover(os.path.join(HERE, "tests"), top_level_dir=HERE)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
