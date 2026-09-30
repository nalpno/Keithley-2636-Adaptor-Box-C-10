# -*- coding: utf-8 -*-
"""UV fotodedektor olcum arayuzunu baslatir (XP surumu).

    python program.py              # normal
    python program.py --simulate   # cihazsiz deneme
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.version_info[:2] < (3, 3):
    sys.stderr.write("Bu program Python 3.4 gerektirir (bulunan: %s).\n"
                     "Kurulum: https://www.python.org/ftp/python/3.4.4/python-3.4.4.msi\n"
                     % sys.version.split()[0])
    sys.exit(1)


def main():
    try:
        from uvpd_xp.gui.app import run
        return run()
    except SystemExit:
        raise
    except Exception:
        from uvpd_xp.errorlog import log_exception
        text, path = log_exception("program baslatilirken")
        sys.stderr.write("\n[HATA] Program baslatilamadi:\n\n" + text + "\n")
        if path:
            sys.stderr.write("Bu hata su dosyaya da yazildi: {0}\n".format(path))
        return 1


if __name__ == "__main__":
    sys.exit(main())
