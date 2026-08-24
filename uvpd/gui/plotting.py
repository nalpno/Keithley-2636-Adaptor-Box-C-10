"""Matplotlib tabanli canli grafik bileseni."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..qtcompat import QtCore, QtWidgets, matplotlib_backend_modules

FigureCanvas, NavigationToolbar = matplotlib_backend_modules()
from matplotlib.figure import Figure  # noqa: E402

LINEAR, LOG_ABS, SYMLOG = "linear", "log", "symlog"

_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
           "#8c564b", "#17becf", "#e377c2"]


class Series:
    def __init__(self, key: str, label: str, color: str, style: str = "-",
                 marker: str = "", linewidth: float = 1.6):
        self.key = key
        self.label = label
        self.color = color
        self.style = style
        self.marker = marker
        self.linewidth = linewidth
        self.x: List[float] = []
        self.y: List[float] = []
        self.visible = True


class MeasurementPlot(QtWidgets.QWidget):
    """Canli veri cizimi yapan, log/dogrusal eksen destekli grafik."""

    def __init__(self, xlabel: str = "Gerilim (V)", ylabel: str = "Akim (A)",
                 parent=None, redraw_ms: int = 150):
        super().__init__(parent)
        self.figure = Figure(figsize=(5.5, 4.0), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.ax = self.figure.add_subplot(111)

        self._series: Dict[str, Series] = {}
        self._spans: List[Tuple[float, float]] = []
        self._yscale = LINEAR
        self._xlabel = xlabel
        self._ylabel = ylabel
        self._title = ""
        self._dirty = False
        self._color_idx = 0

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(redraw_ms)
        self._timer.timeout.connect(self._redraw_if_dirty)
        self._timer.start()
        self.redraw()

    # ------------------------------------------------------------------
    def set_labels(self, xlabel: Optional[str] = None, ylabel: Optional[str] = None,
                   title: Optional[str] = None) -> None:
        if xlabel is not None:
            self._xlabel = xlabel
        if ylabel is not None:
            self._ylabel = ylabel
        if title is not None:
            self._title = title
        self._dirty = True

    def set_yscale(self, mode: str) -> None:
        self._yscale = mode
        self._dirty = True
        self.redraw()

    @property
    def yscale(self) -> str:
        return self._yscale

    def clear(self) -> None:
        self._series.clear()
        self._spans.clear()
        self._color_idx = 0
        self.redraw()

    def add_series(self, key: str, label: str, color: Optional[str] = None,
                   style: str = "-", marker: str = "", linewidth: float = 1.6) -> Series:
        if color is None:
            color = _COLORS[self._color_idx % len(_COLORS)]
            self._color_idx += 1
        s = Series(key, label, color, style, marker, linewidth)
        self._series[key] = s
        self._dirty = True
        return s

    def append(self, key: str, x: float, y: float) -> None:
        s = self._series.get(key)
        if s is None:
            s = self.add_series(key, key)
        s.x.append(float(x))
        s.y.append(float(y))
        self._dirty = True

    def set_data(self, key: str, x: Sequence[float], y: Sequence[float]) -> None:
        s = self._series.get(key)
        if s is None:
            s = self.add_series(key, key)
        s.x = list(np.asarray(x, dtype=float))
        s.y = list(np.asarray(y, dtype=float))
        self._dirty = True

    def set_spans(self, spans: Sequence[Tuple[float, float]]) -> None:
        """Isik acik pencerelerini (zaman tepkisi grafiginde) golgeler."""
        self._spans = [(float(a), float(b)) for a, b in spans]
        self._dirty = True

    def series_keys(self) -> List[str]:
        return list(self._series.keys())

    # ------------------------------------------------------------------
    def _redraw_if_dirty(self) -> None:
        if self._dirty:
            self.redraw()

    def redraw(self) -> None:
        self._dirty = False
        self.ax.clear()
        any_data = False
        has_positive = False
        for s in self._series.values():
            if not s.visible or not s.x:
                continue
            x = np.asarray(s.x, dtype=float)
            y = np.asarray(s.y, dtype=float)
            if self._yscale == LOG_ABS:
                y = np.abs(y)
                y = np.where(y <= 0, np.nan, y)
                has_positive = has_positive or bool(np.any(np.isfinite(y)))
            self.ax.plot(x, y, s.style, marker=s.marker, color=s.color,
                         label=s.label, linewidth=s.linewidth, markersize=3.5)
            any_data = True

        for (a, b) in self._spans:
            self.ax.axvspan(a, b, color="#a855f7", alpha=0.12, lw=0)

        if self._yscale == LOG_ABS:
            # veri henuz yokken log eksen matplotlib uyarisi uretir
            self.ax.set_yscale("log" if has_positive else "linear")
            self.ax.set_ylabel("|" + self._ylabel + "|")
        elif self._yscale == SYMLOG:
            self.ax.set_yscale("symlog", linthresh=1e-12)
            self.ax.set_ylabel(self._ylabel)
        else:
            self.ax.set_yscale("linear")
            self.ax.set_ylabel(self._ylabel)

        self.ax.set_xlabel(self._xlabel)
        if self._title:
            self.ax.set_title(self._title)
        self.ax.grid(True, which="both", alpha=0.25, linestyle=":")
        self.ax.axhline(0, color="#888", linewidth=0.8, alpha=0.6)
        if any_data:
            self.ax.legend(loc="best", fontsize=8)
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    def save_figure(self, path: str, dpi: int = 300) -> None:
        self.figure.savefig(path, dpi=dpi, bbox_inches="tight")


class YScaleSelector(QtWidgets.QWidget):
    """Grafik icin eksen olcegi secici."""

    def __init__(self, plot: MeasurementPlot, default: str = LINEAR, parent=None):
        super().__init__(parent)
        self.plot = plot
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QtWidgets.QLabel("Y ekseni:"))
        self.combo = QtWidgets.QComboBox()
        self.combo.addItem("Dogrusal", LINEAR)
        self.combo.addItem("Logaritmik |I|", LOG_ABS)
        self.combo.addItem("Symlog (isaretli log)", SYMLOG)
        idx = self.combo.findData(default)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        plot.set_yscale(default)
        self.combo.currentIndexChanged.connect(
            lambda _: self.plot.set_yscale(self.combo.currentData()))
        lay.addWidget(self.combo)
        lay.addStretch(1)
