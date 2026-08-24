"""Karsilastirma ve analiz sekmesi.

Iki olcum (tipik olarak karanlik ve UV altinda) ortak gerilim ekseninde
karsilastirilir, fotoakim farki cikarilir ve fotodedektor basarim
parametreleri (R, EQE, D*, NEP, ac/kapa orani) hesaplanir.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import numpy as np

from .. import analysis
from ..dataset import DARK, LIGHT, Dataset
from ..qtcompat import QtCore, QtWidgets
from .plotting import LOG_ABS, MeasurementPlot, YScaleSelector
from .session import Session
from .widgets import FormBuilder, KeyValueTable, group, message

VIEW_IV = "iv"
VIEW_PHOTO = "photo"
VIEW_RATIO = "ratio"
VIEW_DIFF = "diff"


class AnalysisTab(QtWidgets.QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.comparison: Optional[analysis.Comparison] = None
        self._ds_a: Optional[Dataset] = None
        self._ds_b: Optional[Dataset] = None

        # ---------------- olcum secimi ----------------
        f1 = FormBuilder()
        self.combo_dark = QtWidgets.QComboBox()
        self.combo_light = QtWidgets.QComboBox()
        f1.add("A – Karanlik (referans)", self.combo_dark)
        f1.add("B – UV altinda", self.combo_light)

        row = QtWidgets.QHBoxLayout()
        self.btn_load_a = QtWidgets.QPushButton("A'yi dosyadan yukle")
        self.btn_load_b = QtWidgets.QPushButton("B'yi dosyadan yukle")
        row.addWidget(self.btn_load_a)
        row.addWidget(self.btn_load_b)
        rw = QtWidgets.QWidget()
        rw.setLayout(row)
        f1.add_row(rw)

        self.btn_compare = QtWidgets.QPushButton("⇄  Karsilastir ve farki cikar")
        self.btn_compare.setStyleSheet("font-weight:700; padding:6px;")
        f1.add_row(self.btn_compare)
        select_box = group("1) Karsilastirilacak olcumler", f1.widget)

        # ---------------- analiz parametreleri ----------------
        f2 = FormBuilder()
        self.view = f2.combo("Gosterim",
                             [("I–V egrileri (A ve B)", VIEW_IV),
                              ("Fotoakim I_ph = B − A", VIEW_PHOTO),
                              ("Ac/kapa orani |I_B/I_A|", VIEW_RATIO),
                              ("Ham fark (B − A)", VIEW_DIFF)], VIEW_IV)
        self.bias = f2.sci("Analiz bias'i (V)", 1.0,
                           "Parametrelerin hesaplanacagi gerilim noktasi.")
        self.wavelength = f2.sci("Dalga boyu (nm)", session.settings.get("wavelength_nm", 365.0))
        self.power = f2.sci("Optik guc (W)", session.settings.get("optical_power_w", 2e-6))
        self.area = f2.sci("Aktif alan (cm²)", session.settings.get("area_cm2", 0.04))
        self.btn_metrics = QtWidgets.QPushButton("Σ  Parametreleri hesapla")
        f2.add_row(self.btn_metrics)
        param_box = group("2) Fotodedektor parametreleri", f2.widget)

        # ---------------- diyot analizi ----------------
        f3 = FormBuilder()
        self.fit_min = f3.sci("Uydurma alt sinir (V)", 0.1)
        self.fit_max = f3.sci("Uydurma ust sinir (V)", 0.5)
        self.rect_bias = f3.sci("Dogrultma orani bias'i (V)", 1.0)
        self.btn_diode = QtWidgets.QPushButton("Diyot parametrelerini hesapla")
        f3.add_row(self.btn_diode)
        diode_box = group("3) Diyot analizi (opsiyonel)", f3.widget)

        # ---------------- sonuc ----------------
        self.table = KeyValueTable()
        out_row = QtWidgets.QHBoxLayout()
        self.btn_export = QtWidgets.QPushButton("Farki CSV kaydet")
        self.btn_report = QtWidgets.QPushButton("Rapor kaydet (.txt)")
        self.btn_png = QtWidgets.QPushButton("Grafigi PNG kaydet")
        for b in (self.btn_export, self.btn_report, self.btn_png):
            out_row.addWidget(b)
        ow = QtWidgets.QWidget()
        ow.setLayout(out_row)

        left = QtWidgets.QVBoxLayout()
        left.addWidget(select_box)
        left.addWidget(param_box)
        left.addWidget(diode_box)
        left.addWidget(ow)
        left.addStretch(1)
        left_w = QtWidgets.QWidget()
        left_w.setLayout(left)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_w)
        scroll.setMinimumWidth(380)

        self.plot = MeasurementPlot("Gerilim (V)", "Akim (A)")
        plot_w = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(plot_w)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(YScaleSelector(self.plot, default=LOG_ABS))
        pv.addWidget(self.plot, 1)

        table_w = QtWidgets.QWidget()
        tv = QtWidgets.QVBoxLayout(table_w)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addWidget(QtWidgets.QLabel("Sonuclar:"))
        tv.addWidget(self.table, 1)

        right_split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        right_split.addWidget(plot_w)
        right_split.addWidget(table_w)
        right_split.setStretchFactor(0, 3)
        right_split.setStretchFactor(1, 2)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(scroll)
        splitter.addWidget(right_split)
        splitter.setStretchFactor(1, 1)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(splitter)

        # ---------------- sinyaller ----------------
        session.datasets_changed.connect(self.refresh_lists)
        self.btn_compare.clicked.connect(self.do_compare)
        self.btn_metrics.clicked.connect(self.do_metrics)
        self.btn_diode.clicked.connect(self.do_diode)
        self.btn_load_a.clicked.connect(lambda: self._load_file(True))
        self.btn_load_b.clicked.connect(lambda: self._load_file(False))
        self.view.currentIndexChanged.connect(self._draw)
        self.btn_export.clicked.connect(self.export_difference)
        self.btn_report.clicked.connect(self.export_report)
        self.btn_png.clicked.connect(self.export_png)
        self.refresh_lists()

    # ------------------------------------------------------------------
    def refresh_lists(self) -> None:
        for combo, prefer in ((self.combo_dark, DARK), (self.combo_light, LIGHT)):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for idx, ds in enumerate(self.session.datasets):
                combo.addItem(f"{idx + 1}. {ds.label} [{len(ds)} nk]", idx)
            combo.blockSignals(False)
            if current is not None:
                pos = combo.findData(current)
                if pos >= 0:
                    combo.setCurrentIndex(pos)
                    continue
            # varsayilan: turune uygun en son olcumu sec
            for idx in range(len(self.session.datasets) - 1, -1, -1):
                if self.session.datasets[idx].light_state == prefer:
                    pos = combo.findData(idx)
                    if pos >= 0:
                        combo.setCurrentIndex(pos)
                    break

    def select_datasets(self, dark: Dataset, light: Dataset) -> None:
        """Disaridan (ikili olcum sonrasi) secimi ayarlar ve karsilastirir."""
        self.refresh_lists()
        for combo, ds in ((self.combo_dark, dark), (self.combo_light, light)):
            try:
                idx = self.session.datasets.index(ds)
            except ValueError:
                continue
            pos = combo.findData(idx)
            if pos >= 0:
                combo.setCurrentIndex(pos)
        if light.wavelength_nm:
            self.wavelength.setValue(light.wavelength_nm)
        if light.effective_power_w():
            self.power.setValue(light.effective_power_w())
        if light.area_cm2:
            self.area.setValue(light.area_cm2)
        self.do_compare()

    def _selected(self):
        a = self.session.dataset(self.combo_dark.currentData()
                                 if self.combo_dark.currentData() is not None else -1)
        b = self.session.dataset(self.combo_light.currentData()
                                 if self.combo_light.currentData() is not None else -1)
        return a or self._ds_a, b or self._ds_b

    def _load_file(self, is_a: bool) -> None:
        directory = self.session.settings.get("data_dir", ".")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Olcum dosyasi sec", directory, "CSV dosyalari (*.csv);;Tum dosyalar (*)")
        if not path:
            return
        try:
            ds = Dataset.from_csv(path)
        except Exception as exc:
            message(self, "Okuma hatasi", f"{path}\n\n{exc}", "error")
            return
        self.session.add_dataset(ds)
        idx = len(self.session.datasets) - 1
        combo = self.combo_dark if is_a else self.combo_light
        pos = combo.findData(idx)
        if pos >= 0:
            combo.setCurrentIndex(pos)

    # ------------------------------------------------------------------
    def do_compare(self) -> None:
        a, b = self._selected()
        if a is None or b is None:
            message(self, "Secim eksik", "Iki olcum de secilmelidir.", "warn")
            return
        if a is b:
            message(self, "Ayni olcum", "A ve B ayni olcum; fark sifir cikar.", "warn")
        self._ds_a, self._ds_b = a, b
        self.comparison = analysis.compare(a, b)
        if self.comparison.v.size == 0:
            message(self, "Ortak aralik yok",
                    "Iki olcumun gerilim araliklari ortusmuyor.", "warn")
            return
        self._draw()
        self.session.log(
            f"Karsilastirildi: A = {a.label}, B = {b.label}, "
            f"ortak aralik {self.comparison.v.min():g} … {self.comparison.v.max():g} V")
        self.do_metrics()

    def _draw(self) -> None:
        c = self.comparison
        self.plot.clear()
        if c is None or c.v.size == 0:
            return
        view = self.view.currentData()
        if view == VIEW_IV:
            self.plot.set_labels("Gerilim (V)", "Akim (A)", "Karanlik / UV I–V karakteristigi")
            self.plot.add_series("a", f"A: {c.dark_name}", color="#1f77b4")
            self.plot.set_data("a", c.v, c.i_dark)
            self.plot.add_series("b", f"B: {c.light_name}", color="#d62728")
            self.plot.set_data("b", c.v, c.i_light)
            self.plot.add_series("ph", "I_ph = B − A", color="#2ca02c", style="--")
            self.plot.set_data("ph", c.v, c.i_photo)
        elif view == VIEW_PHOTO:
            self.plot.set_labels("Gerilim (V)", "Fotoakim (A)", "Fotoakim")
            self.plot.add_series("ph", "I_ph = I_UV − I_karanlik", color="#2ca02c")
            self.plot.set_data("ph", c.v, c.i_photo)
        elif view == VIEW_RATIO:
            self.plot.set_labels("Gerilim (V)", "Oran", "Ac/kapa orani")
            self.plot.add_series("r", "|I_UV / I_karanlik|", color="#9467bd")
            self.plot.set_data("r", c.v, c.ratio)
        else:
            self.plot.set_labels("Gerilim (V)", "Fark (A)", "Ham fark (B − A)")
            self.plot.add_series("d", "B − A", color="#ff7f0e")
            self.plot.set_data("d", c.v, c.i_light - c.i_dark)
        self.plot.redraw()

    # ------------------------------------------------------------------
    def do_metrics(self) -> None:
        if self.comparison is None or self.comparison.v.size == 0:
            message(self, "Once karsilastirin", "Karsilastirma yapilmadi.", "warn")
            return
        m = analysis.metrics_from_comparison(
            self.comparison,
            bias_v=self.bias.value(0.0),
            wavelength_nm=self.wavelength.value(0.0) or None,
            optical_power_w=self.power.value(0.0) or None,
            area_cm2=self.area.value(0.0) or None,
        )
        rows = [("A (karanlik)", self.comparison.dark_name),
                ("B (isikli)", self.comparison.light_name)] + m.as_rows()
        self.table.set_rows(rows)
        for w in m.warnings:
            self.session.log("Uyari: " + w)

    def do_diode(self) -> None:
        a, b = self._selected()
        target = b if b is not None else a
        if target is None:
            message(self, "Veri yok", "Once bir olcum secin.", "warn")
            return
        p = analysis.diode_parameters(target.v, target.i,
                                      v_min=self.fit_min.value(0.1),
                                      v_max=self.fit_max.value(0.5))
        rr = analysis.rectification_ratio(target.v, target.i, self.rect_bias.value(1.0))
        rows = [
            ("Analiz edilen olcum", target.label),
            ("Idealite faktoru n", f"{p['ideality']:.4g}" if np.isfinite(p["ideality"]) else "-"),
            ("Doyma akimi I0", f"{p['i0']:.4g} A" if np.isfinite(p["i0"]) else "-"),
            ("Uydurma nokta sayisi", str(p["points"])),
            ("Dogrultma orani", f"{rr:.4g}" if np.isfinite(rr) else "-"),
        ]
        self.table.set_rows(rows)

    # ------------------------------------------------------------------
    def export_difference(self) -> None:
        if self.comparison is None or self.comparison.v.size == 0:
            message(self, "Veri yok", "Once karsilastirma yapin.", "warn")
            return
        directory = self.session.settings.get("data_dir", ".")
        os.makedirs(directory, exist_ok=True)
        default = os.path.join(
            directory, datetime.now().strftime("%Y%m%d_%H%M%S") + "_fotoakim_farki.csv")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Fark verisini kaydet", default, "CSV dosyalari (*.csv)")
        if not path:
            return
        c = self.comparison
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(f"# A (karanlik): {c.dark_name}\n")
            fh.write(f"# B (isikli)  : {c.light_name}\n")
            fh.write(f"# dalga boyu  : {self.wavelength.value(0):g} nm, "
                     f"optik guc: {self.power.value(0):g} W, "
                     f"alan: {self.area.value(0):g} cm2\n")
            fh.write("voltage_V,I_dark_A,I_light_A,I_photo_A,on_off_ratio\n")
            for k in range(c.v.size):
                fh.write(f"{c.v[k]:.10g},{c.i_dark[k]:.10g},{c.i_light[k]:.10g},"
                         f"{c.i_photo[k]:.10g},{c.ratio[k]:.10g}\n")
        self.session.log(f"Fark verisi kaydedildi: {path}")

    def export_report(self) -> None:
        if self.table.rowCount() == 0:
            message(self, "Veri yok", "Once parametreleri hesaplayin.", "warn")
            return
        directory = self.session.settings.get("data_dir", ".")
        os.makedirs(directory, exist_ok=True)
        default = os.path.join(
            directory, datetime.now().strftime("%Y%m%d_%H%M%S") + "_rapor.txt")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Raporu kaydet", default, "Metin dosyalari (*.txt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("UV FOTODEDEKTOR OLCUM RAPORU\n")
            fh.write(f"Tarih: {datetime.now().isoformat(timespec='seconds')}\n")
            fh.write("Cihaz: Keithley 2636 + Adapter Box C 10\n")
            fh.write("=" * 56 + "\n")
            fh.write(self.table.to_text() + "\n")
        self.session.log(f"Rapor kaydedildi: {path}")

    def export_png(self) -> None:
        directory = self.session.settings.get("data_dir", ".")
        os.makedirs(directory, exist_ok=True)
        default = os.path.join(
            directory, datetime.now().strftime("%Y%m%d_%H%M%S") + "_grafik.png")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Grafigi kaydet", default, "PNG (*.png);;PDF (*.pdf)")
        if path:
            self.plot.save_figure(path)
            self.session.log(f"Grafik kaydedildi: {path}")
