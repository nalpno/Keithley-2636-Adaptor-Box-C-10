"""Baglanti, SMU ayarlari, guvenlik ve kablolama sekmesi."""

from __future__ import annotations

from ..config import load_wiring
from ..instrument import CURRENT_RANGES, Keithley2636
from ..qtcompat import QtCore, QtWidgets
from ..visa_diag import BACKEND_PY, diagnose, try_backend
from .session import Session
from .widgets import FormBuilder, group, message


def connect_error_hint(exc_text: str, resource: str) -> str:
    """VISA hata metnine gore somut bir aciklama uretir."""
    t = exc_text.upper()
    res = resource.upper()

    if ("RSRC_NFOUND" in t or "INSUFFICIENT LOCATION" in t
            or "NOT PRESENT" in t or "COULD NOT FIND" in t):
        msg = ("Bu adreste cihaz bulunamadi — adres yanlis ya da cihaz "
               "gorunmuyor.\n\n"
               "Once 'Kaynaklari tara' ile GERCEKTEN bulunan bir adres secin. "
               "Elle yazdiginiz veya ornek olarak gordugunuz bir adres "
               "calismaz.")
        if res.startswith("USB"):
            msg += ("\n\nUSB adresi cihazin SERI NUMARASINI icermelidir:\n"
                    "  USB0::0x05E6::0x2636::<seri-no>::INSTR\n"
                    "Ayrica bu adres yalnizca kablo Keithley'in KENDI USB "
                    "portuna takiliysa gecerlidir (GPIB adaptoru degil).")
        elif res.startswith("TCPIP"):
            msg += ("\n\nLAN adresindeki IP, cihazin gercek IP adresi olmalidir:\n"
                    "  MENU > LAN > STATUS > IP-ADDRESS")
        elif res.startswith("GPIB"):
            msg += ("\n\nGPIB icin: ADLINK USB-3488A adaptorunu NI-VISA/KIOL "
                    "goremez. 'gpib-kurulum.bat' calistirip VISA kutuphanesi "
                    "alanina @py yazin.")
        return msg

    if "TMO" in t or "TIMEOUT" in t or "ZAMAN" in t:
        return ("Adres bulundu ama cihaz cevap vermedi (zaman asimi).\n\n"
                "- Keithley'in GPIB adresi bu adresle ayni mi? "
                "(MENU > COMMUNICATION > GPIB, fabrika degeri 26)\n"
                "- Cihaz baska bir program tarafindan kullaniliyor olabilir "
                "(LabVIEW, Keithley Communicator acikken kapatin).\n"
                "- Cihazi kapatip acmayi deneyin.")

    if "NLISTENERS" in t or "NO LISTENER" in t:
        return ("GPIB hattinda bu adreste dinleyen cihaz yok.\n\n"
                "- Keithley acik mi, GPIB kablosu her iki uctan takili mi?\n"
                "- Cihazin GPIB adresini kontrol edin "
                "(MENU > COMMUNICATION > GPIB).")

    if "LOCATE A VISA" in t or "VISALIBRARYERROR" in t:
        return ("VISA kutuphanesi yuklenemedi. '🔍 VISA teshis' dugmesi "
                "eksigin ne oldugunu soyler.")

    if "PERMISSION" in t or "ACCESS" in t or "VI_ERROR_RSRC_BUSY" in t:
        return ("Kaynak baska bir program tarafindan kullaniliyor. "
                "LabVIEW / Keithley Communicator gibi programlari kapatip "
                "tekrar deneyin.")

    return ("Ayrintili teshis icin '🔍 VISA teshis' dugmesini kullanin.")


