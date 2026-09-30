"""Osiloskop CSV dosyalarindan darbe (pulse) tepkisi analizi.

Deney duzeni (v2):

    Keithley 3390 kare dalga ──► UV lamba surucusu   (ve osiloskop CH1)
    Fotodedektor ──► Thorlabs AMP120 (akim → gerilim) ──► osiloskop CH2

CH1 (lambayi suren kare dalga) isigin ne zaman acilip kapandigini, CH2
(AMP120 cikisi) dedektorun tepkisini verir. Akim, ``I = V / G`` ile bulunur
(G: transempedans kazanci, AMP120 icin 1e5 V/A — osiloskop girisi 50 Ω ise
AMP120'nin 50 Ω cikis direnci yuzunden etkin kazanc yariya iner).

Hesaplananlar: periyot, frekans, doluluk orani, ON/OFF seviyeleri, fotoakim
genligi, yukselme/dusme sureleri (%10–%90; tek tek kenarlar ve cevrim
ortalamasi), lamba → sinyal gecikmesi, gurultu, SNR, duyarlilik (A/W), EQE,
NEP, D*, -3 dB bant genisligi.

Rigol DS1000Z/DS2000/DS3100/DS4000 ve benzeri "X,CH1,CH2" bicimindeki CSV
dosyalari okunur (zaman sutunlu ya da Start/Increment + sira numarali).
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .analysis import Q_E, photon_energy_ev

AMP120_GAIN_V_PER_A = 1.0e5      # Thorlabs AMP120, yuksek empedansli yuk
AMP120_RISE_S = 3.5e-6           # 0.35 / 100 kHz (katalog: < 3 µs)
AMP120_BANDWIDTH_HZ = 1.0e5
AMP120_MAX_INPUT_A = 20e-6       # ±20 µA

# ============================================================================
# CSV okuma
# ============================================================================
_PREFIX = {"k": 1e3, "m": 1e-3, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
           "n": 1e-9, "p": 1e-12}
_BASE_UNITS = {"volt": "V", "volts": "V", "v": "V",
               "second": "s", "seconds": "s", "sec": "s", "s": "s",
               "amp": "A", "ampere": "A", "a": "A"}


def _unit_scale(unit: str) -> Tuple[float, str]:
    """'mV' → (1e-3, 'V'); 'Volt' → (1, 'V'); 'us' → (1e-6, 's')."""
    u = unit.strip().strip("()[]").strip()
    if u.lower() in _BASE_UNITS:
        return 1.0, _BASE_UNITS[u.lower()]
    if len(u) >= 2 and u[0] in _PREFIX and u[1:] in ("V", "s", "A"):
        return _PREFIX[u[0]], u[1:]
    return 1.0, u


_NAME_UNIT = re.compile(r"^(.*?)\s*[\(\[]([^\)\]]*)[\)\]]\s*$")


def _split(line: str, delim: str) -> List[str]:
    return [c.strip().strip('"').strip() for c in line.split(delim)]


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


@dataclass
class ScopeTrace:
    """Osiloskoptan okunan kayit: ortak zaman ekseni + kanallar (SI birimde)."""

    t: np.ndarray
    channels: Dict[str, np.ndarray]
    units: Dict[str, str] = field(default_factory=dict)
    path: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def names(self) -> List[str]:
        return list(self.channels.keys())

    @property
    def dt(self) -> float:
        if self.t.size < 2:
            return float("nan")
        return float(np.median(np.diff(self.t)))

    @property
    def duration(self) -> float:
        return float(self.t[-1] - self.t[0]) if self.t.size else 0.0

    def channel(self, name: str) -> np.ndarray:
        if name not in self.channels:
            raise ValueError(f"'{name}' kanali dosyada yok. "
                             f"Mevcut kanallar: {', '.join(self.names)}")
        return self.channels[name]

    def summary(self) -> str:
        return (f"{self.t.size} nokta, ornekleme araligi {fmt_si(self.dt, 's')}, "
                f"kayit suresi {fmt_si(self.duration, 's')}, "
                f"kanallar: {', '.join(self.names)}")


def parse_scope_text(text: str, path: str = "") -> ScopeTrace:
    """Osiloskop CSV metnini okur."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("Dosya bos.")
    delim = max((",", ";", "\t"), key=lines[0].count)
    if lines[0].count(delim) == 0:
        raise ValueError("Sutun ayirici (virgul / noktali virgul / sekme) bulunamadi.")

    header_rows: List[List[str]] = []
    start = None
    for k, ln in enumerate(lines[:60]):
        cells = [c for c in _split(ln, delim) if c != ""]
        if len(cells) >= 2 and all(_is_number(c) for c in cells):
            start = k
            break
        header_rows.append(_split(ln, delim))
    if start is None:
        raise ValueError("Sayisal veri satiri bulunamadi — bu bir osiloskop CSV'si mi?")

    data = np.genfromtxt(io.StringIO("\n".join(lines[start:])), delimiter=delim,
                         dtype=float, invalid_raise=False)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    ncol = data.shape[1]

    names = list(header_rows[0]) if header_rows else []
    names += [""] * (ncol - len(names))
    units = list(header_rows[1]) if len(header_rows) > 1 else []
    units += [""] * (max(ncol, len(names)) - len(units))
    # "CH1(V)" / "Time [ms]" gibi adlardaki birimleri ayir
    for k, nm in enumerate(names):
        m = _NAME_UNIT.match(nm)
        if m:
            names[k] = m.group(1).strip()
            if not units[k] or _is_number(units[k]):
                units[k] = m.group(2)

    notes: List[str] = []
    lower = [n.lower() for n in names]
    # Rigol DS1000Z: X sutunu sira numarasi, Start/Increment ikinci satirda
    t_start = t_inc = None
    if "start" in lower and "increment" in lower and len(header_rows) > 1:
        try:
            t_start = float(header_rows[1][lower.index("start")])
            t_inc = float(header_rows[1][lower.index("increment")])
        except (ValueError, IndexError):
            t_start = t_inc = None

    x = data[:, 0]
    if t_inc is not None:
        t = t_start + x * t_inc
        notes.append(f"Zaman ekseni Start/Increment'ten uretildi "
                     f"(adim {fmt_si(t_inc, 's')}).")
    else:
        scale, base = _unit_scale(units[0])
        if base not in ("s", ""):
            notes.append(f"Ilk sutun birimi '{units[0]}' — zaman olarak kabul edildi.")
        t = x * scale

    skip = {"start", "increment"}
    channels: Dict[str, np.ndarray] = {}
    ch_units: Dict[str, str] = {}
    for k in range(1, ncol):
        col = data[:, k]
        if k < len(lower) and lower[k] in skip:
            continue
        if np.all(np.isnan(col)):
            continue
        name = names[k] or f"Sutun{k + 1}"
        scale, base = _unit_scale(units[k] if k < len(units) else "")
        channels[name] = col * scale
        ch_units[name] = base or "V"

    good = np.isfinite(t)
    for col in channels.values():
        good &= np.isfinite(col)
    if good.sum() < 10:
        raise ValueError("Dosyada yeterli sayisal veri yok.")
    if not good.all():
        notes.append(f"{int((~good).sum())} eksik/bozuk satir atlandi.")
    t = t[good]
    channels = {k: v[good] for k, v in channels.items()}
    if not channels:
        raise ValueError("Dosyada kanal verisi bulunamadi.")
    return ScopeTrace(t=t, channels=channels, units=ch_units, path=path, notes=notes)


