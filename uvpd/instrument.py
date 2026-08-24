"""Keithley 2636 (2600 serisi, TSP) surucusu.

Cihaz GPIB uzerinden (USB-3488A USB/GPIB arabirimi + VISA) kontrol edilir.
2600 serisi varsayilan olarak SCPI degil TSP (Lua) dilini kullanir; bu modul
sadece TSP komutlari gonderir.

Tipik kaynak adresi: ``GPIB0::26::INSTR`` (2636 fabrika cikisi GPIB adresi 26).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Sabitler
# --------------------------------------------------------------------------
SOURCE_VOLTAGE = "voltage"
SOURCE_CURRENT = "current"

#: Keithley 2636 akim olcum kademeleri (A). Dusuk akim limiti secimi icin.
CURRENT_RANGES = [
    1e-10, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1.0, 1.5,
]
#: Gerilim kademeleri (V).
VOLTAGE_RANGES = [200e-3, 2.0, 20.0, 200.0]


@dataclass
class SmuConfig:
    """SMU kaynak/olcum ayarlari (tek kanal icin)."""

    channel: str = "a"                    # "a" veya "b"
    source_func: str = SOURCE_VOLTAGE     # voltage | current
    compliance: float = 1e-3              # akim kaynagi ise V limiti, gerilim kaynagi ise I limiti
    nplc: float = 1.0                     # 0.001 - 25 (50 Hz sebekede 1 NPLC = 20 ms)
    measure_delay: float = 0.0            # olcum oncesi ek bekleme (s); <0 ise AUTO
    filter_count: int = 1                 # 1 = filtre kapali
    filter_type: str = "repeat"           # repeat | moving | median
    four_wire: bool = False               # True ise remote sense (4 uclu)
    autorange: bool = True
    low_range_i: float = 1e-9             # otomatik kademede alt sinir (A)
    low_range_v: float = 200e-3           # otomatik kademede alt sinir (V)
    high_capacitance: bool = False        # yuksek kapasiteli numuneler icin
    auto_zero: str = "auto"               # off | once | auto
    beep_on_finish: bool = True

    @property
    def smu(self) -> str:
        return f"smu{self.channel.lower()}"


class InstrumentError(RuntimeError):
    """Cihaz iletisimi / TSP hata kuyrugu kaynakli hatalar."""


class Keithley2636:
    """PyVISA tabanli TSP surucusu.

    Kullanim::

        k = Keithley2636("GPIB0::26::INSTR")
        k.connect()
        k.apply_config(SmuConfig(source_func="voltage", compliance=1e-3))
        k.output_on()
        i, v = k.set_level_and_measure(0.5)
        k.output_off()
        k.close()
    """

    def __init__(self, resource: str, timeout_ms: int = 30000, read_termination: str = "\n"):
        self.resource = resource
        self.timeout_ms = timeout_ms
        self.read_termination = read_termination
        self._rm = None
        self._inst = None
        self._config = SmuConfig()
        self.idn = ""

    # ------------------------------------------------------------------
    # Baglanti
    # ------------------------------------------------------------------
    @staticmethod
    def list_resources(visa_library: str = "") -> List[str]:
        """Sistemdeki VISA kaynaklarini listeler (GPIB0::26::INSTR gibi)."""
        import pyvisa

        rm = pyvisa.ResourceManager(visa_library)
        try:
            return list(rm.list_resources())
        finally:
            rm.close()

    def connect(self, visa_library: str = "") -> str:
        import pyvisa

        self._rm = pyvisa.ResourceManager(visa_library)
        self._inst = self._rm.open_resource(self.resource)
        self._inst.timeout = self.timeout_ms
        self._inst.read_termination = self.read_termination
        self._inst.write_termination = self.read_termination
        # TSP: prompt ve hata mesajlarinin cikti kuyruguna karismasini engelle
        self.write("localnode.prompts = 0")
        self.write("localnode.showerrors = 0")
        self.write("format.data = format.ASCII")
        self.write("format.asciiprecision = 10")
        self.write("errorqueue.clear()")
        self.idn = self.query("*IDN?")
        log.info("Baglanildi: %s (%s)", self.idn, self.resource)
        return self.idn

    def close(self) -> None:
        if self._inst is not None:
            try:
                self.output_off()
            except Exception:  # pragma: no cover - kapanista hata yutulur
                pass
            try:
                self._inst.close()
            finally:
                self._inst = None
        if self._rm is not None:
            try:
                self._rm.close()
            finally:
                self._rm = None

    @property
    def connected(self) -> bool:
        return self._inst is not None

    # ------------------------------------------------------------------
    # Dusuk seviyeli iletisim
    # ------------------------------------------------------------------
    def write(self, cmd: str) -> None:
        if self._inst is None:
            raise InstrumentError("Cihaz bagli degil.")
        log.debug("W: %s", cmd)
        self._inst.write(cmd)

    def query(self, cmd: str) -> str:
        if self._inst is None:
            raise InstrumentError("Cihaz bagli degil.")
        log.debug("Q: %s", cmd)
        return self._inst.query(cmd).strip()

    def query_floats(self, tsp_expr: str) -> List[float]:
        """``print(<expr>)`` calistirip donen sayilari listeler.

        TSP birden fazla degeri sekme (tab) ile ayirir; virgul ve bosluk da
        ayirici olarak kabul edilir.
        """
        raw = self.query(f"print({tsp_expr})")
        return [float(x) for x in re.split(r"[,;\s]+", raw.strip()) if x]

    def check_errors(self) -> List[str]:
        """TSP hata kuyrugunu bosaltir ve mesajlari dondurur."""
        msgs: List[str] = []
        try:
            count = int(float(self.query("print(errorqueue.count)")))
        except Exception:
            return msgs
        for _ in range(count):
            msgs.append(self.query("print(errorqueue.next())"))
        return msgs

    # ------------------------------------------------------------------
    # Yapilandirma
    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.write("reset()")
        self.write("errorqueue.clear()")
        self.write("status.reset()")

    def apply_config(self, cfg: SmuConfig) -> None:
        """SmuConfig'i cihaza yazar."""
        self._config = cfg
        s = cfg.smu
        self.write(f"{s}.reset()")

        if cfg.source_func == SOURCE_VOLTAGE:
            self.write(f"{s}.source.func = {s}.OUTPUT_DCVOLTS")
            self.write(f"{s}.source.limiti = {cfg.compliance:g}")
            self.write(f"{s}.source.autorangev = {s}.AUTORANGE_ON")
            if cfg.autorange:
                self.write(f"{s}.measure.autorangei = {s}.AUTORANGE_ON")
                self.write(f"{s}.measure.lowrangei = {cfg.low_range_i:g}")
            else:
                self.write(f"{s}.measure.autorangei = {s}.AUTORANGE_OFF")
                self.write(f"{s}.measure.rangei = {abs(cfg.compliance):g}")
        else:
            self.write(f"{s}.source.func = {s}.OUTPUT_DCAMPS")
            self.write(f"{s}.source.limitv = {cfg.compliance:g}")
            self.write(f"{s}.source.autorangei = {s}.AUTORANGE_ON")
            if cfg.autorange:
                self.write(f"{s}.measure.autorangev = {s}.AUTORANGE_ON")
                self.write(f"{s}.measure.lowrangev = {cfg.low_range_v:g}")
            else:
                self.write(f"{s}.measure.autorangev = {s}.AUTORANGE_OFF")
                self.write(f"{s}.measure.rangev = {abs(cfg.compliance):g}")

        self.write(f"{s}.measure.nplc = {max(0.001, min(25.0, cfg.nplc)):g}")

        if cfg.measure_delay < 0:
            self.write(f"{s}.measure.delay = {s}.DELAY_AUTO")
        else:
            self.write(f"{s}.measure.delay = {cfg.measure_delay:g}")

        az = {"off": "AUTOZERO_OFF", "once": "AUTOZERO_ONCE", "auto": "AUTOZERO_AUTO"}
        self.write(f"{s}.measure.autozero = {s}.{az.get(cfg.auto_zero, 'AUTOZERO_AUTO')}")

        if cfg.filter_count and cfg.filter_count > 1:
            ftype = {"repeat": "FILTER_REPEAT_AVG",
                     "moving": "FILTER_MOVING_AVG",
                     "median": "FILTER_MEDIAN"}[cfg.filter_type]
            self.write(f"{s}.measure.filter.count = {int(cfg.filter_count)}")
            self.write(f"{s}.measure.filter.type = {s}.{ftype}")
            self.write(f"{s}.measure.filter.enable = {s}.FILTER_ON")
        else:
            self.write(f"{s}.measure.filter.enable = {s}.FILTER_OFF")

        self.write(f"{s}.sense = {s}.SENSE_{'REMOTE' if cfg.four_wire else 'LOCAL'}")
        self.write(f"{s}.source.highc = {s}.{'ENABLE' if cfg.high_capacitance else 'DISABLE'}")
        # Cikis kapaliyken 0 V, kucuk akim limiti ile guvenli durum
        self.write(f"{s}.source.offfunc = {s}.OUTPUT_DCVOLTS")
        self.write(f"{s}.source.offmode = {s}.OUTPUT_NORMAL")
        self.write(f"{s}.source.offlimiti = 1e-3")
        self.write(f"{s}.source.level{'v' if cfg.source_func == SOURCE_VOLTAGE else 'i'} = 0")

        errs = self.check_errors()
        if errs:
            raise InstrumentError("Cihaz hata kuyrugu: " + " | ".join(errs))

    # ------------------------------------------------------------------
    # Cikis ve olcum
    # ------------------------------------------------------------------
    def output_on(self) -> None:
        self.write(f"{self._config.smu}.source.output = {self._config.smu}.OUTPUT_ON")

    def output_off(self) -> None:
        s = self._config.smu
        self.write(f"{s}.source.level{'v' if self._config.source_func == SOURCE_VOLTAGE else 'i'} = 0")
        self.write(f"{s}.source.output = {s}.OUTPUT_OFF")

    def set_level(self, level: float) -> None:
        s = self._config.smu
        key = "v" if self._config.source_func == SOURCE_VOLTAGE else "i"
        self.write(f"{s}.source.level{key} = {level:.10g}")

    def measure_iv(self) -> Tuple[float, float]:
        """(akim [A], gerilim [V]) ikilisini olcer."""
        vals = self.query_floats(f"{self._config.smu}.measure.iv()")
        return vals[0], vals[1]

    def set_level_and_measure(self, level: float, settle_s: float = 0.0) -> Tuple[float, float]:
        self.set_level(level)
        if settle_s > 0:
            time.sleep(settle_s)
        return self.measure_iv()

    def in_compliance(self) -> bool:
        raw = self.query(f"print({self._config.smu}.source.compliance)")
        return "true" in raw.lower()

    def beep(self, duration: float = 0.2, freq: float = 1200) -> None:
        try:
            self.write("beeper.enable = beeper.ON")
            self.write(f"beeper.beep({duration:g}, {freq:g})")
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------
    # Interlock / digital I/O (istege bagli)
    # ------------------------------------------------------------------
    def read_digio_bit(self, bit: int) -> Optional[int]:
        """Digital I/O hattindan bit okur.

        Adapter Box C 10'un INTERLOCK hatti SMU'nun digital I/O portuna
        baglanmissa numunenin kapali olup olmadigi buradan izlenebilir.
        Baglanti yoksa None doner.
        """
        try:
            return int(float(self.query(f"print(digio.readbit({int(bit)}))")))
        except Exception:
            return None


# --------------------------------------------------------------------------
# Fabrika: gercek cihaz veya simulator
# --------------------------------------------------------------------------
def create_instrument(resource: str, simulate: bool = False, **kwargs):
    """Baglanti tipine gore gercek cihaz veya simulator dondurur."""
    if simulate or resource.upper().startswith("SIM"):
        from .simulator import SimulatedKeithley2636

        return SimulatedKeithley2636(resource, **kwargs)
    return Keithley2636(resource, **kwargs)
