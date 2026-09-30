# -*- coding: utf-8 -*-
"""Hata kaydi: beklenmeyen hatalar program klasorundeki hata_kaydi.txt'ye yazilir.

XP konsolundan metin kopyalamak zahmetli oldugu icin hatanin tamami ayrica
bir dosyaya yazilir; kullanici bu dosyayi dogrudan gonderebilir.
"""

import io
import os
import sys
import traceback
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(PROJECT_DIR, "hata_kaydi.txt")


def write_error(text, where=""):
    """Hata metnini kayit dosyasina ekler; yazilan dosya yolunu dondurur."""
    try:
        with io.open(LOG_PATH, "a", encoding="utf-8", newline="\r\n") as fh:
            fh.write(u"=" * 70 + u"\n")
            fh.write(u"{0}  {1}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), where))
            fh.write(u"Python {0} | {1}\n".format(sys.version.split()[0], sys.executable))
            fh.write(u"{0}\n".format(text))
        return LOG_PATH
    except (IOError, OSError):
        return None


def log_exception(where=""):
    """Etkin istisnayi (except blogu icinde) kaydeder; (metin, yol) dondurur."""
    text = traceback.format_exc()
    return text, write_error(text, where)