class ConnectionTab(QtWidgets.QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        s = session.settings

        # ---------------- baglanti kutusu ----------------
        fb = FormBuilder()
        # Liste yalnizca GERCEKTEN bulunan kaynaklarla doldurulur; ornek
        # adresler asagida ayri bir ipucu satirinda gosterilir ki taranarak
        # bulunmus adreslerle karistirilmasin.
        self.resource = QtWidgets.QComboBox()
        self.resource.setEditable(True)
        saved = str(s.get("resource", "") or "")
        if saved:
            self.resource.addItem(saved)
            self.resource.setCurrentText(saved)
        self.resource.lineEdit().setPlaceholderText(
            "'Kaynaklari tara' ile doldurun veya adresi elle yazin")
        fb.add("VISA kaynagi", self.resource,
               "Bu liste yalnizca taramada bulunan cihazlarla dolar. "
               "Elle adres de yazabilirsiniz.")

        hint = QtWidgets.QLabel(
            "Ornek bicimler (bunlar bulunmus cihaz degil, yalnizca kalip):\n"
            "GPIB0::26::INSTR    ·    USB0::0x05E6::0x2636::<seri-no>::INSTR"
            "    ·    TCPIP0::<ip>::inst0::INSTR")
        hint.setStyleSheet("color:#6b7280; font-size:11px;")
        hint.setWordWrap(True)
        fb.add_row(hint)

        self.visa_lib = QtWidgets.QLineEdit(s.get("visa_library", ""))
        self.visa_lib.setPlaceholderText("bos = sistem VISA (NI/Keysight/ADLINK), @py = pyvisa-py")
        fb.add("VISA kutuphanesi", self.visa_lib)

        self.simulate = fb.check("Simulasyon modu (cihazsiz)", s.get("simulate", False),
                                 "Cihaz baglamadan arayuzu ve analizleri denemek icin")

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_scan = QtWidgets.QPushButton("Kaynaklari tara")
        self.btn_diag = QtWidgets.QPushButton("🔍 VISA teshis")
        self.btn_diag.setToolTip(
            "VISA/GPIB kurulumunu tarar ve 'Could not locate a VISA "
            "implementation' gibi hatalarin sebebini bildirir.")
        self.btn_connect = QtWidgets.QPushButton("Bagla")
        self.btn_disconnect = QtWidgets.QPushButton("Baglantiyi kes")
        self.btn_disconnect.setEnabled(False)
        for b in (self.btn_scan, self.btn_diag, self.btn_connect, self.btn_disconnect):
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
        self.btn_diag.clicked.connect(self._diagnose)
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
        if self.simulate.isChecked():
            found = ["SIM::UVPD::INSTR"]
        else:
            library = self.visa_lib.text().strip()
            try:
                found = Keithley2636.list_resources(library)
            except Exception as exc:
                self._scan_failed(exc, library)
                return
            # Sistem VISA calisti ama hicbir sey gormedi: ucuncu parti GPIB
            # adaptorleri (ADLINK USB-3488A) NI-VISA'da gorunmez, pyvisa-py'de
            # gorunur. Bu durumda @py ile bir kez daha dene.
            if not found and not library:
                ok, result = try_backend(BACKEND_PY)
                if ok and result:
                    self.visa_lib.setText(BACKEND_PY)
                    self._push()
                    found = [str(r) for r in result]
                    self.session.log(
                        "Sistem VISA hicbir cihaz gormedi; pyvisa-py (@py) ile "
                        f"bulundu: {', '.join(found)}")
                    message(self, "pyvisa-py kullaniliyor",
                            "Sistem VISA (NI-VISA / Keithley I/O Layer) hicbir "
                            "cihaz gormedi — ucuncu parti GPIB adaptorlerini "
                            "desteklemez.\n\n"
                            "pyvisa-py ile cihaz bulundu ve 'VISA kutuphanesi' "
                            "alani otomatik olarak @py yapildi.", "info")
        if not found:
            message(self, "Kaynak yok",
                    "Hicbir VISA kaynagi bulunamadi.\n\n"
                    "Cihaz acik ve kablo takili mi? Ayrintili teshis icin "
                    "'VISA teshis' dugmesini kullanin.", "warn")
            return
        current = self.resource.currentText()
        self.resource.clear()
        self.resource.addItems(found)
        if current in found:
            self.resource.setCurrentText(current)
        self.session.log(f"{len(found)} kaynak bulundu: {', '.join(found)}")
        self.session.status.emit(f"{len(found)} VISA kaynagi bulundu")

    def _scan_failed(self, exc: Exception, library: str) -> None:
        """Tarama basarisiz: otomatik yedek backend dene, olmazsa teshise yonlendir."""
        self.session.log(f"VISA hatasi ({library or 'sistem VISA'}): {exc}")

        # Sistem VISA yoksa pyvisa-py ile otomatik olarak bir kez dene
        if not library:
            ok, result = try_backend(BACKEND_PY)
            if ok and result:
                self.visa_lib.setText(BACKEND_PY)
                self.resource.clear()
                self.resource.addItems([str(r) for r in result])
                self.session.log(
                    f"Sistem VISA bulunamadi; pyvisa-py (@py) ile devam edildi. "
                    f"Bulunan kaynaklar: {', '.join(str(r) for r in result)}")
                message(self, "pyvisa-py kullaniliyor",
                        "Sistem VISA kutuphanesi bulunamadi, ancak pyvisa-py "
                        "calisti ve kaynaklari listeledi.\n\n"
                        "'VISA kutuphanesi' alani otomatik olarak @py yapildi.",
                        "info")
                return

        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("VISA hatasi")
        box.setIcon(QtWidgets.QMessageBox.Critical)
        box.setText("Kaynaklar taranamadi.")
        box.setInformativeText(
            f"{exc}\n\n"
            "Bu hata, Python'un bir VISA kutuphanesi bulamadigi anlamina gelir. "
            "LabVIEW calisiyor olsa bile Python ayri bir arayuze ihtiyac duyar.\n\n"
            "Sebebini ogrenmek icin 'Teshisi calistir' dugmesine basin.")
        run_diag = box.addButton("Teshisi calistir", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("Kapat", QtWidgets.QMessageBox.RejectRole)
        box.exec_() if hasattr(box, "exec_") else box.exec()
        if box.clickedButton() is run_diag:
            self._diagnose()

    def _diagnose(self) -> None:
        """VISA teshis raporunu diyalogda gosterir."""
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            report = diagnose()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.session.log("VISA teshisi calistirildi.")

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("VISA / GPIB teshisi")
        dlg.resize(760, 560)
        lay = QtWidgets.QVBoxLayout(dlg)

        view = QtWidgets.QPlainTextEdit(report.text)
        view.setReadOnly(True)
        view.setStyleSheet("font-family:monospace; font-size:11px;")
        lay.addWidget(view, 1)

        row = QtWidgets.QHBoxLayout()
        btn_copy = QtWidgets.QPushButton("Panoya kopyala")
        btn_copy.clicked.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(report.text))
        row.addWidget(btn_copy)
        if report.recommended_library is not None:
            label = report.recommended_library or "(bos = sistem VISA)"
            btn_apply = QtWidgets.QPushButton(f"Oneriyi uygula: {label}")
            btn_apply.setStyleSheet("font-weight:700;")

            def apply_suggestion():
                self.visa_lib.setText(report.recommended_library)
                if report.working_resources:
                    self.resource.clear()
                    self.resource.addItems([str(r) for r in report.working_resources])
                self._push()
                self.session.log(
                    f"VISA kutuphanesi '{report.recommended_library or 'sistem'}' "
                    "olarak ayarlandi.")
                dlg.accept()

            btn_apply.clicked.connect(apply_suggestion)
            row.addWidget(btn_apply)
        row.addStretch(1)
        btn_close = QtWidgets.QPushButton("Kapat")
        btn_close.clicked.connect(dlg.reject)
        row.addWidget(btn_close)
        holder = QtWidgets.QWidget()
        holder.setLayout(row)
        lay.addWidget(holder)

        dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()

    def _connect(self) -> None:
        self._push()
        resource = self.resource.currentText().strip()
        library = self.visa_lib.text().strip()
        try:
            idn = self.session.connect_instrument(
                resource, simulate=self.simulate.isChecked(),
                visa_library=library)
        except Exception as exc:
            self.session.log(f"Baglanti hatasi ({resource}): {exc}")
            hint = connect_error_hint(f"{type(exc).__name__}: {exc}", resource)

            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Baglanti hatasi")
            box.setIcon(QtWidgets.QMessageBox.Critical)
            box.setText(f"{resource} adresine baglanilamadi.")
            box.setInformativeText(hint)
            box.setDetailedText(f"{type(exc).__name__}: {exc}")
            run_diag = box.addButton("🔍 Teshisi calistir",
                                     QtWidgets.QMessageBox.AcceptRole)
            box.addButton("Kapat", QtWidgets.QMessageBox.RejectRole)
            box.exec_() if hasattr(box, "exec_") else box.exec()
            if box.clickedButton() is run_diag:
                self._diagnose()
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
