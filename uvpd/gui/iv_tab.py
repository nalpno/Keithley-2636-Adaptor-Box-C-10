"""I-V taramasi sekmesi (ana olcum ekrani)."""

from __future__ import annotations

import os
from typing import Optional

from ..dataset import DARK, LIGHT, Dataset, suggest_filename
from ..measurement import SampleInfo, SweepConfig, run_sweep
from ..qtcompat import QtCore, QtWidgets, Signal
from .plotting import LOG_ABS, MeasurementPlot, YScaleSelector
from .session import Session
from .widgets import FormBuilder, group, message
from .workers import MeasurementWorker


class IVTab(QtWidgets.QWidget):
    """Gerilim (veya akim) taramasi yapar, egriyi canli cizer."""

    compare_requested = Signal(object, object)   # (karanlik Dataset, isik Dataset)

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.worker: Optional[MeasurementWorker] = None
        self._pending_dual = False
        self._dual_dark: Optional[Dataset] = None
        self._last_dataset: Optional[Dataset] = None
        s = session.settings
        sw = s.get("sweep", {})

        # ---------------- numune / isik ----------------
        f1 = FormBuilder()
        self.sample_name = f1.text("Numune adi", s.get("sample_name", "numune"))
        self.light_state = f1.combo("Isik durumu",
                                    [("Karanlik", DARK), ("UV altinda", LIGHT)], DARK,
                                    "Karanlik ve UV altinda alinan iki olcum daha sonra "
                                    "'Karsilastirma' sekmesinde farklanir.")
        self.wavelength = f1.sci("Dalga boyu (nm)", s.get("wavelength_nm", 365.0),
                                 "UV kaynaginin dalga boyu. EQE ve foton enerjisi "
                                 "hesabinda kullanilir.")
        self.power = f1.sci("Optik guc (W)", s.get("optical_power_w", 2e-6),
                            "Numune uzerine dusen toplam optik guc. "
                            "Duyarlilik (A/W), EQE ve D* icin gerekli.")
        self.area = f1.sci("Aktif alan (cm²)", s.get("area_cm2", 0.04),
                           "Isik goren aktif dedektor alani. D* hesabinda kullanilir.")
        self.notes = f1.text("Not", "")
        sample_box = group("Numune ve isik kaynagi", f1.widget)

        # ---------------- tarama ----------------
        f2 = FormBuilder()
        self.start = f2.sci("Baslangic", sw.get("start", -2.0))
        self.stop = f2.sci("Bitis", sw.get("stop", 2.0))
        self.points = f2.spin("Nokta sayisi", sw.get("points", 101), 2, 100000)
        self.step_label = QtWidgets.QLabel("—")
        f2.add("Adim", self.step_label)
        self.dual = f2.check("Cift yon (ileri + geri)", sw.get("dual", False),
                             "Histerezis incelemek icin taramayi geri de yapar.")
        self.repeat = f2.spin("Tekrar", sw.get("repeat", 1), 1, 100)
        self.settle = f2.sci("Adim bekleme (s)", sw.get("settle_time", 0.05),
                             "Her gerilim adiminda olcumden once beklenen sure. "
                             "Yavas numunelerde artirin.")
        self.autosave = f2.check("Bitince otomatik CSV kaydet", True)
        sweep_box = group("Tarama parametreleri", f2.widget)

        # ---------------- dugmeler ----------------
        self.btn_start = QtWidgets.QPushButton("▶  Taramayi baslat")
        self.btn_start.setStyleSheet("font-weight:700; padding:6px;")
        self.btn_dual = QtWidgets.QPushButton("◐  Ikili olcum (karanlik → UV)")
        self.btn_dual.setToolTip(
            "Once karanlik taramayi yapar, sonra UV kaynagini acmanizi ister, "
            "ardindan ayni taramayi UV altinda tekrarlar ve karsilastirir.")
        self.btn_stop = QtWidgets.QPushButton("■  Durdur")
        self.btn_stop.setEnabled(False)
        self.btn_save = QtWidgets.QPushButton("💾  CSV kaydet")
        self.btn_clear = QtWidgets.QPushButton("Grafigi temizle")

        btns = QtWidgets.QVBoxLayout()
        for b in (self.btn_start, self.btn_dual, self.btn_stop, self.btn_save, self.btn_clear):
            btns.addWidget(b)
        btn_w = QtWidgets.QWidget()
        btn_w.setLayout(btns)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setTextVisible(True)
        self.readout = QtWidgets.QLabel("V = —    I = —")
        self.readout.setStyleSheet("font-family:monospace; font-size:13px; font-weight:600;")

        left = QtWidgets.QVBoxLayout()
        left.addWidget(sample_box)
        left.addWidget(sweep_box)
        left.addWidget(btn_w)
        left.addWidget(self.progress)
        left.addWidget(self.readout)
        left.addStretch(1)
        left_w = QtWidgets.QWidget()
        left_w.setLayout(left)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_w)
        scroll.setMinimumWidth(330)

        self.plot = MeasurementPlot("Gerilim (V)", "Akim (A)")
        right = QtWidgets.QVBoxLayout()
        right.addWidget(YScaleSelector(self.plot, default=LOG_ABS))
        right.addWidget(self.plot, 1)
        right_w = QtWidgets.QWidget()
        right_w.setLayout(right)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(scroll)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(splitter)

        # ---------------- sinyaller ----------------
        self.btn_start.clicked.connect(lambda: self.start_sweep(dual=False))
        self.btn_dual.clicked.connect(lambda: self.start_sweep(dual=True))
        self.btn_stop.clicked.connect(self.stop_sweep)
        self.btn_save.clicked.connect(self.save_last)
        self.btn_clear.clicked.connect(self.plot.clear)
        for w in (self.start, self.stop):
            w.editingFinished.connect(self._update_step)
        self.points.valueChanged.connect(self._update_step)
        self.light_state.currentIndexChanged.connect(self._update_light_fields)
        self._update_step()
        self._update_light_fields()

    # ------------------------------------------------------------------
    def _update_step(self, *_):
        pts = max(2, self.points.value())
        step = (self.stop.value() - self.start.value()) / (pts - 1)
        unit = "V" if self.session.settings.get("source_func") == "voltage" else "A"
        self.step_label.setText(f"{step:.6g} {unit}")

    def _update_light_fields(self, *_):
        is_light = self.light_state.currentData() == LIGHT
        for w in (self.wavelength, self.power):
            w.setEnabled(is_light)

    # ------------------------------------------------------------------
    def sample_info(self, light_state: Optional[str] = None) -> SampleInfo:
        state = light_state or self.light_state.currentData()
        return SampleInfo(
            name=self.sample_name.text().strip() or "numune",
            light_state=state,
            wavelength_nm=self.wavelength.value(365.0),
            optical_power_w=self.power.value(0.0) or None,
            area_cm2=self.area.value(0.0) or None,
            notes=self.notes.text().strip(),
        )

    def sweep_config(self) -> SweepConfig:
        return SweepConfig(
            start=self.start.value(),
            stop=self.stop.value(),
            points=int(self.points.value()),
            dual=self.dual.isChecked(),
            repeat=int(self.repeat.value()),
            settle_time=max(0.0, self.settle.value(0.05)),
        )

    def _validate(self) -> bool:
        s = self.session.settings
        if not self.session.connected:
            message(self, "Cihaz bagli degil",
                    "Once 'Baglanti' sekmesinden cihaza baglanin veya simulasyon "
                    "modunu acin.", "warn")
            return False
        if not s.get("interlock_confirmed"):
            message(self, "Interlock onayi yok",
                    "Baglanti sekmesinde INTERLOCK / kapak onayini isaretlemeden "
                    "olcum baslatilamaz.", "warn")
            return False
        limit_v, limit_i = 60.0, 1.0
        if s.get("source_func") == "voltage":
            if max(abs(self.start.value()), abs(self.stop.value())) > limit_v:
                message(self, "Sinir asimi",
                        f"Adapter Box C 10 icin U_max = {limit_v:g} V DC.", "error")
                return False
            if abs(s.get("compliance", 1e-3)) > limit_i:
                message(self, "Sinir asimi",
                        f"Akim limiti {limit_i:g} A DC degerini asamaz.", "error")
                return False
        else:
            if max(abs(self.start.value()), abs(self.stop.value())) > limit_i:
                message(self, "Sinir asimi",
                        f"Adapter Box C 10 icin I_max = {limit_i:g} A DC.", "error")
                return False
            if abs(s.get("compliance", 1.0)) > limit_v:
                message(self, "Sinir asimi",
                        f"Gerilim limiti {limit_v:g} V DC degerini asamaz.", "error")
                return False
        return True

    # ------------------------------------------------------------------
    def start_sweep(self, dual: bool = False, light_state: Optional[str] = None) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if not self._validate():
            return

        self._pending_dual = dual
        if dual and light_state is None:
            light_state = DARK
            self._dual_dark = None

        sample = self.sample_info(light_state)
        cfg = self.sweep_config()
        smu = self.session.smu_config()
        inst = self.session.instrument

        # Simulasyon modunda UV kaynagini otomatik ac/kapa
        if self.session.simulated and hasattr(inst, "set_uv"):
            inst.set_uv(sample.light_state == LIGHT)

        self._persist_settings()

        key = f"{sample.name}-{sample.light_state}-{len(self.plot.series_keys())}"
        self._active_key = key
        label = ("Karanlik" if sample.light_state == DARK
                 else f"UV {sample.wavelength_nm:g} nm")
        self.plot.add_series(key, f"{sample.name} – {label}", marker=".")

        total = len(cfg.levels()) * max(1, cfg.repeat)
        self.progress.setRange(0, total)
        self.progress.setValue(0)

        def job(on_point, should_stop, log):
            return run_sweep(inst, smu, cfg, sample,
                             on_point=on_point, should_stop=should_stop, log=log)

        self.worker = MeasurementWorker(job, self)
        self.worker.point.connect(self._on_point)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self.worker.message.connect(self.session.log)
        self._set_running(True)
        self.worker.start()

    def stop_sweep(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.session.log("Durdurma istegi gonderildi...")

    # ------------------------------------------------------------------
    def _on_point(self, idx: int, t: float, v: float, i: float) -> None:
        self.plot.append(self._active_key, v, i)
        self.progress.setValue(idx + 1)
        self.readout.setText(f"V = {v:>12.6g} V    I = {i:>12.6g} A")

    def _on_completed(self, ds: Dataset) -> None:
        self._set_running(False)
        self._last_dataset = ds
        if len(ds) == 0:
            self.session.log("Olcum bos dondu.")
            return
        self.session.add_dataset(ds)
        if self.autosave.isChecked():
            self._autosave(ds)

        if self._pending_dual:
            if ds.light_state == DARK:
                self._dual_dark = ds
                self._ask_uv_on()
            else:
                self._pending_dual = False
                if self._dual_dark is not None:
                    self.compare_requested.emit(self._dual_dark, ds)
                    self._dual_dark = None

    def _ask_uv_on(self) -> None:
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("UV kaynagini acin")
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setText(
            f"Karanlik tarama tamamlandi.\n\n"
            f"Simdi {self.wavelength.value(365):g} nm UV kaynagini acin ve numunenin "
            f"kararli hale gelmesini bekleyin.\n\nHazir oldugunuzda 'Devam' tusuna basin.")
        cont = box.addButton("Devam (UV taramasi)", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("Iptal", QtWidgets.QMessageBox.RejectRole)
        box.exec_() if hasattr(box, "exec_") else box.exec()
        if box.clickedButton() is cont:
            self.start_sweep(dual=True, light_state=LIGHT)
        else:
            self._pending_dual = False
            self._dual_dark = None

    def _on_failed(self, text: str) -> None:
        self._set_running(False)
        self._pending_dual = False
        self.session.log("HATA: " + text.splitlines()[0])
        message(self, "Olcum hatasi", text, "error")

    def _set_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_dual.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.session.set_busy(running)

    # ------------------------------------------------------------------
    def _persist_settings(self) -> None:
        s = self.session.settings
        s["sample_name"] = self.sample_name.text().strip()
        s["wavelength_nm"] = self.wavelength.value(365.0)
        s["optical_power_w"] = self.power.value(0.0)
        s["area_cm2"] = self.area.value(0.0)
        s["sweep"] = {"start": self.start.value(), "stop": self.stop.value(),
                      "points": int(self.points.value()), "dual": self.dual.isChecked(),
                      "repeat": int(self.repeat.value()),
                      "settle_time": self.settle.value(0.05)}
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
            message(self, "Veri yok", "Once bir tarama yapin.", "warn")
            return
        directory = self.session.settings.get("data_dir", ".")
        os.makedirs(directory, exist_ok=True)
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Olcumu kaydet", suggest_filename(self._last_dataset, directory),
            "CSV dosyalari (*.csv)")
        if path:
            self._last_dataset.to_csv(path)
            self.session.log(f"Kaydedildi: {path}")
