"""Cihazsiz calisma icin Keithley 2636 simulatoru.

Gercek surucu ile ayni arayuze sahiptir; boylece program laboratuvar disinda
(GPIB baglantisi olmadan) test edilebilir. Numune olarak bir UV fotodedektor
(Schottky/fotodiyot benzeri) modellenir:

    I(V) = I0 * (exp(qV / (n k T)) - 1) + V / Rsh - I_ph

I_ph yalnizca ``uv_on`` iken akar; boylece karanlik/aydinlik farki ve
zaman tepkisi (rise/fall) gercekci bicimde uretilir.
"""

from __future__ import annotations

import math
import random
import time
from typing import List, Optional, Tuple

from .instrument import SOURCE_VOLTAGE, SmuConfig

Q_E = 1.602176634e-19
K_B = 1.380649e-23


class SimulatedKeithley2636:
    """Keithley2636 ile ayni public API'ye sahip sahte cihaz."""

    def __init__(self, resource: str = "SIM", timeout_ms: int = 30000, **_):
        self.resource = resource
        self.timeout_ms = timeout_ms
        self.idn = "Keithley Instruments Inc., Model 2636 (SIMULASYON), 0000000, 1.0.0"
        self._config = SmuConfig()
        self._connected = False
        self._output = False
        self._level = 0.0

        # --- numune modeli parametreleri ---
        self.i0 = 5e-12           # ters doyma akimi (A)
        self.ideality = 1.9       # idealite faktoru
        self.temperature = 298.0  # K
        self.r_shunt = 5e9        # shunt direnc (ohm)
        self.r_series = 250.0     # seri direnc (ohm)
        self.responsivity = 0.18  # A/W (365 nm icin tipik)
        self.optical_power = 2.0e-6   # W (numune uzerine dusen guc)
        self.noise_floor = 4e-13  # A rms
        self.rise_tau = 0.35      # s
        self.fall_tau = 0.55      # s

        self.uv_on = False
        self._uv_changed_at = time.time()
        self._photo_state = 0.0   # 0..1 arasi normalize fotoakim

    # ------------------------------------------------------------------
    @staticmethod
    def list_resources(visa_library: str = "") -> List[str]:
        return ["SIM::UVPD::INSTR"]

    def connect(self, visa_library: str = "") -> str:
        self._connected = True
        return self.idn

    def close(self) -> None:
        self._output = False
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    def write(self, cmd: str) -> None:
        pass

    def query(self, cmd: str) -> str:
        return "0"

    def query_floats(self, tsp_expr: str) -> List[float]:
        return [0.0]

    def check_errors(self) -> List[str]:
        return []

    def reset(self) -> None:
        self._output = False
        self._level = 0.0

    def apply_config(self, cfg: SmuConfig) -> None:
        self._config = cfg

    # ------------------------------------------------------------------
    def output_on(self) -> None:
        self._output = True

    def output_off(self) -> None:
        self._output = False
        self._level = 0.0

    def set_level(self, level: float) -> None:
        self._level = float(level)

    def set_uv(self, on: bool) -> None:
        """Simulasyonda UV kaynagini ac/kapa (GUI'deki test dugmesi icin)."""
        if bool(on) != self.uv_on:
            self.uv_on = bool(on)
            self._uv_changed_at = time.time()

    # ------------------------------------------------------------------
    def _photocurrent(self) -> float:
        """Ust/alt ussel gecisli fotoakim (zaman tepkisi icin)."""
        dt = time.time() - self._uv_changed_at
        target = 1.0 if self.uv_on else 0.0
        tau = self.rise_tau if self.uv_on else self.fall_tau
        start = self._photo_state
        state = target + (start - target) * math.exp(-dt / tau)
        return self.responsivity * self.optical_power * state

    def _diode_current(self, v: float) -> float:
        vt = self.ideality * K_B * self.temperature / Q_E
        # seri direnc icin basit iterasyon
        i = 0.0
        for _ in range(12):
            vd = v - i * self.r_series
            arg = max(-60.0, min(60.0, vd / vt))
            i_new = self.i0 * (math.exp(arg) - 1.0) + vd / self.r_shunt
            i = 0.5 * i + 0.5 * i_new
            if abs(i) > 1.5:
                i = math.copysign(1.5, i)
                break
        return i

    def measure_iv(self) -> Tuple[float, float]:
        if not self._output:
            return random.gauss(0.0, self.noise_floor), 0.0

        i_ph = self._photocurrent()
        self._photo_state = i_ph / max(self.responsivity * self.optical_power, 1e-30)

        if self._config.source_func == SOURCE_VOLTAGE:
            v = self._level
            i = self._diode_current(v) - i_ph
            limit = self._config.compliance
            if abs(i) > limit:  # akim limiti
                i = math.copysign(limit, i)
                v = self._level * 0.98
        else:
            i = self._level
            # akim kaynagi: gerilimi diyot denkleminden geri coz (basit arama)
            lo, hi = -20.0, 20.0
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if self._diode_current(mid) - i_ph < i:
                    lo = mid
                else:
                    hi = mid
            v = 0.5 * (lo + hi)
            v = max(-self._config.compliance, min(self._config.compliance, v))

        i += random.gauss(0.0, self.noise_floor + abs(i) * 2e-4)
        v += random.gauss(0.0, 20e-6)
        return i, v

    def set_level_and_measure(self, level: float, settle_s: float = 0.0) -> Tuple[float, float]:
        self.set_level(level)
        if settle_s > 0:
            time.sleep(settle_s)
        return self.measure_iv()

    def in_compliance(self) -> bool:
        return False

    def beep(self, duration: float = 0.2, freq: float = 1200) -> None:
        pass

    def read_digio_bit(self, bit: int) -> Optional[int]:
        return 1
