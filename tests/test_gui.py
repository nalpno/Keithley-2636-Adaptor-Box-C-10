# -*- coding: utf-8 -*-
"""Arayuz duman testi (simulasyon modu).

Ekran yoksa (sunucu) atlanir. Gelistirme ortaminda Xvfb ile calistirilir.
"""

import os
import shutil
import tempfile
import time
import unittest

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.destroy()
    HAVE_DISPLAY = True
except Exception:
    HAVE_DISPLAY = False


def pump(root, cond, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        if cond():
            root.update()
            return True
        time.sleep(0.01)
    return False


@unittest.skipUnless(HAVE_DISPLAY, "ekran yok")
class GuiTests(unittest.TestCase):
    def setUp(self):
        from uvpd_xp import config
        from uvpd_xp.gui import app as app_mod
        from uvpd_xp.gui import iv_tab
        self.tmp = tempfile.mkdtemp()
        # ayar dosyasi test klasorune yazilsin
        self._orig_path = config.settings_path
        config.settings_path = lambda: os.path.join(self.tmp, "ayarlar.json")
        # ikili olcumdeki "UV kaynagini acin" onayini otomatik ver
        self._orig_ask = iv_tab.ask_ok
        iv_tab.ask_ok = lambda *a, **k: True
        self.root = tk.Tk()
        self.app = app_mod.App(self.root, simulate=True)
        s = self.app.session
        s.settings["data_dir"] = self.tmp
        s.settings["interlock_confirmed"] = True
        self.app.tab_conn.interlock.set(True)
        s.connect("SIM::UVPD::INSTR", "sim")

    def tearDown(self):
        from uvpd_xp import config
        from uvpd_xp.gui import iv_tab
        # once pencereyi kapat (ayarlar hala test klasorune yazilir), sonra geri yukle
        try:
            self.app.on_close()
        except tk.TclError:
            pass
        config.settings_path = self._orig_path
        iv_tab.ask_ok = self._orig_ask
        shutil.rmtree(self.tmp)

    def test_dual_sweep_compare_and_export(self):
        app = self.app
        tab = app.tab_iv
        tab.points.set(11)
        tab.start.set(-0.5)
        tab.stop.set(0.5)
        tab.settle.set(0.0)
        tab.start_sweep(True)
        self.assertTrue(pump(self.root, lambda: len(app.session.datasets) == 2))
        ds_dark, ds_light = app.session.datasets
        self.assertEqual(ds_dark.light_state, "dark")
        self.assertEqual(ds_light.light_state, "light")
        self.assertEqual(len(ds_dark), 11)

        # ikili olcum bitince karsilastirma otomatik yapilmali
        an = app.tab_an
        self.assertTrue(pump(self.root, lambda: an.comparison is not None))
        self.assertEqual(str(app.nb.select()), str(an))
        self.assertGreater(len(an.table.rows()), 10)
        self.assertEqual(app.listbox.size(), 2)

        # otomatik kaydedilen dosyalar
        csvs = [f for f in os.listdir(self.tmp) if f.endswith(".csv")]
        self.assertEqual(len(csvs), 2)

        # tum gosterimler cizilebilmeli
        for k in range(len(an.view.items)):
            an.view.widget.current(k)
            an._draw()
            self.root.update()

        rep = an.write_report(os.path.join(self.tmp, "rapor.txt"))
        with open(rep, "rb") as fh:
            data = fh.read()
        self.assertIn(b"\r\n", data)                      # Not Defteri icin CRLF
        self.assertIn(b"Parametre\tDeger\tBirim", data)
        self.assertIn(b"\tA/W", data)
        diff = an.write_difference(os.path.join(self.tmp, "fark.csv"))
        with open(diff) as fh:
            self.assertIn("voltage_V,I_dark_A", fh.read())

        an.do_diode()
        self.assertTrue(any("Idealite" in r[0] for r in an.table.rows()))

        eps = os.path.join(self.tmp, "g.eps")
        an.plot.save_postscript(eps)
        self.assertGreater(os.path.getsize(eps), 1000)

    def test_transient_auto_cycle(self):
        app = self.app
        inst = app.session.instrument
        inst.rise_tau = inst.fall_tau = 0.05
        tab = app.tab_tr
        tab.duration.set(1.5)
        tab.interval.set(0.02)
        tab.cycle.set(True)
        tab.cycle_delay.set(0.2)
        tab.cycle_on.set(0.4)
        tab.cycle_off.set(0.4)
        tab.start()
        self.assertTrue(pump(self.root, lambda: len(app.session.datasets) == 1))
        ds = app.session.datasets[0]
        self.assertEqual(ds.kind, "transient")
        self.assertIn("light_events", ds.settings)
        self.assertGreater(len(tab.metrics.rows()), 5)

    def test_stop_request_stops_sweep(self):
        app = self.app
        tab = app.tab_iv
        tab.points.set(2000)
        tab.settle.set(0.01)
        tab.start_sweep(False)
        self.assertTrue(pump(self.root, lambda: float(tab.progress.cget("value")) > 5, 10))
        app.emergency_off()                # olcum sirasinda "cikisi hemen kapat"
        self.assertTrue(pump(self.root, lambda: not app.session.busy, 10))
        self.assertEqual(len(app.session.datasets), 1)
        self.assertLess(len(app.session.datasets[0]), 2000)

    def test_callback_error_is_shown_and_logged(self):
        from uvpd_xp import errorlog
        from uvpd_xp.gui import app as app_mod
        shown = []
        orig_err, orig_log = app_mod.error, errorlog.LOG_PATH
        app_mod.error = lambda parent, title, text: shown.append(text)
        errorlog.LOG_PATH = os.path.join(self.tmp, "hata_kaydi.txt")
        try:
            def bad():
                raise ValueError("deneme hatasi")
            self.root.after(0, bad)
            pump(self.root, lambda: bool(shown), 5)
        finally:
            app_mod.error = orig_err
            errorlog.LOG_PATH = orig_log
        self.assertTrue(shown, "hata kullaniciya gosterilmedi")
        self.assertIn("deneme hatasi", shown[0])
        with open(os.path.join(self.tmp, "hata_kaydi.txt")) as fh:
            self.assertIn("ValueError: deneme hatasi", fh.read())

    def test_scope_tab_loads_csv_and_exports(self):
        """v2: osiloskop CSV'si yuklenir, analiz edilir, tum gosterimler cizilir."""
        from uvpd_xp.gui import scope_tab as st
        data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                            "rigol_ds3100_ACOPE_01.csv")
        app = self.app
        tab = app.tab_scope
        self.assertEqual(app.nb.index(tab), 4)          # eski 4 sekme yerinde kaldi
        app.nb.select(tab)
        tab.load50.set(False)
        tab.gain.set(1e5)
        self.assertTrue(tab.load_file(data))
        self.assertEqual(tab.signal_ch.get(), "CH2")
        self.assertEqual(tab.ref_ch.get(), "CH1")
        res = tab.result
        self.assertEqual(res.n_cycles, 5)
        rows = dict(tab.table.rows())
        self.assertEqual(rows["Periyot"], "208 us")
        self.assertIn("A/W", rows["Duyarlilik R = I_ph / P"])

        for key in (st.VIEW_WAVE, st.VIEW_WAVE_I, st.VIEW_EDGES, st.VIEW_CYCLE,
                    st.VIEW_PER_EDGE):
            tab.set_view(key)
            self.root.update()
            self.assertGreater(len(tab.plot.canvas.find_all()), 20, key)

        i1 = res.photocurrent
        tab.load50.set(True)
        tab.analyze()
        self.assertAlmostEqual(tab.result.photocurrent / i1, 2.0)
        self.assertTrue(self.app.session.settings["scope"]["load_50ohm"])

        tab.ref_ch.set(st.NO_REF)
        tab.analyze()
        self.assertIsNone(tab.result.settings.reference)

        for kind, name in (("report", "r.txt"), ("edges", "e.csv"),
                           ("avg", "a.csv"), ("eps", "g.eps")):
            path = tab.export_to(kind, os.path.join(self.tmp, name))
            self.assertGreater(os.path.getsize(path), 100)
        tab.copy_table()
        self.assertIn("Periyot", self.root.clipboard_get())

    def test_plot_log_scale_and_empty(self):
        p = self.app.tab_iv.plot
        p.clear()
        p.set_yscale("log")
        p.redraw()                          # veri yokken hata vermemeli
        p.add_series("x", "x")
        p.set_data("x", [-1, 0, 1], [-1e-9, 0.0, 1e-6])
        p.redraw()
        self.assertGreater(len(p.canvas.find_all()), 10)


if __name__ == "__main__":
    unittest.main()
