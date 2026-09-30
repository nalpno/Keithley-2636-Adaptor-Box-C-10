# -*- coding: utf-8 -*-
"""Olcum veri kabi ve CSV okuma/yazma.

Dosya bicimi modern (Windows 10/11) surumle BIREBIR aynidir: basliktaki
``# UVPD-META:{json}`` satiri tum ayarlari tasir. XP'de alinan olcumler yeni
surumde, yeni surumde alinanlar XP'de acilabilir.
"""

import io
import json
import os
from datetime import datetime

META_PREFIX = "#"
META_TAG = "UVPD-META:"

DARK = "dark"
LIGHT = "light"


def now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class Dataset(object):
    """Tek bir olcumun verisi (t, v, i listeleri) ve meta bilgisi."""

    def __init__(self, name="olcum", kind="iv", light_state=DARK, wavelength_nm=None,
                 optical_power_w=None, irradiance_w_cm2=None, area_cm2=None,
                 timestamp=None, notes="", settings=None):
        self.name = name
        self.kind = kind                    # iv | transient
        self.light_state = light_state      # dark | light
        self.wavelength_nm = wavelength_nm
        self.optical_power_w = optical_power_w
        self.irradiance_w_cm2 = irradiance_w_cm2
        self.area_cm2 = area_cm2
        self.timestamp = timestamp or now_iso()
        self.notes = notes
        self.settings = settings if settings is not None else {}
        self.t = []
        self.v = []
        self.i = []

    def append(self, t, v, i):
        self.t.append(float(t))
        self.v.append(float(v))
        self.i.append(float(i))

    def __len__(self):
        return len(self.i)

    @property
    def label(self):
        if self.light_state == LIGHT and self.wavelength_nm:
            return "{0} - {1:g} nm".format(self.name, self.wavelength_nm)
        if self.light_state == DARK:
            return "{0} - karanlik".format(self.name)
        return self.name

    def effective_power_w(self):
        if self.optical_power_w:
            return float(self.optical_power_w)
        if self.irradiance_w_cm2 and self.area_cm2:
            return float(self.irradiance_w_cm2) * float(self.area_cm2)
        return None

    def metadata(self):
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

    # ---------------- dosya ----------------
    def to_csv(self, path):
        folder = os.path.dirname(os.path.abspath(path))
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        meta = json.dumps(self.metadata(), ensure_ascii=True)
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(u"{0} {1}{2}\n".format(META_PREFIX, META_TAG, meta))
            fh.write(u"{0} Keithley 2636 / Adapter Box C 10 - UV fotodedektor olcumu\n".format(META_PREFIX))
            fh.write(u"{0} olusturma: {1}\n".format(META_PREFIX, self.timestamp))
            fh.write(u"time_s,voltage_V,current_A\n")
            for t, v, i in zip(self.t, self.v, self.i):
                fh.write(u"{0:.6f},{1:.10g},{2:.10g}\n".format(t, v, i))
        return path

    @classmethod
    def from_csv(cls, path):
        meta = {}
        rows = []
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(META_PREFIX):
                    idx = line.find(META_TAG)
                    if idx >= 0:
                        try:
                            meta = json.loads(line[idx + len(META_TAG):])
                        except ValueError:
                            meta = {}
                    continue
                if line[0].isalpha():      # kolon basligi
                    continue
                parts = line.replace(";", ",").split(",")
                try:
                    rows.append([float(p) for p in parts[:3]])
                except ValueError:
                    continue
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
            settings=meta.get("settings", {}) or {},
        )
        for r in rows:
            if len(r) >= 3:
                ds.append(r[0], r[1], r[2])
        return ds


def suggest_filename(ds, directory="."):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if (c.isalnum() and ord(c) < 128) or c in "-_" else "_"
                   for c in ds.name).strip("_") or "olcum"
    if ds.light_state == DARK:
        tag = "karanlik"
    elif ds.wavelength_nm:
        tag = "{0:g}nm".format(ds.wavelength_nm)
    else:
        tag = "isik"
    return os.path.join(directory, "{0}_{1}_{2}_{3}.csv".format(stamp, safe, ds.kind, tag))
