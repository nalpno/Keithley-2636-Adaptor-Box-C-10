# -*- coding: utf-8 -*-
"""Cihaz haberlesme katmani (ctypes ile, harici paket GEREKTIRMEZ).

Windows XP + Python 3.4 icin yazilmistir. pyvisa / pyvisa-py / gpib-ctypes
KULLANILMAZ; surucu DLL'leri dogrudan ctypes ile cagrilir:

* GpibTransport : NI-488.2 uyumlu ``gpib-32.dll``
                  (National Instruments kartlari VE ADLINK USB-3488A gibi
                  NI-488.2 uyumlu adaptorler bu DLL'i kurar)
* VisaTransport : ``visa32.dll`` (NI-VISA / Keysight / Keithley I/O Layer)
                  GPIB, USB-TMC veya LAN kaynaklari icin

Her iki sinif da ayni arayuzu sunar: open(), write(str), read() -> str,
query(str) -> str, clear(), close().
"""

import ctypes
import re
import sys

IS_WINDOWS = sys.platform.startswith("win")

# --------------------------------------------------------------------------
# NI-488.2 sabitleri
# --------------------------------------------------------------------------
ERR = 0x8000     # ibsta: hata
TIMO = 0x4000    # ibsta: zaman asimi
END = 0x2000     # ibsta: EOI / okuma sonu

# ibdev zaman asimi kodlari
T1s, T3s, T10s, T30s, T100s, T300s = 11, 12, 13, 14, 15, 16

IBERR_TEXT = {
    0: "EDVR - sistem hatasi (surucu / DLL sorunu)",
    1: "ECIC - kart denetleyici (CIC) degil",
    2: "ENOL - bu adreste dinleyen cihaz yok (adres yanlis ya da cihaz kapali)",
    3: "EADR - adresleme hatasi",
    4: "EARG - gecersiz arguman",
    5: "ESAC - kart sistem denetleyicisi degil",
    6: "EABO - G/C iptal edildi (genellikle ZAMAN ASIMI: cihaz cevap vermedi)",
    7: "ENEB - GPIB karti bulunamadi (adaptor takili / surucu kurulu mu?)",
    8: "EDMA - DMA hatasi",
    10: "EOIP - asenkron G/C suruyor",
    11: "ECAP - yetenek yok",
    12: "EFSO - dosya sistemi hatasi",
    14: "EBUS - GPIB veri yolu hatasi",
    15: "ESTB - seri yoklama durum baytlari kayboldu",
    16: "ESRQ - SRQ hatti takili",
    20: "ETAB - tablo hatasi",
}

# --------------------------------------------------------------------------
# VISA sabitleri
# --------------------------------------------------------------------------
VI_SUCCESS = 0
VI_SUCCESS_TERM_CHAR = 0x3FFF0005
VI_SUCCESS_MAX_CNT = 0x3FFF0006
VI_ATTR_TMO_VALUE = 0x3FFF001A
VI_ERROR_RSRC_NFOUND = -1073807343   # 0xBFFF0011


class TransportError(RuntimeError):
    """Haberlesme katmani hatasi (kullaniciya gosterilecek Turkce mesajla)."""


# --------------------------------------------------------------------------
# Yardimcilar
# --------------------------------------------------------------------------
_GPIB_RE = re.compile(r"^GPIB(\d*)::(\d+)(?:::(\d+))?(?:::INSTR)?$", re.IGNORECASE)


def parse_gpib_resource(resource):
    """'GPIB0::26::INSTR' -> (kart, birincil_adres, ikincil_adres).

    GPIB kaynagi degilse None doner.
    """
    m = _GPIB_RE.match(resource.strip())
    if not m:
        return None
    board = int(m.group(1) or 0)
    pad = int(m.group(2))
    sad = int(m.group(3)) if m.group(3) else 0
    return board, pad, sad


def gpib_resource_name(board, pad):
    return "GPIB{0}::{1}::INSTR".format(board, pad)


def load_library(name):
    """Windows'ta stdcall (WinDLL) ile DLL yukler."""
    if not IS_WINDOWS:
        raise TransportError(
            "{0} yalnizca Windows'ta yuklenebilir.".format(name))
    try:
        return ctypes.WinDLL(name)
    except OSError as exc:
        raise TransportError(
            "{0} yuklenemedi: {1}".format(name, exc))


def _fn(lib, names):
    """Kutuphaneden verilen adlardan ilk bulunan fonksiyonu dondurur."""
    for n in names:
        f = getattr(lib, n, None)
        if f is not None:
            return f
    return None


