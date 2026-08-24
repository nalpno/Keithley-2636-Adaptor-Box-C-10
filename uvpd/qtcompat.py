"""Qt binding uyumluluk katmani.

Once PyQt5 denenir, yoksa PySide6 kullanilir. Boylece laboratuvar PC'sinde
hangisi kurulu ise program calisir.
"""

BINDING = None

try:  # pragma: no cover - hangi binding varsa o kullanilir
    from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore

    Signal = QtCore.pyqtSignal
    Slot = QtCore.pyqtSlot
    Property = QtCore.pyqtProperty
    BINDING = "PyQt5"
except ImportError:  # pragma: no cover
    from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore

    Signal = QtCore.Signal
    Slot = QtCore.Slot
    Property = QtCore.Property
    BINDING = "PySide6"


def matplotlib_backend_modules():
    """Qt binding'ine uygun matplotlib backend modullerini dondurur."""
    import matplotlib

    if BINDING == "PyQt5":
        matplotlib.use("Qt5Agg", force=False)
    else:
        matplotlib.use("QtAgg", force=False)

    from matplotlib.backends.backend_qtagg import (  # type: ignore
        FigureCanvasQTAgg,
        NavigationToolbar2QT,
    )

    return FigureCanvasQTAgg, NavigationToolbar2QT


__all__ = [
    "QtCore",
    "QtGui",
    "QtWidgets",
    "Signal",
    "Slot",
    "Property",
    "BINDING",
    "matplotlib_backend_modules",
]
