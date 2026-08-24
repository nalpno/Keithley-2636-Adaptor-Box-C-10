"""GUI yardimci bilesenleri."""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from ..qtcompat import QtCore, QtGui, QtWidgets, Signal


class SciLineEdit(QtWidgets.QLineEdit):
    """Bilimsel gosterimi kabul eden sayi girisi (orn. 1e-9, -2.5, 1E3)."""

    valueChanged = Signal(float)

    def __init__(self, value: float = 0.0, decimals: str = "{:g}", parent=None):
        super().__init__(parent)
        self._fmt = decimals
        validator = QtGui.QDoubleValidator(-1e12, 1e12, 12, self)
        validator.setNotation(QtGui.QDoubleValidator.ScientificNotation)
        self.setValidator(validator)
        self.setValue(value)
        self.editingFinished.connect(self._emit)
        self.setAlignment(QtCore.Qt.AlignRight)

    def _emit(self):
        self.valueChanged.emit(self.value())

    def value(self, default: float = 0.0) -> float:
        text = self.text().strip().replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return default

    def setValue(self, value: float) -> None:
        self.setText(self._fmt.format(float(value)))


class FormBuilder:
    """Kisa yoldan QFormLayout kurmak icin yardimci."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        self.widget = QtWidgets.QWidget(parent)
        self.layout = QtWidgets.QFormLayout(self.widget)
        self.layout.setLabelAlignment(QtCore.Qt.AlignRight)
        self.layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

    def add(self, label: str, widget: QtWidgets.QWidget,
            tooltip: str = "") -> QtWidgets.QWidget:
        if tooltip:
            widget.setToolTip(tooltip)
        self.layout.addRow(label, widget)
        return widget

    def add_row(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        self.layout.addRow(widget)
        return widget

    def sci(self, label: str, value: float, tooltip: str = "") -> SciLineEdit:
        return self.add(label, SciLineEdit(value), tooltip)

    def spin(self, label: str, value: int, lo: int = 0, hi: int = 1000000,
             tooltip: str = "") -> QtWidgets.QSpinBox:
        w = QtWidgets.QSpinBox()
        w.setRange(lo, hi)
        w.setValue(int(value))
        return self.add(label, w, tooltip)

    def combo(self, label: str, items: Iterable[Tuple[str, object]],
              current: object = None, tooltip: str = "") -> QtWidgets.QComboBox:
        w = QtWidgets.QComboBox()
        for text, data in items:
            w.addItem(text, data)
        if current is not None:
            idx = w.findData(current)
            if idx >= 0:
                w.setCurrentIndex(idx)
        return self.add(label, w, tooltip)

    def check(self, label: str, checked: bool = False,
              tooltip: str = "") -> QtWidgets.QCheckBox:
        w = QtWidgets.QCheckBox()
        w.setChecked(bool(checked))
        return self.add(label, w, tooltip)

    def text(self, label: str, value: str = "", tooltip: str = "") -> QtWidgets.QLineEdit:
        return self.add(label, QtWidgets.QLineEdit(value), tooltip)


def group(title: str, inner: QtWidgets.QWidget) -> QtWidgets.QGroupBox:
    box = QtWidgets.QGroupBox(title)
    lay = QtWidgets.QVBoxLayout(box)
    lay.setContentsMargins(6, 6, 6, 6)
    lay.addWidget(inner)
    return box


class KeyValueTable(QtWidgets.QTableWidget):
    """Iki kolonlu (parametre / deger) salt-okunur tablo."""

    def __init__(self, parent=None):
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Parametre", "Deger"])
        self.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(True)

    def set_rows(self, rows: List[Tuple[str, str]]) -> None:
        self.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.setItem(r, 0, QtWidgets.QTableWidgetItem(str(k)))
            item = QtWidgets.QTableWidgetItem(str(v))
            item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            self.setItem(r, 1, item)

    def to_text(self) -> str:
        lines = []
        for r in range(self.rowCount()):
            k = self.item(r, 0).text() if self.item(r, 0) else ""
            v = self.item(r, 1).text() if self.item(r, 1) else ""
            lines.append(f"{k}\t{v}")
        return "\n".join(lines)


def message(parent, title: str, text: str, icon="info") -> None:
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon({"info": QtWidgets.QMessageBox.Information,
                 "warn": QtWidgets.QMessageBox.Warning,
                 "error": QtWidgets.QMessageBox.Critical}.get(icon,
                                                              QtWidgets.QMessageBox.Information))
    box.exec_() if hasattr(box, "exec_") else box.exec()
