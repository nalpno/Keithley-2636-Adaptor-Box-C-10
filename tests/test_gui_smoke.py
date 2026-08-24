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