def load_scope_csv(path: str) -> ScopeTrace:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_scope_text(fh.read(), path)


# ============================================================================
# Sinyal isleme yardimcilari
# ============================================================================
def fmt_si(value: Optional[float], unit: str = "", digits: int = 4) -> str:
    """3.52e-6, 's' → '3.52 µs'."""
    if value is None or not np.isfinite(value):
        return "-"
    if value == 0:
        return f"0 {unit}".strip()
    prefixes = [(1e-12, "p"), (1e-9, "n"), (1e-6, "µ"), (1e-3, "m"), (1.0, ""),
                (1e3, "k"), (1e6, "M")]
    mag = abs(value)
    scale, pre = prefixes[0]
    for s, p in prefixes:
        if mag >= s * 0.9995:
            scale, pre = s, p
    return f"{value / scale:.{digits}g} {pre}{unit}".strip()


def interleave_offset(y: np.ndarray) -> float:
    """Cift/tek orneklerin sabit ofsetini (araya-girmeli ADC hatasi) bulur.

    Hem (tek − onceki cift) hem (tek − sonraki cift) farklarinin medyani
    ayni ise bu gercek sinyal degil, sabit bir ofsettir.
    """
    if y.size < 20:
        return 0.0
    a = float(np.median(y[1::2][: y[0::2].size] - y[0::2][: y[1::2].size]))
    b = float(np.median(y[1:-1:2] - y[2::2][: y[1:-1:2].size]))
    if a == 0 or b == 0 or np.sign(a) != np.sign(b):
        return 0.0
    return float(np.sign(a) * min(abs(a), abs(b)))


def remove_interleave(y: np.ndarray, offset: float) -> np.ndarray:
    out = np.array(y, dtype=float, copy=True)
    if offset:
        out[1::2] -= offset / 2.0
        out[0::2] += offset / 2.0
    return out


def moving_average(y: np.ndarray, n: int) -> np.ndarray:
    n = int(n)
    if n <= 1 or y.size < n:
        return np.asarray(y, dtype=float)
    pad_l, pad_r = n // 2, n - 1 - n // 2
    yp = np.pad(y, (pad_l, pad_r), mode="edge")
    c = np.cumsum(np.insert(yp, 0, 0.0))
    return (c[n:] - c[:-n]) / n


