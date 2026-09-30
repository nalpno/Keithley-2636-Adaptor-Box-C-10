"""Osiloskop darbe analizi (uvpd.scope) testleri."""

import math
import os

import numpy as np
import pytest

from uvpd import scope
from uvpd.analysis import photon_energy_ev

DATA = os.path.join(os.path.dirname(__file__), "data", "rigol_ds3100_ACOPE_01.csv")


def synth(period=200e-6, duty=0.5, dt=0.2e-6, cycles=8, tau_r=2e-6, tau_f=5e-6,
          v_on=0.5, v_off=-0.3, delay=1e-6, noise=0.0, seed=1, ref_high=33.0):
    """Kare dalga referansi ve birinci dereceden (ustel) tepki veren sinyal."""
    rng = np.random.default_rng(seed)
    t = np.arange(-period * 0.3, period * (cycles - 0.3), dt)
    phase = np.mod(t, period)
    ref_on = phase < duty * period
    ref = np.where(ref_on, ref_high, 0.0)
    # isik, referanstan `delay` sonra degisir
    light = np.mod(t - delay, period) < duty * period
    y = np.empty_like(t)
    level = v_off
    for k in range(t.size):
        target, tau = (v_on, tau_r) if light[k] else (v_off, tau_f)
        level = target + (level - target) * math.exp(-dt / tau)
        y[k] = level
    y += noise * rng.standard_normal(t.size)
    return scope.ScopeTrace(t=t, channels={"CH1": ref, "CH2": y},
                            units={"CH1": "V", "CH2": "V"}, path="sentetik")


# ---------------------------------------------------------------- CSV okuma
def test_parse_rigol_ds3100_file():
    tr = scope.load_scope_csv(DATA)
    assert tr.names == ["CH1", "CH2"]
    assert tr.t.size == 1200
    assert tr.dt == pytest.approx(1e-6)
    assert tr.t[0] == pytest.approx(-8e-4)


def test_parse_ds1000z_start_increment():
    text = ("X,CH1,CH2,Start,Increment,\n"
            "Sequence,Volt,Volt,-1.000000e-03,2.000000e-06\n"
            + "".join(f"{k},{k % 2 * 5.0:.2f},{0.1 * k:.3f},\n" for k in range(50)))
    tr = scope.parse_scope_text(text)
    assert tr.names == ["CH1", "CH2"]
    assert tr.t[0] == pytest.approx(-1e-3)
    assert tr.dt == pytest.approx(2e-6)
    assert tr.channels["CH2"][10] == pytest.approx(1.0)


def test_parse_units_in_names_semicolon_and_millivolts():
    text = "Time(us);CH1(V);CH2(mV)\n" + "".join(
        f"{k};{k % 2};{100 * k}\n" for k in range(30))
    tr = scope.parse_scope_text(text)
    assert tr.dt == pytest.approx(1e-6)
    assert tr.channels["CH2"][3] == pytest.approx(0.3)


def test_parse_rejects_non_numeric():
    with pytest.raises(ValueError):
        scope.parse_scope_text("a,b\nc,d\n")


# ---------------------------------------------------------------- yardimcilar
def test_interleave_offset_detected_and_removed():
    y = np.repeat([0.0, 1.0, 0.0, 1.0], 100) + 0.1
    y[1::2] += 0.08
    off = scope.interleave_offset(y)
    assert off == pytest.approx(0.08)
    fixed = scope.remove_interleave(y, off)
    assert scope.interleave_offset(fixed) == pytest.approx(0.0, abs=1e-12)


def test_band_power_parseval():
    rng = np.random.default_rng(3)
    r = rng.standard_normal(512)
    r -= r.mean()
    total = scope.band_power(r, 1e-6, 0.5e6)
    assert total == pytest.approx(np.mean(r * r), rel=1e-9)
    assert scope.band_power(r, 1e-6, 1e5) < total


def test_exponential_fits():
    t = np.linspace(0, 60e-6, 400)
    fit = scope.fit_exponential(t, 1 - np.exp(-t / 4e-6), 0.15e-6)
    assert fit.tau == pytest.approx(4e-6, rel=0.05)
    v = 0.7 * np.exp(-t / 2e-6) + 0.3 * np.exp(-t / 30e-6)
    fit = scope.fit_exponential(t, v, 0.15e-6)
    assert fit.double_significant
    assert fit.tau_fast == pytest.approx(2e-6, rel=0.15)
    assert fit.tau_slow == pytest.approx(30e-6, rel=0.15)
    assert fit.frac_fast == pytest.approx(0.7, abs=0.05)


