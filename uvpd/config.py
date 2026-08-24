"""Uygulama ayarlarinin diske kaydedilmesi ve kablolama haritasi."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

APP_DIR = os.path.join(os.path.expanduser("~"), ".uvpd_keithley")
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIRING_PATH = os.path.join(PROJECT_DIR, "config", "wiring.json")

DEFAULTS: Dict[str, Any] = {
    "resource": "GPIB0::26::INSTR",
    "visa_library": "",            # bos = varsayilan VISA; "@py" = pyvisa-py
    "simulate": False,
    "channel": "a",
    "data_dir": os.path.join(os.path.expanduser("~"), "UVPD_olcumleri"),
    "sample_name": "numune",
    "wavelength_nm": 365.0,
    "optical_power_w": 2.0e-6,
    "area_cm2": 0.04,
    "source_func": "voltage",
    "compliance": 1.0e-3,
    "nplc": 1.0,
    "filter_count": 1,
    "four_wire": False,
    "low_range_i": 1.0e-9,
    "auto_zero": "auto",
    "high_capacitance": False,
    "sweep": {"start": -2.0, "stop": 2.0, "points": 101, "dual": False,
              "repeat": 1, "settle_time": 0.05},
    "transient": {"bias": 1.0, "duration": 60.0, "interval": 0.1},
    "interlock_confirmed": False,
}


def load_settings(path: str = SETTINGS_PATH) -> Dict[str, Any]:
    """Kayitli ayarlari yukler; eksik anahtarlar varsayilanla tamamlanir."""
    data = dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(data.get(k), dict):
                merged = dict(data[k])
                merged.update(v)
                data[k] = merged
            else:
                data[k] = v
    except (OSError, ValueError):
        pass
    return data


def save_settings(settings: Dict[str, Any], path: str = SETTINGS_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------
DEFAULT_WIRING = {
    "aciklama": (
        "Keithley 2636 <-> Adapter Box C 10 kablolama haritasi. "
        "Kendi duzeninize gore duzenleyin; program bu tabloyu Baglanti "
        "sekmesinde gosterir."
    ),
    "baglantilar": [
        {"smu": "Kanal A FORCE HI (triax)", "kablo": "2600-ALG-2",
         "kutu": "TRX1", "uc": "Prob 1 (numune ust kontak)",
         "not": "Merkez iletken = FORCE/HI, ic ekran = GUARD, dis ekran = LO/sasi"},
        {"smu": "Kanal A LO (triax)", "kablo": "2600-ALG-2",
         "kutu": "TRX2", "uc": "Prob 2 (numune alt/karsi kontak)",
         "not": "2 uclu (local sense) olcum icin yeterli"},
        {"smu": "Kanal A SENSE HI", "kablo": "triax", "kutu": "TRX4",
         "uc": "Prob 3", "not": "Yalnizca 4 uclu (remote sense) olcumde kullanin"},
        {"smu": "Kanal A SENSE LO", "kablo": "triax", "kutu": "TRX5",
         "uc": "Prob 4", "not": "Yalnizca 4 uclu olcumde kullanin"},
        {"smu": "Kanal B (opsiyonel)", "kablo": "2600-ALG-2",
         "kutu": "TRX3 / B3-B4", "uc": "Ikinci numune veya kapi (gate)",
         "not": "Iki terminalli fotodedektor icin gerekli degil"},
        {"smu": "Sasi / toprak", "kablo": "muz kablo",
         "kutu": "CASE", "uc": "Olcum hucresi govdesi",
         "not": "Dusuk akim olcumlerinde gurultuyu azaltir"},
        {"smu": "Interlock", "kablo": "DB9 koprulu fis",
         "kutu": "INTERLOCK", "uc": "-",
         "not": "Kutu kapagi kapali degilse cikis aktiflesmez; koprulu fis "
                "yalnizca 60 V DC / 1 A sinirlari icinde kullanilmalidir"},
    ],
    "limitler": {"u_max_v": 60.0, "i_max_a": 1.0},
}


def load_wiring(path: str = WIRING_PATH) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return DEFAULT_WIRING


def save_wiring(wiring: Dict[str, Any], path: str = WIRING_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(wiring, fh, indent=2, ensure_ascii=False)
