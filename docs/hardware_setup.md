# Donanim kurulumu ve kablolama

Bu belge fotograflardaki duzene gore hazirlanmistir:
Keithley 2636 (SourceMeter) → PC (USB, LAN veya USB-3488A GPIB arabirimi ile;
bkz. bolum 7), ve Keithley → Adapter Box C 10 → prob istasyonu (numune).

> **Kurulu duzen:** Bolum 4'teki BNC baglantisi laboratuvarda kurulu ve
> LabVIEW ile dogrulanmis durumdadir; `config/wiring.json` bu duzeni icerir ve
> program onu Baglanti sekmesinde gosterir. Kablolamayi degistirirseniz o
> dosyayi da guncelleyin.
>
> Adapter Box C 10'un ic baglantilari (on panel konnektoru → hucre icindeki PCB
> pedi) kutuya ozeldir. Yeni bir hat kullanmadan once **surekliligini
> multimetre ile dogrulayin** (gerilim uygulamadan once).

---

## 1. Kutu sinirlari

Kutunun arkasindaki etikette yazan sinirlar **asilmamalidir**:

| Buyukluk | Sinir |
|---|---|
| U_max | 60 V DC |
| I_max | 1 A DC |

Program bu sinirlari yazilim tarafinda da kontrol eder: tarama araligi veya
limit (compliance) degeri bu degerleri asarsa olcum baslatilmaz.

---

## 2. Adapter Box C 10 on paneli

Fotograftaki on panelde su uclar bulunur:

