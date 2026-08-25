#!/usr/bin/env python3
"""Keithley 2636 baglanti testi (konsol).

GUI'ye gecmeden once cihaz iletisimini adim adim dogrular. Varsayilan olarak
CIKIS ACILMAZ — yalnizca cihazla konusulur.

Kullanim:
    python baglanti_testi.py                 # kaynak tara + bagla + kimlik oku
    python baglanti_testi.py --kaynak "USB0::0x05E6::0x2636::4037576::INSTR"
    python baglanti_testi.py --olcum         # ek olarak guvenli olcum testi yapar
    python baglanti_testi.py --simulate      # cihazsiz deneme
"""

from __future__ import annotations

import argparse
import sys
import time

from uvpd.instrument import SmuConfig, create_instrument
from uvpd.visa_diag import BACKEND_DEFAULT, BACKEND_PY, try_backend

SEP = "-" * 66


def baslik(text: str) -> None:  # pragma: no cover - konsol suslemesi
    print(f"\n{SEP}\n{text}\n{SEP}")


def kaynaklari_bul(library: str):
    """Once verilen backend, olmazsa @py ile kaynak listeler.

    Doner: (kutuphane, kaynaklar, visa_calisiyor)
    ``visa_calisiyor`` VISA katmaninin yuklenip yuklenmedigini soyler; bu,
    "VISA yok" ile "VISA var ama cihaz gorunmuyor" durumlarini ayirir.
    """
    ok, result = try_backend(library)
    if ok:
        print(f"  [ok] VISA katmani yuklendi ({library or 'sistem VISA'}).")
        return library, list(result), True
    print(f"  [!] '{library or 'sistem VISA'}' basarisiz: {result}")
    if library != BACKEND_PY:
        ok, result = try_backend(BACKEND_PY)
        if ok:
            print("  [i] pyvisa-py (@py) calisti.")
            return BACKEND_PY, list(result), True
        print(f"  [!] pyvisa-py de basarisiz: {result}")
    return library, [], False


def cihaz_gorunmuyor_yardimi() -> None:
    """VISA calisiyor ama hicbir cihaz listelenmiyorsa yol gosterir."""
    print("\n  VISA katmani CALISIYOR fakat hicbir cihaz gorunmuyor.")
    print("  Yani KIOL/NI-VISA kurulumu tamam; eksik olan cihazin PC'ye")
    print("  taninmasi. Sirasiyla kontrol edin:\n")
    print("   1. Keithley'in on panel ekrani acik mi? (cihaz enerjili olmali)")
    print("   2. USB kablosu cihazin arkasindaki KARE (tip B) porta takili mi?")
    print("      LAN/TSP-Link portlari degil.")
    print("   3. Kablo veri kablosu mu? Bazi kablolar yalnizca sarj icindir;")
    print("      baska bir USB kablosuyla deneyin.")
    print("   4. Aygit Yoneticisi'ni acin (Win+X > Aygit Yoneticisi):")
    print("      'USB Test and Measurement Devices' altinda Keithley gorunmeli.")
    print("      Sari unlem varsa surucu yuklenmemis demektir.")
    print("   5. KIOL kurulumundan sonra bilgisayar yeniden baslatildi mi?")
    print("      Baslatilmadiysa once onu yapin, sonra cihazi takin.")
    print("   6. KIOL ile gelen 'Keithley Communicator' programini acin:")
    print("      cihaz orada da gorunmuyorsa sorun Python'da degil, Windows")
    print("      surucu tarafindadir.\n")
    print("  Adresi biliyorsaniz taramayi atlayabilirsiniz (seri numarasi")
    print("  cihazin arkasindaki etikette yazar):")
    print('      python baglanti_testi.py --kaynak "USB0::0x05E6::0x2636::<seri-no>::INSTR"\n')
    print("  LAN kablosu takmak da bir secenek:")
    print("      pip install pyvisa-py")
    print('      python baglanti_testi.py --kutuphane @py --kaynak "TCPIP0::<ip>::inst0::INSTR"')
    print("  (IP adresi: cihaz on paneli > MENU > LAN > STATUS > IP-ADDRESS)")


