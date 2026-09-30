# -*- coding: utf-8 -*-
"""Karsilastirma ve analiz sekmesi."""

import io
import os
from datetime import datetime

from tkinter import filedialog, ttk

from .. import analysis
from ..dataset import DARK, LIGHT, Dataset
from .common import Form, KeyValueTable, ScrollFrame, error, info, warn
from .plot import LOG_ABS, CanvasPlot, YScaleSelector

VIEW_IV, VIEW_PHOTO, VIEW_RATIO, VIEW_DIFF = "iv", "photo", "ratio", "diff"


def _num(x):
    return "{0:.6g}".format(x) if analysis.isfinite(x) else ""


class AnalysisTab(ttk.Frame):
    def __init__(self, master, session):
        ttk.Frame.__init__(self, master, padding=6)
        self.session = session
        self.comparison = None
        self.report_rows = []      # (etiket, sayi_veya_metin, birim)
        self.report_head = []

        sf = ScrollFrame(self)
        sf.pack(side="left", fill="y", padx=(0, 6))
        left = sf.inner
        right = ttk.Panedwindow(self, orient="vertical")
        right.pack(side="left", fill="both", expand=True)

        f1 = Form(left, "1) Karsilastirilacak olcumler")
        f1.pack(fill="x", pady=(0, 4))
        self.combo_a = f1.combo("A - Karanlik", [], None, width=30)
        self.combo_b = f1.combo("B - UV altinda", [], None, width=30)
        row = ttk.Frame(f1)
        ttk.Button(row, text="A'yi dosyadan yukle", command=lambda: self._load(True)).pack(side="left", padx=(0, 4))
        ttk.Button(row, text="B'yi dosyadan yukle", command=lambda: self._load(False)).pack(side="left")
        f1.full(row)
        f1.full(ttk.Button(f1, text="Karsilastir ve farki cikar", command=self.do_compare))

        f2 = Form(left, "2) Fotodedektor parametreleri")
        f2.pack(fill="x", pady=(0, 4))
        self.view = f2.combo("Gosterim", [("I-V egrileri (A ve B)", VIEW_IV),
                                          ("Fotoakim I_ph = B - A", VIEW_PHOTO),
                                          ("Ac/kapa orani |I_B/I_A|", VIEW_RATIO),
                                          ("Ham fark (B - A)", VIEW_DIFF)], VIEW_IV, width=24)
        self.bias = f2.sci("Analiz bias'i (V)", 1.0)
        s = session.settings
        self.wavelength = f2.sci("Dalga boyu (nm)", s.get("wavelength_nm", 365.0))
        self.power = f2.sci("Optik guc (W)", s.get("optical_power_w", 2e-6))
        self.area = f2.sci("Aktif alan (cm2)", s.get("area_cm2", 0.04))
        f2.full(ttk.Button(f2, text="Parametreleri hesapla", command=self.do_metrics))

        f3 = Form(left, "3) Diyot analizi (opsiyonel)")
        f3.pack(fill="x", pady=(0, 4))
        self.fit_min = f3.sci("Uydurma alt sinir (V)", 0.1)
        self.fit_max = f3.sci("Uydurma ust sinir (V)", 0.5)
        self.rect_bias = f3.sci("Dogrultma orani bias'i (V)", 1.0)
        f3.full(ttk.Button(f3, text="Diyot parametrelerini hesapla", command=self.do_diode))

        f4 = ttk.Labelframe(left, text="4) Disa aktar", padding=4)
        f4.pack(fill="x")
        ttk.Button(f4, text="Farki CSV kaydet", command=self.export_difference).pack(fill="x", pady=1)
        ttk.Button(f4, text="Rapor kaydet (.txt, Excel'e uygun)", command=self.export_report).pack(fill="x", pady=1)
        ttk.Button(f4, text="Grafigi kaydet (.eps)", command=self.export_eps).pack(fill="x", pady=1)

        top = ttk.Frame(right)
        self.plot = CanvasPlot(top, "Gerilim (V)", "Akim (A)", height=300)
        YScaleSelector(top, self.plot, default=LOG_ABS).pack(anchor="w", pady=(0, 3))
        self.plot.pack(fill="both", expand=True)
        bottom = ttk.Labelframe(right, text="Sonuclar (Ctrl+C ile kopyalanir)", padding=3)
        self.table = KeyValueTable(bottom, height=9)
        self.table.pack(fill="both", expand=True)
        right.add(top, weight=3)
        right.add(bottom, weight=2)

        self.view.bind_change(self._draw)
        session.on("datasets", self.refresh_lists)
        self.refresh_lists()

    # ------------------------------------------------------------------
    def refresh_lists(self):
        items = [("{0}. {1} [{2} nk]".format(k + 1, ds.label, len(ds)), k)
                 for k, ds in enumerate(self.session.datasets)]
        for combo, prefer in ((self.combo_a, DARK), (self.combo_b, LIGHT)):
            cur = combo.get()
            combo.set_items(items, keep=True)
            if cur is None or cur >= len(items):
                for k in range(len(self.session.datasets) - 1, -1, -1):
                    if self.session.datasets[k].light_state == prefer:
                        combo.set(k)
                        break

    def select_datasets(self, dark, light):
        self.refresh_lists()
        for combo, ds in ((self.combo_a, dark), (self.combo_b, light)):
            try:
                combo.set(self.session.datasets.index(ds))
            except ValueError:
                pass
        if light.wavelength_nm:
            self.wavelength.set(light.wavelength_nm)
        if light.effective_power_w():
            self.power.set(light.effective_power_w())
        if light.area_cm2:
            self.area.set(light.area_cm2)
        self.do_compare()

    def _selected(self):
        return self.session.dataset(self.combo_a.get()), self.session.dataset(self.combo_b.get())

    def _load(self, is_a):
        folder = self.session.settings.get("data_dir", ".")
        path = filedialog.askopenfilename(parent=self, title="Olcum dosyasi sec",
                                          initialdir=folder,
                                          filetypes=[("CSV dosyalari", "*.csv"), ("Tum dosyalar", "*.*")])
        if not path:
            return
        try:
            ds = Dataset.from_csv(path)
        except Exception as exc:
            error(self, "Okuma hatasi", "{0}\n\n{1}".format(path, exc))
            return
        self.session.add_dataset(ds)
        (self.combo_a if is_a else self.combo_b).set(len(self.session.datasets) - 1)

    # ------------------------------------------------------------------
    def do_compare(self):
        a, b = self._selected()
        if a is None or b is None:
            warn(self, "Secim eksik", "Iki olcum de secilmelidir.")
            return
        if a is b:
            warn(self, "Ayni olcum", "A ve B ayni olcum; fark sifir cikar.")
        self.comparison = analysis.compare(a, b)
        c = self.comparison
        if not c.v:
            warn(self, "Ortak aralik yok", "Iki olcumun gerilim araliklari ortusmuyor.")
            return
        self._draw()
        self.session.log("Karsilastirildi: A = {0}, B = {1}, ortak aralik {2:g} ... {3:g} V".format(
            a.label, b.label, c.v[0], c.v[-1]))
        self.do_metrics()

    def _draw(self):
        c = self.comparison
        p = self.plot
        p.clear()
        if c is None or not c.v:
            return
        view = self.view.get()
        if view == VIEW_IV:
            p.set_labels("Gerilim (V)", "Akim (A)", "Karanlik / UV I-V karakteristigi")
            p.add_series("a", "A: " + c.dark_name, color="#1f77b4")
            p.set_data("a", c.v, c.i_dark)
            p.add_series("b", "B: " + c.light_name, color="#d62728")
            p.set_data("b", c.v, c.i_light)
            p.add_series("ph", "I_ph = B - A", color="#2ca02c", dash=(6, 3), width=1)
            p.set_data("ph", c.v, c.i_photo)
        elif view == VIEW_PHOTO:
            p.set_labels("Gerilim (V)", "Fotoakim (A)", "Fotoakim")
            p.add_series("ph", "I_ph = I_UV - I_karanlik", color="#2ca02c")
            p.set_data("ph", c.v, c.i_photo)
        elif view == VIEW_RATIO:
            p.set_labels("Gerilim (V)", "Oran", "Ac/kapa orani")
            p.add_series("r", "|I_UV / I_karanlik|", color="#9467bd")
            p.set_data("r", c.v, c.ratio)
        else:
            p.set_labels("Gerilim (V)", "Fark (A)", "Ham fark (B - A)")
            p.add_series("d", "B - A", color="#ff7f0e")
            p.set_data("d", c.v, c.i_photo)
        p.redraw()

    def do_metrics(self):
        c = self.comparison
        if c is None or not c.v:
            warn(self, "Once karsilastirin", "Karsilastirma yapilmadi.")
            return
        m = analysis.metrics_from_comparison(
            c, bias_v=self.bias.get(0.0),
            wavelength_nm=self.wavelength.get(0.0) or None,
            optical_power_w=self.power.get(0.0) or None,
            area_cm2=self.area.get(0.0) or None)
        self.report_head = [("A (karanlik)", c.dark_name), ("B (isikli)", c.light_name)]
        self.report_rows = m.as_table()
        self.table.set_rows(self.report_head + m.as_rows())
        for w in m.warnings:
            self.session.log("Uyari: " + w)

    def do_diode(self):
        a, b = self._selected()
        target = b if b is not None else a
        if target is None:
            warn(self, "Veri yok", "Once bir olcum secin.")
            return
        p = analysis.diode_parameters(target.v, target.i, v_min=self.fit_min.get(0.1),
                                      v_max=self.fit_max.get(0.5))
        rr = analysis.rectification_ratio(target.v, target.i, self.rect_bias.get(1.0))
        self.report_head = [("Analiz edilen olcum", target.label)]
        self.report_rows = [("Idealite faktoru n", p["ideality"], ""),
                            ("Doyma akimi I0", p["i0"], "A"),
                            ("Uydurma nokta sayisi", float(p["points"]), ""),
                            ("Dogrultma orani", rr, "")]
        rows = [(k, ("{0:.4g} {1}".format(v, u)).strip() if analysis.isfinite(v) else "-")
                for k, v, u in self.report_rows]
        rows[2] = (rows[2][0], str(p["points"]))
        self.table.set_rows(self.report_head + rows)

    # ------------------------------------------------------------------
    def _ask_path(self, title, suffix, ext, types):
        folder = self.session.settings.get("data_dir", ".")
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder)
            except OSError:
                folder = "."
        default = datetime.now().strftime("%Y%m%d_%H%M%S") + suffix
        return filedialog.asksaveasfilename(parent=self, title=title, initialdir=folder,
                                            initialfile=default, defaultextension=ext,
                                            filetypes=types)

    def export_difference(self):
        c = self.comparison
        if c is None or not c.v:
            warn(self, "Veri yok", "Once karsilastirma yapin.")
            return
        path = self._ask_path("Fark verisini kaydet", "_fotoakim_farki.csv", ".csv",
                              [("CSV dosyalari", "*.csv")])
        if path:
            self.write_difference(path)
            self.session.log("Fark verisi kaydedildi: {0}".format(path))

    def write_difference(self, path):
        c = self.comparison
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(u"# A (karanlik): {0}\n".format(c.dark_name))
            fh.write(u"# B (isikli)  : {0}\n".format(c.light_name))
            fh.write(u"# dalga boyu  : {0:g} nm, optik guc: {1:g} W, alan: {2:g} cm2\n".format(
                self.wavelength.get(0), self.power.get(0), self.area.get(0)))
            fh.write(u"voltage_V,I_dark_A,I_light_A,I_photo_A,on_off_ratio\n")
            for k in range(len(c.v)):
                fh.write(u"{0},{1},{2},{3},{4}\n".format(
                    _num(c.v[k]), _num(c.i_dark[k]), _num(c.i_light[k]),
                    _num(c.i_photo[k]), _num(c.ratio[k])))
        return path

    def export_report(self):
        if not self.report_rows:
            warn(self, "Veri yok", "Once parametreleri hesaplayin.")
            return
        path = self._ask_path("Raporu kaydet", "_rapor.txt", ".txt", [("Metin dosyalari", "*.txt")])
        if not path:
            return
        self.write_report(path)
        self.session.log("Rapor kaydedildi: {0}".format(path))
        info(self, "Rapor kaydedildi",
             "{0}\n\nExcel'de acmak icin: Veri > Metinden, ayirici = Sekme (Tab).".format(path))

    def write_report(self, path):
        """Sekmeyle ayrilmis rapor: Parametre / Deger (saf sayi) / Birim."""
        with io.open(path, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(u"UV FOTODEDEKTOR OLCUM RAPORU\n")
            fh.write(u"Tarih\t{0}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            fh.write(u"Cihaz\tKeithley 2636B + Adapter Box C 10\n")
            for k, v in self.report_head:
                fh.write(u"{0}\t{1}\n".format(k, v))
            fh.write(u"\nParametre\tDeger\tBirim\n")
            for k, v, u in self.report_rows:
                fh.write(u"{0}\t{1}\t{2}\n".format(k, _num(v), u))
        return path

    def export_eps(self):
        path = self._ask_path("Grafigi kaydet", "_grafik.eps", ".eps",
                              [("Encapsulated PostScript", "*.eps")])
        if path:
            self.plot.save_postscript(path)
            self.session.log("Grafik kaydedildi: {0}".format(path))
