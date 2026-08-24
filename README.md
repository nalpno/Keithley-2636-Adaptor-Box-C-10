# UV Fotodedektor Olcum Arayuzu — Keithley 2636 + Adapter Box C 10

Keithley 2636 SourceMeter'i GPIB (USB-3488A) uzerinden yoneten, UV
fotodedektor karakterizasyonu icin hazirlanmis masaustu arayuz.

**Ne yapar:**

- Gerilim uygulayip akim olcer (**V → I**) veya akim uygulayip gerilim olcer (**I → V**)
- **I–V karakteristigini** canli grafikle cikarir (tek yon / cift yon / tekrarli)
- **Karanlik ve UV altinda** alinan iki olcumu ortak gerilim ekseninde
  karsilastirir, **fotoakimi (I_ph = I_UV − I_karanlik)** cikarir
- Duyarlilik **R (A/W)**, **EQE (%)**, **dedektivite D\* (Jones)**, **NEP**,
  **ac/kapa orani**, **fotoduyarlilik** hesaplar (dalga boyu ve optik guc girilir)
- **Zaman tepkisi** (UV ac/kapa) kaydeder; **yukselme/dusme sureleri (%10–%90)**
  ve on/off oranini bulur
- Idealite faktoru **n**, doyma akimi **I₀** ve dogrultma oranini hesaplar
- Her olcumu meta verisiyle birlikte **CSV** olarak kaydeder, grafik **PNG/PDF**
  ve metin **rapor** cikartir
- Cihaz olmadan denemek icin **simulasyon modu** icerir

---

## Kurulum (Windows — laboratuvar PC'si)

### 1. Python

Kurulu degilse <https://www.python.org/downloads/> adresinden **Python 3.9+**
kurun. Kurulum ekraninda **“Add python.exe to PATH”** kutucugunu isaretlemeyi
unutmayin. Kontrol:

```bat
python --version
```

### 2. Programi indirin

Git varsa:

```bat
git clone -b claude/inspiring-newton-m7ggeg https://github.com/nalpno/Keithley-2636-Adaptor-Box-C-10.git
cd Keithley-2636-Adaptor-Box-C-10
```

Git yoksa: GitHub'da depo sayfasinda dal (branch) listesinden
`claude/inspiring-newton-m7ggeg` secilir → **Code → Download ZIP** → indirilen
dosya bir klasore cikarilir.

### 3. Paketleri kurun

Klasordeki **`kurulum.bat`** dosyasina cift tiklayin. Bu dosya:

- `.venv` adinda yalitilmis bir Python ortami olusturur (sistem Python'unuzu
  ve 4PP programini etkilemez),
- `numpy`, `matplotlib`, `pyvisa`, `PyQt5` paketlerini kurar,
- VISA/GPIB kurulumunu kontrol edip bulunan cihaz adreslerini yazar.

Elle yapmak isterseniz:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Once simulasyonla deneyin

**`baslat-simulasyon.bat`** — cihaz baglamadan arayuzu, taramayi ve analizleri
denemenizi saglar. Buradaki her sey calisiyorsa kurulum tamamdir.

### 5. Cihazla calistirin

USB-3488A'yi ve Keithley'i baglayip **`baslat.bat`** dosyasini calistirin,
ardindan `Baglanti` sekmesinden `Kaynaklari tara` → `Bagla`.

> GPIB surucusu (USB-3488A) ve VISA kutuphanesi ayrica kurulmalidir; 4PP
> programinda kullandiginiz kurulum yeterlidir, yeniden kurmaniza gerek yoktur.

