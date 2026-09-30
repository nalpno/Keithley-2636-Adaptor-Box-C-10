# -*- coding: utf-8 -*-
"""Keithley TSP surucusu: gonderilen komutlar ve cevap ayristirma."""

import unittest

from tests.fakes import IDN, FakeGpibLib, FakeTransport
from uvpd_xp import transport as tr
from uvpd_xp.instrument import Keithley2636, SmuConfig, create_instrument
from uvpd_xp.simulator import SimulatedKeithley2636


class InstrumentTests(unittest.TestCase):
    def make(self):
        t = FakeTransport()
        k = Keithley2636("GPIB0::26::INSTR", transport=t)
        return k, t

    def test_connect_sets_up_tsp_and_reads_idn(self):
        k, t = self.make()
        self.assertEqual(k.connect(), IDN)
        self.assertEqual(t.written[0], "localnode.prompts = 0")
        self.assertIn("format.asciiprecision = 10", t.written)
        self.assertEqual(t.written[-1], "*IDN?")

    def test_apply_config_voltage_source(self):
        k, t = self.make()
        k.connect()
        t.written = []
        k.apply_config(SmuConfig(compliance=1e-3, nplc=5, filter_count=4, four_wire=False))
        w = t.written
        self.assertIn("smua.reset()", w)
        self.assertIn("smua.source.func = smua.OUTPUT_DCVOLTS", w)
        self.assertIn("smua.source.limiti = 0.001", w)
        self.assertIn("smua.measure.nplc = 5", w)
        self.assertIn("smua.measure.filter.count = 4", w)
        self.assertIn("smua.measure.filter.enable = smua.FILTER_ON", w)
        self.assertIn("smua.sense = smua.SENSE_LOCAL", w)
        self.assertIn("print(errorqueue.count)", w)

    def test_apply_config_channel_b_current_source_four_wire(self):
        k, t = self.make()
        k.apply_config(SmuConfig(channel="b", source_func="current", compliance=10,
                                 four_wire=True))
        w = t.written
        self.assertIn("smub.source.func = smub.OUTPUT_DCAMPS", w)
        self.assertIn("smub.source.limitv = 10", w)
        self.assertIn("smub.sense = smub.SENSE_REMOTE", w)

    def test_nplc_is_clamped(self):
        k, t = self.make()
        k.apply_config(SmuConfig(nplc=100))
        self.assertIn("smua.measure.nplc = 25", t.written)

    def test_measure_iv_parses_tab_separated(self):
        k, t = self.make()
        i, v = k.measure_iv()
        self.assertAlmostEqual(i, -1.2345e-9)
        self.assertAlmostEqual(v, -0.5)

    def test_set_level_and_output_off(self):
        k, t = self.make()
        k.apply_config(SmuConfig())
        k.set_level(0.25)
        k.output_off()
        self.assertIn("smua.source.levelv = 0.25", t.written)
        self.assertEqual(t.written[-1], "smua.source.output = smua.OUTPUT_OFF")

    def test_digio(self):
        k, t = self.make()
        k.write_digio_bit(3, True)
        self.assertEqual(t.written[-1], "digio.writebit(3, 1)")
        self.assertEqual(k.read_digio_bit(3), 1)

    def test_over_real_gpib_transport(self):
        """Surucu + GpibTransport + sahte gpib-32.dll uctan uca."""
        lib = FakeGpibLib()
        tt = tr.GpibTransport("GPIB0::26::INSTR", lib=lib)
        tt.open()
        k = Keithley2636("GPIB0::26::INSTR", transport=tt)
        self.assertEqual(k.connect(), IDN)
        k.apply_config(SmuConfig())
        self.assertEqual(k.measure_iv()[1], -0.5)
        k.close()
        self.assertFalse(tt.is_open)
        self.assertIn("smua.source.output = smua.OUTPUT_OFF", lib.written)

    def test_create_instrument_sim(self):
        self.assertIsInstance(create_instrument("SIM::X", backend="sim"), SimulatedKeithley2636)
        self.assertIsInstance(create_instrument("GPIB0::26::INSTR"), Keithley2636)


if __name__ == "__main__":
    unittest.main()