def test_detect_edges_ignores_single_sample_glitches():
    t = np.arange(1000) * 1e-6
    y = np.where(np.mod(t, 200e-6) < 100e-6, 33.0, 0.0)
    y[150] = 0.0                    # kisa dusus (glitch)
    y[151] = 2.4
    rises, falls = scope.detect_edges(t, y)
    assert len(rises) == 4 and len(falls) == 5
    assert np.allclose(np.diff(rises), 200e-6, atol=2e-6)


# ---------------------------------------------------------------- analiz
def test_synthetic_pulse_metrics():
    tau_r, tau_f = 2e-6, 5e-6
    tr = synth(tau_r=tau_r, tau_f=tau_f)
    s = scope.PulseSettings(gain_v_per_a=1e5, wavelength_nm=365.0,
                            optical_power_w=1e-3, area_cm2=0.04,
                            system_rise_s=0.0, noise_bandwidth_hz=1e5)
    r = scope.analyze_pulses(tr, s)
    assert r.period == pytest.approx(200e-6, rel=1e-3)
    assert r.frequency == pytest.approx(5e3, rel=1e-3)
    assert r.duty == pytest.approx(0.5, abs=0.01)
    assert r.n_cycles >= 7
    # 10-90 = ln(9)·τ ≈ 2.197 τ
    assert r.rise_time == pytest.approx(math.log(9) * tau_r, rel=0.05)
    assert r.fall_time == pytest.approx(math.log(9) * tau_f, rel=0.05)
    mr, sr, nr = r.edge_stats("on")
    assert mr == pytest.approx(math.log(9) * tau_r, rel=0.05) and nr >= 7
    assert r.avg_rise.fit.tau == pytest.approx(tau_r, rel=0.1)
    assert r.avg_fall.fit.tau == pytest.approx(tau_f, rel=0.1)
    # gecikme: 1 µs + ln(2)·τ
    md, _, _ = r.edge_stats("on", "delay")
    assert md == pytest.approx(1e-6 + math.log(2) * tau_r, rel=0.1)

    assert r.v_on == pytest.approx(0.5, abs=1e-3)
    assert r.v_off == pytest.approx(-0.3, abs=1e-3)
    assert r.photocurrent == pytest.approx(0.8 / 1e5, rel=1e-3)
    assert r.responsivity == pytest.approx(8e-6 / 1e-3, rel=1e-3)
    assert r.eqe_percent == pytest.approx(r.responsivity * photon_energy_ev(365) * 100)
    assert r.interleave_v == 0.0
    rows = dict(r.report_rows())
    assert "Duyarlilik R = I_ph / P" in rows
    assert rows["Tam cevrim sayisi"] == str(r.n_cycles)


def test_load_50ohm_halves_gain():
    tr = synth()
    a = scope.analyze_pulses(tr, scope.PulseSettings(load_50ohm=False))
    b = scope.analyze_pulses(tr, scope.PulseSettings(load_50ohm=True))
    assert b.photocurrent == pytest.approx(2 * a.photocurrent)


def test_noise_nep_and_dstar():
    tr = synth(noise=0.01, seed=5)
    s = scope.PulseSettings(optical_power_w=1e-3, area_cm2=0.04,
                            noise_bandwidth_hz=2.5e6, dark_current_a=1e-9)
    r = scope.analyze_pulses(tr, s)
    # B = Nyquist → tum beyaz gurultu
    assert r.noise_off_band_v == pytest.approx(0.01, rel=0.15)
    assert r.noise_current == pytest.approx(0.01 / 1e5, rel=0.15)
    assert r.snr == pytest.approx(0.8 / 0.01, rel=0.15)
    assert r.nep_measured == pytest.approx(r.noise_current / r.responsivity)
    assert r.dstar_measured == pytest.approx(
        math.sqrt(0.04 * 2.5e6) / r.nep_measured)
    assert r.dstar_shot == pytest.approx(
        r.responsivity * math.sqrt(0.04) / math.sqrt(2 * 1.602176634e-19 * 1e-9))
    # daha dar bant → daha az gurultu
    r2 = scope.analyze_pulses(tr, scope.PulseSettings(noise_bandwidth_hz=1e5))
    assert r2.noise_off_band_v < r.noise_off_band_v


