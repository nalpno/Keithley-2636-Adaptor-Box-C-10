# Donanim kurulumu ve kablolama

Bu belge fotograflardaki duzene gore hazirlanmistir:
Keithley 2636 (SourceMeter) → USB-3488A USB/GPIB arabirimi → PC,
ve Keithley → Adapter Box C 10 → prob istasyonu (numune).

> **Onemli:** Adapter Box C 10'un ic baglantilari (on panel konnektoru → hucre
> icindeki PCB pedi) kutuya ozeldir. Ilk kurulumda **her hattin surekliligini
> multimetre ile dogrulayin** (gerilim uygulamadan once). Asagidaki tablo
> onerilen bir duzendir; kendi kutunuza gore `config/wiring.json` dosyasini
> guncelleyin, program bu dosyayi Baglanti sekmesinde gosterir.

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
| BNC | `BNC1`, `BNC2` (ikiser adet) | Osiloskop / darbe kaynagi |
| SMA | `SMA1 … SMA4` | Yuksek frekans |
| `CASE` | kirmizi muz | Hucre govdesi / ekran toprak |
| `VAKUUM` | pnomatik hizli baglanti | Numune tutucu vakumu |
| `INTERLOCK` | DB9 | Kapak/guvenlik devresi |

UV fotodedektor olcumleri icin **triaks (TRX) uclari** kullanilmalidir: pA–nA
seviyesindeki fotoakimlar ancak guard'li triaks hatlarla gurultusuz olcusur.

---

## 3. Keithley 2636 arka paneli

Her kanalda (A ve B) dort triaks konnektor vardir:

```
SENSE HI      HI      LO      SENSE LO          (GUARD = ic ekran)
```

- **HI**: kaynak/olcum yuksek ucu (merkez iletken = FORCE, ic ekran = GUARD)
- **LO**: dusuk uc (donus yolu)
- **SENSE HI / SENSE LO**: yalnizca 4 uclu (remote sense) olcumde kullanilir

Elinizdeki **2600-ALG-2** kablolar (triaks → timsah agizli) tam bu is icindir.
Kablo ucundaki iletkenler:

| Kablo ucu | Anlami | Nereye |
|---|---|---|
| Merkez iletken | FORCE / HI (veya LO) | Numune kontagi |
| Ic ekran | GUARD | **Bagli birakilmaz**, kisa devre yapilmaz |
| Dis ekran | Ekran / sasi | `CASE` veya kutu toprak |

> GUARD ucunu asla HI veya LO'ya kisa devre etmeyin; SMU'yu zorlar.

---

## 4. Onerilen baglanti — 2 uclu (local sense) fotodedektor

Iki terminalli bir UV fotodedektor icin en pratik duzen:

| Keithley 2636 | Kablo | Adapter Box C 10 | Numune |
|---|---|---|---|
| Kanal A **HI** | 2600-ALG-2 | `TRX1` | Prob 1 → ust kontak (anot) |
| Kanal A **LO** | 2600-ALG-2 | `TRX2` | Prob 2 → alt kontak (katot) |
| Sasi / toprak | muz kablo | `CASE` | Hucre govdesi |

Hucre icindeki PCB uzerinde `TRX1`, `TRX2` … olarak isaretli pedler,
fotograftaki kisa jumper kablolarla ilgili prob koluna baglanir.

Bu duzende Baglanti sekmesinde **4 uclu (remote sense) kapali** olmalidir.

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

## 7. GPIB baglantisi (USB-3488A)

1. USB-3488A surucusunu ve VISA kutuphanesini kurun (4PP programinda zaten
   kullandiginiz kurulum yeterlidir).
2. Keithley 2636 on panelinden GPIB adresini kontrol edin
   (`MENU → COMMUNICATION → GPIB → ADDRESS`), fabrika degeri **26**.
3. Arabirim `GPIB0` ise VISA kaynak adresi: `GPIB0::26::INSTR`.
4. Programda **Baglanti → Kaynaklari tara** ile adresi dogrulayabilirsiniz.

Alternatifler: cihazin LAN portu (`TCPIP0::<ip>::inst0::INSTR`) veya
USB (`USB0::0x05E6::0x2636::INSTR`) — program her ucunu de destekler.

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
