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
        "Keithley 2636 <-> Adapter Box C 10 kablolama haritasi — laboratuvarda "
        "kurulu ve LabVIEW ile dogrulanmis duzen. Degistirirseniz bu dosyayi "
        "guncelleyin; program bu tabloyu Baglanti sekmesinde gosterir."
    ),
    "olcum_tipi": "2 uclu (local sense), Kanal A",
    "baglantilar": [
        {"smu": "Kanal A HI (triax merkez)", "kablo": "2600-ALG-2 kirmizi klips",
         "kutu": "BNC1 merkez", "uc": "Prob 1 — numune 1. kontak",
         "not": "Kaynak/olcum yuksek ucu. Gerilim isareti buna gore: +V => HI, LO'ya gore pozitif"},
        {"smu": "Kanal A LO (triax merkez)", "kablo": "2600-ALG-2 kirmizi klips",
         "kutu": "BNC2 merkez", "uc": "Prob 2 — numune 2. kontak",
         "not": "Akim donus yolu"},
        {"smu": "Kanal A dis ekran (sasi)", "kablo": "2600-ALG-2 yesil klips",
         "kutu": "CASE", "uc": "Olcum hucresi govdesi",
         "not": "Ekran topraklamasi. Toprak dongusunu onlemek icin YALNIZCA "
                "tek kablodan baglanir"},
        {"smu": "Kanal A GUARD (ic ekran)", "kablo": "2600-ALG-2 siyah klips",
         "kutu": "— (baglanmaz)", "uc": "Yalitilmis, havada",
         "not": "GUARD, HI ile ayni gerilimde surulen bir cikistir. LO'ya, "
                "yesile, BNC govdesine veya numuneye ASLA degdirmeyin. "
                "BNC ile guard tasinmadigi icin kablo sizintisi triaks "
                "baglantiya gore yuksektir (pA seviyesi gerekiyorsa "
                "triaks-triaks kabloya gecin)"},
        {"smu": "Kanal A SENSE HI / SENSE LO", "kablo": "triaks",
         "kutu": "— (kullanilmiyor)", "uc": "Prob 3 / Prob 4",
         "not": "Yalnizca 4 uclu (remote sense) olcumde baglanir; bu duzende "
                "programda '4 uclu' kutucugu KAPALI kalmalidir"},
        {"smu": "Kanal B", "kablo": "2600-ALG-2",
         "kutu": "— (kullanilmiyor)", "uc": "Ikinci numune veya kapi (gate)",
         "not": "Iki terminalli fotodedektor icin gerekli degil"},
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