| Grup | Uclar | Tipik kullanim |
|---|---|---|
| Muz (banana) jaklar | `B1 … B8` | Dusuk frekansli / DC baglantilar, isitici, termocift vb. |
| Triaks | `TRX1 … TRX6` | **SMU baglantilari** (dusuk akim, guard'li) |
| BNC | `BNC1`, `BNC2` (ikiser adet) | **Kullanimda:** Kanal A HI / LO (bkz. bolum 4) |
| SMA | `SMA1 … SMA4` | Yuksek frekans |
| `CASE` | kirmizi muz | Hucre govdesi / ekran toprak |
| `VAKUUM` | pnomatik hizli baglanti | Numune tutucu vakumu |
| `INTERLOCK` | DB9 | Kapak/guvenlik devresi |

Mevcut kurulumda numune `BNC1`/`BNC2` uzerinden baglidir (bolum 4). pA
seviyesindeki karanlik akimlar olculecekse guard hattini numuneye kadar tasiyan
**triaks (TRX) uclarina** gecilmelidir; nA ve ustundeki fotoakimlar icin BNC
baglantisi yeterlidir.

---

## 3. Keithley 2636 arka paneli

Her kanalda (A ve B) dort triaks konnektor vardir:

```
SENSE HI      HI      LO      SENSE LO          (GUARD = ic ekran)
```

- **HI**: kaynak/olcum yuksek ucu (merkez iletken = FORCE, ic ekran = GUARD)
- **LO**: dusuk uc (donus yolu)
- **SENSE HI / SENSE LO**: yalnizca 4 uclu (remote sense) olcumde kullanilir

Elinizdeki **2600-ALG-2** kablolar (triaks → uc timsah agizli) tam bu is icindir.
Kablonun ucundan **kirmizi, siyah ve yesil** olmak uzere uc klips cikar:

| Klips | Triaks iletkeni | Anlami | Nereye baglanir |
|---|---|---|---|
| 🔴 **Kirmizi** | merkez iletken | **FORCE / sinyal** (HI kablosunda HI, LO kablosunda LO) | Numune kontagi |
| ⚫ **Siyah** | ic ekran | **GUARD** — surulen, HI ile ayni gerilimde | **Yalitilmis birakilir** (veya guard halkasina) |
| 🟢 **Yesil** | dis ekran | Ekran / sasi toprak | `CASE` ucu — yalnizca **tek** noktadan |

> ⚠️ **GUARD (siyah) klipsi kritik.** Guard pasif bir ekran degil, HI ile ayni
> gerilimde surulen dusuk empedansli bir cikistir. LO'ya, yesil klipse,
> toprağa veya numuneye **asla degdirmeyin** — SMU'yu zorlar ve olcumu bozar.
> Kullanmayacaksaniz ucunu bantlayip yalitin, havada birakin.

**Renkleri 30 saniyede dogrulayin:** kabloyu cihazdan sokun, multimetreyi
sureklilik kademesine alin; triaks fisin **merkez pimi** ile kirmizi klips,
**ic ekran** ile siyah, **dis govde** ile yesil arasinda sureklilik olmalidir.
Farkli cikarsa asagidaki tum tarifleri kendi kablonuza gore uyarlayin.

### Klipslerle numuneye baglama (2 uclu olcum)

Iki adet 2600-ALG-2 ile:

| Kablo | Kirmizi klips | Siyah klips (GUARD) | Yesil klips |
|---|---|---|---|
| Kanal A **HI**'dan gelen | Prob 1 / ust kontak | yalitilmis, havada | `CASE` (yalnizca bu kablodan) |
| Kanal A **LO**'dan gelen | Prob 2 / alt kontak | yalitilmis, havada | bagli degil (toprak dongusu olmasin) |

Kutunun on panelindeki muz jaklara (`B1`, `B2` …) baglayacaksaniz timsah
agizlari muz kablonun metal govdesine kenetleyin; hucre icinde dogrudan prob
koluna/PCB pedine de kenetlenebilir.

> Triaks jaklara (`TRX1`, `TRX2`) baglanacaksa timsah agizli uc iş gormez;
> **triaks–triaks kablo** (Keithley 7078-TRX serisi) gerekir. Guard hattini
> numuneye kadar tasidigi icin pA seviyesindeki olcumlerde tercih edilen
> yontem budur; nA ve ustu icin timsah agizli baglanti yeterlidir.

### Ilk kurulumda kablolama testi (numuneye dokunmadan)

1. Iki kirmizi klipsi **birbirine kenetleyin** (kisa devre). Programda
   ±0.1 V, limit 1 mA ile kisa bir tarama yapin → akim limite dayanmali
   (yaklasik 1 mA duz cizgi). Cikmiyorsa hat kopuk demektir.
2. Klipsleri ayirin (acik devre), ayni taramayi tekrarlayin → akim birkac pA
   mertebesinde, gurultu seviyesinde kalmali. Buyuk bir akim goruyorsanız
   sizinti/kısa devre vardir; guard klipsinin bir yere degip degmedigine bakin.
3. Ikisi de beklendigi gibiyse numuneyi baglayin.

---

## 4. Kurulu duzen — 2 uclu (local sense), BNC uzerinden

Laboratuvarda kurulu ve LabVIEW ile dogrulanmis baglanti:

| Keithley 2636 (Kanal A) | 2600-ALG-2 klipsi | Adapter Box C 10 | Numune |
|---|---|---|---|
| **HI** merkez iletken | 🔴 kirmizi | `BNC1` merkez | Prob 1 → 1. kontak |
| **LO** merkez iletken | 🔴 kirmizi | `BNC2` merkez | Prob 2 → 2. kontak |
| Dis ekran (sasi) | 🟢 yesil | `CASE` | Hucre govdesi |
| **GUARD** (ic ekran) | ⚫ siyah | baglanmaz | yalitilmis, havada |

- Yesil klips **yalnizca tek kablodan** CASE'e baglanir; iki kablodan da
  baglanirsa toprak dongusu olusur ve gurultu artar.
- BNC merkez–govde ciftinde guard hatti tasinmaz. nA ve ustu fotoakimlar icin
  sorun degil; pA seviyesine inilecekse triaks–triaks kablo (7078-TRX serisi)
  ile `TRX1`/`TRX2` uzerinden baglanmalidir.
- Gerilim isareti: programda +V uygulandiginda `BNC1` ucu `BNC2`'ye gore
  pozitif olur. Akimin isareti beklenenin tersi cikarsa BNC1/BNC2 kablolarini
  yer degistirin.
- Bu duzende Baglanti sekmesinde **4 uclu (remote sense) kapali** olmalidir —
  SENSE uclari bagli olmadigi icin acik birakilirsa cihaz hatali okur.

### Triaks uzerinden alternatif (dusuk akim icin)

| Keithley 2636 | Kablo | Adapter Box C 10 | Numune |
|---|---|---|---|
| Kanal A **HI** | triaks–triaks | `TRX1` | Prob 1 → ust kontak (anot) |
| Kanal A **LO** | triaks–triaks | `TRX2` | Prob 2 → alt kontak (katot) |
| Sasi / toprak | muz kablo | `CASE` | Hucre govdesi |

Hucre icindeki PCB uzerinde `TRX1`, `TRX2` … olarak isaretli pedler,
fotograftaki kisa jumper kablolarla ilgili prob koluna baglanir.

## 5. 4 uclu (remote sense) olcum

Kontak/kablo direncinin onemli oldugu dusuk empedansli numunelerde:

| Keithley 2636 | Kutu | Numune |
|---|---|---|
| Kanal A HI | `TRX1` | Prob 1 (akim surme) |
| Kanal A SENSE HI | `TRX4` | Prob 3 (ayni kontak, gerilim algilama) |
| Kanal A SENSE LO | `TRX5` | Prob 4 (ayni kontak) |
| Kanal A LO | `TRX2` | Prob 2 (akim donusu) |

Prob istasyonunda dort prob kolu mevcuttur (fotograf 2), dolayisiyla bu duzen
uygulanabilir. Programda **4 uclu (remote sense)** kutucugunu isaretleyin.

> Yuksek empedansli / cok dusuk akimli fotodedektorlerde 4 uclu olcum fayda
> saglamaz, gurultuyu artirabilir. Fotoakim pA–nA seviyesindeyse 2 uclu kalin.

---

## 6. INTERLOCK

Kutunun arkasindaki `INTERLOCK` (DB9) ucu, kapak acikken cikisin
etkinlesmesini engelleyen guvenlik hattidir. Fotograf 5'teki elle lehimlenmis
DB9 fis, bu hatti kopruleyen fistir.

- Kutunun kapagi kapaliyken normal olcum yapilir.
- Koprulu fis **yalnizca** 60 V DC / 1 A siniri icinde, bilincli olarak
  kullanilmalidir.
- Interlock hattini Keithley'in **digital I/O** portuna baglarsaniz, kapak
  durumu yazilimdan da okunabilir (`Keithley2636.read_digio_bit`).

Program, olcum baslatmadan once Baglanti sekmesindeki
“INTERLOCK bagli / kapak kapali” onayini arar.

---

## 7. PC baglantisi: USB, LAN veya GPIB

Program uc baglanti yolunu da destekler. Ortak sart: Python'un bir **VISA**
arayuzu bulabilmesi. LabVIEW'in calisiyor olmasi yetmez — LabVIEW kendi
surucusunu kullanir, Python ayri bir VISA katmanina ihtiyac duyar.

> Takildiginizda: **Baglanti → 🔍 VISA teshis** dugmesi sistemi tarar ve hangi
> adimin eksik oldugunu soyler. Ayni raporu konsoldan da alabilirsiniz:
> `python -m uvpd.visa_diag`

### a) USB (en pratik)

1. Bir VISA runtime kurun — ikisinden biri yeterlidir:
   - **Keithley I/O Layer (KIOL)** — Tektronix/Keithley sitesinden, cihaza ozel,
     onerilen
   - **NI-VISA** — ni.com, ucretsiz
   Kurulum, Python ile **ayni bit genisliginde** olmalidir (64-bit Python →
   64-bit VISA). Kurulumdan sonra bilgisayari yeniden baslatin.
2. Cihazi USB (tip B) kablosuyla PC'ye baglayin.
3. Programda **Kaynaklari tara** → adres su bicimde gorunur:
   `USB0::0x05E6::0x2636::<seri-no>::INSTR`

### b) LAN (surucu kurmadan)

VISA runtime kurmak istemiyorsaniz LAN yolu saf Python ile calisir:

```bat
pip install pyvisa-py
```

- Cihazin IP adresini on panelden okuyun: `MENU → LAN → STATUS → IP-ADDRESS`
- Programda **VISA kutuphanesi** alanina `@py` yazin
- **VISA kaynagi** alanina elle girin: `TCPIP0::<ip>::inst0::INSTR`

### c) GPIB (USB-3488A)

1. USB-3488A surucusunu kurun (NI-488.2 uyumlu `gpib-32.dll` saglar).
2. Cihazin GPIB adresini kontrol edin
   (`MENU → COMMUNICATION → GPIB → ADDRESS`), fabrika degeri **26**.
3. Sistemde VISA yoksa: `pip install pyvisa-py gpib-ctypes`, VISA kutuphanesi
   alanina `@py`.
4. Kaynak adresi: `GPIB0::26::INSTR`

> USB-3488A bir National Instruments karti degildir; NI-VISA onu goremeyebilir.
> Bu durumda (c) adimindaki `@py` yolunu kullanin.

---

## 8. UV kaynagi

Isik harici bir kaynaktan verilir. Programda dalga boyu, optik guc ve aktif
alan girilir; bunlar duyarlilik (A/W), EQE ve D* hesaplarinda kullanilir.

- **Elle calisma:** Zaman tepkisi sekmesinde “UV ACIK / UV KAPALI” dugmeleri ile
  isik anlarini isaretlersiniz; program bu anlari veriye kaydeder.
- **Otomatik cevrim:** UV kaynagi veya shutter Keithley'in digital I/O hattina
  bagliysa, program isigi otomatik ac/kapa edip yukselme/dusme surelerini
  cikarabilir (`digio.writebit`).

Optik gucu kalibre bir guc olcerle numune duzleminde olcun; girilen deger
yanlissa R, EQE ve D* degerleri de yanlis olur (I-V ve fotoakim etkilenmez).

---

## 9. Dusuk akim olcumu icin ipuclari

| Sorun | Cozum |
|---|---|
| Gurultulu / gezinen akim | NPLC'yi 5–10 yapin, filtre sayisini 5–10'a cikarin |
| Sizinti akimi | Triaks kullanin, GUARD'i bagli birakin, `CASE`'i topraklayin |
| Yavas olcum | NPLC'yi 0.1–1 yapin, otomatik kademe alt sinirini yukseltin |
| Sifir kaymasi | Auto-zero “Otomatik” kalsin |
| Kapasitif numunede salinim | “Yuksek kapasite modu”nu acin, adim beklemeyi artirin |
| Isik sizmasi | Karanlik olcum sirasinda hucre kapagini ortun |