def test_inverted_reference_and_no_reference():
    tr = synth()
    inv = scope.ScopeTrace(t=tr.t, channels={"CH1": 33.0 - tr.channels["CH1"],
                                             "CH2": tr.channels["CH2"]})
    r = scope.analyze_pulses(inv, scope.PulseSettings(light_on_high=False))
    assert r.delta_v == pytest.approx(0.8, abs=0.01)
    wrong = scope.analyze_pulses(inv, scope.PulseSettings(light_on_high=True))
    assert wrong.delta_v < 0
    assert any("ters kutup" in w for w in wrong.warnings)

    r = scope.analyze_pulses(tr, scope.PulseSettings(reference=None))
    assert r.period == pytest.approx(200e-6, rel=1e-3)
    assert r.rise_time == pytest.approx(math.log(9) * 2e-6, rel=0.1)


def test_no_edges_gives_warning():
    t = np.arange(500) * 1e-6
    tr = scope.ScopeTrace(t=t, channels={"CH1": np.ones_like(t), "CH2": np.zeros_like(t)})
    r = scope.analyze_pulses(tr, scope.PulseSettings())
    assert r.warnings and not r.edges
    assert r.report_rows()          # yine de rapor uretebilmeli


def test_system_rise_correction_and_limit_warning():
    tr = synth(tau_r=1e-6)
    r = scope.analyze_pulses(tr, scope.PulseSettings(system_rise_s=2e-6))
    tr_raw = r.rise_time
    assert r.corrected(tr_raw) == pytest.approx(math.sqrt(tr_raw ** 2 - 4e-12))
    r = scope.analyze_pulses(tr, scope.PulseSettings(system_rise_s=3.5e-6))
    assert math.isnan(r.corrected(r.rise_time))
    assert any("sinir" in w for w in r.warnings)


def test_real_ds3100_recording():
    tr = scope.load_scope_csv(DATA)
    r = scope.analyze_pulses(tr, scope.PulseSettings(
        system_rise_s=scope.AMP120_RISE_S, optical_power_w=1e-3, wavelength_nm=365))
    assert r.interleave_v == pytest.approx(0.08, abs=1e-6)
    assert r.period == pytest.approx(208e-6, rel=0.01)
    assert r.duty == pytest.approx(0.5, abs=0.02)
    assert r.n_cycles == 5
    assert r.delta_v == pytest.approx(0.83, abs=0.03)
    assert r.photocurrent == pytest.approx(8.3e-6, rel=0.05)
    assert 2e-6 < r.rise_time < 6e-6
    mr, sr, n = r.edge_stats("on")
    assert n == 5 and sr < 1e-6            # gurultu sicramasi kenar sanilmamali
    # kapanis: ustel uydurma yapilabilmeli (yavas kuyruk gurultu icinde
    # istatistiksel olarak anlamli olmayabilir)
    assert 1e-6 < r.avg_fall.fit.tau < 30e-6
    assert np.isfinite(r.responsivity) and np.isfinite(r.eqe_percent)


def test_exports(tmp_path):
    r = scope.analyze_pulses(synth(), scope.PulseSettings(optical_power_w=1e-3))
    rep = scope.write_report(r, str(tmp_path / "r.txt"), "numune")
    text = open(rep, encoding="utf-8").read()
    assert "Yukselme suresi" in text and "A/W" in text
    ed = scope.write_edges_csv(r, str(tmp_path / "e.csv"))
    lines = open(ed, encoding="utf-8").read().splitlines()
    assert lines[0].startswith("kenar,tur,t_ref_s")
    assert len(lines) == len(r.edges) + 1
    av = scope.write_average_csv(r, str(tmp_path / "a.csv"))
    assert "tau_s,V_avg_V,I_avg_A" in open(av, encoding="utf-8").read()


def test_fmt_si():
    assert scope.fmt_si(3.52e-6, "s") == "3.52 µs"
    assert scope.fmt_si(0.8303, "V") == "830.3 mV"
    assert scope.fmt_si(float("nan"), "V") == "-"
    assert scope.fmt_si(4807.0, "Hz") == "4.807 kHz"
