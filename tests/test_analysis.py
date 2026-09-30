# -*- coding: utf-8 -*-
"""Saf Python analiz fonksiyonlari (modern surumdeki testlerin karsiligi)."""

import math
import unittest

from uvpd_xp import analysis
from uvpd_xp.dataset import DARK, LIGHT, Dataset


def make_ds(v, i, **kw):
    ds = Dataset(**kw)
    for k, (vv, ii) in enumerate(zip(v, i)):
        ds.append(k, vv, ii)
    return ds


class HelperTests(unittest.TestCase):
    def test_photon_energy(self):
        self.assertAlmostEqual(analysis.photon_energy_ev(365.0), 3.397, places=2)
        self.assertAlmostEqual(analysis.photon_energy_ev(1239.84), 1.0, places=3)

    def test_percentile_matches_numpy(self):
        vals = [5.0, 1.0, 3.0, 2.0, 4.0]
        self.assertAlmostEqual(analysis.percentile(vals, 10), 1.4)
        self.assertAlmostEqual(analysis.percentile(vals, 50), 3.0)
        self.assertAlmostEqual(analysis.percentile(vals, 90), 4.6)

    def test_interp_and_monotonic(self):
        xs, ys = analysis.monotonic_xy([2, 0, 1, 1], [20, 0, 10, 30])
        self.assertEqual(xs, [0.0, 1.0, 2.0])
        self.assertEqual(ys, [0.0, 20.0, 20.0])          # x=1 tekrarlari ortalandi
        self.assertAlmostEqual(analysis.interp(0.5, xs, ys), 10.0)
        self.assertTrue(math.isnan(analysis.interp(3.0, xs, ys)))

    def test_moving_average_same(self):
        out = analysis.moving_average_same([0, 0, 3, 0, 0], 3)
        self.assertEqual([round(v, 6) for v in out], [0, 1, 1, 1, 0])

    def test_linear_fit(self):
        a, b = analysis.linear_fit([0, 1, 2, 3], [1, 3, 5, 7])
        self.assertAlmostEqual(a, 2.0)
        self.assertAlmostEqual(b, 1.0)


class CompareTests(unittest.TestCase):
    def test_compare_and_photocurrent(self):
        v = analysis.linspace(-1, 1, 21)
        dark = make_ds(v, [1e-12 * x for x in v], name="d", light_state=DARK)
        light = make_ds(v, [1e-12 * x + 5e-9 for x in v], name="l", light_state=LIGHT)
        c = analysis.compare(dark, light)
        self.assertEqual(len(c.v), 21)
        for ph in c.i_photo:
            self.assertAlmostEqual(ph, 5e-9, delta=1e-15)
        self.assertAlmostEqual(c.at(0.0)["i_photo_A"], 5e-9, delta=1e-15)

    def test_compare_with_different_grids(self):
        dark = make_ds(analysis.linspace(-2, 2, 41), [0.0] * 41)
        light = make_ds(analysis.linspace(-1, 1, 11), [2e-9] * 11)
        c = analysis.compare(dark, light)
        self.assertGreaterEqual(c.v[0], -1)
        self.assertLessEqual(c.v[-1], 1)
        for ph in c.i_photo:
            self.assertAlmostEqual(ph, 2e-9, delta=1e-15)

    def test_at_uses_nearest_point(self):
        dark = make_ds([-2, -1, 0, 1, 1.96], [1e-9] * 5)
        light = make_ds([-2, -1, 0, 1, 1.96], [2e-9] * 5)
        c = analysis.compare(dark, light)
        self.assertAlmostEqual(c.at(2.0)["bias_V"], 1.96)

    def test_subtract(self):
        a = make_ds([0, 1, 2], [1e-9, 2e-9, 3e-9])
        b = make_ds([0, 1, 2], [1e-9, 1e-9, 1e-9])
        _, d = analysis.subtract(a, b)
        for got, exp in zip(d, [0, 1e-9, 2e-9]):
            self.assertAlmostEqual(got, exp, delta=1e-18)


class MetricTests(unittest.TestCase):
    def test_detector_metrics(self):
        m = analysis.detector_metrics(1e-9, 101e-9, wavelength_nm=365.0,
                                      optical_power_w=1e-6, area_cm2=0.04, bias_v=1.0)
        self.assertAlmostEqual(m.i_photo, 100e-9)
        self.assertAlmostEqual(m.on_off_ratio, 101.0)
        self.assertAlmostEqual(m.responsivity, 0.1)
        self.assertAlmostEqual(m.eqe_percent, 33.97, delta=0.1)
        noise = math.sqrt(2 * analysis.Q_E * 1e-9)
        self.assertAlmostEqual(m.detectivity / (0.1 * math.sqrt(0.04) / noise), 1.0, places=9)
        self.assertAlmostEqual(m.nep / (noise / 0.1), 1.0, places=9)

    def test_metrics_without_power_warns(self):
        m = analysis.detector_metrics(1e-9, 2e-9)
        self.assertFalse(analysis.isfinite(m.responsivity))
        self.assertTrue(any("Optik guc" in w for w in m.warnings))

    def test_as_table_has_numbers_and_units(self):
        m = analysis.detector_metrics(1e-9, 2e-9, 365.0, 1e-6, 0.04)
        rows = dict((k, (v, u)) for k, v, u in m.as_table())
        self.assertEqual(rows["Duyarlilik R"][1], "A/W")
        self.assertIsInstance(rows["Duyarlilik R"][0], float)

    def test_diode_parameters(self):
        n, i0 = 1.8, 1e-12
        kt_q = analysis.K_B * 300 / analysis.Q_E
        v = analysis.linspace(0.1, 0.5, 40)
        i = [i0 * math.exp(x / (n * kt_q)) for x in v]
        p = analysis.diode_parameters(v, i, 0.1, 0.5, temperature_k=300.0)
        self.assertAlmostEqual(p["ideality"], n, delta=n * 1e-3)
        self.assertAlmostEqual(p["i0"] / i0, 1.0, delta=1e-2)

    def test_rectification_ratio(self):
        v = analysis.linspace(-1, 1, 101)
        i = [x * 1e-6 if x > 0 else x * 1e-9 for x in v]
        self.assertAlmostEqual(analysis.rectification_ratio(v, i, 1.0), 1000.0, delta=1e-6)


class TransientTests(unittest.TestCase):
    def test_square_wave(self):
        dt, tau = 0.01, 0.2
        t = [k * dt for k in range(4000)]
        state, sig = 0.0, [0.0]
        for k in range(1, len(t)):
            target = 1.0 if int(t[k] // 5) % 2 == 1 else 0.0
            state = target + (state - target) * math.exp(-dt / tau)
            sig.append(state)
        i = [1e-9 + s * 99e-9 for s in sig]
        m = analysis.transient_metrics(t, i)
        self.assertAlmostEqual(m.on_off_ratio / 100.0, 1.0, delta=0.05)
        expected = tau * math.log(9)
        self.assertAlmostEqual(m.rise_time_s / expected, 1.0, delta=0.15)
        self.assertAlmostEqual(m.fall_time_s / expected, 1.0, delta=0.15)
        self.assertGreaterEqual(m.n_cycles, 3)

    def test_light_spans(self):
        ds = make_ds([0] * 10, [0] * 10)
        ds.settings["light_events"] = [[2.0, 1], [5.0, 0], [7.0, 1]]
        self.assertEqual(analysis.light_spans(ds), [(2.0, 5.0), (7.0, 9.0)])


if __name__ == "__main__":
    unittest.main()
