"""Olcum veri kabi ve CSV okuma/yazma.

CSV dosyalari basliginda ``#`` ile baslayan JSON meta veri blogu tasir;
boylece dosya hem Excel/Origin ile acilabilir hem de program tarafindan
tum ayarlariyla geri yuklenebilir.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

META_PREFIX = "#"
META_TAG = "UVPD-META:"

#: Isik durumu etiketleri
DARK = "dark"
LIGHT = "light"


@dataclass
class Dataset:
    """Tek bir olcumun verisi + meta bilgisi.

    Kolonlar:
        t : olcum zamani (s, olcum baslangicina gore)
        v : gerilim (V)
        i : akim (A)
    """

    name: str = "olcum"
    kind: str = "iv"                      # iv | transient
    light_state: str = DARK               # dark | light
    wavelength_nm: Optional[float] = None
    optical_power_w: Optional[float] = None      # numune uzerine dusen toplam guc
    irradiance_w_cm2: Optional[float] = None     # veya siddet
    area_cm2: Optional[float] = None             # aktif alan
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    notes: str = ""
    settings: Dict[str, Any] = field(default_factory=dict)

    t: np.ndarray = field(default_factory=lambda: np.empty(0))
    v: np.ndarray = field(default_factory=lambda: np.empty(0))
    i: np.ndarray = field(default_factory=lambda: np.empty(0))

    # ------------------------------------------------------------------
    def append(self, t: float, v: float, i: float) -> None:
        self.t = np.append(self.t, t)
        self.v = np.append(self.v, v)
        self.i = np.append(self.i, i)

    def __len__(self) -> int:
        return int(self.i.size)

    @property
    def label(self) -> str:
        parts = [self.name]
        if self.light_state == LIGHT and self.wavelength_nm:
            parts.append(f"{self.wavelength_nm:g} nm")
        elif self.light_state == DARK:
            parts.append("karanlik")
        return " – ".join(parts)

    def effective_power_w(self) -> Optional[float]:
        """Optik gucu dogrudan ya da siddet x alan uzerinden dondurur."""
        if self.optical_power_w:
            return float(self.optical_power_w)
        if self.irradiance_w_cm2 and self.area_cm2:
            return float(self.irradiance_w_cm2) * float(self.area_cm2)
        return None

    # ------------------------------------------------------------------
    def metadata(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "light_state": self.light_state,
            "wavelength_nm": self.wavelength_nm,
            "optical_power_w": self.optical_power_w,
            "irradiance_w_cm2": self.irradiance_w_cm2,
            "area_cm2": self.area_cm2,
            "timestamp": self.timestamp,
            "notes": self.notes,
            "settings": self.settings,
        }

    def to_csv(self, path: str) -> str:
        path = os.fspath(path)
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        meta = json.dumps(self.metadata(), ensure_ascii=False)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(f"{META_PREFIX} {META_TAG}{meta}\n")
            fh.write(f"{META_PREFIX} Keithley 2636 / Adapter Box C 10 - UV fotodedektor olcumu\n")
            fh.write(f"{META_PREFIX} olusturma: {self.timestamp}\n")
            fh.write("time_s,voltage_V,current_A\n")
            for t, v, i in zip(self.t, self.v, self.i):
                fh.write(f"{t:.6f},{v:.10g},{i:.10g}\n")
        return path

    @classmethod
    def from_csv(cls, path: str) -> "Dataset":
        meta: Dict[str, Any] = {}
        rows: List[List[float]] = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(META_PREFIX):
                    idx = line.find(META_TAG)
                    if idx >= 0:
                        meta = json.loads(line[idx + len(META_TAG):])
                    continue
                if line[0].isalpha():  # kolon basligi
                    continue
                parts = [p for p in line.replace(";", ",").split(",")]
                try:
                    rows.append([float(p) for p in parts[:3]])
                except ValueError:
                    continue

        arr = np.array(rows, dtype=float) if rows else np.empty((0, 3))
        ds = cls(
            name=meta.get("name", os.path.splitext(os.path.basename(path))[0]),
            kind=meta.get("kind", "iv"),
            light_state=meta.get("light_state", DARK),
            wavelength_nm=meta.get("wavelength_nm"),
            optical_power_w=meta.get("optical_power_w"),
            irradiance_w_cm2=meta.get("irradiance_w_cm2"),
            area_cm2=meta.get("area_cm2"),
            timestamp=meta.get("timestamp", ""),
            notes=meta.get("notes", ""),
            settings=meta.get("settings", {}),
        )
        if arr.size:
            ds.t, ds.v, ds.i = arr[:, 0], arr[:, 1], arr[:, 2]
        return ds


def suggest_filename(ds: Dataset, directory: str = ".") -> str:
    """Olcumden anlamli bir dosya adi uretir."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in ds.name).strip("_") or "olcum"
    tag = "karanlik" if ds.light_state == DARK else (
        f"{ds.wavelength_nm:g}nm" if ds.wavelength_nm else "isik")
    return os.path.join(directory, f"{stamp}_{safe}_{ds.kind}_{tag}.csv")