# ==========================================================================
# GPIB (NI-488.2 API, gpib-32.dll)
# ==========================================================================
class GpibTransport(object):
    """NI-488.2 uyumlu gpib-32.dll ile cihaz haberlesmesi."""

    kind = "gpib"
    DLL_NAME = "gpib-32.dll"
    BUFSIZE = 4096

    def __init__(self, resource, timeout_code=T30s, lib=None):
        parsed = parse_gpib_resource(resource)
        if parsed is None:
            raise TransportError(
                "'{0}' bir GPIB adresi degil. Ornek: GPIB0::26::INSTR".format(resource))
        self.resource = resource
        self.board, self.pad, self.sad = parsed
        self.timeout_code = timeout_code
        self._lib = lib
        self._ud = -1

    # ---------------- kutuphane ----------------
    def _load(self):
        if self._lib is None:
            self._lib = load_library(self.DLL_NAME)
        lib = self._lib
        c_int, c_long = ctypes.c_int, ctypes.c_long
        for name, args in (("ibdev", [c_int] * 6),
                           ("ibwrt", [c_int, ctypes.c_char_p, c_long]),
                           ("ibrd", [c_int, ctypes.c_void_p, c_long]),
                           ("ibclr", [c_int]),
                           ("ibonl", [c_int, c_int]),
                           ("ibtmo", [c_int, c_int])):
            f = getattr(lib, name, None)
            if f is None:
                raise TransportError(
                    "{0} icinde '{1}' fonksiyonu yok; NI-488.2 uyumlu bir "
                    "GPIB surucusu degil.".format(self.DLL_NAME, name))
            try:
                f.argtypes = args
                f.restype = c_int
            except (AttributeError, TypeError):
                pass
        return lib

    def _iberr(self):
        f = _fn(self._lib, ("ThreadIberr",))
        if f is not None:
            try:
                return int(f())
            except Exception:
                pass
        for var in ("user_iberr", "iberr"):
            try:
                return int(ctypes.c_int.in_dll(self._lib, var).value)
            except Exception:
                pass
        return None

    def _ibcnt(self):
        f = _fn(self._lib, ("ThreadIbcntl", "ThreadIbcnt"))
        if f is not None:
            try:
                return int(f())
            except Exception:
                pass
        for var in ("user_ibcntl", "ibcntl", "user_ibcnt", "ibcnt"):
            try:
                return int(ctypes.c_long.in_dll(self._lib, var).value)
            except Exception:
                pass
        return None

    def _raise(self, what, sta):
        code = self._iberr()
        text = IBERR_TEXT.get(code, "bilinmeyen hata")
        if sta & TIMO and code != 6:
            text += " (zaman asimi)"
        raise TransportError(
            "GPIB {0} basarisiz ({1}): iberr={2} {3}".format(
                what, self.resource, code, text))

    # ---------------- arayuz ----------------
    def open(self):
        lib = self._load()
        sad = (0x60 + self.sad) if self.sad else 0
        ud = int(lib.ibdev(self.board, self.pad, sad, self.timeout_code, 1, 0))
        if ud < 0:
            self._raise("ibdev (cihaz acma)", ERR)
        self._ud = ud
        self.clear()

    def clear(self):
        if self._ud < 0:
            return
        sta = int(self._lib.ibclr(self._ud))
        if sta & ERR:
            self._raise("ibclr (cihaz temizleme)", sta)

    def write(self, cmd):
        if self._ud < 0:
            raise TransportError("GPIB baglantisi acik degil.")
        data = (cmd + "\n").encode("ascii")
        sta = int(self._lib.ibwrt(self._ud, data, len(data)))
        if sta & ERR:
            self._raise("yazma", sta)

    def read(self):
        if self._ud < 0:
            raise TransportError("GPIB baglantisi acik degil.")
        chunks = []
        for _ in range(1000):
            buf = ctypes.create_string_buffer(self.BUFSIZE)
            sta = int(self._lib.ibrd(self._ud, buf, self.BUFSIZE))
            if sta & ERR:
                self._raise("okuma", sta)
            n = self._ibcnt()
            raw = buf.raw
            if n is None or n < 0 or n > self.BUFSIZE:
                n = raw.find(b"\x00")
                if n < 0:
                    n = self.BUFSIZE
            chunks.append(raw[:n])
            if sta & END or n < self.BUFSIZE:
                break
        return b"".join(chunks).decode("ascii", "replace").strip()

    def query(self, cmd):
        self.write(cmd)
        return self.read()

    def close(self):
        if self._ud >= 0 and self._lib is not None:
            try:
                self._lib.ibonl(self._ud, 0)
            except Exception:
                pass
        self._ud = -1

    @property
    def is_open(self):
        return self._ud >= 0


