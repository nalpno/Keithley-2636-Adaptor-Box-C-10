"""VISA / GPIB kurulum teshisi.

"Could not locate a VISA implementation" hatasinin sebebini bulmak icin
sistemi tarar: Python surumu ve bit genisligi, kurulu paketler, diskteki VISA
ve GPIB surucu kutuphaneleri, ve calisan backend'ler.

Qt'den bagimsizdir; konsoldan da calistirilabilir::

    python -m uvpd.visa_diag
"""

from __future__ import annotations

import os
import platform
import struct
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# VISA kutuphanesi olarak denenecek backend'ler
BACKEND_DEFAULT = ""      # sistem VISA (NI-VISA, Keysight IO, ADLINK ...)
BACKEND_PY = "@py"        # saf Python: pyvisa-py


@dataclass
class Diagnosis:
    """Teshis sonucu: ekrana basilacak metin + onerilen ayar."""

    lines: List[str] = field(default_factory=list)
    suggestion: str = ""
    recommended_library: Optional[str] = None   # "@py", "" veya None
    working_resources: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def add(self, line: str = "") -> None:
        self.lines.append(line)


# --------------------------------------------------------------------------
def python_bits() -> int:
    return struct.calcsize("P") * 8


def module_version(name: str) -> Optional[str]:
    """Paket kuruluysa surumunu, degilse None dondurur."""
    try:
        mod = __import__(name)
    except Exception:
        return None
    return getattr(mod, "__version__", "kurulu")


def visa_dll_candidates() -> List[Tuple[str, bool, str]]:
    """Windows'ta aranan VISA/GPIB kutuphaneleri: (yol, var mi, aciklama)."""
    if os.name != "nt":
        return []
    root = os.environ.get("SystemRoot", r"C:\Windows")
    sys32 = os.path.join(root, "System32")
    wow64 = os.path.join(root, "SysWOW64")
    cands = [
        (os.path.join(sys32, "visa64.dll"), "64-bit VISA (64-bit Python icin)"),
        (os.path.join(sys32, "visa32.dll"), "System32'deki VISA"),
        (os.path.join(wow64, "visa32.dll"), "32-bit VISA (32-bit Python icin)"),
        (os.path.join(sys32, "gpib-32.dll"), "NI-488.2 uyumlu GPIB surucusu "
                                             "(ADLINK USB-3488A surucusu bunu kurar)"),
        (os.path.join(sys32, "ni4882.dll"), "NI-488.2 surucusu"),
    ]
    return [(path, os.path.exists(path), note) for path, note in cands]


def try_backend(library: str) -> Tuple[bool, object]:
    """Bir backend ile kaynak listelemeyi dener.

    Basarili ise (True, kaynak listesi), degilse (False, hata mesaji) doner.
    """
    try:
        import pyvisa
    except ImportError as exc:
        return False, f"pyvisa kurulu degil ({exc})"
    rm = None
    try:
        rm = pyvisa.ResourceManager(library)
        return True, list(rm.list_resources())
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        if rm is not None:
            try:
                rm.close()
            except Exception:
                pass


def has_gpib_resource(resources) -> bool:
    return any(str(r).upper().startswith("GPIB") for r in resources)


