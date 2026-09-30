# -*- coding: utf-8 -*-
"""Keithley 2636/2636B (2600 serisi, TSP) surucusu - Python 3.4 / XP surumu.

2600 serisi SCPI degil TSP (Lua) dili kullanir. Komutlar modern surumle
birebir aynidir; yalnizca haberlesme katmani (transport.py) farklidir.
"""

import re
import time

from .transport import BACKEND_AUTO, BACKEND_SIM, open_transport

SOURCE_VOLTAGE = "voltage"
SOURCE_CURRENT = "current"

#: Akim olcum kademeleri (A)
CURRENT_RANGES = [1e-10, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3,
                  1e-2, 1e-1, 1.0, 1.5]


class InstrumentError(RuntimeError):
    """Cihaz iletisimi / TSP hata kuyrugu kaynakli hatalar."""


class SmuConfig(object):
    """SMU kaynak/olcum ayarlari (tek kanal)."""

    def __init__(self, channel="a", source_func=SOURCE_VOLTAGE, compliance=1e-3,
                 nplc=1.0, measure_delay=0.0, filter_count=1, filter_type="repeat",
                 four_wire=False, autorange=True, low_range_i=1e-9,
                 low_range_v=0.2, high_capacitance=False, auto_zero="auto",
                 beep_on_finish=True):
        self.channel = channel
        self.source_func = source_func
        self.compliance = float(compliance)
        self.nplc = float(nplc)
        self.measure_delay = float(measure_delay)
        self.filter_count = int(filter_count)
        self.filter_type = filter_type
        self.four_wire = bool(four_wire)
        self.autorange = bool(autorange)
        self.low_range_i = float(low_range_i)
        self.low_range_v = float(low_range_v)
        self.high_capacitance = bool(high_capacitance)
        self.auto_zero = auto_zero
        self.beep_on_finish = bool(beep_on_finish)

    @property
    def smu(self):
        return "smu" + self.channel.lower()

    def as_dict(self):
        return dict(self.__dict__)


def _num(x):
    return "{0:g}".format(float(x))


