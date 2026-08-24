"""UV fotodedektor analiz fonksiyonlari.

Iki olcumun (karanlik / UV altinda) karsilastirilmasi, fotoakim farki ve
standart fotodedektor basarim parametreleri burada hesaplanir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np

from .dataset import Dataset

# Fiziksel sabitler
Q_E = 1.602176634e-19      # C
H_PLANCK = 6.62607015e-34  # J*s
C_LIGHT = 2.99792458e8     # m/s


# --------------------------------------------------------------------------
# Yardimcilar
# --------------------------------------------------------------------------
def photon_energy_ev(wavelength_nm: float) -> float:
    """Dalga boyundan foton enerjisi (eV). E = 1239.84 / lambda[nm]."""
    return (H_PLANCK * C_LIGHT / (wavelength_nm * 1e-9)) / Q_E


def monotonic_xy(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """x'e gore siralar, ayni x degerlerini ortalar (interpolasyon icin)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size == 0:
        return x, y
    order = np.argsort(x, kind="stable")
    xs, ys = x[order], y[order]
    ux, inv = np.unique(xs, return_inverse=True)
    if ux.size == xs.size:
        return xs, ys
    uy = np.zeros_like(ux)
    np.add.at(uy, inv, ys)
    counts = np.bincount(inv, minlength=ux.size)
    return ux, uy / counts


def interpolate_to(ds: Dataset, v_grid: np.ndarray) -> np.ndarray:
    """Veri setinin akimini verilen gerilim eksenine tasir."""
    x, y = monotonic_xy(ds.v, ds.i)
    if x.size == 0:
        return np.full_like(np.asarray(v_grid, dtype=float), np.nan)
    return np.interp(np.asarray(v_grid, dtype=float), x, y, left=np.nan, right=np.nan)


def common_voltage_grid(a: Dataset, b: Dataset, points: int = 0) -> np.ndarray:
    """Iki olcumun ortak gerilim araligi icin eksen uretir.

    Nokta sayisi verilmezse yogun olan olcumun kendi noktalari kullanilir.
    """
    xa, _ = monotonic_xy(a.v, a.i)
    xb, _ = monotonic_xy(b.v, b.i)
    if xa.size == 0 or xb.size == 0:
        return np.empty(0)
    lo = max(xa.min(), xb.min())
    hi = min(xa.max(), xb.max())
    if hi <= lo:
        return np.empty(0)
    if points > 0:
        return np.linspace(lo, hi, int(points))
    base = xa if xa.size >= xb.size else xb
    grid = base[(base >= lo) & (base <= hi)]
    return grid if grid.size >= 2 else np.linspace(lo, hi, 101)


# --------------------------------------------------------------------------
# Karanlik / aydinlik karsilastirmasi
# --------------------------------------------------------------------------
@dataclass
class Comparison:
    """Iki I-V egrisinin ortak eksende karsilastirmasi."""

    v: np.ndarray
    i_dark: np.ndarray
    i_light: np.ndarray
    i_photo: np.ndarray          # I_light - I_dark
    ratio: np.ndarray            # |I_light| / |I_dark|  (on/off)
    dark_name: str = "karanlik"
    light_name: str = "isik"

    def at(self, bias: float) -> Dict[str, float]:
        """Belirli bir bias geriliminde degerleri dondurur."""
        if self.v.size == 0:
            return {}
        idx = int(np.nanargmin(np.abs(self.v - bias)))
        return {
            "bias_V": float(self.v[idx]),
            "i_dark_A": float(self.i_dark[idx]),
            "i_light_A": float(self.i_light[idx]),
            "i_photo_A": float(self.i_photo[idx]),
            "on_off_ratio": float(self.ratio[idx]),
        }


def compare(dark: Dataset, light: Dataset, points: int = 0) -> Comparison:
    """Karanlik ve aydinlik I-V egrilerini ortak eksende karsilastirir."""
    grid = common_voltage_grid(dark, light, points)
    i_d = interpolate_to(dark, grid)
    i_l = interpolate_to(light, grid)
    i_ph = i_l - i_d
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.abs(i_l) / np.abs(i_d)
    return Comparison(v=grid, i_dark=i_d, i_light=i_l, i_photo=i_ph, ratio=ratio,
                      dark_name=dark.label, light_name=light.label)


