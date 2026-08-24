"""Olcumleri arka planda calistiran QThread worker'i.

Olcum sirasinda arayuzun donmamasi ve "Durdur" dugmesinin calismasi icin tum
GPIB trafigi bu is parcaciginda yurutulur.
"""

from __future__ import annotations

import traceback
from typing import Callable, Optional

from ..dataset import Dataset
from ..qtcompat import QtCore, Signal


class MeasurementWorker(QtCore.QThread):
    """Verilen olcum fonksiyonunu arka planda calistirir.

    ``func(on_point, should_stop, log)`` imzasina sahip bir cagrilabilir alir
    ve bir :class:`Dataset` dondurmesini bekler.
    """

    point = Signal(int, float, float, float)   # idx, t, v, i
    completed = Signal(object)                 # Dataset
    failed = Signal(str)
    message = Signal(str)

    def __init__(self, func: Callable[..., Dataset], parent=None):
        super().__init__(parent)
        self._func = func
        self._stop = False
        self.result: Optional[Dataset] = None

    def stop(self) -> None:
        self._stop = True

    def should_stop(self) -> bool:
        return self._stop or self.isInterruptionRequested()

    def run(self) -> None:  # pragma: no cover - is parcacigi
        try:
            ds = self._func(
                on_point=lambda i, t, v, cur: self.point.emit(int(i), float(t),
                                                              float(v), float(cur)),
                should_stop=self.should_stop,
                log=lambda msg: self.message.emit(str(msg)),
            )
            self.result = ds
            self.completed.emit(ds)
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")
