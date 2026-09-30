# -*- coding: utf-8 -*-
"""Veri dosyalari ve olcum motorlari (simulatorle)."""

import io
import os
import shutil
import tempfile
import unittest

from uvpd_xp.analysis import compare
from uvpd_xp.dataset import DARK, LIGHT, Dataset, suggest_filename
from uvpd_xp.instrument import SmuConfig
from uvpd_xp.measurement import SampleInfo, SweepConfig, TransientConfig, run_sweep, run_transient
from uvpd_xp.simulator import SimulatedKeithley2636

# Modern (Windows 10/11) surumun yazdigi dosyadan bir ornek
MODERN_CSV = (
    u'# UVPD-META:{"name": "ZnO-1", "kind": "iv", "light_state": "light", '
    u'"wavelength_nm": 365.0, "optical_power_w": 2e-06, "irradiance_w_cm2": null, '
    u'"area_cm2": 0.04, "timestamp": "2026-09-01T10:00:00", "notes": "", "settings": {}}\n'
    u"# Keithley 2636 / Adapter Box C 10 - UV fotodedektor olcumu\n"
    u"# olusturma: 2026-09-01T10:00:00\n"
    u"time_s,voltage_V,current_A\n"
    u"0.000000,-1,-3.2e-07\n"
    u"0.050000,0,-1e-12\n"
    u"0.100000,1,4.5e-06\n")


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_roundtrip(self):
        ds = Dataset(name="ZnO-1", light_state=LIGHT, wavelength_nm=365.0,
                     optical_power_w=1.5e-6, area_cm2=0.04, notes="deneme")
        for k in range(5):
            ds.append(k * 0.1, k * 0.5, k * 1e-9)
        path = ds.to_csv(os.path.join(self.tmp, "a", "b.csv"))
        back = Dataset.from_csv(path)
        self.assertEqual(back.name, "ZnO-1")
        self.assertEqual(back.light_state, LIGHT)
        self.assertEqual(back.wavelength_nm, 365.0)
        self.assertEqual(back.notes, "deneme")
        self.assertEqual(len(back), 5)
        self.assertAlmostEqual(back.i[4], 4e-9)

    def test_reads_modern_version_file(self):
        path = os.path.join(self.tmp, "modern.csv")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(MODERN_CSV)
        ds = Dataset.from_csv(path)
        self.assertEqual(ds.name, "ZnO-1")
        self.assertEqual(ds.optical_power_w, 2e-6)
        self.assertEqual(ds.v, [-1.0, 0.0, 1.0])
        self.assertAlmostEqual(ds.i[2], 4.5e-6)

    def test_written_file_header_matches_modern_format(self):
        ds = Dataset(name="x")
        ds.append(0, 0, 0)
        path = ds.to_csv(os.path.join(self.tmp, "x.csv"))
        with io.open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertTrue(lines[0].startswith("# UVPD-META:{"))
        self.assertEqual(lines[3], "time_s,voltage_V,current_A")

    def test_suggest_filename_is_ascii_and_safe(self):
        ds = Dataset(name="numune 1/2 \u00e7", light_state=DARK)
        name = os.path.basename(suggest_filename(ds, self.tmp))
        self.assertTrue(name.endswith("_iv_karanlik.csv"))
        name.encode("ascii")
        self.assertNotIn("/", name)


class MeasurementTests(unittest.TestCase):
    def sim(self):
        s = SimulatedKeithley2636()
        s.connect()
        return s

    def test_sweep_levels_dual(self):
        lv = SweepConfig(start=-1, stop=1, points=5, dual=True).levels()
        self.assertEqual(len(lv), 9)
        self.assertEqual((lv[0], lv[4], lv[-1]), (-1, 1, -1))

    def test_run_sweep(self):
        ds = run_sweep(self.sim(), SmuConfig(), SweepConfig(-1, 1, 21, settle_time=0, hold_time=0),
                       SampleInfo(name="sim"))
        self.assertEqual(len(ds), 21)
        self.assertGreater(abs(ds.i[-1]), abs(ds.i[0]))
        self.assertEqual(ds.settings["program"], "uvpd_xp")

    def test_dark_vs_light_photocurrent(self):
        inst = self.sim()
        inst.noise_floor = 0.0
        cfg = SweepConfig(-1.0, 0.0, 11, settle_time=0, hold_time=0)
        inst.set_uv(False)
        dark = run_sweep(inst, SmuConfig(), cfg, SampleInfo(light_state=DARK))
        inst.set_uv(True)
        inst.settle_uv()
        light = run_sweep(inst, SmuConfig(), cfg, SampleInfo(light_state=LIGHT, optical_power_w=2e-6))
        c = compare(dark, light)
        mean_ph = sum(c.i_photo) / len(c.i_photo)
        self.assertLess(mean_ph, 0)
        self.assertAlmostEqual(abs(mean_ph) / (inst.responsivity * inst.optical_power), 1.0, delta=0.1)

    def test_stop_callback(self):
        calls = [0]

        def should_stop():
            calls[0] += 1
            return calls[0] > 5

        ds = run_sweep(self.sim(), SmuConfig(), SweepConfig(points=50, settle_time=0, hold_time=0),
                       SampleInfo(), should_stop=should_stop)
        self.assertTrue(0 < len(ds) < 50)

    def test_transient_auto_cycle(self):
        inst = self.sim()
        inst.rise_tau = inst.fall_tau = 0.05
        cfg = TransientConfig(bias=-1.0, duration=1.2, interval=0.02, hold_time=0,
                              cycle_enabled=True, cycle_delay=0.3, cycle_on=0.3, cycle_off=0.3)
        ds = run_transient(inst, SmuConfig(), cfg, SampleInfo(light_state=LIGHT),
                           light_control=inst.set_uv)
        self.assertGreater(len(ds), 30)
        self.assertEqual(ds.kind, "transient")
        self.assertEqual(ds.settings["light_events"][0][1], 1)
        self.assertGreater(max(abs(x) for x in ds.i), max(abs(x) for x in ds.i[:5]))


if __name__ == "__main__":
    unittest.main()
