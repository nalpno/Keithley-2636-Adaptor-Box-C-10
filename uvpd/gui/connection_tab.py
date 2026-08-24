"""Baglanti, SMU ayarlari, guvenlik ve kablolama sekmesi."""

from __future__ import annotations

from ..config import load_wiring
from ..instrument import CURRENT_RANGES, Keithley2636
from ..qtcompat import QtCore, QtWidgets
from .session import Session
from .widgets import FormBuilder, group, message


class ConnectionTab(QtWidgets.QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        s = session.settings

        # ---------------- baglanti kutusu ----------------
        fb = FormBuilder()
        self.resource = QtWidgets.QComboBox()
        self.resource.setEditable(True)
        self.resource.addItems([s.get("resource", "GPIB0::26::INSTR"),
                                "GPIB0::26::INSTR", "GPIB0::25::INSTR",
                                "TCPIP0::192.168.1.10::inst0::INSTR",
                                "USB0::0x05E6::0x2636::INSTR"])
        self.resource.setCurrentText(s.get("resource", "GPIB0::26::INSTR"))
        fb.add("VISA kaynagi", self.resource,
               "USB-3488A + GPIB icin tipik adres: GPIB0::26::INSTR "
               "(2636 fabrika GPIB adresi 26)")

        self.visa_lib = QtWidgets.QLineEdit(s.get("visa_library", ""))
        self.visa_lib.setPlaceholderText("bos = sistem VISA (NI/Keysight/MCC), @py = pyvisa-py")
        fb.add("VISA kutuphanesi", self.visa_lib)

        self.simulate = fb.check("Simulasyon modu (cihazsiz)", s.get("simulate", False),
                                 "Cihaz baglamadan arayuzu ve analizleri denemek icin")

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_scan = QtWidgets.QPushButton("Kaynaklari tara")
        self.btn_connect = QtWidgets.QPushButton("Bagla")
        self.btn_disconnect = QtWidgets.QPushButton("Baglantiyi kes")
        self.btn_disconnect.setEnabled(False)
        for b in (self.btn_scan, self.btn_connect, self.btn_disconnect):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        holder = QtWidgets.QWidget()
        holder.setLayout(btn_row)
        fb.add_row(holder)

        self.idn_label = QtWidgets.QLabel("—")
        self.idn_label.setWordWrap(True)
        self.idn_label.setStyleSheet("color:#555;")
        fb.add("Cihaz kimligi", self.idn_label)

        conn_box = group("1) Cihaz baglantisi", fb.widget)

        # ---------------- SMU ayarlari ----------------
        f2 = FormBuilder()
        self.channel = f2.combo("SMU kanali", [("Kanal A", "a"), ("Kanal B", "b")],
                                s.get("channel", "a"))
        self.source_func = f2.combo(
            "Kaynak tipi",
            [("Gerilim kaynagi / akim olc (V→I)", "voltage"),
             ("Akim kaynagi / gerilim olc (I→V)", "current")],
            s.get("source_func", "voltage"),
            "Fotodedektor I-V karakteristigi icin gerilim kaynagi kullanilir.")
        self.compliance = f2.sci("Limit (compliance)", s.get("compliance", 1e-3),
                                 "Gerilim kaynaginda akim limiti [A], akim kaynaginda "
                                 "gerilim limiti [V]. Numuneyi korur.")
        self.nplc = f2.sci("NPLC (integrasyon)", s.get("nplc", 1.0),
                           "0.001–25. Buyuk NPLC = dusuk gurultu, yavas olcum. "
                           "pA seviyesi icin 5–10 onerilir.")
        self.filter_count = f2.spin("Filtre (ortalama) sayisi", s.get("filter_count", 1), 1, 100,
                                    "1 = filtre kapali. Gurultulu dusuk akimda 5–10.")
        self.low_range = f2.combo(
            "Otomatik kademe alt siniri",
            [(f"{r:g} A", r) for r in CURRENT_RANGES[:8]],
            s.get("low_range_i", 1e-9),
            "Otomatik kademelemenin inebilecegi en dusuk akim kademesi. "
            "Cok dusuk secilirse olcum yavaslar.")
        self.four_wire = f2.check("4 uclu (remote sense)", s.get("four_wire", False),
                                  "Dusuk empedansli numunelerde kablo direncini yok eder. "
                                  "SENSE HI/LO uclarinin bagli olmasi gerekir.")
        self.auto_zero = f2.combo("Auto-zero",
                                  [("Otomatik", "auto"), ("Bir kez", "once"), ("Kapali", "off")],
                                  s.get("auto_zero", "auto"))
        self.high_c = f2.check("Yuksek kapasite modu", s.get("high_capacitance", False),
                               "Genis alanli / kapasitif numunelerde kararliligi artirir.")
        smu_box = group("2) SMU olcum ayarlari", f2.widget)

        # ---------------- guvenlik ----------------
        f3 = FormBuilder()
        limits = load_wiring().get("limitler", {})
        lim_label = QtWidgets.QLabel(
            f"Adapter Box C 10 sinirlari:  U_max = {limits.get('u_max_v', 60):g} V DC,  "
            f"I_max = {limits.get('i_max_a', 1):g} A DC")
        lim_label.setStyleSheet("font-weight:600; color:#b45309;")
        f3.add_row(lim_label)
        self.interlock = f3.check(
            "INTERLOCK bagli / kutu kapagi kapali (onayliyorum)",
            s.get("interlock_confirmed", False),
            "Adapter Box C 10 arkasindaki INTERLOCK ucu koprulenmemisse cikis aktiflesmez.")
        self.btn_output_off = QtWidgets.QPushButton("⏻  CIKISI HEMEN KAPAT")
        self.btn_output_off.setStyleSheet(
            "background:#dc2626; color:white; font-weight:700; padding:6px;")
        f3.add_row(self.btn_output_off)
        safety_box = group("3) Guvenlik", f3.widget)

        # ---------------- kablolama ----------------
        self.wiring_table = QtWidgets.QTableWidget(0, 4)
        self.wiring_table.setHorizontalHeaderLabels(
            ["Keithley 2636", "Kablo", "Adapter Box C 10", "Numune ucu / not"])
        self.wiring_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents)
        self.wiring_table.horizontalHeader().setStretchLastSection(True)
        self.wiring_table.verticalHeader().setVisible(False)
        self.wiring_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.wiring_table.setAlternatingRowColors(True)
        self._fill_wiring()
        wiring_box = group("4) Kablolama haritasi (config/wiring.json)", self.wiring_table)

        # ---------------- yerlesim ----------------
        left = QtWidgets.QVBoxLayout()
        left.addWidget(conn_box)
        left.addWidget(smu_box)
        left.addWidget(safety_box)
        left.addStretch(1)
        left_w = QtWidgets.QWidget()
        left_w.setLayout(left)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_w)
        splitter.addWidget(scroll)
        splitter.addWidget(wiring_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(splitter)

        # ---------------- baglantilar ----------------
        self.btn_scan.clicked.connect(self._scan)
        self.btn_connect.clicked.connect(self._connect)
        self.btn_disconnect.clicked.connect(self.session.disconnect_instrument)
        self.btn_output_off.clicked.connect(self._output_off)
        self.session.connection_changed.connect(self._on_connection)

        for w in (self.channel, self.source_func, self.low_range, self.auto_zero):
            w.currentIndexChanged.connect(self._push)
        for w in (self.four_wire, self.high_c, self.interlock, self.simulate):
            w.toggled.connect(self._push)
        self.filter_count.valueChanged.connect(self._push)
        for w in (self.compliance, self.nplc):
            w.editingFinished.connect(self._push)
        self._push()

    # ------------------------------------------------------------------
    def _fill_wiring(self) -> None:
        rows = load_wiring().get("baglantilar", [])
        self.wiring_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(("smu", "kablo", "kutu", "not")):
                item = QtWidgets.QTableWidgetItem(str(row.get(key, "")))
                item.setToolTip(str(row.get("not", "")))
                self.wiring_table.setItem(r, c, item)

    def _push(self, *_) -> None:
        """Arayuzdeki ayarlari oturum ayarlarina yazar."""
        s = self.session.settings
        s["channel"] = self.channel.currentData()
        s["source_func"] = self.source_func.currentData()
        s["compliance"] = self.compliance.value(1e-3)
        s["nplc"] = self.nplc.value(1.0)
        s["filter_count"] = int(self.filter_count.value())
        s["low_range_i"] = float(self.low_range.currentData())
        s["four_wire"] = self.four_wire.isChecked()
        s["auto_zero"] = self.auto_zero.currentData()
        s["high_capacitance"] = self.high_c.isChecked()
        s["interlock_confirmed"] = self.interlock.isChecked()
        s["simulate"] = self.simulate.isChecked()

    # ------------------------------------------------------------------
    def _scan(self) -> None:
        try:
            if self.simulate.isChecked():
                found = ["SIM::UVPD::INSTR"]
            else:
                found = Keithley2636.list_resources(self.visa_lib.text().strip())
        except Exception as exc:
            message(self, "VISA hatasi",
                    f"Kaynaklar taranamadi:\n{exc}\n\n"
                    "GPIB surucusunun (USB-3488A) ve VISA kutuphanesinin "
                    "kurulu oldugundan emin olun.", "error")
            return
        if not found:
            message(self, "Kaynak yok", "Hicbir VISA kaynagi bulunamadi.", "warn")
            return
        current = self.resource.currentText()
        self.resource.clear()
        self.resource.addItems(found)
        if current in found:
            self.resource.setCurrentText(current)
        self.session.log(f"Bulunan kaynaklar: {', '.join(found)}")

    def _connect(self) -> None:
        self._push()
        resource = self.resource.currentText().strip()
        try:
            idn = self.session.connect_instrument(
                resource, simulate=self.simulate.isChecked(),
                visa_library=self.visa_lib.text().strip())
        except Exception as exc:
            message(self, "Baglanti hatasi",
                    f"{resource} adresine baglanilamadi:\n\n{exc}", "error")
            return
        self.idn_label.setText(idn)

    def _output_off(self) -> None:
        inst = self.session.instrument
        if inst is None:
            return
        try:
            inst.output_off()
            self.session.log("Cikis kapatildi (acil durdurma).")
        except Exception as exc:
            message(self, "Hata", str(exc), "error")

    def _on_connection(self, connected: bool) -> None:
        self.btn_connect.setEnabled(not connected)
        self.btn_disconnect.setEnabled(connected)
        self.resource.setEnabled(not connected)
        self.simulate.setEnabled(not connected)
        if not connected:
            self.idn_label.setText("—")
