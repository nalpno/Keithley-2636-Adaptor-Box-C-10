"""Olcum motorlari: I-V taramasi ve zaman tepkisi (fotoyanit) kaydi.

Bu modul Qt'den bagimsizdir; GUI worker'lari (``uvpd.gui.workers``) buradaki
fonksiyonlari geri cagirimlarla (callback) kullanir. Boylece motorlar
konsoldan veya testten de calistirilabilir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

from .dataset import DARK, LIGHT, Dataset
from .instrument import SOURCE_VOLTAGE, SmuConfig

PointCallback = Callable[[int, float, float, float], None]   # (idx, t, v, i)
StopCheck = Callable[[], bool]
LogCallback = Callable[[str], None]


# --------------------------------------------------------------------------
@dataclass
class SweepConfig:
    """I-V taramasi parametreleri."""

    start: float = -1.0
    stop: float = 1.0
    points: int = 101
    dual: bool = False              # ileri + geri tarama (histerezis)
    repeat: int = 1                 # tekrar sayisi (ortalama icin degil, ard arda tarama)
    settle_time: float = 0.05       # her adimda olcumden once bekleme (s)
    hold_time: float = 0.2          # cikis acildiktan sonra ilk bekleme (s)
    return_to_zero: bool = True     # bitince kaynagi sifirla

    def levels(self) -> np.ndarray:
        pts = max(2, int(self.points))
        fwd = np.linspace(self.start, self.stop, pts)
        if self.dual:
            return np.concatenate([fwd, fwd[-2::-1]])
        return fwd

    @property
    def step(self) -> float:
        pts = max(2, int(self.points))
        return (self.stop - self.start) / (pts - 1)


@dataclass
class TransientConfig:
    """Sabit bias altinda zamana bagli akim/gerilim kaydi."""

    bias: float = 1.0               # kaynak seviyesi (V veya A)
    duration: float = 60.0          # toplam sure (s)
    interval: float = 0.1           # ornekleme araligi (s)
    hold_time: float = 0.5          # cikis acildiktan sonra bekleme (s)
    return_to_zero: bool = True

    # --- otomatik UV ac/kapa cevrimi (shutter digital I/O'ya bagliysa) ---
    cycle_enabled: bool = False
    cycle_delay: float = 5.0        # ilk acilmadan once karanlik bekleme (s)
    cycle_on: float = 10.0          # UV acik suresi (s)
    cycle_off: float = 10.0         # UV kapali suresi (s)

    @property
    def n_points(self) -> int:
        return max(1, int(round(self.duration / max(self.interval, 1e-3))))


@dataclass
class SampleInfo:
    """Numune ve isik kaynagi bilgileri (meta veri olarak kaydedilir)."""

    name: str = "numune"
    light_state: str = DARK
    wavelength_nm: Optional[float] = 365.0
    optical_power_w: Optional[float] = None
    irradiance_w_cm2: Optional[float] = None
    area_cm2: Optional[float] = None
    notes: str = ""

    def apply_to(self, ds: Dataset) -> Dataset:
        ds.name = self.name
        ds.light_state = self.light_state
        ds.wavelength_nm = self.wavelength_nm if self.light_state == LIGHT else None
        ds.optical_power_w = self.optical_power_w if self.light_state == LIGHT else None
        ds.irradiance_w_cm2 = self.irradiance_w_cm2 if self.light_state == LIGHT else None
        ds.area_cm2 = self.area_cm2
        ds.notes = self.notes
        return ds


# --------------------------------------------------------------------------
def _settings_dict(smu: SmuConfig, extra: dict) -> dict:
    d = {
        "channel": smu.channel,
        "source_func": smu.source_func,
        "compliance": smu.compliance,
        "nplc": smu.nplc,
        "filter_count": smu.filter_count,
        "four_wire": smu.four_wire,
        "low_range_i": smu.low_range_i,
        "auto_zero": smu.auto_zero,
        "high_capacitance": smu.high_capacitance,
    }
    d.update(extra)
    return d


def run_sweep(inst, smu: SmuConfig, cfg: SweepConfig, sample: SampleInfo,
              on_point: Optional[PointCallback] = None,
              should_stop: Optional[StopCheck] = None,
              log: Optional[LogCallback] = None) -> Dataset:
    """I-V taramasini yurutur ve Dataset dondurur.

    Tarama nokta nokta yapilir; her nokta aninda GUI'ye bildirilir, boylece
    egri canli cizilir ve istenildigi an durdurulabilir.
    """
    ds = sample.apply_to(Dataset(kind="iv"))
    ds.settings = _settings_dict(smu, {
        "sweep": {"start": cfg.start, "stop": cfg.stop, "points": cfg.points,
                  "dual": cfg.dual, "repeat": cfg.repeat,
                  "settle_time": cfg.settle_time},
    })

    levels = cfg.levels()
    inst.apply_config(smu)
    inst.output_on()
    if log:
        unit = "V" if smu.source_func == SOURCE_VOLTAGE else "A"
        log(f"Tarama basladi: {cfg.start:g} -> {cfg.stop:g} {unit}, "
            f"{len(levels)} nokta x {cfg.repeat} tekrar")
    try:
        if cfg.hold_time > 0:
            time.sleep(cfg.hold_time)
        t0 = time.time()
        idx = 0
        for rep in range(max(1, int(cfg.repeat))):
            for level in levels:
                if should_stop and should_stop():
                    if log:
                        log("Kullanici tarafindan durduruldu.")
                    return ds
                i_meas, v_meas = inst.set_level_and_measure(float(level), cfg.settle_time)
                t = time.time() - t0
                ds.append(t, v_meas, i_meas)
                if on_point:
                    on_point(idx, t, v_meas, i_meas)
                idx += 1
    finally:
        if cfg.return_to_zero:
            try:
                inst.output_off()
            except Exception:
                pass
    if log:
        log(f"Tarama bitti: {len(ds)} nokta.")
    if smu.beep_on_finish:
        try:
            inst.beep()
        except Exception:
            pass
    return ds


def run_transient(inst, smu: SmuConfig, cfg: TransientConfig, sample: SampleInfo,
                  on_point: Optional[PointCallback] = None,
                  should_stop: Optional[StopCheck] = None,
                  log: Optional[LogCallback] = None,
                  light_events: Optional[List] = None,
                  light_control: Optional[Callable[[bool], None]] = None) -> Dataset:
    """Sabit bias altinda zaman tepkisi (UV ac/kapa) kaydi.

    ``light_events`` disaridan verilirse (GUI'de "UV ACIK/KAPALI" dugmesi ile
    doldurulan liste) olcum sonunda meta veriye yazilir ve grafikte isik
    pencereleri gosterilir.

    ``cfg.cycle_enabled`` acikken UV kaynagi/shutter ``light_control(bool)``
    ile otomatik olarak ac/kapa edilir ve gecis anlari kaydedilir.
    """
    ds = sample.apply_to(Dataset(kind="transient"))
    ds.settings = _settings_dict(smu, {
        "transient": {"bias": cfg.bias, "duration": cfg.duration,
                      "interval": cfg.interval,
                      "cycle_enabled": cfg.cycle_enabled,
                      "cycle_delay": cfg.cycle_delay,
                      "cycle_on": cfg.cycle_on, "cycle_off": cfg.cycle_off},
    })
    auto_events: List = []

    inst.apply_config(smu)
    inst.set_level(cfg.bias)
    inst.output_on()
    if log:
        unit = "V" if smu.source_func == SOURCE_VOLTAGE else "A"
        log(f"Zaman tepkisi basladi: bias {cfg.bias:g} {unit}, "
            f"{cfg.duration:g} s @ {cfg.interval:g} s")
    try:
        if cfg.hold_time > 0:
            time.sleep(cfg.hold_time)
        t0 = time.time()
        idx = 0
        next_t = t0
        light_on = False
        next_toggle = t0 + cfg.cycle_delay if cfg.cycle_enabled else None
        while True:
            if should_stop and should_stop():
                if log:
                    log("Kullanici tarafindan durduruldu.")
                break
            now = time.time()
            if now - t0 >= cfg.duration:
                break

            # otomatik UV cevrimi
            if next_toggle is not None and now >= next_toggle:
                light_on = not light_on
                if light_control:
                    try:
                        light_control(light_on)
                    except Exception as exc:  # pragma: no cover
                        if log:
                            log(f"Isik kontrolu hatasi: {exc}")
                auto_events.append((now - t0, 1 if light_on else 0))
                next_toggle = now + (cfg.cycle_on if light_on else cfg.cycle_off)
                if log:
                    log(f"UV {'ACIK' if light_on else 'KAPALI'} (t = {now - t0:.2f} s)")

            i_meas, v_meas = inst.measure_iv()
            t = time.time() - t0
            ds.append(t, v_meas, i_meas)
            if on_point:
                on_point(idx, t, v_meas, i_meas)
            idx += 1
            next_t += cfg.interval
            sleep_for = next_t - time.time()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:  # olcum, istenen araliktan yavas -> takvimi guncelle
                next_t = time.time()
    finally:
        if cfg.cycle_enabled and light_control:
            try:
                light_control(False)
            except Exception:
                pass
        if cfg.return_to_zero:
            try:
                inst.output_off()
            except Exception:
                pass

    events = list(auto_events) + list(light_events or [])
    if events:
        events.sort(key=lambda e: e[0])
        ds.settings["light_events"] = [[float(t), int(state)] for t, state in events]
    if log:
        log(f"Zaman tepkisi bitti: {len(ds)} nokta.")
    if smu.beep_on_finish:
        try:
            inst.beep()
        except Exception:
            pass
    return ds


def spot_measure(inst, smu: SmuConfig, level: float, settle: float = 0.1):
    """Tek noktali olcum (hizli kontrol icin)."""
    inst.apply_config(smu)
    inst.output_on()
    try:
        time.sleep(max(0.0, settle))
        return inst.set_level_and_measure(level, settle)
    finally:
        inst.output_off()
