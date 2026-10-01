# -*- coding: utf-8 -*-
"""Osiloskop darbe analizi (uvpd_xp.scope) testleri - harici paket gerekmez."""

import math
import os
import random
import shutil
import tempfile
import unittest

from uvpd_xp import scope
from uvpd_xp.analysis import photon_energy_ev

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                    "rigol_ds3100_ACOPE_01.csv")


def synth(period=200e-6, duty=0.5, dt=0.2e-6, cycles=8, tau_r=2e-6, tau_f=5e-6,
          v_on=0.5, v_off=-0.3, delay=1e-6, noise=0.0, seed=1, ref_high=33.0):
    """Kare dalga referansi ve birinci dereceden (ustel) tepki veren sinyal."""
    rng = random.Random(seed)
    n = int(round(period * cycles / dt))
    t = [-period * 0.3 + k * dt for k in range(n)]
    ref, y = [], []
    level = v_off
    for tk in t:
        ref.append(ref_high if (tk % period) < duty * period else 0.0)
        light = ((tk - delay) % period) < duty * period
        target, tau = (v_on, tau_r) if light else (v_off, tau_f)
        level = target + (level - target) * math.exp(-dt / tau)
        y.append(level + (rng.gauss(0.0, noise) if noise else 0.0))
    return scope.ScopeTrace(t, {"CH1": ref, "CH2": y}, {"CH1": "V", "CH2": "V"}, "sentetik")


class ParseTests(unittest.TestCase):
    def test_rigol_ds3100_file(self):
        tr = scope.load_scope_csv(DATA)
        self.assertEqual(tr.names, ["CH1", "CH2"])
        self.assertEqual(len(tr.t), 1200)
        self.assertAlmostEqual(tr.dt, 1e-6, places=12)
        self.assertAlmostEqual(tr.t[0], -8e-4, places=12)

    def test_ds1000z_start_increment(self):
        text = ("X,CH1,CH2,Start,Increment,\n"
                "Sequence,Volt,Volt,-1.000000e-03,2.000000e-06\n"
                + "".join("{0},{1:.2f},{2:.3f},\n".format(k, k % 2 * 5.0, 0.1 * k)
                          for k in range(50)))
        tr = scope.parse_scope_text(text)
        self.assertEqual(tr.names, ["CH1", "CH2"])
        self.assertAlmostEqual(tr.t[0], -1e-3)
        self.assertAlmostEqual(tr.dt, 2e-6)
        self.assertAlmostEqual(tr.channels["CH2"][10], 1.0)

    def test_units_in_names_semicolon_millivolts(self):
        text = "Time(us);CH1(V);CH2(mV)\n" + "".join(
            "{0};{1};{2}\n".format(k, k % 2, 100 * k) for k in range(30))
        tr = scope.parse_scope_text(text)
        self.assertAlmostEqual(tr.dt, 1e-6)
        self.assertAlmostEqual(tr.channels["CH2"][3], 0.3)

    def test_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            scope.parse_scope_text("a,b\nc,d\n")


class HelperTests(unittest.TestCase):
    def test_interleave_offset(self):
        y = [0.1] * 100 + [1.1] * 100 + [0.1] * 100 + [1.1] * 100
        y = [v + (0.08 if k % 2 else 0.0) for k, v in enumerate(y)]
        off = scope.interleave_offset(y)
        self.assertAlmostEqual(off, 0.08)
        fixed = scope.remove_interleave(y, off)
        self.assertAlmostEqual(scope.interleave_offset(fixed), 0.0, places=12)

    def test_band_power_parseval(self):
        rng = random.Random(3)
        r = [rng.gauss(0, 1) for _ in range(512)]
        m = sum(r) / len(r)
        r = [v - m for v in r]
        total = scope.band_power(r, 1e-6, 0.5e6)
        self.assertAlmostEqual(total, sum(v * v for v in r) / len(r), places=9)
        self.assertLess(scope.band_power(r, 1e-6, 1e5), total)

    def test_exponential_fits(self):
        t = [60e-6 * k / 399.0 for k in range(400)]
        fit = scope.fit_exponential(t, [1 - math.exp(-x / 4e-6) for x in t], 0.15e-6)
        self.assertAlmostEqual(fit.tau / 4e-6, 1.0, delta=0.05)
        v = [0.7 * math.exp(-x / 2e-6) + 0.3 * math.exp(-x / 30e-6) for x in t]
        fit = scope.fit_exponential(t, v, 0.15e-6)
        self.assertTrue(fit.double_significant)
        self.assertAlmostEqual(fit.tau_fast / 2e-6, 1.0, delta=0.15)
        self.assertAlmostEqual(fit.tau_slow / 30e-6, 1.0, delta=0.15)
        self.assertAlmostEqual(fit.frac_fast, 0.7, delta=0.05)

    def test_detect_edges_ignores_glitches(self):
        t = [k * 1e-6 for k in range(1000)]
        y = [33.0 if (x % 200e-6) < 100e-6 else 0.0 for x in t]
        y[150] = 0.0
        y[151] = 2.4
        rises, falls = scope.detect_edges(t, y)
        self.assertEqual((len(rises), len(falls)), (4, 5))
        for a, b in zip(rises, rises[1:]):
            self.assertAlmostEqual(b - a, 200e-6, delta=2e-6)

    def test_fmt_si(self):
        self.assertEqual(scope.fmt_si(3.52e-6, "s"), "3.52 us")
        self.assertEqual(scope.fmt_si(0.8303, "V"), "830.3 mV")
        self.assertEqual(scope.fmt_si(float("nan"), "V"), "-")
        self.assertEqual(scope.fmt_si(4807.0, "Hz"), "4.807 kHz")


