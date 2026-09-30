# UV Fotodedektor Olcum Arayuzu — **Windows XP surumu**

Keithley 2636B + Adapter Box C 10 ile UV fotodedektor I–V ve zaman tepkisi
olcumleri icin arayuz. Bu dal (`claude/winxp-python34`), laboratuvardaki
**Windows XP Professional SP3** bilgisayar icin hazirlanmis ayri bir surumdur.

Modern surum (Windows 10/11, PyQt5) `claude/inspiring-newton-m7ggeg` dalindadir
ve bu daldan etkilenmez.

## Bu surumun ozelligi: hicbir paket kurulmaz

| | Modern surum | **XP surumu** |
|---|---|---|
| Python | 3.9+ | **3.4.4 (32-bit)** |
| Arayuz | PyQt5 + matplotlib | **Tkinter** (Python ile birlikte gelir) |
| Hesaplama | numpy | **saf Python** |
| Cihaz haberlesmesi | pyvisa / pyvisa-py / gpib-ctypes | **gpib-32.dll / visa32.dll dogrudan (ctypes)** |
| `pip install` | gerekli | **gerekmez — internet de gerekmez** |

Olcum dosyalari (CSV) iki surumde **ayni bicimdedir**: XP'de alinan olcum
yeni PC'de, yeni PC'de alinan XP'de acilir.

---

## 1. Python 3.4.4 kurulumu

### Neden bu surum?

- **Python 3.4.4, Windows XP'yi destekleyen son Python surumudur** ve
  Windows kurulum dosyasi yayinlanmis son 3.4 surumudur. Python 3.5 ve
  sonrasi XP'de calismaz.
- **32-bit** olmali. "Windows XP Professional Version 2002" 32-bit bir
  isletim sistemidir (64-bit XP "Version 2003" olarak gorunur). Bilgisayarin
  4 GB yerine **3.45 GB** RAM gostermesi de 32-bit isletim sisteminin
  isaretidir.

### Indirme baglantisi

**https://www.python.org/ftp/python/3.4.4/python-3.4.4.msi**
(32-bit Windows yukleyicisi, ~24 MB)

Surum sayfasi: https://www.python.org/downloads/release/python-344/

> **Dikkat: XP'nin tarayicisi python.org ve GitHub'i acamaz** (bu siteler XP'nin
> desteklemedigi TLS 1.2 ister).** Dosyayi **modern bilgisayarda indirip USB
> bellekle** XP'ye tasiyin. Ayni sey program dosyalari icin de gecerli.
>
> `-amd64.msi` ile biten dosyayi **indirmeyin**; o 64-bit surumdur ve XP'de
> calismaz.

### Kurulum adimlari