def gpib_scan(board=0, lib=None, pads=range(1, 31)):
    """GPIB hattindaki dinleyici cihazlari bulur (ibln ile).

    Doner: ['GPIB0::26::INSTR', ...]
    """
    if lib is None:
        lib = load_library(GpibTransport.DLL_NAME)
    find = _fn(lib, ("ibfindA", "ibfind"))
    ibln = getattr(lib, "ibln", None)
    if find is None or ibln is None:
        raise TransportError("gpib-32.dll icinde ibfind/ibln yok.")
    try:
        find.argtypes = [ctypes.c_char_p]
        find.restype = ctypes.c_int
        ibln.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.POINTER(ctypes.c_short)]
        ibln.restype = ctypes.c_int
    except (AttributeError, TypeError):
        pass

    bd = int(find("GPIB{0}".format(board).encode("ascii")))
    if bd < 0:
        raise TransportError(
            "GPIB{0} karti bulunamadi (ENEB). Adaptor takili ve surucu "
            "kurulu mu?".format(board))
    found = []
    for pad in pads:
        listen = ctypes.c_short(0)
        sta = int(ibln(bd, pad, 0, ctypes.pointer(listen)))
        if not (sta & ERR) and listen.value:
            found.append(gpib_resource_name(board, pad))
    return found


# ==========================================================================
# VISA (visa32.dll)
# ==========================================================================
class VisaTransport(object):
    """VISA kutuphanesi (visa32.dll) ile cihaz haberlesmesi."""

    kind = "visa"
    DLL_NAME = "visa32.dll"
    BUFSIZE = 4096

    def __init__(self, resource, timeout_ms=30000, lib=None):
        self.resource = resource
        self.timeout_ms = int(timeout_ms)
        self._lib = lib
        self._rm = None
        self._vi = None

    def _load(self):
        if self._lib is None:
            self._lib = load_library(self.DLL_NAME)
        lib = self._lib
        u32, i32 = ctypes.c_uint32, ctypes.c_int32
        p_u32 = ctypes.POINTER(u32)
        protos = (
            ("viOpenDefaultRM", [p_u32]),
            ("viOpen", [u32, ctypes.c_char_p, u32, u32, p_u32]),
            ("viClose", [u32]),
            ("viWrite", [u32, ctypes.c_char_p, u32, p_u32]),
            ("viRead", [u32, ctypes.c_void_p, u32, p_u32]),
            ("viSetAttribute", [u32, u32, u32]),
            ("viClear", [u32]),
        )
        for name, args in protos:
            f = getattr(lib, name, None)
            if f is None:
                raise TransportError(
                    "{0} icinde '{1}' yok; gecerli bir VISA kutuphanesi "
                    "degil.".format(self.DLL_NAME, name))
            try:
                f.argtypes = args
                f.restype = i32
            except (AttributeError, TypeError):
                pass
        return lib

    def _check(self, status, what):
        status = int(status)
        if status < 0:
            raise TransportError("VISA {0} basarisiz ({1}): {2}".format(
                what, self.resource, visa_status_text(self._lib, status, self._vi)))
        return status

    def open(self):
        lib = self._load()
        rm = ctypes.c_uint32(0)
        self._check(lib.viOpenDefaultRM(ctypes.pointer(rm)), "viOpenDefaultRM")
        self._rm = rm.value
        vi = ctypes.c_uint32(0)
        try:
            self._check(lib.viOpen(self._rm, self.resource.encode("ascii"), 0, 0,
                                   ctypes.pointer(vi)), "viOpen (cihaz acma)")
        except TransportError:
            lib.viClose(self._rm)
            self._rm = None
            raise
        self._vi = vi.value
        self._check(lib.viSetAttribute(self._vi, VI_ATTR_TMO_VALUE, self.timeout_ms),
                    "zaman asimi ayari")
        self.clear()

    def clear(self):
        if self._vi is not None:
            try:
                self._lib.viClear(self._vi)
            except Exception:
                pass

    def write(self, cmd):
        if self._vi is None:
            raise TransportError("VISA baglantisi acik degil.")
        data = (cmd + "\n").encode("ascii")
        ret = ctypes.c_uint32(0)
        self._check(self._lib.viWrite(self._vi, data, len(data), ctypes.pointer(ret)),
                    "yazma")

    def read(self):
        if self._vi is None:
            raise TransportError("VISA baglantisi acik degil.")
        chunks = []
        for _ in range(1000):
            buf = ctypes.create_string_buffer(self.BUFSIZE)
            ret = ctypes.c_uint32(0)
            st = self._check(self._lib.viRead(self._vi, buf, self.BUFSIZE,
                                              ctypes.pointer(ret)), "okuma")
            n = min(int(ret.value), self.BUFSIZE)
            chunks.append(buf.raw[:n])
            if st != VI_SUCCESS_MAX_CNT:
                break
        return b"".join(chunks).decode("ascii", "replace").strip()

    def query(self, cmd):
        self.write(cmd)
        return self.read()

    def close(self):
        lib = self._lib
        if lib is not None:
            for h in (self._vi, self._rm):
                if h is not None:
                    try:
                        lib.viClose(h)
                    except Exception:
                        pass
        self._vi = None
        self._rm = None

    @property
    def is_open(self):
        return self._vi is not None


