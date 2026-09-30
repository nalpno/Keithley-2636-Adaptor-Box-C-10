# -*- coding: utf-8 -*-
"""XP konsolunda guvenli yazdirma.

XP komut istemi cp857/cp437 kod sayfasi kullanir. Bir yol ya da cihaz
cevabi bu kod sayfasinda olmayan bir karakter icerirse print() cokmesin
diye stdout 'errors=replace' ile yeniden sarilir.
"""

import io
import sys


def make_console_safe():
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "detach"):
            continue
        if getattr(stream, "errors", None) == "replace":
            continue                      # zaten sarilmis
        try:
            enc = getattr(stream, "encoding", None) or "ascii"
            stream.flush()
            # detach(): eski sarmalayici cop toplanirken alttaki tamponu
            # KAPATMASIN diye baglantiyi koparir.
            buf = stream.detach()
            setattr(sys, name, io.TextIOWrapper(buf, encoding=enc, errors="replace",
                                                line_buffering=True))
        except Exception:
            pass
