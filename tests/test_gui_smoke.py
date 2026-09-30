"""Arayuz duman testi: pencere kurulur, simulasyon modunda kisa bir tarama
yapilir ve karsilastirma calistirilir. Ekransiz (offscreen) calisir."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("matplotlib")
qtcompat = pytest.importorskip("uvpd.qtcompat")

from uvpd.dataset import DARK, LIGHT  # noqa: E402
from uvpd.qtcompat import QtWidgets  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield application


def _pump(app, predicate, timeout=30.0):
    """Olay dongusunu isletirken kosulun saglanmasini bekler."""
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if predicate():
            app.processEvents()
            return True
        time.sleep(0.02)
    return False


def test_main_window_sweep_and_compare(app, tmp_path):
    from uvpd.gui.main_window import MainWindow

    win = MainWindow(simulate=True)
    win.session.settings["data_dir"] = str(tmp_path)
    win.session.settings["interlock_confirmed"] = True
    win.session.connect_instrument("SIM::UVPD::INSTR", simulate=True)
    assert win.session.connected

    tab = win.tab_iv
    tab.points.setValue(11)
    tab.start.setValue(-0.5)
    tab.stop.setValue(0.5)
    tab.settle.setValue(0.0)
    tab.autosave.setChecked(True)

    # karanlik tarama
    tab.light_state.setCurrentIndex(0)
    tab.start_sweep(dual=False)
    assert _pump(app, lambda: len(win.session.datasets) == 1)
    assert win.session.datasets[0].light_state == DARK
    assert len(win.session.datasets[0]) == 11

    # UV altinda tarama
    tab.light_state.setCurrentIndex(1)
    tab.start_sweep(dual=False)
    assert _pump(app, lambda: len(win.session.datasets) == 2)
    assert win.session.datasets[1].light_state == LIGHT

    # otomatik kayit dosyalari olustu mu
    assert len(list(tmp_path.glob("*.csv"))) == 2

    # karsilastirma
    an = win.tab_an
    an.select_datasets(win.session.datasets[0], win.session.datasets[1])
    assert an.comparison is not None
    assert an.comparison.v.size > 0
    assert an.table.rowCount() > 5

    # gosterim modlarinin hepsi cizilebiliyor mu
    for idx in range(an.view.count()):
        an.view.setCurrentIndex(idx)
        app.processEvents()

    # diyot analizi
    an.do_diode()
    assert an.table.rowCount() >= 5

    win.close()


def test_transient_tab_short_run(app, tmp_path):
    from uvpd.gui.main_window import MainWindow

    win = MainWindow(simulate=True)
    win.session.settings["data_dir"] = str(tmp_path)
    win.session.settings["interlock_confirmed"] = True
    win.session.connect_instrument("SIM::UVPD::INSTR", simulate=True)

    tab = win.tab_tr
    tab.duration.setValue(1.5)
    tab.interval.setValue(0.02)
    tab.cycle_enabled.setChecked(True)
    tab.cycle_delay.setValue(0.2)
    tab.cycle_on.setValue(0.4)
    tab.cycle_off.setValue(0.4)
    tab.start()
    assert _pump(app, lambda: len(win.session.datasets) == 1)
    ds = win.session.datasets[0]
    assert ds.kind == "transient"
    assert "light_events" in ds.settings
    assert tab.metrics.rowCount() > 0
    win.close()


def test_connect_error_hints():
    """Bagli olmayan adres hatalarinda dogru yonlendirme verilmeli."""
    from uvpd.gui.connection_tab import connect_error_hint

    h = connect_error_hint("VI_ERROR_RSRC_NFOUND: Insufficient location information",
                           "USB0::0x05E6::0x2636::INSTR")
    assert "Kaynaklari tara" in h
    assert "SERI NUMARASINI" in h

    h = connect_error_hint("VI_ERROR_RSRC_NFOUND: not present", "GPIB0::26::INSTR")
    assert "gpib-kurulum.bat" in h

    h = connect_error_hint("VI_ERROR_RSRC_NFOUND: not present",
                           "TCPIP0::192.168.1.10::inst0::INSTR")
    assert "IP-ADDRESS" in h

    h = connect_error_hint("VI_ERROR_TMO: Timeout expired", "GPIB0::26::INSTR")
    assert "zaman asimi" in h.lower()

    h = connect_error_hint("VI_ERROR_NLISTENERS: no listeners", "GPIB0::26::INSTR")
    assert "dinleyen" in h

    h = connect_error_hint("ValueError: Could not locate a VISA implementation", "x")
    assert "VISA teshis" in h


def test_resource_combo_has_no_fake_presets(app):
    """Kaynak listesi yalnizca kayitli/taranmis adresleri icermeli."""
    from uvpd.gui.main_window import MainWindow

    win = MainWindow(simulate=True)
    tab = win.tab_conn
    items = [tab.resource.itemText(i) for i in range(tab.resource.count())]
    # Ornek adresler listeye konmamali (kullanici onlari bulunmus sanmasin)
    assert "TCPIP0::192.168.1.10::inst0::INSTR" not in items
    assert "USB0::0x05E6::0x2636::INSTR" not in items
    assert len(items) <= 1
    win.close()


def test_scope_tab_loads_csv_and_exports(app, tmp_path):
    """v2: osiloskop CSV'si yuklenir, analiz edilir, tum gosterimler cizilir."""
    from uvpd.gui.main_window import MainWindow
    from uvpd.gui import scope_tab as st

    data = os.path.join(os.path.dirname(__file__), "data", "rigol_ds3100_ACOPE_01.csv")
    win = MainWindow(simulate=True)
    win.session.settings["data_dir"] = str(tmp_path)
    tab = win.tab_scope
    assert win.tabs.indexOf(tab) == 4          # eski 4 sekme yerinde kaldi
    tab.load50.setChecked(False)               # onceki calismadan kalan ayar olmasin
    tab.gain.setValue(1e5)

    assert tab.load_file(data)
    assert tab.signal_ch.currentData() == "CH2"
    assert tab.ref_ch.currentData() == "CH1"
    res = tab.result
    assert res is not None and res.n_cycles == 5
    rows = dict((tab.table.item(r, 0).text(), tab.table.item(r, 1).text())
                for r in range(tab.table.rowCount()))
    assert rows["Periyot"] == "208 µs"
    assert "A/W" in rows["Duyarlilik R = I_ph / P"]

    for idx in range(tab.view.count()):
        tab.view.setCurrentIndex(idx)
        app.processEvents()

    # 50 Ω secenegi fotoakimi iki katina cikarir
    i1 = res.photocurrent
    tab.load50.setChecked(True)
    tab.analyze()
    assert tab.result.photocurrent == pytest.approx(2 * i1)
    assert win.session.settings["scope"]["load_50ohm"] is True

    # referans yok secenegi
    tab.ref_ch.setCurrentIndex(tab.ref_ch.findData(st.NO_REF))
    tab.analyze()
    assert tab.result.settings.reference is None

    for kind, name in (("report", "r.txt"), ("edges", "e.csv"),
                       ("avg", "a.csv"), ("png", "g.png")):
        path = tab.export_to(kind, str(tmp_path / name))
        assert os.path.getsize(path) > 100
    win.close()