def median_filter(y: np.ndarray, n: int = 5) -> np.ndarray:
    n = int(n) | 1
    if n <= 1 or y.size < n:
        return np.asarray(y, dtype=float)
    from numpy.lib.stride_tricks import sliding_window_view
    yp = np.pad(y, n // 2, mode="edge")
    return np.median(sliding_window_view(yp, n), axis=1)


def channel_stats(y: np.ndarray) -> Dict[str, float]:
    """Osiloskobun Measure menusundeki gerilim olcumlerinin karsiligi."""
    y = np.asarray(y, dtype=float)
    vmax, vmin = float(np.max(y)), float(np.min(y))
    mid = 0.5 * (vmax + vmin)

    def mode(vals: np.ndarray) -> float:
        if vals.size == 0:
            return float("nan")
        u, c = np.unique(np.round(vals, 12), return_counts=True)
        if u.size <= max(64, vals.size // 20):       # nicemlenmis veri
            return float(u[np.argmax(c)])
        h, edges = np.histogram(vals, bins=100)
        k = int(np.argmax(h))
        return float(0.5 * (edges[k] + edges[k + 1]))

    top, base = mode(y[y >= mid]), mode(y[y < mid])
    return {"max": vmax, "min": vmin, "pkpk": vmax - vmin,
            "high": top, "low": base, "amp": top - base,
            "avg": float(np.mean(y)), "rms": float(np.sqrt(np.mean(y * y))),
            "ac_rms": float(np.std(y))}


def detect_edges(t: np.ndarray, y: np.ndarray, median: int = 5,
                 hysteresis: Tuple[float, float] = (0.3, 0.7)
                 ) -> Tuple[np.ndarray, np.ndarray]:
    """Kare dalganin yukselen ve dusen kenar zamanlarini bulur.

    Median filtre + histerezisli (Schmitt) esik ile tek orneklik sicramalar
    ve kenardaki titresim elenir; kenar zamani %50 seviyesinin gecildigi an
    (dogrusal interpolasyon) olarak verilir.
    """
    yf = median_filter(np.asarray(y, dtype=float), median)
    lo, hi = np.percentile(yf, [2, 98])
    if not np.isfinite(hi - lo) or hi - lo <= 0:
        return np.array([]), np.array([])
    th_lo = lo + hysteresis[0] * (hi - lo)
    th_hi = lo + hysteresis[1] * (hi - lo)
    mid = 0.5 * (lo + hi)

    mark = np.zeros(yf.size, dtype=np.int8)
    mark[yf >= th_hi] = 1
    mark[yf <= th_lo] = -1
    idx = np.where(mark != 0, np.arange(yf.size), 0)
    np.maximum.accumulate(idx, out=idx)
    state = mark[idx]
    first = np.flatnonzero(mark)
    if first.size == 0:
        return np.array([]), np.array([])
    state[: first[0]] = mark[first[0]]
    change = np.flatnonzero(np.diff(state)) + 1

    rises, falls = [], []
    prev = 0
    for k in change:
        up = state[k] > 0
        seg = yf[prev:k + 1]
        # %50 seviyesinin kenardan onceki son gecisi
        cand = np.flatnonzero(seg < mid) if up else np.flatnonzero(seg > mid)
        j = prev + int(cand[-1]) if cand.size else k - 1
        j = min(max(j, 0), yf.size - 2)
        y0, y1 = yf[j], yf[j + 1]
        frac = 0.5 if y1 == y0 else float(np.clip((mid - y0) / (y1 - y0), 0.0, 1.0))
        te = float(t[j] + frac * (t[j + 1] - t[j]))
        (rises if up else falls).append(te)
        prev = k
    return np.asarray(rises), np.asarray(falls)


def _window(t: np.ndarray, y: np.ndarray, a: float, b: float
            ) -> Tuple[float, float, int]:
    """[a, b) araligindaki ortalama, dogrusal egilim cikarilmis gurultu, nokta sayisi."""
    mean, res = _window_residuals(t, y, a, b)
    if res.size < 3:
        return mean, float("nan"), int(res.size)
    return mean, float(np.sqrt(np.sum(res * res) / max(res.size - 2, 1))), int(res.size)


def _window_residuals(t: np.ndarray, y: np.ndarray, a: float, b: float
                      ) -> Tuple[float, np.ndarray]:
    """[a, b) araligindaki ortalama ve dogrusal egilimi cikarilmis artiklar."""
    i0, i1 = np.searchsorted(t, [a, b])
    if i1 - i0 < 3:
        return float("nan"), np.array([])
    tt, yy = t[i0:i1], y[i0:i1]
    try:
        p = np.polyfit(tt - tt[0], yy, 1)
        res = yy - np.polyval(p, tt - tt[0])
    except (np.linalg.LinAlgError, ValueError):  # pragma: no cover
        res = yy - np.mean(yy)
    return float(np.mean(yy)), res


def band_power(res: np.ndarray, dt: float, f_max: float) -> float:
    """Artiklarin 0 < f <= f_max bandindaki ortalama gucu (V²) — Parseval ile."""
    n = res.size
    if n < 4 or not (dt > 0):
        return float("nan")
    spec = np.abs(np.fft.rfft(res)) ** 2
    f = np.fft.rfftfreq(n, dt)
    w = np.full(spec.size, 2.0)
    w[0] = 1.0
    if n % 2 == 0:
        w[-1] = 1.0
    keep = (f > 0) & (f <= f_max) if f_max and f_max > 0 else (f > 0)
    return float(np.sum(w[keep] * spec[keep]) / (n * n))


@dataclass
class ExpFit:
    """Ortalama kenara ustel uydurma: v(t) = C + Σ A_k·exp(−t/τ_k)."""

    tau: float = float("nan")             # tek ustel
    rmse1: float = float("nan")
    tau_fast: float = float("nan")        # cift ustel
    tau_slow: float = float("nan")
    frac_fast: float = float("nan")       # hizli bilesenin genlik payi
    rmse2: float = float("nan")
    t_from: float = float("nan")
    t_to: float = float("nan")
    n: int = 0

    @property
    def f_statistic(self) -> float:
        """Ikinci ustel terimin getirdigi iyilesme icin F istatistigi (2 ek parametre)."""
        if not (np.isfinite(self.rmse1) and np.isfinite(self.rmse2)) or self.n <= 6:
            return float("nan")
        sse1, sse2 = self.rmse1 ** 2 * self.n, self.rmse2 ** 2 * self.n
        if sse2 <= 0:
            return float("inf")
        return ((sse1 - sse2) / 2.0) / (sse2 / (self.n - 5))

    @property
    def double_significant(self) -> bool:
        """Cift ustel, tek ustelden anlamli olarak iyi mi (F > 10) ve fiziksel mi."""
        f = self.f_statistic
        return (np.isfinite(self.rmse2) and (f > 10 or f == float("inf"))
                and self.tau_slow > 3 * self.tau_fast
                and 0.05 < self.frac_fast < 0.95)


def fit_exponential(t: np.ndarray, v: np.ndarray, dt: float) -> ExpFit:
    """Tek ve cift ustel uydurma (τ izgarasi + dogrusal en kucuk kareler).

    Harici kutuphane (scipy) gerektirmez. t, uydurmanin baslangicina gore
    kaydirilmis zaman olmalidir.
    """
    fit = ExpFit()
    good = np.isfinite(t) & np.isfinite(v)
    t, v = t[good], v[good]
    if t.size < 8:
        return fit
    x = t - t[0]
    span = float(x[-1])
    if span <= 0:
        return fit
    fit.t_from, fit.t_to, fit.n = float(t[0]), float(t[-1]), int(t.size)
    taus = np.logspace(np.log10(max(dt, span / 1000) * 0.3), np.log10(span * 5), 160)
    ones = np.ones_like(x)

    def solve(cols):
        a = np.column_stack(cols)
        coef, *_ = np.linalg.lstsq(a, v, rcond=None)
        r = v - a @ coef
        return coef, float(np.sqrt(np.mean(r * r)))

    best = None
    exps = [np.exp(-x / tau) for tau in taus]
    for tau, e in zip(taus, exps):
        coef, rmse = solve([e, ones])
        if best is None or rmse < best[0]:
            best = (rmse, tau)
    fit.rmse1, fit.tau = best

    best2 = None
    sub = range(0, taus.size, 3)
    for i in sub:
        for j in sub:
            if taus[j] <= 2 * taus[i]:
                continue
            coef, rmse = solve([exps[i], exps[j], ones])
            if best2 is None or rmse < best2[0]:
                best2 = (rmse, taus[i], taus[j], coef)
    if best2 is not None:
        rmse, tf, tsl, coef = best2
        a1, a2 = abs(coef[0]), abs(coef[1])
        # iki bilesen ayni yonde olmali (fiziksel olarak anlamli)
        if np.sign(coef[0]) == np.sign(coef[1]) and a1 + a2 > 0:
            fit.rmse2, fit.tau_fast, fit.tau_slow = rmse, float(tf), float(tsl)
            fit.frac_fast = float(a1 / (a1 + a2))
    return fit


@dataclass
class EdgeTiming:
    kind: str                 # "on" (isik acildi) / "off" (isik kapandi)
    t_ref: float              # referans (CH1) kenari
    t10: float = float("nan")
    t50: float = float("nan")
    t90: float = float("nan")
    duration: float = float("nan")    # %10→%90 (acilis) / %90→%10 (kapanis)
    delay: float = float("nan")       # t50 − t_ref
    v_before: float = float("nan")
    v_after: float = float("nan")


def edge_timing(t: np.ndarray, y: np.ndarray, t_ref: float, v0: float, v1: float,
                t_start: float, t_stop: float, kind: str = "on") -> EdgeTiming:
    """v0 seviyesinden v1 seviyesine gecisin %10/%50/%90 zamanlari.

    Sinyal (y − v0)/(v1 − v0) ile 0→1 araligina normalize edilir; boylece
    yukselen ve dusen kenar ayni sekilde islenir.
    """
    e = EdgeTiming(kind=kind, t_ref=t_ref, v_before=v0, v_after=v1)
    amp = v1 - v0
    if not (np.isfinite(amp) and amp != 0):
        return e
    i0, i1 = np.searchsorted(t, [t_start, t_stop])
    if i1 - i0 < 3:
        return e
    tt = t[i0:i1]
    p = (y[i0:i1] - v0) / amp

    def cross(j: int, level: float) -> float:
        # j-1 ile j arasinda seviye gecisi
        if j <= 0:
            return float(tt[0])
        a, b = p[j - 1], p[j]
        frac = 0.5 if b == a else float(np.clip((level - a) / (b - a), 0.0, 1.0))
        return float(tt[j - 1] + frac * (tt[j] - tt[j - 1]))

    # %50 gecisini 3 ornekli ortalama uzerinde ara: tek orneklik gurultu
    # sicramalari kenar sanilmasin; gecis zamani yine ham veriden hesaplanir.
    ps = moving_average(p, 3) if p.size >= 6 else p
    above = np.flatnonzero(ps >= 0.5)
    if above.size == 0:
        return e
    k50 = int(above[0])
    while k50 > 0 and p[k50 - 1] >= 0.5:
        k50 -= 1
    while k50 < p.size - 1 and p[k50] < 0.5:
        k50 += 1
    below10 = np.flatnonzero(p[:k50 + 1] <= 0.1)
    above90 = np.flatnonzero(p[k50:] >= 0.9)
    e.t50 = cross(k50, 0.5)
    e.delay = e.t50 - t_ref
    if below10.size:
        e.t10 = cross(int(below10[-1]) + 1, 0.1)
    if above90.size:
        e.t90 = cross(k50 + int(above90[0]), 0.9)
    if np.isfinite(e.t10) and np.isfinite(e.t90) and e.t90 > e.t10:
        e.duration = e.t90 - e.t10
    return e


# ============================================================================
# Darbe analizi
# ============================================================================
@dataclass
class PulseSettings:
    signal: str = "CH2"
    reference: Optional[str] = "CH1"      # None: sinyalin kendisi referans
    light_on_high: bool = True            # lamba referans YUKSEK iken yanar
    gain_v_per_a: float = AMP120_GAIN_V_PER_A
    load_50ohm: bool = False              # osiloskop girisi 50 Ω → kazanc × 0.5
    dc_coupled: bool = False              # CH2 DC kuplajli ve AMP120 sifiri ayarli
    smooth: int = 1                       # hareketli ortalama (ornek)
    fix_interleave: bool = True
    plateau_fraction: float = 0.3         # seviye icin her yarim periyodun son kismi
    wavelength_nm: Optional[float] = None
    optical_power_w: Optional[float] = None
    area_cm2: Optional[float] = None
    dark_current_a: Optional[float] = None
    noise_bandwidth_hz: float = AMP120_BANDWIDTH_HZ
    system_rise_s: float = 0.0            # yukselteç + osiloskop yukselme suresi

    @property
    def effective_gain(self) -> float:
        return self.gain_v_per_a * (0.5 if self.load_50ohm else 1.0)


@dataclass
class AveragedEdge:
    tau: np.ndarray                       # kenara gore zaman (s)
    v: np.ndarray                         # ortalama sinyal (V)
    count: int
    timing: EdgeTiming
    fit: ExpFit = field(default_factory=ExpFit)

    @property
    def normalized(self) -> np.ndarray:
        tm = self.timing
        amp = tm.v_after - tm.v_before
        if not np.isfinite(amp) or amp == 0:
            return np.full_like(self.v, np.nan)
        return (self.v - tm.v_before) / amp


def _nan_stats(values: List[float]) -> Tuple[float, float, int]:
    v = np.asarray([x for x in values if np.isfinite(x)], dtype=float)
    if v.size == 0:
        return float("nan"), float("nan"), 0
    return float(np.mean(v)), float(np.std(v, ddof=1)) if v.size > 1 else 0.0, int(v.size)


@dataclass
class PulseResult:
    settings: PulseSettings
    trace: ScopeTrace
    t: np.ndarray
    signal: np.ndarray                    # islenmis sinyal (V)
    reference: Optional[np.ndarray]
    interleave_v: float = 0.0
    on_edges: np.ndarray = field(default_factory=lambda: np.array([]))
    off_edges: np.ndarray = field(default_factory=lambda: np.array([]))
    period: float = float("nan")
    on_width: float = float("nan")
    off_width: float = float("nan")
    v_on: float = float("nan")
    v_off: float = float("nan")
    v_on_spread: float = float("nan")     # cevrimden cevrime std
    v_off_spread: float = float("nan")
    noise_on_v: float = float("nan")      # tam bant (osiloskop bandi)
    noise_off_v: float = float("nan")     # tam bant — karanlik gurultu
    noise_on_band_v: float = float("nan")  # gurultu bant genisligi B icinde
    noise_off_band_v: float = float("nan")
    n_on_levels: int = 0
    n_off_levels: int = 0
    edges: List[EdgeTiming] = field(default_factory=list)
    avg_rise: Optional[AveragedEdge] = None
    avg_fall: Optional[AveragedEdge] = None
    cycle_tau: np.ndarray = field(default_factory=lambda: np.array([]))
    cycle_avg: np.ndarray = field(default_factory=lambda: np.array([]))
    stats_signal: Dict[str, float] = field(default_factory=dict)
    stats_reference: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    # ------------------------------------------------------------ zamanlama
    @property
    def frequency(self) -> float:
        return 1.0 / self.period if np.isfinite(self.period) and self.period > 0 else float("nan")

    @property
    def duty(self) -> float:
        if np.isfinite(self.period) and self.period > 0:
            return self.on_width / self.period
        return float("nan")

    @property
    def n_cycles(self) -> int:
        return int(min(self.on_edges.size, self.off_edges.size))

    def light_spans(self) -> List[Tuple[float, float]]:
        """Isigin acik oldugu zaman araliklari (kayit sinirlarina kirpilmis)."""
        t0, t1 = float(self.t[0]), float(self.t[-1])
        ev = sorted([(float(x), 1) for x in self.on_edges] +
                    [(float(x), 0) for x in self.off_edges])
        spans, start = [], None
        if ev and ev[0][1] == 0:
            start = t0
        for tm, state in ev:
            if state == 1 and start is None:
                start = tm
            elif state == 0 and start is not None:
                spans.append((start, tm))
                start = None
        if start is not None:
            spans.append((start, t1))
        return spans

    def edge_stats(self, kind: str, attr: str = "duration") -> Tuple[float, float, int]:
        return _nan_stats([getattr(e, attr) for e in self.edges if e.kind == kind])

    @property
    def rise_time(self) -> float:
        """Birincil yukselme suresi: cevrim ortalamasindan, yoksa kenarlarin ortalamasi."""
        if self.avg_rise is not None and np.isfinite(self.avg_rise.timing.duration):
            return self.avg_rise.timing.duration
        return self.edge_stats("on")[0]

    @property
    def fall_time(self) -> float:
        if self.avg_fall is not None and np.isfinite(self.avg_fall.timing.duration):
            return self.avg_fall.timing.duration
        return self.edge_stats("off")[0]

    def corrected(self, tr: float) -> float:
        """Sistem yukselme suresi karesel olarak cikarilmis deger."""
        ts = self.settings.system_rise_s
        if not ts or not np.isfinite(tr):
            return tr
        if tr <= ts:
            return float("nan")
        return math.sqrt(tr * tr - ts * ts)

    @property
    def pulse_width_50(self) -> float:
        """Sinyalin %50'de olculen darbe genisligi (isik acik suresinin tepkisi)."""
        ons = sorted((e.t50 for e in self.edges if e.kind == "on" and np.isfinite(e.t50)))
        offs = sorted((e.t50 for e in self.edges if e.kind == "off" and np.isfinite(e.t50)))
        widths = []
        for a in ons:
            later = [b for b in offs if b > a]
            if later and later[0] - a < self.period:
                widths.append(later[0] - a)
        return float(np.median(widths)) if widths else float("nan")

    # ------------------------------------------------------------ elektriksel
    @property
    def delta_v(self) -> float:
        return self.v_on - self.v_off

    @property
    def gain(self) -> float:
        return self.settings.effective_gain

    @property
    def photocurrent(self) -> float:
        return abs(self.delta_v) / self.gain if self.gain else float("nan")

    @property
    def photocurrent_spread(self) -> float:
        s = math.hypot(self.v_on_spread if np.isfinite(self.v_on_spread) else 0.0,
                       self.v_off_spread if np.isfinite(self.v_off_spread) else 0.0)
        return s / self.gain if self.gain else float("nan")

    @property
    def noise_current(self) -> float:
        return self.noise_off_used / self.gain if self.gain else float("nan")

    @property
    def snr(self) -> float:
        n = self.noise_off_used
        if np.isfinite(n) and n > 0:
            return abs(self.delta_v) / n
        return float("nan")

    @property
    def noise_off_used(self) -> float:
        """NEP/D*/SNR icin kullanilan karanlik gurultu: B icindeki, yoksa tam bant."""
        if np.isfinite(self.noise_off_band_v):
            return self.noise_off_band_v
        return self.noise_off_v

    @property
    def responsivity(self) -> float:
        p = self.settings.optical_power_w
        return self.photocurrent / p if p else float("nan")

    @property
    def eqe_percent(self) -> float:
        lam = self.settings.wavelength_nm
        if not lam or not np.isfinite(self.responsivity):
            return float("nan")
        return self.responsivity * photon_energy_ev(lam) * 100.0

    @property
    def nep_measured(self) -> float:
        """Olculen gurultu akimina esdeger optik guc (W, olcum bant genisliginde)."""
        r = self.responsivity
        return self.noise_current / r if np.isfinite(r) and r > 0 else float("nan")

    @property
    def nep_measured_per_rthz(self) -> float:
        b = self.settings.noise_bandwidth_hz
        return self.nep_measured / math.sqrt(b) if b and b > 0 else float("nan")

    @property
    def dstar_measured(self) -> float:
        """D* = sqrt(A·B) / NEP (Jones) — olculen toplam gurultuyle (alt sinir)."""
        a, b = self.settings.area_cm2, self.settings.noise_bandwidth_hz
        nep = self.nep_measured
        if not (a and b and np.isfinite(nep) and nep > 0):
            return float("nan")
        return math.sqrt(a * b) / nep

    @property
    def dstar_shot(self) -> float:
        """D* = R·sqrt(A) / sqrt(2q·I_karanlik) (Keithley'den girilen karanlik akimla)."""
        a, idark, r = (self.settings.area_cm2, self.settings.dark_current_a,
                       self.responsivity)
        if not (a and idark and np.isfinite(r)):
            return float("nan")
        return r * math.sqrt(a) / math.sqrt(2 * Q_E * abs(idark))

    @property
    def nep_shot_per_rthz(self) -> float:
        idark, r = self.settings.dark_current_a, self.responsivity
        if not (idark and np.isfinite(r) and r > 0):
            return float("nan")
        return math.sqrt(2 * Q_E * abs(idark)) / r

    @property
    def i_on(self) -> float:
        return self.v_on / self.gain if self.gain else float("nan")

    @property
    def i_off(self) -> float:
        return self.v_off / self.gain if self.gain else float("nan")

    @property
    def on_off_ratio(self) -> float:
        if self.settings.dc_coupled and self.v_off and np.sign(self.v_on) == np.sign(self.v_off):
            return abs(self.v_on / self.v_off)
        return float("nan")

    # ------------------------------------------------------------ rapor
    def report_rows(self) -> List[Tuple[str, str]]:
        s = self.settings
        tr, tf = self.rise_time, self.fall_time
        tr_c, tf_c = self.corrected(tr), self.corrected(tf)
        er, ef = self.edge_stats("on"), self.edge_stats("off")
        dr, df = self.edge_stats("on", "delay"), self.edge_stats("off", "delay")

        def pm(stats, unit):
            m, sd, n = stats
            if n == 0:
                return "-"
            return f"{fmt_si(m, unit)} ± {fmt_si(sd, unit)} (N={n})"

        def g(x, fmt="{:.4g}", unit=""):
            return "-" if x is None or not np.isfinite(x) else (fmt.format(x) + (" " + unit if unit else ""))

        bw = 0.35 / (tr_c if np.isfinite(tr_c) else tr) if tr and np.isfinite(tr) else float("nan")
        rows: List[Tuple[str, str]] = [
            ("— Dosya —", ""),
            ("Dosya", self.trace.path or "-"),
            ("Ornek sayisi / aralik", f"{self.t.size} / {fmt_si(self.trace.dt, 's')}"),
            ("Sinyal / referans kanali", f"{s.signal} / {s.reference or '(sinyalin kendisi)'}"),
            ("— Zamanlama (referans) —", ""),
            ("Periyot", fmt_si(self.period, "s")),
            ("Frekans", fmt_si(self.frequency, "Hz")),
            ("Isik acik suresi (+genislik)", fmt_si(self.on_width, "s")),
            ("Isik kapali suresi (−genislik)", fmt_si(self.off_width, "s")),
            ("Doluluk orani (isik acik)", g(self.duty * 100, "{:.2f}", "%")),
            ("Tam cevrim sayisi", str(self.n_cycles)),
            ("— Tepki suresi —", ""),
            ("Yukselme suresi %10→%90 (cevrim ortalamasi)", fmt_si(tr, "s")),
            ("Dusme suresi %90→%10 (cevrim ortalamasi)", fmt_si(tf, "s")),
            ("Yukselme, tek tek kenarlar", pm(er, "s")),
            ("Dusme, tek tek kenarlar", pm(ef, "s")),
        ]
        if s.system_rise_s:
            rows += [
                ("Sistem yukselme suresi (cikarilan)", fmt_si(s.system_rise_s, "s")),
                ("Duzeltilmis yukselme suresi", fmt_si(tr_c, "s") if np.isfinite(tr_c)
                 else "sistem sinirinda (olculemez)"),
                ("Duzeltilmis dusme suresi", fmt_si(tf_c, "s") if np.isfinite(tf_c)
                 else "sistem sinirinda (olculemez)"),
            ]
        rows += [
            ("Zaman sabiti τ ≈ t_r / 2.2", fmt_si((tr_c if np.isfinite(tr_c) else tr) / 2.197, "s")),
            ("-3 dB bant genisligi ≈ 0.35 / t_r", fmt_si(bw, "Hz")),
        ]
        for label, ae in (("Acilis (yukselme)", self.avg_rise), ("Kapanis (dusme)", self.avg_fall)):
            if ae is None or not np.isfinite(ae.fit.tau):
                continue
            f = ae.fit
            rows.append((f"{label}: tek ustel τ", fmt_si(f.tau, "s")))
            if f.double_significant:
                rows.append((f"{label}: cift ustel τ_hizli / τ_yavas",
                             f"{fmt_si(f.tau_fast, 's')} ({f.frac_fast * 100:.0f}%) / "
                             f"{fmt_si(f.tau_slow, 's')} ({(1 - f.frac_fast) * 100:.0f}%)"))
        if s.reference:
            rows += [
                ("Gecikme: lamba acilis → sinyal %50", pm(dr, "s")),
                ("Gecikme: lamba kapanis → sinyal %50", pm(df, "s")),
            ]
        rows += [
            ("Sinyal darbe genisligi (%50)", fmt_si(self.pulse_width_50, "s")),
            ("— Seviyeler (CH sinyal) —", ""),
            ("V_on (isik acik plato)", fmt_si(self.v_on, "V")),
            ("V_off (isik kapali plato)", fmt_si(self.v_off, "V")),
            ("ΔV = V_on − V_off", fmt_si(self.delta_v, "V")),
            ("ΔV cevrimden cevrime degisim (std)",
             fmt_si(math.hypot(np.nan_to_num(self.v_on_spread), np.nan_to_num(self.v_off_spread)), "V")),
            ("Gurultu isik kapali, tam bant (RMS)", fmt_si(self.noise_off_v, "V")),
            ("Gurultu isik acik, tam bant (RMS)", fmt_si(self.noise_on_v, "V")),
            (f"Gurultu isik kapali, B = {fmt_si(s.noise_bandwidth_hz, 'Hz')} icinde",
             fmt_si(self.noise_off_band_v, "V")),
            ("Gurultu isik acik, B icinde", fmt_si(self.noise_on_band_v, "V")),
            ("SNR = ΔV / karanlik gurultu (B icinde)", g(self.snr, "{:.1f}") + (
                f"  ({20 * math.log10(self.snr):.1f} dB)" if np.isfinite(self.snr) and self.snr > 0 else "")),
        ]
        if self.interleave_v:
            rows.append(("ADC cift/tek ornek ofseti (duzeltildi)", fmt_si(self.interleave_v, "V")))
        rows += [
            ("— Akim (I = V / G) —", ""),
            ("Etkin transempedans kazanci G", g(self.gain, "{:.4g}", "V/A") +
             (" (50 Ω yuk: ×0.5)" if s.load_50ohm else "")),
            ("Fotoakim I_ph = |ΔV| / G", fmt_si(self.photocurrent, "A")),
            ("Fotoakim cevrim degisimi (std)", fmt_si(self.photocurrent_spread, "A")),
            ("Karanlik gurultu akimi (RMS, B icinde)", fmt_si(self.noise_current, "A")),
        ]
        if s.dc_coupled:
            rows += [
                ("I_on (isik acik)", fmt_si(self.i_on, "A")),
                ("I_off (karanlik)", fmt_si(self.i_off, "A")),
                ("Ac/kapa orani I_on / I_off", g(self.on_off_ratio, "{:.4g}")),
            ]
        else:
            rows.append(("I_on / I_off, karanlik akim",
                         "AC kuplajda hesaplanamaz (DC seviye yok)"))
        rows += [
            ("— Fotodedektor —", ""),
            ("Dalga boyu", g(s.wavelength_nm, "{:g}", "nm")),
            ("Optik guc", fmt_si(s.optical_power_w, "W")),
            ("Aktif alan", g(s.area_cm2, "{:g}", "cm²")),
            ("Duyarlilik R = I_ph / P", g(self.responsivity, "{:.4g}", "A/W")),
            ("EQE", g(self.eqe_percent, "{:.4g}", "%")),
            ("Gurultu bant genisligi B", fmt_si(s.noise_bandwidth_hz, "Hz")),
            ("NEP (olculen gurultu, B icinde)", fmt_si(self.nep_measured, "W")),
            ("NEP (olculen, /√Hz)", g(self.nep_measured_per_rthz, "{:.4g}", "W/√Hz")),
            ("D* (olculen gurultu)", g(self.dstar_measured, "{:.4g}", "Jones")),
        ]
        if s.dark_current_a:
            rows += [
                ("Karanlik akim (girilen)", fmt_si(s.dark_current_a, "A")),
                ("D* (shot gurultu, karanlik akimdan)", g(self.dstar_shot, "{:.4g}", "Jones")),
                ("NEP (shot, /√Hz)", g(self.nep_shot_per_rthz, "{:.4g}", "W/√Hz")),
            ]
        st = self.stats_signal
        if st:
            rows += [
                ("— Osiloskop Measure karsiligi (ham sinyal) —", ""),
                ("Vpp", fmt_si(st["pkpk"], "V")),
                ("Vmax / Vmin", f"{fmt_si(st['max'], 'V')} / {fmt_si(st['min'], 'V')}"),
                ("Vtop (High) / Vbase (Low)", f"{fmt_si(st['high'], 'V')} / {fmt_si(st['low'], 'V')}"),
                ("Vamp", fmt_si(st["amp"], "V")),
                ("Vavg / Vrms", f"{fmt_si(st['avg'], 'V')} / {fmt_si(st['rms'], 'V')}"),
            ]
        return rows

    def edges_table(self) -> Tuple[List[str], List[List[float]]]:
        head = ["kenar", "tur", "t_ref_s", "t10_s", "t50_s", "t90_s",
                "sure_10_90_s", "gecikme_s", "V_once_V", "V_sonra_V"]
        rows = []
        for k, e in enumerate(sorted(self.edges, key=lambda x: x.t_ref)):
            rows.append([k + 1, e.kind, e.t_ref, e.t10, e.t50, e.t90,
                         e.duration, e.delay, e.v_before, e.v_after])
        return head, rows


def _level_windows(edges: List[Tuple[float, str]], t0: float, t1: float,
                   l_on: float, l_off: float, frac: float, guard: float = 0.0
                   ) -> List[Tuple[str, float, float]]:
    """Her yari-periyodun sonundaki plato penceresi: (durum, a, b).

    guard: pencerenin kenardan once biraktigi pay (yari-periyodun kesri).
    """
    out = []
    # kenarlardan once gelen bolumler
    for k, (te, kind) in enumerate(edges):
        before = "off" if kind == "on" else "on"
        length = l_off if before == "off" else l_on
        a, b = te - (frac + guard) * length, te - guard * length
        prev_edge = edges[k - 1][0] if k > 0 else t0
        if a >= max(t0, prev_edge):
            out.append((before, a, b))
    # son kenardan sonraki bolum tamamlanmissa
    if edges:
        te, kind = edges[-1]
        length = l_on if kind == "on" else l_off
        if te + length <= t1:
            out.append((kind, te + (1 - frac - guard) * length, te + (1 - guard) * length))
    return out


def _average_edge(t: np.ndarray, y: np.ndarray, centers: np.ndarray,
                  pre: float, post: float, dt: float, kind: str, frac: float,
                  lead: float = 0.0, guard: float = 0.0) -> Optional[AveragedEdge]:
    """Kenarlari `centers` zamanlarina hizalayip ortalar.

    centers her kenarin sinyal %50 noktasidir (tetik titresimi ortalamayi
    genisletmesin diye); referans kenar ortalama olarak `lead` kadar oncedir.
    Onceki yari-periyot [−lead−pre, −lead), sonraki [−lead, −lead+post).
    """
    if centers.size == 0 or not (pre > 0 and post > 0 and dt > 0):
        return None
    tau = np.arange(-lead - pre, -lead + post, dt)
    if tau.size < 6:
        return None
    stack = []
    for c in centers:
        seg = np.interp(c + tau, t, y, left=np.nan, right=np.nan)
        if np.isfinite(seg).sum() > tau.size // 3:
            stack.append(seg)
    if not stack:
        return None
    arr = np.vstack(stack)
    counts = np.isfinite(arr).sum(axis=0)
    with np.errstate(invalid="ignore"):
        v = np.where(counts > 0, np.nansum(arr, axis=0) / np.maximum(counts, 1), np.nan)
    good = np.isfinite(v)
    tau_g, v_g = tau[good], v[good]
    v0, _, _ = _window(tau_g, v_g, -lead - (frac + guard) * pre, -lead - guard * pre)
    v1, _, _ = _window(tau_g, v_g, -lead + post * (1 - frac - guard),
                       -lead + post * (1 - guard))
    timing = edge_timing(tau_g, v_g, -lead, v0, v1, -lead - 0.1 * pre, -lead + post, kind)
    # ustel uydurma: %10 noktasindan (yoksa kenardan) segment sonuna kadar
    t_from = timing.t10 if np.isfinite(timing.t10) else 0.0
    sel = tau_g >= t_from
    fit = fit_exponential(tau_g[sel], v_g[sel], dt)
    return AveragedEdge(tau=tau_g, v=v_g, count=len(stack), timing=timing, fit=fit)


def analyze_pulses(trace: ScopeTrace, settings: PulseSettings) -> PulseResult:
    """Kare dalgayla surulen lamba altinda alinmis osiloskop kaydini analiz eder."""
    s = settings
    t = np.asarray(trace.t, dtype=float)
    raw = np.asarray(trace.channel(s.signal), dtype=float)
    ref_raw = np.asarray(trace.channel(s.reference), dtype=float) if s.reference else None

    off = interleave_offset(raw) if s.fix_interleave else 0.0
    y = remove_interleave(raw, off)
    y = moving_average(y, s.smooth)

    res = PulseResult(settings=s, trace=trace, t=t, signal=y, reference=ref_raw,
                      interleave_v=off)
    res.stats_signal = channel_stats(raw)
    if ref_raw is not None:
        res.stats_reference = channel_stats(ref_raw)

    # --------------------------------------------------------- kenarlar
    if ref_raw is not None:
        r = remove_interleave(ref_raw, interleave_offset(ref_raw) if s.fix_interleave else 0.0)
    else:
        r = moving_average(y, max(3, s.smooth))
    rises, falls = detect_edges(t, r)
    on_e, off_e = (rises, falls) if s.light_on_high else (falls, rises)
    res.on_edges, res.off_edges = on_e, off_e
    if on_e.size + off_e.size < 2 or on_e.size == 0 or off_e.size == 0:
        res.warnings.append(
            "Referans kanalda kare dalga kenari bulunamadi. Kanal secimini "
            "kontrol edin veya kayda en az bir tam periyot sigdirin.")
        return res

    # --------------------------------------------------------- periyot ve genislik
    on_w = [float(off_e[off_e > a][0] - a) for a in on_e if np.any(off_e > a)]
    off_w = [float(on_e[on_e > a][0] - a) for a in off_e if np.any(on_e > a)]
    per = []
    if on_e.size > 1:
        per += list(np.diff(on_e))
    if off_e.size > 1:
        per += list(np.diff(off_e))
    res.on_width = float(np.median(on_w)) if on_w else float("nan")
    res.off_width = float(np.median(off_w)) if off_w else float("nan")
    if per:
        res.period = float(np.median(per))
    elif np.isfinite(res.on_width) and np.isfinite(res.off_width):
        res.period = res.on_width + res.off_width
    if not np.isfinite(res.on_width) and np.isfinite(res.period):
        res.on_width = res.period - res.off_width
    if not np.isfinite(res.off_width) and np.isfinite(res.period):
        res.off_width = res.period - res.on_width
    l_on, l_off = res.on_width, res.off_width
    if not (np.isfinite(l_on) and np.isfinite(l_off) and l_on > 0 and l_off > 0):
        res.warnings.append("Isik acik/kapali sureleri belirlenemedi.")
        return res
    if res.n_cycles < 3:
        res.warnings.append(
            f"Kayitta yalnizca {res.n_cycles} tam cevrim var; ortalamalar icin "
            "osiloskopta daha fazla periyot kaydedin.")

    # --------------------------------------------------------- plato seviyeleri
    frac = float(np.clip(s.plateau_fraction, 0.05, 0.9))
    edges = sorted([(float(x), "on") for x in on_e] + [(float(x), "off") for x in off_e])
    # referans yoksa kenar sinyalin kendi %50 noktasidir; plato pencereleri
    # gecisin ilk yarisini icermesin diye kenardan biraz once biter
    guard = 0.1 if ref_raw is None else 0.0
    wins = _level_windows(edges, float(t[0]), float(t[-1]), l_on, l_off, frac, guard)
    lv = {"on": [], "off": []}
    nz = {"on": [0.0, 0, 0.0, 0], "off": [0.0, 0, 0.0, 0]}  # Σres², Σ(n-2), Σ n·P_B, Σ n
    dt = trace.dt
    band = s.noise_bandwidth_hz if s.noise_bandwidth_hz and s.noise_bandwidth_hz > 0 else 0.0
    for state, a, b in wins:
        m, r = _window_residuals(t, y, a, b)
        if np.isfinite(m) and r.size >= 3:
            lv[state].append(m)
            nz[state][0] += float(np.sum(r * r))
            nz[state][1] += max(r.size - 2, 1)
            if band:
                nz[state][2] += r.size * band_power(r, dt, band)
                nz[state][3] += r.size
    for state in ("on", "off"):
        vals = np.asarray(lv[state])
        level = float(np.median(vals)) if vals.size else float("nan")
        spread = float(np.std(vals, ddof=1)) if vals.size > 1 else float("nan")
        noise = math.sqrt(nz[state][0] / nz[state][1]) if nz[state][1] else float("nan")
        nb = (math.sqrt(nz[state][2] / nz[state][3])
              if band and nz[state][3] else float("nan"))
        if state == "on":
            res.v_on, res.v_on_spread, res.noise_on_v, res.n_on_levels = level, spread, noise, vals.size
            res.noise_on_band_v = nb
        else:
            res.v_off, res.v_off_spread, res.noise_off_v, res.n_off_levels = level, spread, noise, vals.size
            res.noise_off_band_v = nb

    # --------------------------------------------------------- tek tek kenarlar
    t0, t1 = float(t[0]), float(t[-1])
    for k, (te, kind) in enumerate(edges):
        l_prev = l_off if kind == "on" else l_on
        l_next = l_on if kind == "on" else l_off
        v0, _, _ = _window(t, y, te - (frac + guard) * l_prev, te - guard * l_prev)
        nxt = edges[k + 1][0] if k + 1 < len(edges) else te + l_next
        if nxt > t1:
            continue
        v1, _, _ = _window(t, y, nxt - (frac + guard) * l_next, nxt - guard * l_next)
        start = max(te - 0.1 * l_prev, t0)
        e = edge_timing(t, y, te, v0, v1, start, nxt, kind)
        res.edges.append(e)

    # --------------------------------------------------------- cevrim ortalamasi
    def centers(kind: str, ref_edges: np.ndarray) -> Tuple[np.ndarray, float]:
        ok = [e for e in res.edges if e.kind == kind and np.isfinite(e.t50)]
        if not ok:
            return ref_edges, 0.0
        return (np.asarray([e.t50 for e in ok]),
                float(np.median([e.delay for e in ok])))

    c_on, lead_on = centers("on", on_e)
    c_off, lead_off = centers("off", off_e)
    res.avg_rise = _average_edge(t, y, c_on, l_off, l_on, dt, "on", frac, lead_on, guard)
    res.avg_fall = _average_edge(t, y, c_off, l_on, l_off, dt, "off", frac, lead_off, guard)
    if np.isfinite(res.period) and on_e.size:
        tau = np.arange(-0.5 * l_off, res.period - 0.5 * l_off, dt)
        stack = [np.interp(c + tau, t, y, left=np.nan, right=np.nan) for c in on_e]
        arr = np.vstack(stack)
        cnt = np.isfinite(arr).sum(axis=0)
        with np.errstate(invalid="ignore"):
            avg = np.where(cnt > 0, np.nansum(arr, axis=0) / np.maximum(cnt, 1), np.nan)
        res.cycle_tau, res.cycle_avg = tau, avg

    # --------------------------------------------------------- uyarilar
    tr, tf = res.rise_time, res.fall_time
    if np.isfinite(res.delta_v) and res.delta_v < 0:
        res.warnings.append(
            "Isik acikken sinyal DUSUYOR (ters kutup). Hesaplar |ΔV| ile yapildi; "
            "lamba referans dusukken yaniyorsa 'Lamba referans YUKSEK iken yanar' "
            "secimini kaldirin.")
    for name, val in (("Yukselme", tr), ("Dusme", tf)):
        if np.isfinite(val) and np.isfinite(dt) and val < 3 * dt:
            res.warnings.append(
                f"{name} suresi ({fmt_si(val, 's')}) yalnizca ~{val / dt:.1f} ornek; "
                "cozunurluk yetersiz. Osiloskopta zaman olcegini kucultun "
                "(kenari buyutun) ve yeniden kaydedin.")
    if s.system_rise_s and np.isfinite(tr) and tr < 1.5 * s.system_rise_s:
        res.warnings.append(
            f"Olculen yukselme suresi ({fmt_si(tr, 's')}) yukselteç/sistem "
            f"sinirina ({fmt_si(s.system_rise_s, 's')}) yakin. Dedektor bundan "
            "hizli olabilir; daha genis bantli bir yukselteç veya daha dusuk "
            "kazanc gerekir.")
    if np.isfinite(res.snr) and res.snr < 5:
        res.warnings.append(f"SNR dusuk ({res.snr:.1f}); osiloskopta Average "
                            "modunu veya 'Yumusatma' ayarini kullanin.")
    vmax = max(abs(res.stats_signal["max"]), abs(res.stats_signal["min"]))
    limit = 1.0 if s.load_50ohm else 2.0
    if abs(s.gain_v_per_a - AMP120_GAIN_V_PER_A) < 1 and vmax > 0.9 * limit:
        res.warnings.append(
            f"Sinyal ({fmt_si(vmax, 'V')}) AMP120 cikis sinirina (±{limit:g} V) "
            "yakin — doyum olabilir.")
    if abs(s.gain_v_per_a - AMP120_GAIN_V_PER_A) < 1 and \
            np.isfinite(res.photocurrent) and res.photocurrent > AMP120_MAX_INPUT_A:
        res.warnings.append("Fotoakim AMP120 giris sinirini (±20 µA) asiyor.")
    return res


def write_report(result: PulseResult, path: str, title: str = "") -> str:
    from datetime import datetime
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("UV FOTODEDEKTOR DARBE (PULSE) TEPKISI RAPORU\n")
        fh.write(f"Tarih: {datetime.now().isoformat(timespec='seconds')}\n")
        if title:
            fh.write(f"Numune: {title}\n")
        fh.write("Duzen: Keithley 3390 kare dalga → UV lamba; dedektor → "
                 "AMP120 → osiloskop\n")
        fh.write("=" * 60 + "\n")
        for k, v in result.report_rows():
            fh.write(f"{k}\t{v}\n")
        if result.warnings:
            fh.write("\nUYARILAR\n")
            for w in result.warnings:
                fh.write(f"- {w}\n")
    return path


def write_edges_csv(result: PulseResult, path: str) -> str:
    head, rows = result.edges_table()
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(head) + "\n")
        for r in rows:
            fh.write(",".join(x if isinstance(x, str) else f"{x:.10g}" for x in r) + "\n")
    return path


def write_average_csv(result: PulseResult, path: str) -> str:
    """Cevrim ortalamasi alinmis dalga ve normalize kenarlar."""
    g = result.gain or 1.0
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(f"# ortalama darbe, kazanc G = {g:g} V/A, periyot = {result.period:.10g} s\n")
        fh.write("tau_s,V_avg_V,I_avg_A\n")
        for a, b in zip(result.cycle_tau, result.cycle_avg):
            fh.write(f"{a:.10g},{b:.10g},{b / g:.10g}\n")
        for name, ae in (("yukselen", result.avg_rise), ("dusen", result.avg_fall)):
            if ae is None:
                continue
            fh.write(f"\n# ortalama {name} kenar ({ae.count} kenar), normalize 0..1\n")
            fh.write("tau_s,V_avg_V,normalize\n")
            for a, b, c in zip(ae.tau, ae.v, ae.normalized):
                fh.write(f"{a:.10g},{b:.10g},{c:.6g}\n")
    return path
