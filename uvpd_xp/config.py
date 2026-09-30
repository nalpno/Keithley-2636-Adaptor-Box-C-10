# -*- coding: utf-8 -*-
"""Ayarlarin kaydi ve kablolama haritasi.

Ayarlar program klasorundeki ``ayarlar_xp.json`` dosyasina yazilir (USB
bellekle tasinabilir). Klasor yazilamazsa kullanici klasoru kullanilir.
"""

import io
import json
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIRING_PATH = os.path.join(PROJECT_DIR, "config", "wiring.json")
_LOCAL_SETTINGS = os.path.join(PROJECT_DIR, "ayarlar_xp.json")
_HOME_SETTINGS = os.path.join(os.path.expanduser("~"), ".uvpd_keithley_xp", "settings.json")

DEFAULTS = {
    "resource": "GPIB0::26::INSTR",
    "backend": "auto",
    "channel": "a",
    "data_dir": os.path.join(PROJECT_DIR, "olcumler"),
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


def settings_path():
    """Yazilabilir ayar dosyasi yolu."""
    if os.path.exists(_LOCAL_SETTINGS):
        return _LOCAL_SETTINGS
    try:
        with io.open(_LOCAL_SETTINGS, "a", encoding="utf-8"):
            pass
        os.remove(_LOCAL_SETTINGS)
        return _LOCAL_SETTINGS
    except (IOError, OSError):
        return _HOME_SETTINGS


def load_settings(path=None):
    path = path or settings_path()
    data = json.loads(json.dumps(DEFAULTS))      # derin kopya
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(data.get(k), dict):
                data[k].update(v)
            else:
                data[k] = v
    except (IOError, OSError, ValueError):
        pass
    return data


def save_settings(settings, path=None):
    path = path or settings_path()
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    text = json.dumps(settings, indent=2, ensure_ascii=True, sort_keys=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(u"" + text)
    return path


def load_wiring(path=WIRING_PATH):
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (IOError, OSError, ValueError):
        return {"baglantilar": [], "limitler": {"u_max_v": 60.0, "i_max_a": 1.0}}