### Linux / macOS

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_gui.py --simulate     # deneme
python run_gui.py                # cihazla
```

### Kurulum sorunlari

| Belirti | Cozum |
|---|---|
| `'python' is not recognized` | Python PATH'e eklenmemis; Python'u “Add to PATH” isaretli olarak yeniden kurun |
| `Could not locate a VISA implementation` | VISA kutuphanesi yok/gorunmuyor: NI-VISA, Keysight IO Libraries veya MCC VISA kurulu olmali (4PP icin kullandiginiz hangisiyse) |
| `Kaynaklari tara` bos donuyor | USB-3488A kablosu/surucusu, cihazin acik olmasi ve GPIB adresi kontrol edilir (cihaz on paneli: `MENU → COMMUNICATION → GPIB`) |
| Birden fazla VISA kurulu, yanlisi kullaniliyor | Baglanti sekmesindeki **VISA kutuphanesi** alanina DLL yolunu yazin (orn. `C:\Windows\System32\visa64.dll`) |
| `PyQt5` kurulamiyor | `pip install PySide6` yeterlidir; program otomatik olarak onu kullanir |
| Grafik penceresi acilmiyor (Linux) | `sudo apt install libxcb-xinerama0 libgl1` |

---

## Kullanim akisi

### 1 · Baglanti ve Ayarlar

1. **VISA kaynagi**: `GPIB0::26::INSTR` (2636'nin fabrika GPIB adresi 26).
   `Kaynaklari tara` ile listeleyebilirsiniz.
2. `Bagla` — cihaz kimligi (IDN) ekranda gorunur.
3. **SMU ayarlari**: kanal (A/B), kaynak tipi, limit (compliance), NPLC,
   filtre, 4 uclu olcum, otomatik kademe alt siniri, auto-zero.
4. **Guvenlik**: `INTERLOCK bagli / kapak kapali` onayi isaretlenmeden olcum
   baslamaz. `CIKISI HEMEN KAPAT` dugmesi her an cikisi keser.
5. Alt kisimda **kablolama haritasi** (`config/wiring.json`) gosterilir.

### 2 · I–V Olcumu

- Numune adi, isik durumu (**Karanlik / UV altinda**), dalga boyu, optik guc,
  aktif alan girilir.
- Tarama: baslangic, bitis, nokta sayisi, cift yon, tekrar, adim beklemesi.
- `Taramayi baslat` — egri nokta nokta canli cizilir, `Durdur` ile her an
  kesilebilir. Y ekseni dogrusal / log|I| / symlog secilebilir.
- **`Ikili olcum (karanlik → UV)`**: once karanlik taramayi yapar, sonra
  “UV kaynagini acin” uyarisi verir, ardindan ayni taramayi UV altinda
  tekrarlar ve dogrudan **Karsilastirma** sekmesine gecip farki cikarir.
  Aradiginiz karanlik/aydinlik kiyaslamasinin en kisa yolu budur.
- Olcumler bitince otomatik olarak CSV'ye kaydedilir (veri klasoru
  `Dosya → Veri klasorunu sec` ile degistirilir).

### 3 · Zaman Tepkisi

Sabit bias altinda akim–zaman kaydi:

- Elle: kayit sirasinda `UV ACIK` / `UV KAPALI` dugmeleriyle isik anlarini
  isaretlersiniz; grafikte isikli pencereler golgelenir.
- Otomatik: UV kaynagi/shutter Keithley digital I/O hattina bagliysa program
  isigi kendisi ac/kapa eder (ilk bekleme / acik sure / kapali sure).
- Bitince yukselme suresi (%10→%90), dusme suresi (%90→%10), on/off orani ve
  (optik guc girilmisse) R, EQE, D\* tabloya yazilir.

### 4 · Karsilastirma ve Analiz

- A (karanlik) ve B (UV) olcumleri oturum listesinden veya CSV dosyasindan secilir.
- `Karsilastir ve farki cikar` — iki egri ortak gerilim ekseninde
  interpolasyonla eslestirilir (nokta sayilari farkli olsa da calisir).
- Gosterim: I–V egrileri / fotoakim / ac-kapa orani / ham fark.
- `Parametreleri hesapla` — secilen bias geriliminde tum fotodedektor
  parametreleri.
- Diyot analizi: secilen gerilim araliginda ln(I)–V uydurmasi ile **n** ve **I₀**,
  ayrica dogrultma orani.
- Cikti: fark verisi CSV, metin rapor, grafik PNG/PDF.

---

## Hesaplanan buyuklukler

| Buyukluk | Bagintii |
|---|---|
| Fotoakim | `I_ph = I_UV − I_karanlik` |
| Ac/kapa orani | `|I_UV| / |I_karanlik|` |
| Fotoduyarlilik | `(|I_UV| − |I_karanlik|) / |I_karanlik|` |
| Foton enerjisi | `E = 1239.84 / λ[nm]` eV |
| Duyarlilik | `R = I_ph / P_opt` (A/W) |
| Kuantum verimi | `EQE = R · h·c / (q·λ) = R · E[eV]` (×100 → %) |
| Dedektivite | `D* = R·√A / √(2·q·I_karanlik)` (Jones) |
| NEP | `√(2·q·I_karanlik) / R` (W/Hz^0.5) |
| Idealite | `ln I = ln I₀ + qV/(n·k·T)` egiminden |

`D*` karanlik akim shot gurultusu sinirli varsayimla hesaplanir. Optik guc
girilmezse R, EQE ve D\* hesaplanmaz (program uyari verir); fotoakim, oran ve
I–V egrileri her durumda cikarilir.

---

## Veri formati

CSV dosyalari basliginda JSON meta veri tasir; hem Excel/Origin ile acilir hem
de program tarafindan tum ayarlariyla geri yuklenir:

```
# UVPD-META:{"name": "ZnO-1", "kind": "iv", "light_state": "light",
#            "wavelength_nm": 365.0, "optical_power_w": 2e-06, ...}
time_s,voltage_V,current_A
0.000000,-2,-1.2345e-11
...
```

---

## Donanim

Kablolama, triaks/guard baglantilari, interlock ve dusuk akim ipuclari icin:
**[docs/hardware_setup.md](docs/hardware_setup.md)**

Ozet (2 uclu olcum):

| Keithley 2636 | Kablo | Adapter Box C 10 | Numune |
|---|---|---|---|
| Kanal A HI | 2600-ALG-2 | `TRX1` | Prob 1 (ust kontak) |
| Kanal A LO | 2600-ALG-2 | `TRX2` | Prob 2 (alt kontak) |
| Sasi | muz kablo | `CASE` | Hucre govdesi |

Sinirlar: **60 V DC / 1 A DC** (kutu etiketi). Program bu sinirlari yazilimda
da denetler.

---

## Proje yapisi

```
kurulum.bat                Windows kurulum betigi
baslat.bat                 programi calistirir
baslat-simulasyon.bat      cihazsiz deneme modu
run_gui.py                 arayuzu baslatir
uvpd/
  instrument.py            Keithley 2636 TSP surucusu (pyvisa)
  simulator.py             cihazsiz test icin sahte SMU (fotodiyot modeli)
  measurement.py           I-V taramasi ve zaman tepkisi motorlari
  analysis.py              karsilastirma, R/EQE/D*, rise-fall, diyot uydurma
  dataset.py               veri kabi + meta verili CSV okuma/yazma
  config.py                ayarlar ve kablolama haritasi
  gui/                     sekmeler, canli grafik, olcum is parcacigi
config/wiring.json         kablolama haritasi (duzenlenebilir)
docs/hardware_setup.md     donanim kurulumu
tests/                     birim ve arayuz testleri
```

## Testler

```bash
python -m pytest tests -q            # arayuz testleri dahil (offscreen calisir)
```

## Notlar ve sinirlar

- 2600 serisi **TSP** (Lua) dili kullanir; surucu SCPI degil TSP komutlari gonderir.
- Tarama nokta nokta yapilir (canli grafik ve anlik durdurma icin). Cok hizli
  taramalar gerekirse cihaz ici `SweepVLinMeasureI` fonksiyonlari ile
  hizlandirma eklenebilir.
- Zaman tepkisinde en kucuk pratik ornekleme araligi GPIB gidis-gelisi ve NPLC
  ile sinirlidir (~10–20 ms). Mikrosaniye mertebesinde tepki icin osiloskop
  gerekir.
- Program ayarlari `~/.uvpd_keithley/settings.json` dosyasinda saklanir.
