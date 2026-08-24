"""Uygulama genelinde paylasilan durum: cihaz baglantisi ve olcum listesi."""

from __future__ import annotations

import logging
from typing import List, Optional

from ..config import load_settings, save_settings
from ..dataset import Dataset
from ..instrument import SmuConfig, create_instrument
from ..qtcompat import QtCore, Signal

log = logging.getLogger(__name__)


class Session(QtCore.QObject):
    """Cihaz + oturumdaki olcumler. Sekmeler bu nesne uzerinden haberlesir."""

    connection_changed = Signal(bool)      # bagli mi
    datasets_changed = Signal()
    message = Signal(str)                  # log paneline yazilacak mesaj
    status = Signal(str)                   # durum cubugu
    busy_changed = Signal(bool)            # olcum suruyor mu

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = load_settings()
        self.instrument = None
        self.datasets: List[Dataset] = []
        self._busy = False

    # ------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self.instrument is not None and self.instrument.connected

    @property
    def simulated(self) -> bool:
        return bool(self.settings.get("simulate"))

    @property
    def busy(self) -> bool:
        return self._busy

    def set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busy_changed.emit(value)

    def log(self, text: str) -> None:
        log.info(text)
        self.message.emit(text)

    # ------------------------------------------------------------------
    def connect_instrument(self, resource: str, simulate: bool = False,
                           visa_library: str = "") -> str:
        self.disconnect_instrument()
        self.instrument = create_instrument(resource, simulate=simulate)
        idn = self.instrument.connect(visa_library)
        self.settings["resource"] = resource
        self.settings["simulate"] = simulate
        self.settings["visa_library"] = visa_library
        self.log(f"Baglandi: {idn}")
        self.connection_changed.emit(True)
        self.status.emit(f"Bagli: {resource}")
        return idn

    def disconnect_instrument(self) -> None:
        if self.instrument is not None:
            try:
                self.instrument.close()
            except Exception as exc:  # pragma: no cover
                self.log(f"Kapatma hatasi: {exc}")
            self.instrument = None
            self.connection_changed.emit(False)
            self.status.emit("Bagli degil")
            self.log("Baglanti kapatildi.")

    def require_instrument(self):
        if not self.connected:
            raise RuntimeError("Once Baglanti sekmesinden cihaza baglanin "
                               "(veya simulasyon modunu secin).")
        return self.instrument

    # ------------------------------------------------------------------
    def add_dataset(self, ds: Dataset) -> None:
        self.datasets.append(ds)
        self.datasets_changed.emit()
        self.log(f"Olcum eklendi: {ds.label} ({len(ds)} nokta)")

    def remove_dataset(self, index: int) -> None:
        if 0 <= index < len(self.datasets):
            ds = self.datasets.pop(index)
            self.datasets_changed.emit()
            self.log(f"Olcum silindi: {ds.label}")

    def dataset(self, index: int) -> Optional[Dataset]:
        if 0 <= index < len(self.datasets):
            return self.datasets[index]
        return None

    # ------------------------------------------------------------------
    def smu_config(self, overrides: Optional[dict] = None) -> SmuConfig:
        """Ayarlardan SmuConfig uretir."""
        s = self.settings
        cfg = SmuConfig(
            channel=s.get("channel", "a"),
            source_func=s.get("source_func", "voltage"),
            compliance=float(s.get("compliance", 1e-3)),
            nplc=float(s.get("nplc", 1.0)),
            filter_count=int(s.get("filter_count", 1)),
            four_wire=bool(s.get("four_wire", False)),
            low_range_i=float(s.get("low_range_i", 1e-9)),
            auto_zero=s.get("auto_zero", "auto"),
            high_capacitance=bool(s.get("high_capacitance", False)),
        )
        for k, v in (overrides or {}).items():
            setattr(cfg, k, v)
        return cfg

    def save(self) -> None:
        try:
            save_settings(self.settings)
        except OSError as exc:  # pragma: no cover
            self.log(f"Ayarlar kaydedilemedi: {exc}")
