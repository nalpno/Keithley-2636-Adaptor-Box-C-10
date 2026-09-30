# -*- coding: utf-8 -*-
"""Kurulum ve surucu teshisi (XP surumu).

Konsoldan:  python -m uvpd_xp.diag
"""

import os
import platform
import struct
import sys

from . import transport as tr


class Diagnosis(object):
    def __init__(self):
        self.lines = []
        self.suggestion = ""
        self.backend = None          # onerilen arayuz
        self.resources = []          # bulunan kaynaklar

    def add(self, line=""):
        self.lines.append(line)

    @property
    def text(self):
        return "\n".join(self.lines)


def python_bits():
    return struct.calcsize("P") * 8


def dll_candidates():
    if not tr.IS_WINDOWS:
        return []
    root = os.environ.get("SystemRoot", r"C:\WINDOWS")
    sys32 = os.path.join(root, "system32")
    return [
        (os.path.join(sys32, "gpib-32.dll"), "NI-488.2 uyumlu GPIB surucusu (NI veya ADLINK kurar)"),
        (os.path.join(sys32, "visa32.dll"), "VISA kutuphanesi (NI-VISA / Keysight / KIOL)"),
    ]


def diagnose(scan=True, gpib_scan=None, visa_scan=None):
    """Sistemi tarar, okunabilir rapor ve oneri uretir.

    gpib_scan / visa_scan parametreleri test icin disaridan verilebilir.
    """
    gpib_scan = gpib_scan or tr.gpib_scan
    visa_scan = visa_scan or tr.visa_scan
    d = Diagnosis()

    d.add("=== SISTEM ===")
    d.add("Python      : {0} ({1}-bit)".format(platform.python_version(), python_bits()))
    d.add("Yorumlayici : {0}".format(sys.executable))
    d.add("Isletim sis.: {0}".format(platform.platform()))
    try:
        import tkinter
        d.add("Tkinter     : var (Tk {0})".format(tkinter.TkVersion))
    except Exception as exc:
        d.add("Tkinter     : YOK ({0}) - Python kurulumunda Tcl/Tk secili olmali".format(exc))
    d.add()

    dlls = dll_candidates()
    if dlls:
        d.add("=== SURUCU DOSYALARI ===")
        for path, note in dlls:
            d.add("[{0}] {1}".format("VAR" if os.path.exists(path) else " - ", path))
            d.add("        {0}".format(note))
        d.add()

    gpib_found, visa_found = [], []
    gpib_err = visa_err = None
    if scan:
        d.add("=== TARAMA ===")
        try:
            gpib_found = list(gpib_scan())
            d.add("gpib-32.dll : BASARILI  {0}".format(gpib_found))
        except Exception as exc:
            gpib_err = str(exc)
            d.add("gpib-32.dll : BASARISIZ  {0}".format(gpib_err))
        try:
            visa_found = list(visa_scan())
            d.add("visa32.dll  : BASARILI  {0}".format(visa_found))
        except Exception as exc:
            visa_err = str(exc)
            d.add("visa32.dll  : BASARISIZ  {0}".format(visa_err))
        d.add()

    if gpib_found:
        d.backend = tr.BACKEND_GPIB
        d.resources = gpib_found
        d.suggestion = (
            "GPIB karti calisiyor ve cihaz bulundu: {0}\n"
            "Programda:  Arayuz = GPIB (gpib-32.dll),  Kaynak = {1}".format(
                gpib_found, gpib_found[0]))
    elif visa_found:
        d.backend = tr.BACKEND_VISA
        d.resources = visa_found
        d.suggestion = (
            "VISA calisiyor, kaynaklar: {0}\n"
            "Programda:  Arayuz = VISA (visa32.dll),  Kaynak = listeden secin.".format(visa_found))
    elif scan and gpib_err is None:
        d.backend = tr.BACKEND_GPIB
        d.suggestion = (
            "gpib-32.dll yuklendi ve GPIB karti calisiyor, FAKAT hatta cihaz yok.\n"
            "- Keithley acik mi? GPIB kablosu iki uctan da takili mi?\n"
            "- Keithley'in GPIB adresi: MENU > COMMUNICATION > GPIB (fabrika 26).\n"
            "- Bu PC'de LabVIEW veya baska bir program cihazi kullaniyorsa kapatin.")
    else:
        d.suggestion = (
            "Calisan bir GPIB/VISA surucusu bulunamadi.\n"
            "- Bu PC daha once Keithley ile haberlesiyorduysa surucu kurulu olmali;\n"
            "  C:\\WINDOWS\\system32 icinde gpib-32.dll ya da visa32.dll arayin.\n"
            "- ADLINK USB-3488A kullaniliyorsa ADLINK'in XP surucusunu kurun.\n"
            "- NI GPIB karti kullaniliyorsa NI-488.2 (XP destekleyen surum) kurun.\n"
            "- Cihazsiz denemek icin programi simulasyon modunda baslatin.")

    d.add("=== ONERI ===")
    d.add(d.suggestion)
    return d


def main():
    from .console import make_console_safe
    make_console_safe()
    print(diagnose().text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
