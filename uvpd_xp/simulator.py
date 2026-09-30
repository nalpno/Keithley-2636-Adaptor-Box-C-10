# -*- coding: utf-8 -*-
"""Cihazsiz calisma icin Keithley 2636 simulatoru (UV fotodedektor modeli).

    I(V) = I0 * (exp(qV / nkT) - 1) + V / Rsh - I_ph

I_ph yalnizca ``uv_on`` iken akar; acma/kapamada ustel gecis vardir, boylece
karanlik/aydinlik farki ve zaman tepkisi gercekci uretilir.
"""

import math
import random
import time

from .instrument import SOURCE_VOLTAGE, SmuConfig

Q_E = 1.602176634e-19
K_B = 1.380649e-23
_now = time.perf_counter


class SimulatedKeithley2636(object):
    """Keithley2636 ile ayni public arayuze sahip sahte cihaz."""

    transport_kind = "sim"

    def __init__(self, resource="SIM", **_):
        self.resource = resource
        self.idn = "Keithley Instruments Inc., Model 2636B (SIMULASYON), 0000000, 3.0.3"
        self._config = SmuConfig()
        self._connected = False
        self._output = False
        self._level = 0.0

        self.i0 = 5e-12
        self.ideality = 1.9
        self.temperature = 298.0
        self.r_shunt = 5e9
        self.r_series = 250.0
        self.responsivity = 0.18      # A/W
        self.optical_power = 2.0e-6   # W
        self.noise_floor = 4e-13      # A
        self.rise_tau = 0.35          # s
        self.fall_tau = 0.55          # s

        self.uv_on = False
        self._uv_changed_at = _now()
        self._photo_state = 0.0
        self._state_at_change = 0.0

    # ---------------- baglanti ----------------
    def connect(self):
        self._connected = True
        return self.idn

    def close(self):
        self._output = False
        self._connected = False

    @property
    def connected(self):
        return self._connected

    def write(self, cmd):
        pass

    def query(self, cmd):
        return "0"

    def check_errors(self):
        return []

    def reset(self):
        self._output = False
        self._level = 0.0

    def apply_config(self, cfg):
        self._config = cfg

    # ---------------- cikis / olcum ----------------
    def output_on(self):
        self._output = True

    def output_off(self):
        self._output = False
        self._level = 0.0

    def set_level(self, level):
        self._level = float(level)

    def set_uv(self, on):
        """Simulasyonda UV kaynagini ac/kapa."""
        if bool(on) != self.uv_on:
            self._state_at_change = self._state()
            self.uv_on = bool(on)
            self._uv_changed_at = _now()

    def settle_uv(self):
        """Gecisi tamamlanmis say (testler icin)."""
        self._uv_changed_at -= 100.0

    def _state(self):
        dt = _now() - self._uv_changed_at
        target = 1.0 if self.uv_on else 0.0
        tau = self.rise_tau if self.uv_on else self.fall_tau
        return target + (self._state_at_change - target) * math.exp(-dt / tau)

    def _photocurrent(self):
        return self.responsivity * self.optical_power * self._state()

    def _diode_current(self, v):
        vt = self.ideality * K_B * self.temperature / Q_E
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

    def measure_iv(self):
        if not self._output:
            return random.gauss(0.0, self.noise_floor), 0.0
        i_ph = self._photocurrent()
        if self._config.source_func == SOURCE_VOLTAGE:
            v = self._level
            i = self._diode_current(v) - i_ph
            limit = self._config.compliance
            if abs(i) > limit:
                i = math.copysign(limit, i)
                v = self._level * 0.98
        else:
            i = self._level
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

    def set_level_and_measure(self, level, settle_s=0.0):
        self.set_level(level)
        if settle_s > 0:
            time.sleep(settle_s)
        return self.measure_iv()

    def beep(self, duration=0.2, freq=1200):
        pass

    def write_digio_bit(self, bit, value):
        self.set_uv(bool(value))

    def read_digio_bit(self, bit):
        return 1
