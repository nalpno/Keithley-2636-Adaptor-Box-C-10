# -*- coding: utf-8 -*-
"""Testler icin sahte gpib-32.dll / visa32.dll ve Keithley cevap uretici.

Gercek DLL'ler yalnizca Windows'ta vardir; bu sahte nesneler ayni fonksiyon
imzalarini taklit ederek transport katmaninin mantigini her platformda test
etmeyi saglar.
"""

import ctypes

from uvpd_xp.transport import END, ERR, TIMO, VI_ERROR_RSRC_NFOUND, VI_SUCCESS_MAX_CNT

IDN = "Keithley Instruments Inc., Model 2636B, 4037576, 3.0.3"


def keithley_answer(cmd):
    """Bir TSP komutuna Keithley'in verecegi cevap (cevap yoksa None)."""
    cmd = cmd.strip()
    if cmd == "*IDN?":
        return IDN
    if cmd.startswith("print(") and "measure.iv()" in cmd:
        return "-1.234500000e-09\t-5.000000000e-01"
    if cmd == "print(errorqueue.count)":
        return "0.00000e+00"
    if cmd.startswith("print(digio.readbit"):
        return "1.00000e+00"
    if cmd.startswith("print("):
        return "0"
    return None


class FakeGpibLib(object):
    """NI-488.2 API taklidi."""

    def __init__(self, listeners=(26,), with_count=True, fail_read_err=None, long_answer=None):
        self.listeners = set(listeners)
        self.with_count = with_count
        self.fail_read_err = fail_read_err
        self.long_answer = long_answer
        self.written = []
        self.pending = b""
        self.cnt = 0
        self.err = 0
        self.online = {}
        if not with_count:
            # ThreadIbcntl yoksa transport NUL'a kadar okumaya dusmeli
            self.ThreadIbcntl = None

    # --- cihaz ---
    def ibdev(self, board, pad, sad, tmo, eot, eos):
        if pad not in self.listeners:
            self.err = 2       # ENOL (bazi suruculer ibdev'de degil ilk G/C'de verir)
        self.online[1] = pad
        return 1

    def ibclr(self, ud):
        if self.online.get(ud) not in self.listeners:
            self.err = 2
            return ERR
        return 0

    def ibonl(self, ud, v):
        self.online.pop(ud, None)
        return 0

    def ibtmo(self, ud, tmo):
        return 0

    def ibwrt(self, ud, data, n):
        if self.online.get(ud) not in self.listeners:
            self.err = 2
            return ERR
        text = bytes(data[:n]).decode("ascii").strip()
        self.written.append(text)
        ans = self.long_answer if (self.long_answer and text == "*IDN?") else keithley_answer(text)
        if ans is not None:
            self.pending = (ans + "\n").encode("ascii")
        self.cnt = n
        return 0

    def ibrd(self, ud, buf, n):
        if self.fail_read_err is not None:
            self.err = self.fail_read_err
            return ERR | TIMO
        chunk = self.pending[:n]
        self.pending = self.pending[n:]
        ctypes.memmove(buf, chunk, len(chunk))
        self.cnt = len(chunk)
        return END if not self.pending else 0

    def ThreadIbcntl(self):
        return self.cnt

    def ThreadIberr(self):
        return self.err

    # --- tarama ---
    def ibfind(self, name):
        return 0 if name == b"GPIB0" else -1

    def ibln(self, bd, pad, sad, listen_ptr):
        listen_ptr.contents.value = 1 if pad in self.listeners else 0
        return 0


class FakeVisaLib(object):
    """VISA API taklidi."""

    def __init__(self, resources=("GPIB0::26::INSTR", "ASRL1::INSTR"), long_answer=None):
        self.resources = list(resources)
        self.long_answer = long_answer
        self.pending = b""
        self.written = []
        self.closed = []

    def viOpenDefaultRM(self, ptr):
        ptr.contents.value = 100
        return 0

    def viOpen(self, rm, name, mode, tmo, ptr):
        if name.decode("ascii") not in self.resources:
            return VI_ERROR_RSRC_NFOUND
        ptr.contents.value = 200
        return 0

    def viSetAttribute(self, vi, attr, value):
        return 0

    def viClear(self, vi):
        return 0

    def viClose(self, h):
        self.closed.append(h)
        return 0

    def viWrite(self, vi, data, n, ret_ptr):
        text = bytes(data[:n]).decode("ascii").strip()
        self.written.append(text)
        ans = self.long_answer if (self.long_answer and text == "*IDN?") else keithley_answer(text)
        if ans is not None:
            self.pending = (ans + "\n").encode("ascii")
        ret_ptr.contents.value = n
        return 0

    def viRead(self, vi, buf, n, ret_ptr):
        chunk = self.pending[:n]
        self.pending = self.pending[n:]
        ctypes.memmove(buf, chunk, len(chunk))
        ret_ptr.contents.value = len(chunk)
        return VI_SUCCESS_MAX_CNT if self.pending else 0

    def viFindRsrc(self, rm, expr, flist_ptr, count_ptr, desc):
        if not self.resources:
            return VI_ERROR_RSRC_NFOUND
        flist_ptr.contents.value = 300
        count_ptr.contents.value = len(self.resources)
        self._idx = 1
        desc.value = self.resources[0].encode("ascii")
        return 0

    def viFindNext(self, flist, desc):
        desc.value = self.resources[self._idx].encode("ascii")
        self._idx += 1
        return 0


class FakeTransport(object):
    """Instrument testleri icin: yazilan komutlari kaydeder, cevap uretir."""

    kind = "fake"

    def __init__(self):
        self.written = []
        self.is_open = True
        self._answer = None

    def open(self):
        self.is_open = True

    def write(self, cmd):
        self.written.append(cmd)
        self._answer = keithley_answer(cmd)

    def read(self):
        return self._answer or ""

    def query(self, cmd):
        self.write(cmd)
        return self.read()

    def clear(self):
        pass

    def close(self):
        self.is_open = False
