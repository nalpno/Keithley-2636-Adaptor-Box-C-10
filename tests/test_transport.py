# -*- coding: utf-8 -*-
"""GPIB (gpib-32.dll) ve VISA (visa32.dll) katmani - sahte DLL'lerle."""

import unittest

from tests.fakes import IDN, FakeGpibLib, FakeVisaLib
from uvpd_xp import transport as tr


class ParseTests(unittest.TestCase):
    def test_parse_gpib_resource(self):
        self.assertEqual(tr.parse_gpib_resource("GPIB0::26::INSTR"), (0, 26, 0))
        self.assertEqual(tr.parse_gpib_resource("gpib1::5::INSTR"), (1, 5, 0))
        self.assertEqual(tr.parse_gpib_resource("GPIB::26"), (0, 26, 0))
        self.assertEqual(tr.parse_gpib_resource("GPIB0::26::3::INSTR"), (0, 26, 3))
        self.assertIsNone(tr.parse_gpib_resource("USB0::0x05E6::0x2636::123::INSTR"))
        self.assertIsNone(tr.parse_gpib_resource("TCPIP0::1.2.3.4::inst0::INSTR"))

    def test_not_gpib_raises(self):
        with self.assertRaises(tr.TransportError):
            tr.GpibTransport("USB0::1::2::INSTR", lib=FakeGpibLib())


class GpibTests(unittest.TestCase):
    def open(self, **kw):
        lib = FakeGpibLib(**kw)
        t = tr.GpibTransport("GPIB0::26::INSTR", lib=lib)
        t.open()
        return t, lib

    def test_query_idn(self):
        t, lib = self.open()
        self.assertTrue(t.is_open)
        self.assertEqual(t.query("*IDN?"), IDN)
        self.assertEqual(lib.written[-1], "*IDN?")

    def test_tab_separated_answer(self):
        t, _ = self.open()
        self.assertEqual(t.query("print(smua.measure.iv())"),
                         "-1.234500000e-09\t-5.000000000e-01")

    def test_long_answer_is_read_in_chunks(self):
        long_answer = "X" * 50 + "END"
        t, _ = self.open(long_answer=long_answer)
        t.BUFSIZE = 16
        self.assertEqual(t.query("*IDN?"), long_answer)

    def test_count_fallback_without_ibcntl(self):
        t, _ = self.open(with_count=False)
        self.assertEqual(t.query("*IDN?"), IDN)

    def test_no_listener_gives_enol(self):
        lib = FakeGpibLib(listeners=())
        t = tr.GpibTransport("GPIB0::26::INSTR", lib=lib)
        with self.assertRaises(tr.TransportError) as cm:
            t.open()
        self.assertIn("ENOL", str(cm.exception))

    def test_timeout_is_reported(self):
        t, _ = self.open(fail_read_err=6)
        t.write("*IDN?")
        with self.assertRaises(tr.TransportError) as cm:
            t.read()
        self.assertIn("EABO", str(cm.exception))

    def test_close(self):
        t, lib = self.open()
        t.close()
        self.assertFalse(t.is_open)
        with self.assertRaises(tr.TransportError):
            t.write("x")

    def test_scan_finds_listeners(self):
        lib = FakeGpibLib(listeners=(5, 26))
        self.assertEqual(tr.gpib_scan(0, lib=lib), ["GPIB0::5::INSTR", "GPIB0::26::INSTR"])

    def test_scan_missing_board(self):
        with self.assertRaises(tr.TransportError) as cm:
            tr.gpib_scan(3, lib=FakeGpibLib())
        self.assertIn("GPIB3", str(cm.exception))


class VisaTests(unittest.TestCase):
    def test_query_idn(self):
        lib = FakeVisaLib()
        t = tr.VisaTransport("GPIB0::26::INSTR", lib=lib)
        t.open()
        self.assertEqual(t.query("*IDN?"), IDN)
        t.close()
        self.assertIn(200, lib.closed)
        self.assertIn(100, lib.closed)

    def test_long_answer_uses_max_cnt_loop(self):
        long_answer = "Y" * 40 + "Z"
        lib = FakeVisaLib(long_answer=long_answer)
        t = tr.VisaTransport("GPIB0::26::INSTR", lib=lib)
        t.BUFSIZE = 8
        t.open()
        self.assertEqual(t.query("*IDN?"), long_answer)

    def test_unknown_resource(self):
        t = tr.VisaTransport("GPIB0::9::INSTR", lib=FakeVisaLib())
        with self.assertRaises(tr.TransportError) as cm:
            t.open()
        self.assertIn("BFFF0011", str(cm.exception))

    def test_scan(self):
        self.assertEqual(tr.visa_scan(lib=FakeVisaLib()), ["GPIB0::26::INSTR", "ASRL1::INSTR"])
        self.assertEqual(tr.visa_scan(lib=FakeVisaLib(resources=())), [])


class OpenTransportTests(unittest.TestCase):
    def test_gpib_backend_rejects_non_gpib(self):
        with self.assertRaises(tr.TransportError):
            tr.open_transport("USB0::1::2::INSTR", tr.BACKEND_GPIB)

    def test_timeout_codes(self):
        self.assertEqual(tr._tmo_code(1000), tr.T1s)
        self.assertEqual(tr._tmo_code(30000), tr.T30s)
        self.assertEqual(tr._tmo_code(10 ** 6), tr.T300s)


if __name__ == "__main__":
    unittest.main()