class AnalysisTests(unittest.TestCase):
    def rel(self, a, b, tol):
        self.assertTrue(abs(a - b) <= tol * abs(b), "{0!r} != {1!r} (+/-{2:.0%})".format(a, b, tol))

    def test_synthetic_pulse_metrics(self):
        tau_r, tau_f = 2e-6, 5e-6
        tr = synth(tau_r=tau_r, tau_f=tau_f)
        s = scope.PulseSettings(gain_v_per_a=1e5, wavelength_nm=365.0, optical_power_w=1e-3,
                                area_cm2=0.04, system_rise_s=0.0, noise_bandwidth_hz=1e5)
        r = scope.analyze_pulses(tr, s)
        self.rel(r.period, 200e-6, 1e-3)
        self.rel(r.frequency, 5e3, 1e-3)
        self.assertAlmostEqual(r.duty, 0.5, delta=0.01)
        self.assertGreaterEqual(r.n_cycles, 7)
        self.rel(r.rise_time, math.log(9) * tau_r, 0.05)
        self.rel(r.fall_time, math.log(9) * tau_f, 0.05)
        m, sd, n = r.edge_stats("on")
        self.rel(m, math.log(9) * tau_r, 0.05)
        self.assertGreaterEqual(n, 7)
        self.rel(r.avg_rise.fit.tau, tau_r, 0.1)
        self.rel(r.avg_fall.fit.tau, tau_f, 0.1)
        self.rel(r.edge_stats("on", "delay")[0], 1e-6 + math.log(2) * tau_r, 0.1)
        self.assertAlmostEqual(r.v_on, 0.5, delta=1e-3)
        self.assertAlmostEqual(r.v_off, -0.3, delta=1e-3)
        self.rel(r.photocurrent, 0.8 / 1e5, 1e-3)
        self.rel(r.responsivity, 8e-6 / 1e-3, 1e-3)
        self.rel(r.eqe_percent, r.responsivity * photon_energy_ev(365) * 100, 1e-12)
        self.assertEqual(r.interleave_v, 0.0)
        rows = dict(r.report_rows())
        self.assertIn("Duyarlilik R = I_ph / P", rows)
        self.assertEqual(rows["Tam cevrim sayisi"], str(r.n_cycles))

    def test_load_50ohm_halves_gain(self):
        tr = synth()
        a = scope.analyze_pulses(tr, scope.PulseSettings(load_50ohm=False))
        b = scope.analyze_pulses(tr, scope.PulseSettings(load_50ohm=True))
        self.rel(b.photocurrent, 2 * a.photocurrent, 1e-9)

    def test_noise_nep_dstar(self):
        tr = synth(noise=0.01, seed=5)
        s = scope.PulseSettings(optical_power_w=1e-3, area_cm2=0.04,
                                noise_bandwidth_hz=2.5e6, dark_current_a=1e-9)
        r = scope.analyze_pulses(tr, s)
        self.rel(r.noise_off_band_v, 0.01, 0.15)
        self.rel(r.noise_current, 0.01 / 1e5, 0.15)
        self.rel(r.snr, 0.8 / 0.01, 0.15)
        self.rel(r.nep_measured, r.noise_current / r.responsivity, 1e-12)
        self.rel(r.dstar_measured, math.sqrt(0.04 * 2.5e6) / r.nep_measured, 1e-12)
        self.rel(r.dstar_shot, r.responsivity * math.sqrt(0.04) /
                 math.sqrt(2 * 1.602176634e-19 * 1e-9), 1e-12)
        r2 = scope.analyze_pulses(tr, scope.PulseSettings(noise_bandwidth_hz=1e5))
        self.assertLess(r2.noise_off_band_v, r.noise_off_band_v)

    def test_inverted_reference_and_no_reference(self):
        tr = synth()
        inv = scope.ScopeTrace(tr.t, {"CH1": [33.0 - v for v in tr.channels["CH1"]],
                                      "CH2": tr.channels["CH2"]})
        r = scope.analyze_pulses(inv, scope.PulseSettings(light_on_high=False))
        self.assertAlmostEqual(r.delta_v, 0.8, delta=0.01)
        wrong = scope.analyze_pulses(inv, scope.PulseSettings(light_on_high=True))
        self.assertLess(wrong.delta_v, 0)
        self.assertTrue(any("ters kutup" in w for w in wrong.warnings))
        r = scope.analyze_pulses(tr, scope.PulseSettings(reference=None))
        self.rel(r.period, 200e-6, 1e-3)
        self.rel(r.rise_time, math.log(9) * 2e-6, 0.1)

    def test_no_edges_gives_warning(self):
        t = [k * 1e-6 for k in range(500)]
        tr = scope.ScopeTrace(t, {"CH1": [1.0] * 500, "CH2": [0.0] * 500})
        r = scope.analyze_pulses(tr, scope.PulseSettings())
        self.assertTrue(r.warnings)
        self.assertFalse(r.edges)
        self.assertTrue(r.report_rows())

    def test_system_rise_correction(self):
        tr = synth(tau_r=1e-6)
        r = scope.analyze_pulses(tr, scope.PulseSettings(system_rise_s=2e-6))
        raw = r.rise_time
        self.rel(r.corrected(raw), math.sqrt(raw ** 2 - 4e-12), 1e-9)
        r = scope.analyze_pulses(tr, scope.PulseSettings(system_rise_s=3.5e-6))
        self.assertTrue(math.isnan(r.corrected(r.rise_time)))
        self.assertTrue(any("sinir" in w for w in r.warnings))

    def test_real_ds3100_recording(self):
        """Modern (numpy) surumle ayni sonuclar."""
        tr = scope.load_scope_csv(DATA)
        r = scope.analyze_pulses(tr, scope.PulseSettings(
            system_rise_s=scope.AMP120_RISE_S, optical_power_w=1e-3, wavelength_nm=365,
            area_cm2=0.04))
        self.assertAlmostEqual(r.interleave_v, 0.08, places=9)
        self.assertEqual(r.n_cycles, 5)
        # modern surumun ayni dosyadaki degerleri (5 anlamli basamak)
        expected = [(r.period, 2.0801e-4), (r.duty, 0.50009), (r.v_on, 0.47226),
                    (r.v_off, -0.35806), (r.noise_off_v, 0.25194),
                    (r.noise_off_band_v, 0.048749), (r.rise_time, 3.4731e-6),
                    (r.fall_time, 6.9793e-6), (r.edge_stats("on")[0], 3.2702e-6),
                    (r.avg_rise.fit.tau, 1.5425e-6), (r.avg_fall.fit.tau, 5.8943e-6),
                    (r.responsivity, 0.0083032)]
        for got, want in expected:
            self.rel(got, want, 1e-4)
        self.assertLess(r.edge_stats("on")[1], 1e-6)

    def test_exports(self):
        tmp = tempfile.mkdtemp()
        try:
            r = scope.analyze_pulses(synth(), scope.PulseSettings(optical_power_w=1e-3))
            rep = scope.write_report(r, os.path.join(tmp, "r.txt"), "numune")
            with open(rep, "rb") as fh:
                data = fh.read()
            self.assertIn(b"\r\n", data)
            self.assertIn(b"Parametre\tDeger\tBirim", data)
            self.assertIn(b"\tA/W", data)
            ed = scope.write_edges_csv(r, os.path.join(tmp, "e.csv"))
            with open(ed) as fh:
                lines = fh.read().splitlines()
            self.assertTrue(lines[0].startswith("kenar,tur,t_ref_s"))
            self.assertEqual(len(lines), len(r.edges) + 1)
            av = scope.write_average_csv(r, os.path.join(tmp, "a.csv"))
            with open(av) as fh:
                self.assertIn("tau_s,V_avg_V,I_avg_A", fh.read())
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
