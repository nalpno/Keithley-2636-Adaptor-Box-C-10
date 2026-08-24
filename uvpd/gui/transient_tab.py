"""Zaman tepkisi (foto-anahtarlama) sekmesi.

Sabit bias altinda akim zamana karsi kaydedilir; UV kaynagi elle veya
(shutter digital I/O'ya bagliysa) otomatik cevrimle ac/kapa edilir.
Bitiminde yukselme/dusme sureleri ve ac/kapa orani hesaplanir.
"""

from __future__ import annotations

import math
import os
from typing import List, Optional

from .. import analysis
from ..dataset import LIGHT, Dataset, suggest_filename
from ..measurement import SampleInfo, TransientConfig, run_transient
from ..qtcompat import QtCore, QtWidgets
from .plotting import MeasurementPlot, YScaleSelector
from .session import Session
from .widgets import FormBuilder, KeyValueTable, group, message
from .workers import MeasurementWorker


class TransientTab(QtWidgets.QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.worker: Optional[MeasurementWorker] = None
        self._events: List = []
        self._last_t = 0.0
        self._last_dataset: Optional[Dataset] = None
        s = session.settings
        tr = s.get("transient", {})

        # ---------------- parametreler ----------------
        f1 = FormBuilder()
        self.sample_name = f1.text("Numune adi", s.get("sample_name", "numune"))
        self.bias = f1.sci("Bias (V veya A)", tr.get("bias", 1.0),
                           "Sabit tutulacak kaynak seviyesi. Fotodedektorlerde "
                           "genellikle kucuk ters/ileri bias kullanilir.")
        self.duration = f1.sci("Toplam sure (s)", tr.get("duration", 60.0))
        self.interval = f1.sci("Ornekleme araligi (s)", tr.get("interval", 0.1),
                               "Hizli tepki icin NPLC'yi de kucultun (0.01–0.1).")
        self.wavelength = f1.sci("Dalga boyu (nm)", s.get("wavelength_nm", 365.0))
        self.power = f1.sci("Optik guc (W)", s.get("optical_power_w", 2e-6))
        self.area = f1.sci("Aktif alan (cm²)", s.get("area_cm2", 0.04))
        self.autosave = f1.check("Bitince otomatik CSV kaydet", True)
        param_box = group("Olcum parametreleri", f1.widget)

        # ---------------- otomatik cevrim ----------------
        f2 = FormBuilder()
        self.cycle_enabled = f2.check(
            "Otomatik UV cevrimi (shutter digital I/O)", False,
            "Sadece UV kaynagi/shutter Keithley'in digital I/O hattina bagliysa "
            "kullanin. Aksi halde asagidaki elle isaretleme dugmelerini kullanin.")
        self.digio_line = f2.spin("Digital I/O hatti", 1, 1, 14)
        self.cycle_delay = f2.sci("Ilk bekleme (s)", 5.0)
        self.cycle_on = f2.sci("UV acik (s)", 10.0)
        self.cycle_off = f2.sci("UV kapali (s)", 10.0)
        cycle_box = group("Otomatik cevrim (opsiyonel)", f2.widget)

        # ---------------- dugmeler ----------------
        self.btn_start = QtWidgets.QPushButton("▶  Kaydi baslat")
        self.btn_start.setStyleSheet("font-weight:700; padding:6px;")
        self.btn_stop = QtWidgets.QPushButton("■  Durdur")
        self.btn_stop.setEnabled(False)
        self.btn_uv_on = QtWidgets.QPushButton("☀  UV ACIK olarak isaretle")
        self.btn_uv_off = QtWidgets.QPushButton("🌑  UV KAPALI olarak isaretle")
        self.btn_uv_on.setEnabled(False)
        self.btn_uv_off.setEnabled(False)
        self.btn_save = QtWidgets.QPushButton("💾  CSV kaydet")

        btns = QtWidgets.QVBoxLayout()
        for b in (self.btn_start, self.btn_stop, self.btn_uv_on,
                  self.btn_uv_off, self.btn_save):
            btns.addWidget(b)
        btn_w = QtWidgets.QWidget()
        btn_w.setLayout(btns)

        self.readout = QtWidgets.QLabel("t = —    I = —")
        self.readout.setStyleSheet("font-family:monospace; font-size:13px; font-weight:600;")
        self.metrics = KeyValueTable()

        left = QtWidgets.QVBoxLayout()
        left.addWidget(param_box)
        left.addWidget(cycle_box)
        left.addWidget(btn_w)
        left.addWidget(self.readout)
        left.addStretch(1)
        left_w = QtWidgets.QWidget()
        left_w.setLayout(left)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_w)
        scroll.setMinimumWidth(330)

        self.plot = MeasurementPlot("Zaman (s)", "Akim (A)")
        plot_w = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(plot_w)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(YScaleSelector(self.plot))
        pv.addWidget(self.plot, 1)

        table_w = QtWidgets.QWidget()
        tv = QtWidgets.QVBoxLayout(table_w)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addWidget(QtWidgets.QLabel("Tepki parametreleri:"))
        tv.addWidget(self.metrics, 1)

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
        self.btn_start.clicked.connect(self.start)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_uv_on.clicked.connect(lambda: self._mark(1))
        self.btn_uv_off.clicked.connect(lambda: self._mark(0))
        self.btn_save.clicked.connect(self.save_last)
        self.cycle_enabled.toggled.connect(self._on_cycle_toggle)
        self._on_cycle_toggle(False)

    # ------------------------------------------------------------------
    def _on_cycle_toggle(self, on: bool) -> None:
        for w in (self.digio_line, self.cycle_delay, self.cycle_on, self.cycle_off):
            w.setEnabled(on)

    def _mark(self, state: int) -> None:
        """Elle UV ac/kapa isaretlemesi (olcum zaman ekseninde)."""
        self._events.append((self._last_t, state))
        self.session.log(f"Isaret: UV {'ACIK' if state else 'KAPALI'} @ t = {self._last_t:.2f} s")
        inst = self.session.instrument
        if self.session.simulated and hasattr(inst, "set_uv"):
            inst.set_uv(bool(state))
        self.plot.set_spans(self._spans_from_events())

    def _spans_from_events(self):
        spans, start = [], None
        for t, st in self._events:
            if st == 1 and start is None:
                start = t
            elif st == 0 and start is not None:
                spans.append((start, t))
                start = None
        if start is not None:
            spans.append((start, max(self._last_t, start)))
        return spans

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.session.connected:
            message(self, "Cihaz bagli degil", "Once cihaza baglanin.", "warn")
            return
        if not self.session.settings.get("interlock_confirmed"):
            message(self, "Interlock onayi yok",
                    "Baglanti sekmesinde INTERLOCK onayini isaretleyin.", "warn")
            return

        inst = self.session.instrument
        smu = self.session.smu_config()
        cfg = TransientConfig(
            bias=self.bias.value(1.0),
            duration=max(1.0, self.duration.value(60.0)),
            interval=max(0.005, self.interval.value(0.1)),
            cycle_enabled=self.cycle_enabled.isChecked(),
            cycle_delay=self.cycle_delay.value(5.0),
            cycle_on=self.cycle_on.value(10.0),
            cycle_off=self.cycle_off.value(10.0),
        )
        sample = SampleInfo(
            name=self.sample_name.text().strip() or "numune",
            light_state=LIGHT,
            wavelength_nm=self.wavelength.value(365.0),
            optical_power_w=self.power.value(0.0) or None,
            area_cm2=self.area.value(0.0) or None,
        )

        self._events = []
        self._last_t = 0.0
        self.plot.clear()
        self.plot.add_series("i", f"{sample.name} @ {cfg.bias:g}", marker="")
        self.metrics.set_rows([])

        line = int(self.digio_line.value())
        simulated = self.session.simulated

        def light_control(on: bool) -> None:
            if simulated and hasattr(inst, "set_uv"):
                inst.set_uv(on)
            else:
                inst.write(f"digio.writebit({line}, {1 if on else 0})")

        def job(on_point, should_stop, log):
            return run_transient(inst, smu, cfg, sample,
                                 on_point=on_point, should_stop=should_stop, log=log,
                                 light_events=self._events,
                                 light_control=light_control if cfg.cycle_enabled else None)

        self.worker = MeasurementWorker(job, self)
        self.worker.point.connect(self._on_point)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self.worker.message.connect(self.session.log)
        self._set_running(True)
        self._persist_settings()
        self.worker.start()

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()

    # ------------------------------------------------------------------
    def _on_point(self, idx: int, t: float, v: float, i: float) -> None:
        self._last_t = t
        self.plot.append("i", t, i)
        self.readout.setText(f"t = {t:>8.2f} s    I = {i:>12.6g} A    V = {v:.4g} V")

    def _on_completed(self, ds: Dataset) -> None:
        self._set_running(False)
        self._last_dataset = ds
        if len(ds) == 0:
            return
        self.session.add_dataset(ds)
        self.plot.set_spans(analysis.light_spans(ds))
        m = analysis.transient_metrics(ds.t, ds.i)
        rows = m.as_rows()
        power = ds.effective_power_w()
        if power and math.isfinite(m.i_on):
            det = analysis.detector_metrics(
                i_dark=m.i_off, i_light=m.i_on,
                wavelength_nm=ds.wavelength_nm, optical_power_w=power,
                area_cm2=ds.area_cm2, bias_v=ds.settings.get("transient", {}).get("bias", 0.0))
            rows = rows + [("—", "—")] + det.as_rows()[8:]
        self.metrics.set_rows(rows)
        for w in m.warnings:
            self.session.log("Uyari: " + w)
        if self.autosave.isChecked():
            self._autosave(ds)

    def _on_failed(self, text: str) -> None:
        self._set_running(False)
        self.session.log("HATA: " + text.splitlines()[0])
        message(self, "Olcum hatasi", text, "error")

    def _set_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        manual = running and not self.cycle_enabled.isChecked()
        self.btn_uv_on.setEnabled(manual)
        self.btn_uv_off.setEnabled(manual)
        self.session.set_busy(running)

    # ------------------------------------------------------------------
    def _persist_settings(self) -> None:
        s = self.session.settings
        s["transient"] = {"bias": self.bias.value(1.0),
                          "duration": self.duration.value(60.0),
                          "interval": self.interval.value(0.1)}
        self.session.save()

    def _autosave(self, ds: Dataset) -> None:
        directory = self.session.settings.get("data_dir", ".")
        try:
            os.makedirs(directory, exist_ok=True)
            path = ds.to_csv(suggest_filename(ds, directory))
            self.session.log(f"Kaydedildi: {path}")
        except OSError as exc:
            self.session.log(f"Otomatik kayit basarisiz: {exc}")

    def save_last(self) -> None:
        if self._last_dataset is None or len(self._last_dataset) == 0:
            message(self, "Veri yok", "Once bir kayit alin.", "warn")
            return
        directory = self.session.settings.get("data_dir", ".")
        os.makedirs(directory, exist_ok=True)
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Kaydi kaydet", suggest_filename(self._last_dataset, directory),
            "CSV dosyalari (*.csv)")
        if path:
            self._last_dataset.to_csv(path)
            self.session.log(f"Kaydedildi: {path}")