class Keithley2636(object):
    """TSP komutlariyla Keithley 2600 serisi kontrolu.

    ``transport`` verilirse onu kullanir (testler icin); verilmezse
    connect() sirasinda ``resource`` ve ``backend``'e gore acilir.
    """

    def __init__(self, resource, backend=BACKEND_AUTO, timeout_ms=30000, transport=None):
        self.resource = resource
        self.backend = backend
        self.timeout_ms = timeout_ms
        self._t = transport
        self._config = SmuConfig()
        self.idn = ""

    # ---------------- baglanti ----------------
    def connect(self):
        if self._t is None:
            self._t = open_transport(self.resource, self.backend, self.timeout_ms)
        elif not getattr(self._t, "is_open", True):
            self._t.open()
        # prompt ve hata mesajlari cikti kuyruguna karismasin
        self.write("localnode.prompts = 0")
        self.write("localnode.showerrors = 0")
        self.write("format.data = format.ASCII")
        self.write("format.asciiprecision = 10")
        self.write("errorqueue.clear()")
        self.idn = self.query("*IDN?")
        return self.idn

    def close(self):
        if self._t is not None:
            try:
                self.output_off()
            except Exception:
                pass
            try:
                self._t.close()
            finally:
                self._t = None

    @property
    def connected(self):
        return self._t is not None and getattr(self._t, "is_open", True)

    @property
    def transport_kind(self):
        return getattr(self._t, "kind", "?")

    # ---------------- dusuk seviye ----------------
    def write(self, cmd):
        if self._t is None:
            raise InstrumentError("Cihaz bagli degil.")
        self._t.write(cmd)

    def query(self, cmd):
        if self._t is None:
            raise InstrumentError("Cihaz bagli degil.")
        return self._t.query(cmd).strip()

    def query_floats(self, expr):
        """print(expr) calistirir; TSP degerleri sekme ile ayirir."""
        raw = self.query("print({0})".format(expr))
        vals = []
        for part in re.split(r"[,;\s]+", raw.strip()):
            if part:
                vals.append(float(part))
        return vals

    def check_errors(self):
        msgs = []
        try:
            count = int(float(self.query("print(errorqueue.count)")))
        except Exception:
            return msgs
        for _ in range(count):
            msgs.append(self.query("print(errorqueue.next())"))
        return msgs

    # ---------------- yapilandirma ----------------
    def reset(self):
        self.write("reset()")
        self.write("errorqueue.clear()")

    def apply_config(self, cfg):
        self._config = cfg
        s = cfg.smu
        w = self.write
        w("{0}.reset()".format(s))
        if cfg.source_func == SOURCE_VOLTAGE:
            w("{0}.source.func = {0}.OUTPUT_DCVOLTS".format(s))
            w("{0}.source.limiti = {1}".format(s, _num(cfg.compliance)))
            w("{0}.source.autorangev = {0}.AUTORANGE_ON".format(s))
            if cfg.autorange:
                w("{0}.measure.autorangei = {0}.AUTORANGE_ON".format(s))
                w("{0}.measure.lowrangei = {1}".format(s, _num(cfg.low_range_i)))
            else:
                w("{0}.measure.autorangei = {0}.AUTORANGE_OFF".format(s))
                w("{0}.measure.rangei = {1}".format(s, _num(abs(cfg.compliance))))
        else:
            w("{0}.source.func = {0}.OUTPUT_DCAMPS".format(s))
            w("{0}.source.limitv = {1}".format(s, _num(cfg.compliance)))
            w("{0}.source.autorangei = {0}.AUTORANGE_ON".format(s))
            if cfg.autorange:
                w("{0}.measure.autorangev = {0}.AUTORANGE_ON".format(s))
                w("{0}.measure.lowrangev = {1}".format(s, _num(cfg.low_range_v)))
            else:
                w("{0}.measure.autorangev = {0}.AUTORANGE_OFF".format(s))
                w("{0}.measure.rangev = {1}".format(s, _num(abs(cfg.compliance))))

        w("{0}.measure.nplc = {1}".format(s, _num(max(0.001, min(25.0, cfg.nplc)))))
        if cfg.measure_delay < 0:
            w("{0}.measure.delay = {0}.DELAY_AUTO".format(s))
        else:
            w("{0}.measure.delay = {1}".format(s, _num(cfg.measure_delay)))

        az = {"off": "AUTOZERO_OFF", "once": "AUTOZERO_ONCE", "auto": "AUTOZERO_AUTO"}
        w("{0}.measure.autozero = {0}.{1}".format(s, az.get(cfg.auto_zero, "AUTOZERO_AUTO")))

        if cfg.filter_count > 1:
            ftype = {"repeat": "FILTER_REPEAT_AVG", "moving": "FILTER_MOVING_AVG",
                     "median": "FILTER_MEDIAN"}.get(cfg.filter_type, "FILTER_REPEAT_AVG")
            w("{0}.measure.filter.count = {1}".format(s, int(cfg.filter_count)))
            w("{0}.measure.filter.type = {0}.{1}".format(s, ftype))
            w("{0}.measure.filter.enable = {0}.FILTER_ON".format(s))
        else:
            w("{0}.measure.filter.enable = {0}.FILTER_OFF".format(s))

        w("{0}.sense = {0}.SENSE_{1}".format(s, "REMOTE" if cfg.four_wire else "LOCAL"))
        w("{0}.source.highc = {0}.{1}".format(s, "ENABLE" if cfg.high_capacitance else "DISABLE"))
        # cikis kapaliyken 0 V, kucuk akim limitiyle guvenli durum
        w("{0}.source.offfunc = {0}.OUTPUT_DCVOLTS".format(s))
        w("{0}.source.offmode = {0}.OUTPUT_NORMAL".format(s))
        w("{0}.source.offlimiti = 1e-3".format(s))
        w("{0}.source.level{1} = 0".format(s, "v" if cfg.source_func == SOURCE_VOLTAGE else "i"))

        errs = self.check_errors()
        if errs:
            raise InstrumentError("Cihaz hata kuyrugu: " + " | ".join(errs))

    # ---------------- cikis / olcum ----------------
    def _level_key(self):
        return "v" if self._config.source_func == SOURCE_VOLTAGE else "i"

    def output_on(self):
        self.write("{0}.source.output = {0}.OUTPUT_ON".format(self._config.smu))

    def output_off(self):
        s = self._config.smu
        self.write("{0}.source.level{1} = 0".format(s, self._level_key()))
        self.write("{0}.source.output = {0}.OUTPUT_OFF".format(s))

    def set_level(self, level):
        self.write("{0}.source.level{1} = {2:.10g}".format(
            self._config.smu, self._level_key(), float(level)))

    def measure_iv(self):
        """(akim [A], gerilim [V])"""
        vals = self.query_floats("{0}.measure.iv()".format(self._config.smu))
        if len(vals) < 2:
            raise InstrumentError("Beklenmeyen olcum cevabi: {0!r}".format(vals))
        return vals[0], vals[1]

    def set_level_and_measure(self, level, settle_s=0.0):
        self.set_level(level)
        if settle_s > 0:
            time.sleep(settle_s)
        return self.measure_iv()

    def beep(self, duration=0.2, freq=1200):
        try:
            self.write("beeper.enable = beeper.ON")
            self.write("beeper.beep({0}, {1})".format(_num(duration), _num(freq)))
        except Exception:
            pass

    def write_digio_bit(self, bit, value):
        """Digital I/O hattina yazar (UV shutter kontrolu icin)."""
        self.write("digio.writebit({0}, {1})".format(int(bit), 1 if value else 0))

    def read_digio_bit(self, bit):
        try:
            return int(float(self.query("print(digio.readbit({0}))".format(int(bit)))))
        except Exception:
            return None


def create_instrument(resource, backend=BACKEND_AUTO, timeout_ms=30000):
    """Arayuz tipine gore gercek cihaz ya da simulator dondurur."""
    if backend == BACKEND_SIM or resource.upper().startswith("SIM"):
        from .simulator import SimulatedKeithley2636
        return SimulatedKeithley2636(resource)
    return Keithley2636(resource, backend=backend, timeout_ms=timeout_ms)
