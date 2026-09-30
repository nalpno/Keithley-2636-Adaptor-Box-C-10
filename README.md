# UV Fotodedektor Olcum Arayuzu — Keithley 2636 + Adapter Box C 10

Keithley 2636 SourceMeter'i **USB, LAN veya GPIB** uzerinden yoneten, UV
fotodedektor karakterizasyonu icin hazirlanmis masaustu arayuz.

> **Surum 2 (bu dal: `claude/win11-v2-osiloskop`)** — v1'in tum ozelliklerine
> ek olarak **5. sekme: Osiloskop Darbe Analizi**. Keithley 3390 kare dalgasiyla
> darbelenen UV lamba altinda, Thorlabs AMP120 ciktisinin osiloskop (Rigol
> DS3100 vb.) CSV kaydindan **tepki suresi, fotoakim, duyarlilik, EQE, NEP ve
> D\*** hesaplar. Ilk dort sekme v1 ile aynidir.
>
> v1 `claude/inspiring-newton-m7ggeg` dalinda **degismeden** durur. Iki surumu
> yan yana kullanmak icin v2'yi **ayri bir klasore** indirin (bkz.
> [v2 kurulumu](#v2-kurulumu-v1in-yanina)).

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
- **(v2)** Osiloskop CSV'sinden **darbe analizi**: periyot/frekans/doluluk,
  %10–%90 yukselme/dusme (tek tek kenarlar + cevrim ortalamasi), ustel zaman
  sabitleri, lamba→sinyal gecikmesi, fotoakim (I = V/G), R, EQE, gurultu,
  SNR, NEP, D\*
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

### 2. Programi indirin (git ile — onerilen)

ZIP indirip her seferinde klasore acmak yerine bir kez `git clone` yapin;
sonraki guncellemeler tek tikla gelir.

**Git kurulu degilse:** <https://git-scm.com/download/win> → kurulumda tum
varsayilanlar kabul edilebilir.

Komut istemini acin (Baslat > `cmd`) ve calistirin:

```bat
cd /d C:\
git clone -b claude/inspiring-newton-m7ggeg https://github.com/nalpno/Keithley-2636-Adaptor-Box-C-10.git Keithley_2636_adaptor_box_C_10
cd Keithley_2636_adaptor_box_C_10
```

Bu, kodu `C:\Keithley_2636_adaptor_box_C_10` klasorune indirir. Depo ozel ise
GitHub kullanici adi/parolasi (veya tarayici ile oturum) sorulur.

**Sonraki guncellemeler:** klasordeki **`guncelle.bat`** dosyasina cift
tiklayin — `git pull` yapar ve gerekirse paketleri gunceller. Elle yapmak
isterseniz:

```bat
cd /d C:\Keithley_2636_adaptor_box_C_10
git pull
```

> Bir klasorde hizlica komut istemi acmak icin: Dosya Gezgini'nde o klasoru
> acin, adres cubuguna `cmd` yazip Enter'a basin.

Git kullanmak istemezseniz: GitHub'da dal listesinden
`claude/inspiring-newton-m7ggeg` secilir → **Code → Download ZIP**.

### v2 kurulumu (v1'in yanina)

v1 zaten `C:\Keithley_2636_adaptor_box_C_10` klasorunde kuruluysa ona
dokunmadan v2'yi ikinci bir klasore indirin:

```bat
cd /d C:\
git clone -b claude/win11-v2-osiloskop https://github.com/nalpno/Keithley-2636-Adaptor-Box-C-10.git Keithley_v2
cd Keithley_v2
kurulum.bat
```

Sonra `C:\Keithley_v2\baslat.bat` v2'yi, eski klasordeki `baslat.bat` v1'i
acar. Iki klasorun `guncelle.bat` dosyalari yalnizca kendi surumunu gunceller.
(ADLINK GPIB icin v2 klasorunde de bir kez `gpib-kurulum.bat` calistirin.)
Ayarlar (`%USERPROFILE%\.uvpd_keithley\settings.json`) ortaktir; v2'nin
ekledigi alanlari v1 yok sayar.

Git olmadan: GitHub'da dal listesinden `claude/win11-v2-osiloskop` → **Code →
Download ZIP**, ayri bir klasore acin, `kurulum.bat`.

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

### 4. Baglantiyi test edin

Cihazi USB ile takip acin, sonra **`test-baglanti.bat`** dosyasini calistirin.
Betik VISA kaynaklarini tarar, cihaza baglanir ve kimligini (`*IDN?`) okur —
**cikisi acmaz**, yani numune icin risk yoktur:

```bat
python baglanti_testi.py                 # kaynak tara + bagla + kimlik oku
python baglanti_testi.py --olcum         # ek olarak guvenli olcum testi (±0.1 V, 1 mA limit)
python baglanti_testi.py --kaynak "USB0::0x05E6::0x2636::<seri>::INSTR"
```

`--olcum` cikisi kisa sureligine acar; **numune bagli degilken** (acik devre)
beklenen sonuc pA seviyesinde akimdir.

### 5. Once simulasyonla deneyin

**`baslat-simulasyon.bat`** — cihaz baglamadan arayuzu, taramayi ve analizleri
denemenizi saglar. Buradaki her sey calisiyorsa kurulum tamamdir.

### 6. Cihazla calistirin

Keithley'i baglayip **`baslat.bat`** dosyasini calistirin, ardindan `Baglanti`
sekmesinden `Kaynaklari tara` → `Bagla`.

> **Python icin ayrica bir VISA arayuzu gerekir.** LabVIEW'in calisiyor olmasi
> yetmez; LabVIEW kendi surucusunu kullanir. Baglanti sekmesindeki
> **🔍 VISA teshis** dugmesi neyin eksik oldugunu soyler.
>
> - **USB ile:** Keithley I/O Layer (KIOL) veya NI-VISA kurun (Python ile ayni
>   bit genisliginde). Adres: `USB0::0x05E6::0x2636::<seri-no>::INSTR`
> - **LAN ile:** surucu gerekmez — `pip install pyvisa-py`, VISA kutuphanesi
>   alanina `@py`, kaynak `TCPIP0::<ip>::inst0::INSTR`
> - **GPIB (ADLINK USB-3488A) ile:** NI-VISA/KIOL bu adaptoru **goremez**.
>   **`gpib-kurulum.bat`** calistirin (pyvisa-py + gpib-ctypes kurar ve
>   baglantiyi dener); VISA kutuphanesi `@py`, kaynak `GPIB0::26::INSTR`
>
> Ayrinti: [docs/hardware_setup.md](docs/hardware_setup.md) bolum 7.

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
| `Could not locate a VISA implementation` | Bu PC'de VISA yok. **Baglanti → 🔍 VISA teshis** dugmesine basin, rapor hangi adimin eksik oldugunu soyler. Ozet: USB icin Keithley I/O Layer veya NI-VISA kurun; LAN icin `pip install pyvisa-py` + `@py` yeterlidir. Ayrinti: [docs/hardware_setup.md](docs/hardware_setup.md) bolum 7 |
| `Kaynaklari tara` bos donuyor | Cihaz acik ve kablo takili mi? USB'de Keithley I/O Layer / NI-VISA kurulu mu? GPIB'de cihaz adresi dogru mu (`MENU → COMMUNICATION → GPIB`)? **🔍 VISA teshis** raporunu okuyun |
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

### 5 · Osiloskop Darbe Analizi (v2)

Cihaz baglantisi **gerekmez**; osiloskoptan alinan CSV dosyasiyla calisir.

**Duzen:** Keithley 3390 kare dalga → UV lamba surucusu ve osiloskop **CH1**;
fotodedektor → **Thorlabs AMP120** (akim → gerilim) → osiloskop **CH2**.

1. **Osiloskop CSV dosyasi ac…** (veya dosyayi pencereye surukleyin). Rigol
   DS1000Z/DS2000/DS3100/DS4000 bicimleri (`X,CH1,CH2` + birim satiri veya
   `Start/Increment`) ve `Time(s),CH1(V)` gibi basliklar okunur; mV/µs gibi
   birimler SI'ya cevrilir.
2. **Kanallar:** sinyal = CH2 (AMP120), referans = CH1 (lamba surusu).
   Referans kaydetmediyseniz "(yok — sinyalin kendisi)" secin; kenarlar sinyalden
   bulunur (bu durumda gecikme olculemez).
3. **Yukseltec:** AMP120 kazanci **1e5 V/A** (100 kV/A). Osiloskop girisi
   **50 Ω** ise kutucugu isaretleyin — AMP120'nin 50 Ω cikis direnci yuzunden
   etkin kazanc **yariya** iner. Osiloskop girisi 1 MΩ ise isaretlemeyin.
   CH2 **AC kuplajli** ise (ekranda `CH2 ~`) "DC kuplajli" kutucugunu bos
   birakin: mutlak seviye kaybolur, fotoakim **genlikten (ΔV)** hesaplanir.
4. **Isik ve dedektor:** dalga boyu, **dedektore dusen** optik guc, aktif alan.
   Keithley I–V olcumunden ayni bias'taki karanlik akimi girerseniz shot-gurultu
   D\* de hesaplanir.
5. **Analiz et** — dosya acilinca otomatik de yapilir.

**Gosterimler:** dalga formu (lamba acik alanlar mor, V_on/V_off cizgileri,
%50 gecisleri), ortalama kenarlar (normalize, %10/%90 isaretli), ortalama darbe
(bir periyot), tek tek kenar sureleri.

**Cikti:** rapor (.txt), kenar tablosu (.csv — her kenarin t10/t50/t90, sure,
gecikme), ortalama dalga (.csv), grafik (.png/.pdf), tabloyu panoya kopyala
(Excel'e yapistirilir).

**Nasil hesaplanir:**

- **Kenarlar** referans kanaldan bulunur: 5 noktali medyan filtre + histerezisli
  esik (tek orneklik sicramalar ve kenar titresimi elenir), kenar zamani %50
  gecisi (interpolasyonlu).
- **Seviyeler:** her yarim periyodun son %30'u (plato payi) ortalanir;
  V_on/V_off tum cevrimlerin ortancasidir.
- **Yukselme/dusme (%10–%90):** her kenar kendi onceki ve sonraki platosuna gore
  olculur (tek tek kenarlar: ort ± std). Ayrica kenarlar **sinyalin kendi %50
  noktasina hizalanip** ortalanir (tetik titresimi ortalamayi genisletmez) —
  tabloda "cevrim ortalamasi" satiri budur ve gurultuye en dayanikli degerdir.
- **Ustel uydurma:** ortalama kenara tek ustel τ; ikinci (yavas) bilesen
  istatistiksel olarak anlamliysa (F-testi) τ_hizli / τ_yavas ve paylari.
  Dusmede yavas bir kuyruk varsa %10–%90 suresi buna cok duyarlidir; o zaman
  τ degerlerini raporlayin.
- **Sistem siniri:** AMP120'nin bant genisligi 100 kHz → yukselme suresi
  ≈ 0.35/100 kHz ≈ **3.5 µs**. Bu deger "Sistem yukselme suresi" alaninda
  girilidir ve `t_det = √(t_olc² − t_sis²)` ile cikarilir. Olculen sure bu
  sinira yakinsa program uyarir: **dedektor daha hizli olabilir**, olcum
  yukseltecle sinirlidir.
- **Gurultu:** plato pencerelerinde egilim cikarilmis RMS. Hem tam bantta hem
  **B icinde** (FFT ile, varsayilan 100 kHz = AMP120 bandi) verilir; B disindaki
  gurultu dedektorden gelemez (yukseltec o frekanslari gecirmez), osiloskoba
  giren parazittir. NEP, D\* ve SNR **B icindeki karanlik (lamba kapali)
  gurultuyle** hesaplanir.
- **ADC cift/tek ornek ofseti:** bazi osiloskoplarda ardisik ornekler arasinda
  sabit bir fark olur (araya-girmeli ADC). Otomatik bulunur, cikarilir ve
  raporda yazilir.

| Buyukluk | Baginti |
|---|---|
| Fotoakim | `I_ph = abs(V_on − V_off) / G` |
| Duyarlilik | `R = I_ph / P_opt` |
| EQE | `R · 1239.84 / λ[nm] · 100 %` |
| Gurultu akimi | `i_n = σ_V(B) / G` |
| NEP (olculen) | `i_n / R` (W, B icinde); `/ √B` → W/√Hz |
| D\* (olculen) | `√(A·B) / NEP` (Jones) — toplam gurultuyle, alt sinir |
| D\* (shot) | `R·√A / √(2q·I_karanlik)` — karanlik akim girildiyse |
| Bant genisligi | `f₋₃dB ≈ 0.35 / t_r`, `τ ≈ t_r / 2.2` |

**Iyi kayit icin ipuclari:** osiloskop ekranina 5–20 periyot sigdirin; kenar
suresini hassas olcmek icin ayrica zaman olcegini kucultup (kenari buyutup)
ikinci bir kayit alin — yukselme suresi en az ~10 ornek icermeli. Gurultu
yuksekse osiloskopta **Average** modu veya **20 MHz bant siniri** acin, ya da
"Yumusatma" ayarini 3–5 yapin (cok buyuk degerler kenarlari yavaslatir).

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
guncelle.bat               git pull ile programi gunceller
gpib-kurulum.bat           ADLINK GPIB adaptoru icin pyvisa-py + gpib-ctypes
baslat.bat                 programi calistirir
baslat-simulasyon.bat      cihazsiz deneme modu
test-baglanti.bat          cihaz baglantisini konsoldan dogrular
run_gui.py                 arayuzu baslatir
baglanti_testi.py          baglanti testi betigi
uvpd/
  instrument.py            Keithley 2636 TSP surucusu (pyvisa)
  simulator.py             cihazsiz test icin sahte SMU (fotodiyot modeli)
  measurement.py           I-V taramasi ve zaman tepkisi motorlari
  analysis.py              karsilastirma, R/EQE/D*, rise-fall, diyot uydurma
  scope.py                 (v2) osiloskop CSV okuma ve darbe analizi
  dataset.py               veri kabi + meta verili CSV okuma/yazma
  config.py                ayarlar ve kablolama haritasi
  visa_diag.py             VISA/GPIB kurulum teshisi
  gui/                     sekmeler, canli grafik, olcum is parcacigi
    scope_tab.py           (v2) 5. sekme: osiloskop darbe analizi
config/wiring.json         kablolama haritasi (duzenlenebilir)
docs/hardware_setup.md     donanim kurulumu
tests/                     birim ve arayuz testleri
  data/                    ornek Rigol DS3100 kaydi (test verisi)
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
