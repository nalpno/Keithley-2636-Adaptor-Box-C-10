# -*- coding: utf-8 -*-
"""Olcum motorlari: I-V taramasi ve zaman tepkisi.

Arayuzden bagimsizdir; ilerleme geri cagirimlarla (callback) bildirilir.
Zaman damgalari icin time.perf_counter kullanilir (XP'de time.time
cozunurlugu ~16 ms'dir, perf_counter mikrosaniye mertebesindedir).
"""

import time

from .analysis import linspace
from .dataset import DARK, LIGHT, Dataset
from .instrument import SOURCE_VOLTAGE

_now = time.perf_counter


class SweepConfig(object):
    def __init__(self, start=-1.0, stop=1.0, points=101, dual=False, repeat=1,
                 settle_time=0.05, hold_time=0.2, return_to_zero=True):
        self.start = float(start)
        self.stop = float(stop)
        self.points = int(points)
        self.dual = bool(dual)
        self.repeat = int(repeat)
        self.settle_time = float(settle_time)
        self.hold_time = float(hold_time)
        self.return_to_zero = bool(return_to_zero)

    def levels(self):
        fwd = linspace(self.start, self.stop, max(2, self.points))
        if self.dual:
            return fwd + fwd[-2::-1]
        return fwd

    @property
    def step(self):
        return (self.stop - self.start) / float(max(2, self.points) - 1)


class TransientConfig(object):
    def __init__(self, bias=1.0, duration=60.0, interval=0.1, hold_time=0.5,
                 return_to_zero=True, cycle_enabled=False, cycle_delay=5.0,
                 cycle_on=10.0, cycle_off=10.0):
        self.bias = float(bias)
        self.duration = float(duration)
        self.interval = float(interval)
        self.hold_time = float(hold_time)
        self.return_to_zero = bool(return_to_zero)
        self.cycle_enabled = bool(cycle_enabled)
        self.cycle_delay = float(cycle_delay)
        self.cycle_on = float(cycle_on)
        self.cycle_off = float(cycle_off)


class SampleInfo(object):
    def __init__(self, name="numune", light_state=DARK, wavelength_nm=365.0,
                 optical_power_w=None, irradiance_w_cm2=None, area_cm2=None, notes=""):
        self.name = name
        self.light_state = light_state
        self.wavelength_nm = wavelength_nm
        self.optical_power_w = optical_power_w
        self.irradiance_w_cm2 = irradiance_w_cm2
        self.area_cm2 = area_cm2
        self.notes = notes

    def apply_to(self, ds):
        light = self.light_state == LIGHT
        ds.name = self.name
        ds.light_state = self.light_state
        ds.wavelength_nm = self.wavelength_nm if light else None
        ds.optical_power_w = self.optical_power_w if light else None
        ds.irradiance_w_cm2 = self.irradiance_w_cm2 if light else None
        ds.area_cm2 = self.area_cm2
        ds.notes = self.notes
        return ds


def _settings_dict(smu, extra):
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
        "program": "uvpd_xp",
    }
    d.update(extra)
    return d


def _unit(smu):
    return "V" if smu.source_func == SOURCE_VOLTAGE else "A"


def run_sweep(inst, smu, cfg, sample, on_point=None, should_stop=None, log=None):
    """I-V taramasi. Her nokta on_point(idx, t, v, i) ile bildirilir."""
    ds = sample.apply_to(Dataset(kind="iv"))
    ds.settings = _settings_dict(smu, {"sweep": {
        "start": cfg.start, "stop": cfg.stop, "points": cfg.points,
        "dual": cfg.dual, "repeat": cfg.repeat, "settle_time": cfg.settle_time}})
    levels = cfg.levels()
    inst.apply_config(smu)
    inst.output_on()
    if log:
        log("Tarama basladi: {0:g} -> {1:g} {2}, {3} nokta x {4} tekrar".format(
            cfg.start, cfg.stop, _unit(smu), len(levels), cfg.repeat))
    try:
        if cfg.hold_time > 0:
            time.sleep(cfg.hold_time)
        t0 = _now()
        idx = 0
        for _rep in range(max(1, cfg.repeat)):
            for level in levels:
                if should_stop and should_stop():
                    if log:
                        log("Kullanici tarafindan durduruldu.")
                    return ds
                i_meas, v_meas = inst.set_level_and_measure(level, cfg.settle_time)
                t = _now() - t0
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
        log("Tarama bitti: {0} nokta.".format(len(ds)))
    if smu.beep_on_finish:
        try:
            inst.beep()
        except Exception:
            pass
    return ds


def run_transient(inst, smu, cfg, sample, on_point=None, should_stop=None, log=None,
                  light_events=None, light_control=None):
    """Sabit bias altinda akim-zaman kaydi (UV ac/kapa)."""
    ds = sample.apply_to(Dataset(kind="transient"))
    ds.settings = _settings_dict(smu, {"transient": {
        "bias": cfg.bias, "duration": cfg.duration, "interval": cfg.interval,
        "cycle_enabled": cfg.cycle_enabled, "cycle_delay": cfg.cycle_delay,
        "cycle_on": cfg.cycle_on, "cycle_off": cfg.cycle_off}})
    auto_events = []

    inst.apply_config(smu)
    inst.set_level(cfg.bias)
    inst.output_on()
    if log:
        log("Zaman tepkisi basladi: bias {0:g} {1}, {2:g} s @ {3:g} s".format(
            cfg.bias, _unit(smu), cfg.duration, cfg.interval))
    try:
        if cfg.hold_time > 0:
            time.sleep(cfg.hold_time)
        t0 = _now()
        idx = 0
        next_t = t0
        light_on = False
        next_toggle = (t0 + cfg.cycle_delay) if cfg.cycle_enabled else None
        while True:
            if should_stop and should_stop():
                if log:
                    log("Kullanici tarafindan durduruldu.")
                break
            now = _now()
            if now - t0 >= cfg.duration:
                break
            if next_toggle is not None and now >= next_toggle:
                light_on = not light_on
                if light_control:
                    try:
                        light_control(light_on)
                    except Exception as exc:
                        if log:
                            log("Isik kontrolu hatasi: {0}".format(exc))
                auto_events.append((now - t0, 1 if light_on else 0))
                next_toggle = now + (cfg.cycle_on if light_on else cfg.cycle_off)
                if log:
                    log("UV {0} (t = {1:.2f} s)".format("ACIK" if light_on else "KAPALI", now - t0))
            i_meas, v_meas = inst.measure_iv()
            t = _now() - t0
            ds.append(t, v_meas, i_meas)
            if on_point:
                on_point(idx, t, v_meas, i_meas)
            idx += 1
            next_t += cfg.interval
            wait = next_t - _now()
            if wait > 0:
                time.sleep(wait)
            else:
                next_t = _now()
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
        ds.settings["light_events"] = [[float(t), int(s)] for t, s in events]
    if log:
        log("Zaman tepkisi bitti: {0} nokta.".format(len(ds)))
    if smu.beep_on_finish:
        try:
            inst.beep()
        except Exception:
            pass
    return ds