# --------------------------------------------------------------------------
def diagnose(probe_backends: bool = True) -> Diagnosis:
    """Sistemi tarar ve okunabilir bir teshis raporu uretir."""
    d = Diagnosis()

    d.add("=== SISTEM ===")
    d.add(f"Python      : {platform.python_version()} ({python_bits()}-bit)")
    d.add(f"Yorumlayici : {sys.executable}")
    d.add(f"Isletim sis.: {platform.platform()}")
    d.add()

    d.add("=== PAKETLER ===")
    pyvisa_ver = module_version("pyvisa")
    pyvisa_py_ver = module_version("pyvisa_py")
    gpib_ctypes_ver = module_version("gpib_ctypes")
    pyusb_ver = module_version("usb")
    d.add(f"pyvisa      : {pyvisa_ver or 'KURULU DEGIL'}")
    d.add(f"pyvisa-py   : {pyvisa_py_ver or 'kurulu degil'}  (LAN icin yeterli)")
    d.add(f"gpib-ctypes : {gpib_ctypes_ver or 'kurulu degil'}  (GPIB icin)")
    d.add(f"pyusb       : {pyusb_ver or 'kurulu degil'}  (pyvisa-py ile USB icin)")
    d.add()

    dlls = visa_dll_candidates()
    gpib_dll_found = False
    visa64_found = visa32_only = False
    if dlls:
        d.add("=== SURUCU KUTUPHANELERI ===")
        for path, exists, note in dlls:
            d.add(f"[{'VAR' if exists else ' - '}] {path}")
            d.add(f"        {note}")
            base = os.path.basename(path).lower()
            if exists and base == "gpib-32.dll":
                gpib_dll_found = True
            if exists and base == "visa64.dll":
                visa64_found = True
            if exists and base == "visa32.dll":
                visa32_only = True
        d.add()

    if probe_backends:
        d.add("=== BACKEND DENEMELERI ===")
        ok_default, res_default = try_backend(BACKEND_DEFAULT)
        d.add(f"Sistem VISA (bos)  : {'BASARILI' if ok_default else 'BASARISIZ'}")
        d.add(f"    {res_default}")
        ok_py, res_py = try_backend(BACKEND_PY)
        d.add(f"pyvisa-py (@py)    : {'BASARILI' if ok_py else 'BASARISIZ'}")
        d.add(f"    {res_py}")
        d.add()
    else:
        ok_default = ok_py = False
        res_default = res_py = []

    # ---------------- oneri ----------------
    if ok_default and has_gpib_resource(res_default):
        d.recommended_library = BACKEND_DEFAULT
        d.working_resources = list(res_default)
        d.suggestion = (
            "Sistem VISA calisiyor ve GPIB kaynagi goruluyor.\n"
            "VISA kutuphanesi alanini BOS birakin, kaynak olarak "
            f"{[r for r in res_default if str(r).upper().startswith('GPIB')]} "
            "adresini secip Bagla'ya basin.")
    elif ok_py and has_gpib_resource(res_py):
        d.recommended_library = BACKEND_PY
        d.working_resources = list(res_py)
        d.suggestion = (
            "Sistem VISA yok ama pyvisa-py GPIB kartini goruyor.\n"
            "Baglanti sekmesindeki 'VISA kutuphanesi' alanina  @py  yazin, "
            "sonra Kaynaklari tara.")
    elif not pyvisa_ver:
        d.suggestion = ("pyvisa kurulu degil. Kurulum:\n"
                        "    pip install pyvisa")
    elif ok_default:
        d.recommended_library = BACKEND_DEFAULT
        d.working_resources = list(res_default)
        d.suggestion = (
            "Sistem VISA calisiyor fakat cihaz kaynaklari arasinda "
            "gorunmuyor.\n"
            f"Listelenen kaynaklar: {list(res_default) or '(hicbiri)'}\n\n"
            "- Keithley acik mi, USB/LAN/GPIB kablosu takili mi?\n"
            "- USB ile bagliysa adres  USB0::0x05E6::0x2636::<seri-no>::INSTR "
            "bicimindedir; gorunmuyorsa cihazin USB surucusu (Keithley I/O "
            "Layer) eksik olabilir.\n"
            "- GPIB ile bagliysa cihaz adresini kontrol edin "
            "(MENU > COMMUNICATION > GPIB, fabrika degeri 26). USB-3488A bir "
            "NI karti degildir; NI-VISA onu goremeyebilir, bu durumda "
            "pyvisa-py + gpib-ctypes ve  @py  kullanin.\n"
            "- LAN ile bagliysa kaynagi elle girin: "
            "TCPIP0::<IP>::inst0::INSTR")
    elif gpib_dll_found and not pyvisa_py_ver:
        d.recommended_library = BACKEND_PY
        d.suggestion = (
            "Sistemde VISA yok, ancak NI-488.2 uyumlu GPIB surucusu "
            "(gpib-32.dll) kurulu — LabVIEW bu surucuyu kullaniyor olmali.\n"
            "Python tarafinda bu surucuyu kullanmak icin:\n"
            "    pip install pyvisa-py gpib-ctypes\n"
            "sonra 'VISA kutuphanesi' alanina  @py  yazip Kaynaklari tara.")
    elif visa32_only and not visa64_found and python_bits() == 64:
        d.suggestion = (
            "Sistemde yalnizca 32-bit VISA (visa32.dll) var, Python ise 64-bit.\n"
            "Cozum (birini secin):\n"
            "  a) 64-bit VISA kurun (NI-VISA / Keysight IO Libraries),\n"
            "  b) veya 32-bit Python kurup programi onunla calistirin,\n"
            "  c) veya:  pip install pyvisa-py gpib-ctypes  ve  @py  kullanin.")
    else:
        d.recommended_library = BACKEND_PY if gpib_dll_found else None
        d.suggestion = (
            "Bu bilgisayarda calisan bir VISA arayuzu YOK.\n"
            "Cozum, cihazi nasil bagladiginiza gore degisir:\n"
            "\n"
            "[USB kablosu ile bagliysa]  ← en yaygin durum\n"
            "  USB-TMC icin bir VISA runtime kurulmalidir. Ikisinden biri:\n"
            "    * Keithley I/O Layer (KIOL) — Tektronix/Keithley sitesinden, "
            "cihaza ozel, onerilen\n"
            "    * NI-VISA — ni.com, ucretsiz\n"
            "  Kurduktan sonra cihazi USB'den takip 'Kaynaklari tara' deyin; "
            "adres su bicimde cikar:\n"
            "    USB0::0x05E6::0x2636::<seri-no>::INSTR\n"
            "  (Kurulum sonrasi bilgisayari yeniden baslatmak gerekebilir.)\n"
            "\n"
            "[LAN kablosu ile baglanabiliyorsa]  ← surucu gerektirmeyen yol\n"
            "    pip install pyvisa-py\n"
            "  'VISA kutuphanesi' alanina  @py  yazin, kaynak olarak da\n"
            "    TCPIP0::<cihazin-IP-adresi>::inst0::INSTR\n"
            "  girin. IP adresi cihazin on panelinden okunur "
            "(MENU > LAN > STATUS > IP-ADDRESS).\n"
            "\n"
            "[GPIB (USB-3488A) ile bagliysa]\n"
            "    pip install pyvisa-py gpib-ctypes\n"
            "  ve 'VISA kutuphanesi' alanina  @py  yazin; GPIB surucusunun "
            "(gpib-32.dll) kurulu olmasi gerekir.\n"
            "\n"
            "Not: Sistem VISA kurarsaniz Python ile ayni bit genisliginde "
            f"olmalidir (bu Python {python_bits()}-bit).")

    d.add("=== ONERI ===")
    d.add(d.suggestion)
    return d


def main() -> int:  # pragma: no cover - konsol kullanimi
    print(diagnose().text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