def visa_status_text(lib, status, session=None):
    """VISA durum kodunun aciklamasini dondurur."""
    f = getattr(lib, "viStatusDesc", None) if lib is not None else None
    if f is not None:
        try:
            buf = ctypes.create_string_buffer(256)
            f(session or 0, status, buf)
            text = buf.value.decode("ascii", "replace").strip()
            if text:
                return "{0} (kod 0x{1:08X})".format(text, status & 0xFFFFFFFF)
        except Exception:
            pass
    return "kod 0x{0:08X}".format(status & 0xFFFFFFFF)


def visa_scan(lib=None, expr="?*INSTR"):
    """VISA'nin gordugu kaynaklari listeler."""
    if lib is None:
        lib = load_library(VisaTransport.DLL_NAME)
    u32 = ctypes.c_uint32
    rm = u32(0)
    st = int(lib.viOpenDefaultRM(ctypes.pointer(rm)))
    if st < 0:
        raise TransportError("VISA kaynak yoneticisi acilamadi: " +
                             visa_status_text(lib, st))
    found = []
    try:
        flist = u32(0)
        count = u32(0)
        desc = ctypes.create_string_buffer(256)
        st = int(lib.viFindRsrc(rm.value, expr.encode("ascii"), ctypes.pointer(flist),
                                ctypes.pointer(count), desc))
        if st < 0:
            return found      # VI_ERROR_RSRC_NFOUND: kaynak yok
        found.append(desc.value.decode("ascii", "replace"))
        for _ in range(max(0, int(count.value) - 1)):
            if int(lib.viFindNext(flist.value, desc)) < 0:
                break
            found.append(desc.value.decode("ascii", "replace"))
        try:
            lib.viClose(flist.value)
        except Exception:
            pass
    finally:
        try:
            lib.viClose(rm.value)
        except Exception:
            pass
    return found


# ==========================================================================
# Secim ve tarama
# ==========================================================================
BACKEND_AUTO = "auto"
BACKEND_GPIB = "gpib"
BACKEND_VISA = "visa"
BACKEND_SIM = "sim"

BACKEND_LABELS = [
    ("Otomatik (once gpib-32.dll, sonra VISA)", BACKEND_AUTO),
    ("GPIB - gpib-32.dll (NI / ADLINK)", BACKEND_GPIB),
    ("VISA - visa32.dll", BACKEND_VISA),
    ("Simulasyon (cihazsiz)", BACKEND_SIM),
]


def open_transport(resource, backend=BACKEND_AUTO, timeout_ms=30000):
    """Kaynak ve arayuz tipine gore acik bir transport dondurur."""
    is_gpib = parse_gpib_resource(resource) is not None
    errors = []

    if backend in (BACKEND_AUTO, BACKEND_GPIB) and is_gpib:
        try:
            t = GpibTransport(resource, timeout_code=_tmo_code(timeout_ms))
            t.open()
            return t
        except TransportError as exc:
            errors.append(str(exc))
            if backend == BACKEND_GPIB:
                raise
    elif backend == BACKEND_GPIB and not is_gpib:
        raise TransportError(
            "'GPIB' arayuzu secili ama '{0}' bir GPIB adresi degil.".format(resource))

    if backend in (BACKEND_AUTO, BACKEND_VISA):
        try:
            t = VisaTransport(resource, timeout_ms=timeout_ms)
            t.open()
            return t
        except TransportError as exc:
            errors.append(str(exc))

    raise TransportError("Baglanti kurulamadi:\n- " + "\n- ".join(errors or ["bilinmeyen"]))


def _tmo_code(timeout_ms):
    if timeout_ms <= 1000:
        return T1s
    if timeout_ms <= 3000:
        return T3s
    if timeout_ms <= 10000:
        return T10s
    if timeout_ms <= 30000:
        return T30s
    if timeout_ms <= 100000:
        return T100s
    return T300s


def scan_all(board=0):
    """Tum arayuzlerde kaynak tarar.

    Doner: (kaynaklar, notlar) -- notlar, kullaniciya gosterilecek durum
    satirlaridir (hangi DLL yuklendi, hangisi yuklenmedi).
    """
    resources = []
    notes = []
    try:
        g = gpib_scan(board)
        notes.append("gpib-32.dll: {0} cihaz bulundu".format(len(g)))
        resources.extend(g)
    except TransportError as exc:
        notes.append("gpib-32.dll: " + str(exc))
    try:
        v = visa_scan()
        notes.append("visa32.dll: {0} kaynak bulundu".format(len(v)))
        for r in v:
            if r not in resources:
                resources.append(r)
    except TransportError as exc:
        notes.append("visa32.dll: " + str(exc))
    return resources, notes
