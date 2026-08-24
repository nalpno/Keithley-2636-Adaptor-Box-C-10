"""Ana pencere: sekmeler, olcum listesi ve gunluk paneli."""

from __future__ import annotations

import os
from datetime import datetime

from .. import __version__
from ..dataset import Dataset, suggest_filename
from ..qtcompat import QtCore, QtGui, QtWidgets
from .analysis_tab import AnalysisTab
from .connection_tab import ConnectionTab
from .iv_tab import IVTab
from .session import Session
from .transient_tab import TransientTab
from .widgets import message

APP_TITLE = "UV Fotodedektor Olcum Arayuzu — Keithley 2636 / Adapter Box C 10"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, simulate: bool = False, parent=None):
        super().__init__(parent)
        self.session = Session(self)
        if simulate:
            self.session.settings["simulate"] = True

        self.setWindowTitle(APP_TITLE)
        self.resize(1380, 860)

        # ---------------- sekmeler ----------------
        self.tabs = QtWidgets.QTabWidget()
        self.tab_conn = ConnectionTab(self.session)
        self.tab_iv = IVTab(self.session)
        self.tab_tr = TransientTab(self.session)
        self.tab_an = AnalysisTab(self.session)
        self.tabs.addTab(self.tab_conn, "1 · Baglanti ve Ayarlar")
        self.tabs.addTab(self.tab_iv, "2 · I–V Olcumu")
        self.tabs.addTab(self.tab_tr, "3 · Zaman Tepkisi")
        self.tabs.addTab(self.tab_an, "4 · Karsilastirma ve Analiz")
        self.setCentralWidget(self.tabs)

        # ---------------- olcum listesi ----------------
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        btns = QtWidgets.QHBoxLayout()
        self.btn_load = QtWidgets.QPushButton("Yukle")
        self.btn_save = QtWidgets.QPushButton("Kaydet")
        self.btn_del = QtWidgets.QPushButton("Sil")
        for b in (self.btn_load, self.btn_save, self.btn_del):
            btns.addWidget(b)
        holder = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(holder)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.addWidget(self.list_widget, 1)
        bw = QtWidgets.QWidget()
        bw.setLayout(btns)
        vl.addWidget(bw)

        dock = QtWidgets.QDockWidget("Oturumdaki olcumler", self)
        dock.setWidget(holder)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        self.dock_list = dock

        # ---------------- gunluk ----------------
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setStyleSheet("font-family:monospace; font-size:11px;")
        log_dock = QtWidgets.QDockWidget("Gunluk", self)
        log_dock.setWidget(self.log_view)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, log_dock)
        log_dock.resize(100, 140)
        self.dock_log = log_dock

        # ---------------- durum cubugu ----------------
        self.status_label = QtWidgets.QLabel("Bagli degil")
        self.statusBar().addPermanentWidget(self.status_label)
        self.statusBar().showMessage("Hazir")

        self._build_menu()

        # ---------------- sinyaller ----------------
        self.session.message.connect(self._append_log)
        self.session.status.connect(self.status_label.setText)
        self.session.datasets_changed.connect(self._refresh_list)
        self.session.busy_changed.connect(self._on_busy)
        self.tab_iv.compare_requested.connect(self._on_compare_requested)
        self.btn_load.clicked.connect(self.load_dataset)
        self.btn_save.clicked.connect(self.save_selected)
        self.btn_del.clicked.connect(self.delete_selected)

        self.session.log(f"UV fotodedektor arayuzu v{__version__} hazir.")
        if self.session.settings.get("simulate"):
            self.session.log("Simulasyon modu acik — gercek cihaz kullanilmiyor.")

    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("&Dosya")
        act_load = m_file.addAction("Olcum yukle (CSV)…")
        act_load.triggered.connect(self.load_dataset)
        act_save = m_file.addAction("Secili olcumu kaydet…")
        act_save.triggered.connect(self.save_selected)
        m_file.addSeparator()
        act_dir = m_file.addAction("Veri klasorunu sec…")
        act_dir.triggered.connect(self.choose_data_dir)
        m_file.addSeparator()
        act_quit = m_file.addAction("Cikis")
        act_quit.triggered.connect(self.close)

        m_view = self.menuBar().addMenu("&Gorunum")
        m_view.addAction(self.dock_list.toggleViewAction())
        m_view.addAction(self.dock_log.toggleViewAction())

        m_help = self.menuBar().addMenu("&Yardim")
        act_about = m_help.addAction("Hakkinda")
        act_about.triggered.connect(self._about)
        act_wiring = m_help.addAction("Kablolama dosyasinin yeri")
        act_wiring.triggered.connect(self._wiring_path)

    def _about(self) -> None:
        message(self, "Hakkinda",
                f"UV Fotodedektor Olcum Arayuzu v{__version__}\n\n"
                "Keithley 2636 (TSP, GPIB/VISA) + Adapter Box C 10\n"
                "I–V karakteristigi, karanlik/UV karsilastirmasi, fotoakim,\n"
                "duyarlilik (A/W), EQE, D*, zaman tepkisi.\n\n"
                "Sinirlar: 60 V DC / 1 A DC (Adapter Box C 10).")

    def _wiring_path(self) -> None:
        from ..config import WIRING_PATH
        message(self, "Kablolama dosyasi",
                f"Kablolama haritasi su dosyadan okunuyor:\n\n{WIRING_PATH}\n\n"
                "Kendi baglantilariniza gore duzenleyip programi yeniden baslatin.")

    # ------------------------------------------------------------------
    def _append_log(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{stamp}] {text}")

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for idx, ds in enumerate(self.session.datasets):
            item = QtWidgets.QListWidgetItem(
                f"{idx + 1}. {ds.label}  ·  {ds.kind}  ·  {len(ds)} nokta")
            item.setToolTip(f"{ds.timestamp}\n{ds.notes}")
            self.list_widget.addItem(item)

    def _on_busy(self, busy: bool) -> None:
        self.statusBar().showMessage("Olcum suruyor…" if busy else "Hazir")
        # olcum sirasinda baglanti ayarlarini kilitle
        self.tab_conn.setEnabled(not busy)

    def _on_compare_requested(self, dark: Dataset, light: Dataset) -> None:
        self.tabs.setCurrentWidget(self.tab_an)
        self.tab_an.select_datasets(dark, light)

    # ------------------------------------------------------------------
    def load_dataset(self) -> None:
        directory = self.session.settings.get("data_dir", ".")
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Olcum dosyalari sec", directory,
            "CSV dosyalari (*.csv);;Tum dosyalar (*)")
        for path in paths:
            try:
                self.session.add_dataset(Dataset.from_csv(path))
            except Exception as exc:
                message(self, "Okuma hatasi", f"{path}\n\n{exc}", "error")

    def save_selected(self) -> None:
        rows = [i.row() for i in self.list_widget.selectedIndexes()]
        if not rows:
            message(self, "Secim yok", "Listeden bir olcum secin.", "warn")
            return
        directory = self.session.settings.get("data_dir", ".")
        os.makedirs(directory, exist_ok=True)
        for row in rows:
            ds = self.session.dataset(row)
            if ds is None:
                continue
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, f"Kaydet: {ds.label}", suggest_filename(ds, directory),
                "CSV dosyalari (*.csv)")
            if path:
                ds.to_csv(path)
                self.session.log(f"Kaydedildi: {path}")

    def delete_selected(self) -> None:
        rows = sorted((i.row() for i in self.list_widget.selectedIndexes()), reverse=True)
        for row in rows:
            self.session.remove_dataset(row)

    def choose_data_dir(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Veri klasoru sec", self.session.settings.get("data_dir", "."))
        if directory:
            self.session.settings["data_dir"] = directory
            self.session.save()
            self.session.log(f"Veri klasoru: {directory}")

    # ------------------------------------------------------------------
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        for tab in (self.tab_iv, self.tab_tr):
            worker = getattr(tab, "worker", None)
            if worker is not None and worker.isRunning():
                worker.stop()
                worker.wait(3000)
        self.session.disconnect_instrument()
        self.session.save()
        event.accept()
