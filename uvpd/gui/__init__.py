"""PyQt/PySide arayuzu."""

from __future__ import annotations

import logging
import sys


def run(argv=None) -> int:
    """Uygulamayi baslatir."""
    import argparse

    parser = argparse.ArgumentParser(
        description="UV fotodedektor olcum arayuzu (Keithley 2636 + Adapter Box C 10)")
    parser.add_argument("--simulate", action="store_true",
                        help="Cihaz olmadan simulasyon modunda baslat")
    parser.add_argument("--debug", action="store_true", help="Ayrintili gunluk")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    from ..qtcompat import QtWidgets
    from .main_window import MainWindow

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("UVPD Keithley 2636")
    win = MainWindow(simulate=args.simulate)
    win.show()
    return app.exec_() if hasattr(app, "exec_") else app.exec()