def subtract(a: Dataset, b: Dataset, points: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    """Genel amacli fark: (a - b) akimi, ortak gerilim ekseninde."""
    grid = common_voltage_grid(a, b, points)
    return grid, interpolate_to(a, grid) - interpolate_to(b, grid)


# --------------------------------------------------------------------------
# Fotodedektor basarim parametreleri
# --------------------------------------------------------------------------
@dataclass
class DetectorMetrics:
    bias_v: float = 0.0
    i_dark: float = float("nan")
    i_light: float = float("nan")
    i_photo: float = float("nan")
    on_off_ratio: float = float("nan")
    photosensitivity: float = float("nan")      # (I_light - I_dark)/I_dark
    responsivity: float = float("nan")          # A/W
    eqe_percent: float = float("nan")           # %
    detectivity: float = float("nan")           # Jones (cm*Hz^0.5/W)
    nep: float = float("nan")                   # W/Hz^0.5
    gain: float = float("nan")                  # fotoiletken kazanc
    photon_energy_ev: float = float("nan")
    optical_power_w: float = float("nan")
    area_cm2: float = float("nan")
    wavelength_nm: float = float("nan")
    warnings: list = field(default_factory=list)

    def as_rows(self) -> list:
        """(etiket, deger metni) listesi - tablo gosterimi icin."""
        def f(x, unit="", fmt="{:.4g}"):
            if x is None or (isinstance(x, float) and not np.isfinite(x)):
                return "-"
            return (fmt.format(x) + (f" {unit}" if unit else "")).strip()

        return [
            ("Bias gerilimi", f(self.bias_v, "V")),
            ("Karanlik akim I_dark", f(self.i_dark, "A")),
            ("Aydinlik akim I_light", f(self.i_light, "A")),
            ("Fotoakim I_ph = I_light - I_dark", f(self.i_photo, "A")),
            ("Ac/Kapa orani |I_light/I_dark|", f(self.on_off_ratio)),
            ("Fotoduyarlilik (I_ph/I_dark)", f(self.photosensitivity)),
            ("Dalga boyu", f(self.wavelength_nm, "nm")),
            ("Foton enerjisi", f(self.photon_energy_ev, "eV")),
            ("Optik guc", f(self.optical_power_w, "W")),
            ("Aktif alan", f(self.area_cm2, "cm²")),
            ("Duyarlilik R", f(self.responsivity, "A/W")),
            ("EQE", f(self.eqe_percent, "%")),
            ("Kazanc G", f(self.gain)),
            ("Dedektivite D*", f(self.detectivity, "Jones")),
            ("NEP", f(self.nep, "W/Hz^0.5")),
        ]


def detector_metrics(
    i_dark: float,
    i_light: float,
    wavelength_nm: Optional[float] = None,
    optical_power_w: Optional[float] = None,
    area_cm2: Optional[float] = None,
    bias_v: float = 0.0,
) -> DetectorMetrics:
    """Tek bir bias noktasi icin fotodedektor parametrelerini hesaplar.

    D* shot-gurultu (karanlik akim) sinirli varsayimla hesaplanir:
        D* = R * sqrt(A) / sqrt(2 q I_dark)
    """
    m = DetectorMetrics(bias_v=bias_v, i_dark=i_dark, i_light=i_light)
    m.i_photo = i_light - i_dark
    if i_dark != 0:
        m.on_off_ratio = abs(i_light) / abs(i_dark)
        m.photosensitivity = (abs(i_light) - abs(i_dark)) / abs(i_dark)
    else:
        m.warnings.append("I_dark = 0, oran hesaplanamadi.")

    if wavelength_nm:
        m.wavelength_nm = float(wavelength_nm)
        m.photon_energy_ev = photon_energy_ev(float(wavelength_nm))
    if area_cm2:
        m.area_cm2 = float(area_cm2)

    if optical_power_w and optical_power_w > 0:
        m.optical_power_w = float(optical_power_w)
        m.responsivity = abs(m.i_photo) / float(optical_power_w)
        if wavelength_nm:
            e_ph = m.photon_energy_ev * Q_E              # J
            m.eqe_percent = 100.0 * m.responsivity * e_ph / Q_E
            m.gain = m.eqe_percent / 100.0
        if area_cm2 and i_dark != 0:
            noise = np.sqrt(2.0 * Q_E * abs(i_dark))     # A/Hz^0.5
            m.detectivity = m.responsivity * np.sqrt(float(area_cm2)) / noise
            m.nep = noise / m.responsivity if m.responsivity else float("nan")
        elif not area_cm2:
            m.warnings.append("Aktif alan girilmedi; D* hesaplanamadi.")
    else:
        m.warnings.append("Optik guc girilmedi; R, EQE ve D* hesaplanamadi.")

    return m


def metrics_from_comparison(
    cmp_: Comparison,
    bias_v: float,
    wavelength_nm: Optional[float] = None,
    optical_power_w: Optional[float] = None,
    area_cm2: Optional[float] = None,
) -> DetectorMetrics:
    """Karsilastirmadan secilen bias noktasinda parametreleri hesaplar."""
    pt = cmp_.at(bias_v)
    if not pt:
        return DetectorMetrics(warnings=["Ortak gerilim araligi bulunamadi."])
    return detector_metrics(
        i_dark=pt["i_dark_A"],
        i_light=pt["i_light_A"],
        wavelength_nm=wavelength_nm,
        optical_power_w=optical_power_w,
        area_cm2=area_cm2,
        bias_v=pt["bias_V"],
    )


# --------------------------------------------------------------------------
# Diyot parametreleri (ln I - V bolgesinden)
# --------------------------------------------------------------------------
def diode_parameters(v: np.ndarray, i: np.ndarray,
                     v_min: float = 0.1, v_max: float = 0.5,
                     temperature_k: float = 300.0) -> Dict[str, float]:
    """Ileri besleme dogrusal bolgesinden idealite faktoru ve I0.

    ln(I) = ln(I0) + qV / (n k T)  -> egimden n, kesim noktasindan I0.
    """
    v = np.asarray(v, dtype=float)
    i = np.asarray(i, dtype=float)
    mask = (v >= v_min) & (v <= v_max) & (i > 0) & np.isfinite(i)
    out = {"ideality": float("nan"), "i0": float("nan"),
           "barrier_height_ev": float("nan"), "points": int(mask.sum())}
    if mask.sum() < 3:
        return out
    slope, intercept = np.polyfit(v[mask], np.log(i[mask]), 1)
    kt_q = 1.380649e-23 * temperature_k / Q_E
    if slope > 0:
        out["ideality"] = float(1.0 / (slope * kt_q))
    out["i0"] = float(np.exp(intercept))
    return out


def rectification_ratio(v: np.ndarray, i: np.ndarray, bias: float = 1.0) -> float:
    """|I(+bias)| / |I(-bias)| dogrultma orani."""
    x, y = monotonic_xy(v, i)
    if x.size < 2 or bias > x.max() or -bias < x.min():
        return float("nan")
    ip = float(np.interp(bias, x, y))
    im = float(np.interp(-bias, x, y))
    return abs(ip) / abs(im) if im != 0 else float("nan")


# --------------------------------------------------------------------------
# Zaman tepkisi (foto-anahtarlama) analizi
# --------------------------------------------------------------------------
@dataclass
class TransientMetrics:
    i_off: float = float("nan")
    i_on: float = float("nan")
    on_off_ratio: float = float("nan")
    rise_time_s: float = float("nan")     # %10 -> %90
    fall_time_s: float = float("nan")     # %90 -> %10
    n_cycles: int = 0
    warnings: list = field(default_factory=list)

    def as_rows(self) -> list:
        def f(x, unit=""):
            if x is None or (isinstance(x, float) and not np.isfinite(x)):
                return "-"
            return f"{x:.4g} {unit}".strip()

        return [
            ("Kapali (karanlik) akim", f(self.i_off, "A")),
            ("Acik (UV) akim", f(self.i_on, "A")),
            ("Ac/Kapa orani", f(self.on_off_ratio)),
            ("Yukselme suresi (10-90%)", f(self.rise_time_s, "s")),
            ("Dusme suresi (90-10%)", f(self.fall_time_s, "s")),
            ("Algilanan cevrim sayisi", str(self.n_cycles)),
        ]


def light_spans(ds: Dataset) -> list:
    """Meta verideki isik olaylarindan (t, 0/1) golgelenecek araliklari uretir."""
    events = ds.settings.get("light_events") or []
    if not events:
        return []
    t_end = float(ds.t[-1]) if ds.t.size else 0.0
    spans, start = [], None
    for t, state in sorted(events, key=lambda e: e[0]):
        if int(state) == 1 and start is None:
            start = float(t)
        elif int(state) == 0 and start is not None:
            spans.append((start, float(t)))
            start = None
    if start is not None:
        spans.append((start, t_end))
    return spans


def _interp_cross(t: np.ndarray, y: np.ndarray, level: float, k: int) -> float:
    """k-1 ile k ornekleri arasinda `level` seviyesinin gecildigi zaman."""
    if k <= 0:
        return float(t[0])
    y0, y1 = float(y[k - 1]), float(y[k])
    if y1 == y0:
        return float(t[k])
    frac = (level - y0) / (y1 - y0)
    return float(t[k - 1] + frac * (t[k] - t[k - 1]))


def _cross_forward(t: np.ndarray, y: np.ndarray, level: float,
                   start: int, above: bool) -> Optional[float]:
    """`start` indeksinden ileri dogru ilk seviye gecisi."""
    seg = y[start:]
    idx = np.where(seg >= level)[0] if above else np.where(seg <= level)[0]
    if idx.size == 0:
        return None
    return _interp_cross(t, y, level, int(start + idx[0]))


def _cross_backward(t: np.ndarray, y: np.ndarray, level: float,
                    end: int, above: bool) -> Optional[float]:
    """`end` indeksinden geri dogru son seviye gecisi."""
    seg = y[:end + 1]
    idx = np.where(seg >= level)[0] if above else np.where(seg <= level)[0]
    if idx.size == 0:
        return None
    k = int(idx[-1])
    return _interp_cross(t, y, level, min(k + 1, t.size - 1))


def transient_metrics(t: np.ndarray, i: np.ndarray,
                      smooth: int = 1) -> TransientMetrics:
    """UV ac/kapa cevrimlerinden yukselme/dusme sureleri ve on/off orani.

    Sinyalin mutlak degeri kullanilir (ters bias'ta akim negatiftir).
    Kenarlar sinyalin %50 seviyesinden otomatik bulunur.
    """
    m = TransientMetrics()
    t = np.asarray(t, dtype=float)
    y = np.abs(np.asarray(i, dtype=float))
    if t.size < 10:
        m.warnings.append("Yeterli nokta yok.")
        return m

    if smooth and smooth > 1:
        k = int(smooth)
        kernel = np.ones(k) / k
        y = np.convolve(y, kernel, mode="same")

    lo = float(np.percentile(y, 10))
    hi = float(np.percentile(y, 90))
    m.i_off, m.i_on = lo, hi
    if lo > 0:
        m.on_off_ratio = hi / lo
    if hi - lo <= 0:
        m.warnings.append("Isik ac/kapa gecisi algilanamadi.")
        return m

    mid = lo + 0.5 * (hi - lo)
    above = y > mid
    edges = np.diff(above.astype(int))
    rise_idx = np.where(edges == 1)[0]
    fall_idx = np.where(edges == -1)[0]
    m.n_cycles = int(min(rise_idx.size, fall_idx.size))

    lvl10 = lo + 0.1 * (hi - lo)
    lvl90 = lo + 0.9 * (hi - lo)

    rise_times, fall_times = [], []
    for r in rise_idx:
        # yukselen kenar: %10 gecisi kenardan once, %90 gecisi kenardan sonra
        t10 = _cross_backward(t, y, lvl10, int(r), above=False)
        t90 = _cross_forward(t, y, lvl90, int(r), above=True)
        if t10 is not None and t90 is not None and t90 > t10:
            rise_times.append(t90 - t10)
    for f_ in fall_idx:
        # dusen kenar: %90 gecisi kenardan once, %10 gecisi kenardan sonra
        t90 = _cross_backward(t, y, lvl90, int(f_), above=True)
        t10 = _cross_forward(t, y, lvl10, int(f_), above=False)
        if t10 is not None and t90 is not None and t10 > t90:
            fall_times.append(t10 - t90)

    if rise_times:
        m.rise_time_s = float(np.median(rise_times))
    if fall_times:
        m.fall_time_s = float(np.median(fall_times))
    if not rise_times and not fall_times:
        m.warnings.append("Kenar bulunamadi; ornekleme araligini kucultun.")
    return m
