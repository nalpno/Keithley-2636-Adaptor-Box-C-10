# -*- coding: utf-8 -*-
"""Keithley 2636 baglanti testi (konsol) - XP surumu.

Varsayilan olarak CIKIS ACILMAZ; yalnizca cihazla konusulur.

    python baglanti_testi.py                          # tara + bagla + kimlik oku
    python baglanti_testi.py --kaynak GPIB0::26::INSTR
    python baglanti_testi.py --arayuz visa            # visa32.dll ile dene
    python baglanti_testi.py --olcum                  # ek olarak guvenli olcum testi
    python baglanti_testi.py --simulate               # cihazsiz deneme
"""

import argparse
import os
import sys
import time

if sys.version_info[:2] < (3, 3):
    sys.stderr.write("Bu program Python 3.4 gerektirir (bulunan: %s).\n"
                     "Kurulum: https://www.python.org/ftp/python/3.4.4/python-3.4.4.msi\n"
                     % sys.version.split()[0])
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uvpd_xp import transport as tr  # noqa: E402
from uvpd_xp.config import load_settings, save_settings, settings_path  # noqa: E402
from uvpd_xp.console import make_console_safe  # noqa: E402
from uvpd_xp.instrument import SmuConfig, create_instrument  # noqa: E402

SEP = "-" * 64


def baslik(text):
    print("\n" + SEP + "\n" + text + "\n" + SEP)


def tara(arayuz):
    if arayuz == tr.BACKEND_SIM:
        return ["SIM::UVPD::INSTR"], ["simulasyon"]
    if arayuz == tr.BACKEND_GPIB:
        try:
            return tr.gpib_scan(), ["gpib-32.dll yuklendi"]
        except tr.TransportError as exc:
            return [], ["gpib-32.dll: {0}".format(exc)]
    if arayuz == tr.BACKEND_VISA:
        try:
            return tr.visa_scan(), ["visa32.dll yuklendi"]
        except tr.TransportError as exc:
            return [], ["visa32.dll: {0}".format(exc)]
    return tr.scan_all()


def main(argv=None):
    make_console_safe()
    ayar = load_settings()
    ap = argparse.ArgumentParser(description="Keithley 2636 baglanti testi (XP)")
    ap.add_argument("--kaynak", default="", help="Kaynak adresi (bos = taramada bulunan)")
    ap.add_argument("--arayuz", default=ayar.get("backend", "auto"),
                    choices=["auto", "gpib", "visa", "sim"], help="Haberlesme arayuzu")
    ap.add_argument("--kanal", default="a", choices=["a", "b"])
    ap.add_argument("--olcum", action="store_true", help="Guvenli olcum testi de yap")
    ap.add_argument("--limit", type=float, default=1e-3, help="Akim limiti (A)")
    ap.add_argument("--gerilim", type=float, default=0.1, help="Test gerilimi (V)")
    ap.add_argument("--kaydetme", action="store_true", help="Calisan ayari programa kaydetme")
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--teshis", action="store_true", help="Yalnizca surucu teshis raporunu yaz")
    args = ap.parse_args(argv)
    if args.teshis:
        from uvpd_xp.diag import diagnose
        print(diagnose().text)
        return 0
    if args.simulate:
        args.arayuz = tr.BACKEND_SIM

    print("Python {0} | {1}".format(sys.version.split()[0], sys.executable))

    baslik("1) Kaynaklar taraniyor (arayuz: {0})".format(args.arayuz))
    bulunan, notlar = tara(args.arayuz)
    for n in notlar:
        print("  [i] " + n)
    for r in bulunan:
        print("  - " + r)
    kaynak = args.kaynak or (bulunan[0] if bulunan else "")
    if not kaynak:
        print("\n  Hicbir cihaz bulunamadi.")
        print("  - Keithley acik mi, GPIB kablosu iki uctan takili mi?")
        print("  - Adres biliniyorsa:  python baglanti_testi.py --kaynak GPIB0::26::INSTR")
        print("  - Ayrintili teshis:   python -m uvpd_xp.diag   (veya teshis.bat)")
        return 1
    if args.kaynak and args.kaynak not in bulunan:
        print("  (Verilen adres taramada yok; yine de dogrudan denenecek.)")
    print("\n  Secilen kaynak: " + kaynak)

    baslik("2) Cihaza baglaniliyor")
    inst = create_instrument(kaynak, backend=args.arayuz)
    try:
        idn = inst.connect()
    except Exception as exc:
        print("  BASARISIZ: {0}".format(exc))
        return 1
    print("  BAGLANDI (arayuz: {0})".format(getattr(inst, "transport_kind", args.arayuz)))
    print("  Kimlik: " + idn)
    print("  (Keithley on panelinde 'REM' yazisi yanmali.)")

    if not args.simulate and not args.kaydetme:
        ayar["resource"] = kaynak
        ayar["backend"] = args.arayuz
        try:
            yol = save_settings(ayar, settings_path())
            print("  [i] Ayar programa kaydedildi: {0}".format(yol))
        except (IOError, OSError) as exc:
            print("  [!] Ayar kaydedilemedi: {0}".format(exc))

    try:
        baslik("3) Hata kuyrugu")
        hatalar = inst.check_errors()
        print("  Temiz." if not hatalar else "  " + "\n  ".join(hatalar))

        if not args.olcum:
            baslik("SONUC")
            print("  Iletisim calisiyor. Cikis acilmadi.")
            print("  Olcum testi icin (kablolar sokukken):")
            print("      python baglanti_testi.py --kaynak {0} --olcum".format(kaynak))
            return 0

        baslik("4) Olcum testi (cikis kisa sureligine acilir)")
        print("  Kanal {0}, limit {1:g} A, gerilim 0 ve +/-{2:g} V".format(
            args.kanal.upper(), args.limit, abs(args.gerilim)))
        print("  UYARI: numune bagliysa bu gerilim numuneye uygulanir.")
        print("  Acik devrede beklenen: pA seviyesi. Kisa devrede: akim limite dayanir.\n")
        inst.apply_config(SmuConfig(channel=args.kanal, compliance=args.limit, nplc=1.0))
        inst.output_on()
        time.sleep(0.3)
        for seviye in (0.0, abs(args.gerilim), -abs(args.gerilim), 0.0):
            i, v = inst.set_level_and_measure(seviye, 0.2)
            print("    V_ayar = {0:+7.3f} V  ->  V = {1:+12.6g} V   I = {2:+12.6g} A".format(seviye, v, i))
        inst.output_off()
        print("\n  Cikis kapatildi.")
        baslik("SONUC")
        print("  Olcum zinciri calisiyor. Programi baslatin:  baslat.bat")
        return 0
    finally:
        try:
            inst.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        from uvpd_xp.errorlog import log_exception
        _text, _path = log_exception("baglanti_testi")
        print("\n[HATA] Beklenmeyen hata:\n\n" + _text)
        if _path:
            print("Bu hata su dosyaya da yazildi: {0}".format(_path))
        sys.exit(1)