def ayarlari_kaydet(kaynak: str, library: str) -> None:
    """Calisan baglanti ayarini programin ayar dosyasina yazar.

    Boylece arayuz acildiginda ayni kaynak/kutuphane hazir gelir.
    """
    try:
        from uvpd.config import SETTINGS_PATH, load_settings, save_settings

        ayarlar = load_settings()
        ayarlar["resource"] = kaynak
        ayarlar["visa_library"] = library
        ayarlar["simulate"] = False
        save_settings(ayarlar)
        print(f"\n  [i] Bu ayar programa kaydedildi ({SETTINGS_PATH}):")
        print(f"      VISA kaynagi     : {kaynak}")
        print(f"      VISA kutuphanesi : {library or '(sistem VISA)'}")
        print("      Arayuz acildiginda hazir gelecek.")
    except Exception as exc:  # pragma: no cover
        print(f"  [!] Ayar kaydedilemedi: {exc}")


def komut_metni(args, kaynak: str, library: str, ek: str = "") -> str:
    """Kullanicinin tekrar calistirabilecegi tam komutu uretir."""
    parcalar = ["python baglanti_testi.py"]
    if library:
        parcalar.append(f"--kutuphane {library}")
    if kaynak:
        parcalar.append(f'--kaynak "{kaynak}"')
    if args.kanal != "a":
        parcalar.append(f"--kanal {args.kanal}")
    if ek:
        parcalar.append(ek)
    return " ".join(parcalar)