1. `python-3.4.4.msi` dosyasina cift tiklayin.
2. **"Install for all users"** secin → Next.
3. Klasor: **`C:\Python34\`** (varsayilani degistirmeyin) → Next.
4. Bilesen listesinde:
   - **Tcl/Tk** bileseni **secili kalmali** (varsayilan olarak secilidir —
     arayuz bunu kullanir, kaldirmayin).
   - Istege bagli: **"Add python.exe to Path"** secilebilir. Secilmese de
     program `C:\Python34`'u kendisi bulur.
5. Finish.

---

## 2. Programi XP'ye kopyalama

1. **Modern bilgisayarda** GitHub'da depoyu acin, dal listesinden
   **`claude/winxp-python34`** secin → **Code → Download ZIP**.
2. ZIP'i USB bellekle XP'ye tasiyin.
3. **ZIP'i mutlaka ayiklayin:** ZIP dosyasina sag tiklayin → **Tumunu Ayikla**
   (Extract All) → ornegin **`C:\Keithley_XP`**. ZIP'in icine girip
   oradaki `.bat` dosyasina cift tiklamak **calismaz** — XP o dosyayi tek
   basina calistirir, programin diger dosyalari yaninda olmaz.

Git kurmak gerekmez. Guncelleme gerektiginde ayni adimlari tekrarlayin
(`ayarlar_xp.json` ve `olcumler\` klasorunu yedekleyip yenisinin icine
kopyalayin).

---

## 3. Calistirma

Klasordeki `.bat` dosyalarina cift tiklayin:

| Dosya | Ne yapar |
|---|---|
| **`teshis.bat`** | Ilk calistirilacak dosya. Python surumunu, GPIB/VISA surucusunu ve bagli cihazlari kontrol eder, ne yapilacagini yazar. |
| **`test-baglanti.bat`** | Cihaza baglanir, kimligini okur. **Cikisi acmaz.** |
| **`baslat.bat`** | Programi baslatir. |
| `baslat-simulasyon.bat` | Cihaz olmadan deneme. |
| `testleri-calistir.bat` | Programin kendi testlerini XP uzerinde calistirir. |

Siyah konsol penceresi program acikken acik kalir; hata olursa mesaj orada
gorunur ve pencere siz bir tusa basana kadar kapanmaz. **Kapatmayin.**

Beklenmeyen her hata ayrica program klasorundeki **`hata_kaydi.txt`**
dosyasina yazilir; sorun bildirirken bu dosyayi gondermeniz yeterli.

### Ilk baglanti

1. **LabVIEW'i kapatin** — ayni GPIB cihazini iki program ayni anda
   kullanamaz.
2. `teshis.bat` → raporda `gpib-32.dll : BASARILI ['GPIB0::26::INSTR']`
   gibi bir satir gormelisiniz.
3. `baslat.bat` → **Baglanti** sekmesi:
   - **Arayuz:** Otomatik (veya GPIB)
   - **Kaynak:** `GPIB0::26::INSTR` (ya da **Kaynaklari tara**)
   - **Bagla** → Keithley'in on panelinde **REM** yazisi yanar.
4. **SMU ayarlari:** Kanal A, gerilim kaynagi, **4 uclu KAPALI**
   (BNC1/BNC2 duzeninde SENSE uclari bagli degildir), limit `1e-3` A.
5. **INTERLOCK bagli / kapak kapali** kutucugunu isaretleyin.

Kablolama: [docs/hardware_setup.md](docs/hardware_setup.md) — kurulu ve
LabVIEW ile dogrulanmis BNC1/BNC2 duzeni bolum 4'te.

---

## 4. Ozellikler

Modern surumle ayni olcum ve analizler:

- **I–V taramasi** — gerilim veya akim kaynagi, tek/cift yon, tekrar, canli grafik
  (dogrusal / log|I|).
- **Ikili olcum (karanlik → UV)** — karanlik tarama, "UV kaynagini acin"
  uyarisi, UV taramasi, otomatik karsilastirma.
- **Zaman tepkisi** — elle UV ac/kapa isaretleme veya digital I/O ile
  otomatik shutter; yukselme/dusme sureleri, ac/kapa orani.
- **Karsilastirma** — I_ph = I_UV − I_karanlik, R (A/W), EQE, D\*, NEP,
  idealite faktoru, dogrultma orani.
- **Acil durdurma** — pencerenin sag ustunde, **her sekmeden** erisilebilir.
- **Guvenlik** — 60 V / 1 A sinirlari ve interlock onayi olmadan olcum baslamaz.

### XP surumune ozgu farklar

- **Rapor (.txt)** uc sutunludur: `Parametre / Deger / Birim`. Deger sutunu
  saf sayidir; Excel'de *Veri > Metinden*, ayirici **Sekme** ile acin.
- **Tablolarda Ctrl+C** secili satirlari (secim yoksa tumunu) kopyalar.
- **Grafik** `.eps` olarak kaydedilir (PNG icin ek kutuphane gerekirdi).
  EPS dosyasi Origin, Word ve Illustrator'da acilir.
- Ayarlar programin klasorundeki `ayarlar_xp.json` dosyasinda, olcumler
  `olcumler\` klasorunde tutulur — klasor USB bellekle tasinabilir.
- Arayuz 1024×768 ekrana gore duzenlenmistir; sol paneller gerekirse kaydirilir.

### Hesaplanan buyuklukler

| Buyukluk | Baginti |
|---|---|
| Fotoakim | `I_ph = I_UV − I_karanlik` |
| Duyarlilik | `R = |I_ph| / P_opt` (A/W) |
| Kuantum verimi | `EQE = R · E_ph[eV]` (×100 → %) |
| Dedektivite | `D* = R·√A / √(2q·I_karanlik)` (Jones, shot-gurultu sinirli) |
| NEP | `√(2q·I_karanlik) / R` |

R, EQE ve D\* **Analiz bias'i** alanindaki gerilime **en yakin** olcum
noktasinda hesaplanir; kullanilan gercek bias tabloda "Bias gerilimi"
satirinda yazar.

---

## 5. Sorun giderme

| Belirti | Cozum |
|---|---|
| `.bat`'a tiklayinca pencere acilip hemen kapaniyor / hicbir sey olmuyor | ZIP ayiklanmamis (bolum 2, adim 3). Emin olmak icin: Baslat → Calistir → `cmd` → `cd C:\Keithley_XP` → `teshis.bat` yazin; pencere acik kalir ve mesaji okuyabilirsiniz. |
| `[HATA] Program dosyalari bu klasorde bulunamadi` | Ayni sebep: ZIP'in icinden calistiriliyor. Once ayiklayin. |
| `[HATA] Python 3.4 bulunamadi` | Python 3.4.4'u `C:\Python34` klasorune kurun (bolum 1). |
| Teshiste `gpib-32.dll : BASARISIZ ... yuklenemedi` | GPIB adaptorunun/kartinin XP surucusu kurulu degil. |
| `ENEB - GPIB karti bulunamadi` | USB-GPIB adaptoru takili mi? Aygit Yoneticisi'nde gorunuyor mu? |
| `ENOL - bu adreste dinleyen cihaz yok` | Keithley acik mi, GPIB kablosu takili mi, adres 26 mi? |
| `EABO - ... ZAMAN ASIMI` | LabVIEW acik olabilir, kapatin. Keithley'i kapatip acin. |
| Arayuz acilmiyor, `tkinter` hatasi | Python kurulumunda Tcl/Tk bileseni kaldirilmis; yeniden kurup secin. |
| Program penceresi ekrana sigmiyor | Pencereyi buyutun; sol panellerde kaydirma cubugu cikar. |

---

## Proje yapisi

```
baslat.bat / baslat-simulasyon.bat / test-baglanti.bat / teshis.bat / testleri-calistir.bat
program.py               arayuzu baslatir
baglanti_testi.py        konsol baglanti testi (--teshis ile surucu raporu)
run_tests.py             testleri calistirir
uvpd_xp/
  transport.py           gpib-32.dll / visa32.dll (ctypes) haberlesme katmani
  instrument.py          Keithley 2636 TSP surucusu
  simulator.py           cihazsiz test icin sahte SMU
  measurement.py         I-V taramasi ve zaman tepkisi
  analysis.py            karsilastirma, R/EQE/D*, rise/fall (saf Python)
  dataset.py             CSV okuma/yazma (modern surumle ayni bicim)
  diag.py                surucu teshisi
  console.py             XP konsolunda guvenli yazdirma
  errorlog.py            beklenmeyen hatalari hata_kaydi.txt'ye yazar
  gui/                   Tkinter arayuzu
config/wiring.json       kablolama haritasi
docs/hardware_setup.md   donanim kurulumu
tests/                   66 test (unittest; harici paket gerekmez)
```

### Dogrulama

Kod, XP'deki Python 3.4.4 ile ayni dil surumu olan **Python 3.4.10** ile
derlenip Tk 8.6 arayuzuyle test edilmistir (66 test; gercek Tk penceresinde
ikili olcum, karsilastirma, zaman tepkisi ve acil durdurma dahil). GPIB ve
VISA katmani, gercek DLL'lerin fonksiyon imzalarini taklit eden sahte
suruculerle test edilmistir. **Gercek bir XP bilgisayarinda henuz
calistirilmamistir** — ilk kullanimda `teshis.bat` ve `test-baglanti.bat`
ciktilarini kontrol edin.