def kaynak_sec(kaynaklar):
    """Listeden Keithley'e en cok benzeyen kaynagi secer."""
    for r in kaynaklar:
        u = str(r).upper()
        if "0X05E6" in u or "2636" in u:      # Keithley VID / model
            return str(r)
    for onek in ("USB", "GPIB", "TCPIP"):
        for r in kaynaklar:
            if str(r).upper().startswith(onek):
                return str(r)
    return str(kaynaklar[0]) if kaynaklar else ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Keithley 2636 baglanti testi")
    ap.add_argument("--kaynak", default="", help="VISA kaynak adresi (bos = otomatik sec)")
    ap.add_argument("--kutuphane", default=BACKEND_DEFAULT,
                    help="VISA kutuphanesi (bos = sistem VISA, @py = pyvisa-py)")
    ap.add_argument("--kanal", default="a", choices=["a", "b"], help="SMU kanali")
    ap.add_argument("--olcum", action="store_true",
                    help="Cikisi kisa sureligine acip guvenli bir olcum testi yapar")
    ap.add_argument("--limit", type=float, default=1e-3, help="Akim limiti (A), varsayilan 1e-3")
    ap.add_argument("--gerilim", type=float, default=0.1,
                    help="Olcum testinde uygulanacak gerilim (V), varsayilan 0.1")
    ap.add_argument("--kaydetme", action="store_true",
                    help="Basarili baglanti ayarini programa kaydetme")
    ap.add_argument("--simulate", action="store_true", help="Cihazsiz simulasyon")
    args = ap.parse_args(argv)

    baslik("1) VISA kaynaklari taraniyor")
    if args.simulate:
        library, kaynaklar, visa_ok = "", ["SIM::UVPD::INSTR"], True
    else:
        library, kaynaklar, visa_ok = kaynaklari_bul(args.kutuphane)

    for r in kaynaklar:
        print(f"  - {r}")

    if not kaynaklar and not args.kaynak:
        if visa_ok:
            cihaz_gorunmuyor_yardimi()
        else:
            print("\n  VISA katmani yuklenemedi — cihazdan once bunu cozmek gerekir.")
            print("  Ayrintili teshis icin:  python -m uvpd.visa_diag")
        return 1

    # Kaynak elle verildiyse tarama bos donse bile denenir
    kaynak = args.kaynak or kaynak_sec(kaynaklar)
    if args.kaynak and not kaynaklar:
        print("  (Tarama bos dondu; verilen adres dogrudan denenecek.)")
    print(f"\n  Secilen kaynak : {kaynak}")
    print(f"  VISA kutuphane : {library or '(sistem VISA)'}")

    baslik("2) Cihaza baglaniliyor")
    inst = create_instrument(kaynak, simulate=args.simulate)
    try:
        idn = inst.connect(library)
    except Exception as exc:
        print(f"  BASARISIZ: {exc}\n")
        print("  Kontrol listesi:")
        print("   - Cihaz acik mi, USB kablosu takili mi?")
        print("   - KIOL/NI-VISA kurulumundan sonra bilgisayar yeniden baslatildi mi?")
        print("   - Kaynak adresi dogru mu? (yukaridaki listeden birini --kaynak ile verin)")
        return 1
    print(f"  BAGLANDI\n  Kimlik (*IDN?): {idn}")

    parcalar = [p.strip() for p in idn.split(",")]
    if len(parcalar) >= 3:
        print(f"    Uretici : {parcalar[0]}")
        print(f"    Model   : {parcalar[1]}")
        print(f"    Seri no : {parcalar[2]}")

    if not args.simulate and not args.kaydetme:
        ayarlari_kaydet(kaynak, library)

    try:
        baslik("3) Hata kuyrugu")
        hatalar = inst.check_errors()
        print("  Temiz." if not hatalar else "  " + "\n  ".join(hatalar))

        if not args.olcum:
            baslik("SONUC")
            print("  Iletisim calisiyor. Cikis acilmadi.\n")
            print("  Olcum zincirini de denemek icin (kablolar sokukken):")
            print(f"      {komut_metni(args, kaynak, library, '--olcum')}\n")
            print("  Arayuzu baslatmak icin:  baslat.bat")
            return 0

        baslik("4) Olcum testi (cikis kisa sureligine acilir)")
        print(f"  Kanal      : {args.kanal.upper()}")
        print(f"  Akim limiti: {args.limit:g} A")
        print(f"  Gerilim    : 0 V ve ±{abs(args.gerilim):g} V")
        print("\n  UYARI: Numune bagliysa bu gerilim numuneye uygulanir.")
        print("  Acik devre (kablolar sokuk) testinde beklenen: pA seviyesinde akim.")
        print("  Kisa devre testinde beklenen: akim limite dayanir.\n")

        cfg = SmuConfig(channel=args.kanal, source_func="voltage",
                        compliance=args.limit, nplc=1.0, four_wire=False,
                        autorange=True, low_range_i=1e-9)
        inst.apply_config(cfg)
        inst.output_on()
        time.sleep(0.3)
        for seviye in (0.0, abs(args.gerilim), -abs(args.gerilim), 0.0):
            i, v = inst.set_level_and_measure(seviye, settle_s=0.2)
            print(f"    V_ayar = {seviye:+7.3f} V   ->   V_olculen = {v:+12.6g} V   "
                  f"I = {i:+12.6g} A")
        inst.output_off()
        print("\n  Cikis kapatildi.")

        hatalar = inst.check_errors()
        if hatalar:
            print("  Cihaz hata kuyrugu: " + " | ".join(hatalar))

        baslik("SONUC")
        print("  Olcum zinciri calisiyor. Artik programi baslatabilirsiniz:")
        print("      baslat.bat   (veya  python run_gui.py )\n")
        print("  Arayuzde Baglanti sekmesinde su degerler hazir gelmeli:")
        print(f"      VISA kaynagi     : {kaynak}")
        print(f"      VISA kutuphanesi : {library or '(sistem VISA)'}")
        return 0
    finally:
        try:
            inst.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
